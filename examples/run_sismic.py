from __future__ import annotations

import argparse
import ast
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import sismic.io as sio
import syside
from sismic.clock import SimulatedClock
from sismic.exceptions import CodeEvaluationError
from sismic.helpers import coverage_from_trace
from sismic.interpreter import Interpreter

from sysmlc import configure_logging
from sysmlc.backends.quake import build_statechart
from sysmlc.explore import iter_model_elements
from sysmlc.loader import load_syside_model
from sysmlc.logging import PACKAGE_LOGGER_NAME

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Mapping

    from sismic.model import Statechart
    from sismic.model.steps import MacroStep

logger = logging.getLogger(f"{PACKAGE_LOGGER_NAME}.run_sismic")

SM_EXAMPLES_DIR = (
    Path(__file__).resolve().parent.parent / "models" / "sm-examples"
)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "sismic"

REALTIME_POLL_INTERVAL_SECONDS = 0.001


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build and execute a sismic statechart from a SysML "
            "state-machine example under models/sm-examples/."
        )
    )
    parser.add_argument(
        "example",
        help=(
            "Example to run. Accepts a bare number (`01`), an `sm`-"
            "prefixed number (`sm01`), or the full folder name "
            "(`sm01-helloworld`)."
        ),
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=100.0,
        help=(
            "Clock speed multiplier for time-triggered statecharts: "
            "simulated time advances this many times faster than the "
            "wall clock, so a timer fires sooner. Pass 1.0 for true "
            "wall-clock time. (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--max-wall-seconds",
        type=float,
        default=10.0,
        help=(
            "Wall-clock safety cap on a real-time run, in seconds. A "
            "machine with no final state would otherwise run forever. "
            "(default: %(default)s)"
        ),
    )
    return parser.parse_args()


def resolve_example_folder(arg: str) -> str:
    """Map a number / short prefix / full name to the actual folder name.

    Accepted inputs:
        ``"01"``              -> matches ``sm01-*``
        ``"sm01"``            -> matches ``sm01-*``
        ``"sm01-helloworld"`` -> used as-is

    Args:
        arg: The raw ``example`` argument from the command line.

    Returns:
        The folder name to look up under ``models/sm-examples/``.

    Raises:
        SystemExit: If a number / short prefix matches zero or multiple
            folders.
    """
    if arg.isdigit():
        prefix = f"sm{int(arg):02d}-"
    elif arg.startswith("sm") and arg[2:].isdigit():
        prefix = f"{arg}-"
    else:
        return arg

    matches = sorted(
        p.name
        for p in SM_EXAMPLES_DIR.iterdir()
        if p.is_dir() and p.name.startswith(prefix)
    )
    if not matches:
        raise SystemExit(f"No example folder matches {prefix}*")
    if len(matches) > 1:
        raise SystemExit(
            f"Multiple folders match {prefix}*: {matches}; "
            "pass the full folder name to disambiguate."
        )
    return matches[0]


def resolve_state_def_qns(model: syside.Model) -> list[str]:
    """Return the qualified names of every ``StateDefinition`` in ``model``.

    Args:
        model: Loaded syside model.

    Returns:
        Qualified names of every ``StateDefinition``, sorted.

    Raises:
        SystemExit: If the model contains no ``StateDefinition``.
    """
    state_defs = iter_model_elements(model, syside.StateDefinition)
    if not state_defs:
        raise SystemExit("No StateDefinition found in the model.")
    return sorted(str(sd.qualified_name) for sd in state_defs)


def print_structure(statechart: Statechart) -> None:
    """Print the built statechart as an indented state hierarchy.

    Args:
        statechart: A built ``sismic.model.Statechart``.
    """
    print("  States:")
    _print_state_tree(statechart, statechart.root, depth=2)
    print("  Transitions:")
    transitions = list(statechart.transitions)
    if not transitions:
        print("    (none)")
    for trans in transitions:
        event = trans.event or "<eventless>"
        guard = trans.guard if trans.guard else "<no guard>"
        print(
            f"    {trans.source} -> {trans.target}  "
            f"[event: {event}] [guard: {guard}]"
        )


def _print_state_tree(statechart: Statechart, name: str, depth: int) -> None:
    """Print ``name`` and its descendants as an indented tree.

    A composite state's line is annotated with ``(initial: <substate>)``
    naming its initial substate; its children are printed in declaration
    order, indented beneath it.

    Args:
        statechart: A built ``sismic.model.Statechart``.
        name: The state to print, with its children below it.
        depth: Indentation level; each level is two spaces.
    """
    state = statechart.state_for(name)
    short = name.split("::")[-1]
    initial = getattr(state, "initial", None)
    suffix = f"  (initial: {initial.split('::')[-1]})" if initial else ""
    print(f"{'  ' * depth}{short}{suffix}")
    for child in statechart.children_for(name):
        _print_state_tree(statechart, child, depth + 1)


def print_trace(steps: list[MacroStep]) -> None:
    """Print the execution trace using sismic's built-in step formatting.

    Args:
        steps: The list of ``MacroStep`` instances returned by
            ``Interpreter.execute()``.
    """
    print("  Macro steps:")
    if not steps:
        print("    (none)")
        return
    for i, macro in enumerate(steps, start=1):
        print(f"    {i}. {macro}")


def print_coverage(coverage: Mapping[str, Counter]) -> None:
    """Print state and transition coverage from an execution trace.

    Args:
        coverage: Per-category counts from the execution trace.
    """

    def _format_key(key: object) -> str:
        if hasattr(key, "source") and hasattr(key, "target"):
            return f"{key.source} -> {key.target}"
        return str(key)

    print("  Coverage:")
    for category, counter in coverage.items():
        if not counter:
            print(f"    {category}: (none)")
            continue
        items = ", ".join(
            f"{_format_key(k)} ({n}x)" for k, n in counter.items()
        )
        print(f"    {category}: {items}")


def write_artifacts(folder_name: str, statechart: Statechart) -> Path:
    """Write the YAML and PlantUML artifacts for a statechart.

    Args:
        folder_name: The example folder name; used as the output
            subdirectory under ``output/sismic/``.
        statechart: The built statechart to serialize.

    Returns:
        The directory the artifacts were written to.
    """
    out_dir = OUTPUT_DIR / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    name = statechart.name
    (out_dir / f"{name}.yaml").write_text(sio.export_to_yaml(statechart))
    (out_dir / f"{name}.puml").write_text(sio.export_to_plantuml(statechart))
    return out_dir


def main() -> int:
    """Build and run the sismic statechart for the chosen SM example.

    Returns:
        Process exit code (0 on success, non-zero on error).
    """
    configure_logging("INFO")
    args = parse_args()

    folder_name = resolve_example_folder(args.example)
    model_dir = SM_EXAMPLES_DIR / folder_name
    if not model_dir.is_dir():
        print(
            f"Example directory not found: {model_dir}",
            file=sys.stderr,
        )
        return 1

    model = load_syside_model(model_dir)

    state_def_qns = resolve_state_def_qns(model)
    logger.info("Found %d StateDefinition(s) in the model", len(state_def_qns))
    for state_def_qn in state_def_qns:
        print()
        print("=" * 72)
        print(state_def_qn)
        print("=" * 72)
        run_one(
            model,
            state_def_qn,
            folder_name,
            speed=args.speed,
            max_wall_seconds=args.max_wall_seconds,
        )
    return 0


def _guard_calls_after(guard: str) -> bool:
    """Whether ``guard`` calls sismic's bare ``after()`` time helper.

    Parses the guard as a Python expression and looks for a call to a
    bare ``after`` function -- the form the sismic backend emits for a
    relative time trigger (``accept after <duration>``).
    A guard that does not parse as a Python
    expression falls back to the substring test.

    Args:
        guard: A transition guard's emitted Python source.

    Returns:
        ``True`` if the guard calls a bare ``after(...)`` function.
    """
    try:
        tree = ast.parse(guard, mode="eval")
    except SyntaxError:
        return "after(" in guard
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "after"
        for node in ast.walk(tree)
    )


def _has_timer(statechart: Statechart) -> bool:
    """Whether any transition guard uses sismic's ``after()`` time helper.

    The sismic backend emits a relative time trigger (``accept after
    <duration>``) as an ``after(...)`` guard. Its presence is what tells
    the runner to drive the clock in real time rather than evaluate the
    machine once at t=0.

    Args:
        statechart: A built ``sismic.model.Statechart``.

    Returns:
        ``True`` if at least one transition guard calls ``after(...)``.
    """
    return any(
        _guard_calls_after(transition.guard)
        for transition in statechart.transitions
        if transition.guard
    )


def _run_realtime(
    interpreter: Interpreter, max_wall_seconds: float
) -> tuple[list[MacroStep], CodeEvaluationError | None]:
    """Drive ``interpreter`` in real time and return its trace.

    The interpreter's clock auto-advances (it must already be started),
    so ``after(...)`` guards come due on their own. The loop processes a
    macro step whenever one is ready and sleeps briefly otherwise. It
    ends when the machine reaches a final configuration or
    ``max_wall_seconds`` of wall-clock time elapse, whichever comes
    first; the cap stops a machine with no final state (a state sink)
    from running forever.

    Args:
        interpreter: Interpreter whose clock has been started.
        max_wall_seconds: Wall-clock safety cap on the run, in seconds.

    Returns:
        The collected macro-step trace and, if one was raised mid-run,
        the ``CodeEvaluationError`` that stopped it (otherwise ``None``).
    """
    trace: list[MacroStep] = []
    deadline = time.monotonic() + max_wall_seconds
    try:
        while not interpreter.final and time.monotonic() < deadline:
            step = interpreter.execute_once()
            if step is None:
                time.sleep(REALTIME_POLL_INTERVAL_SECONDS)
            else:
                trace.append(step)
    except CodeEvaluationError as exc:
        return trace, exc
    return trace, None


def _execute_passive(
    interpreter: Interpreter,
) -> tuple[list[MacroStep], CodeEvaluationError | None]:
    """Evaluate ``interpreter`` once at t=0 and return its trace.

    The clock stays at 0, so a time-triggered transition simply waits and
    never fires. A ``CodeEvaluationError`` is captured rather than raised
    so the caller can still persist the artifacts.

    Args:
        interpreter: Interpreter with a passive (un-started) clock.

    Returns:
        The macro-step trace and, if one was raised, the
        ``CodeEvaluationError`` (otherwise ``None``).
    """
    try:
        return interpreter.execute(), None
    except CodeEvaluationError as exc:
        return [], exc


def run_one(
    model: syside.Model,
    state_def_qn: str,
    folder_name: str,
    *,
    speed: float,
    max_wall_seconds: float,
) -> None:
    """Build, execute, and persist the statechart for ``state_def_qn``.

    A statechart with a time trigger (an ``after(...)`` guard) is run in
    real time so the timer fires on its own; any other statechart is
    evaluated once at t=0. Writes the statechart YAML and the PlantUML
    diagram to ``output/sismic/<folder_name>/``.

    Args:
        model: Loaded syside model.
        state_def_qn: Qualified name of the SysML state def to run.
        folder_name: The example folder name; the output subdirectory.
        speed: Real-time clock speed multiplier; used only in real-time
            mode.
        max_wall_seconds: Wall-clock safety cap on a real-time run, in
            seconds.
    """
    logger.info("Building for %s", state_def_qn)
    statechart = build_statechart(model, state_def_qn)

    print("\nStatechart structure:")
    print_structure(statechart)

    realtime = _has_timer(statechart)
    if realtime:
        clock = SimulatedClock()
        clock.speed = speed
        interpreter = Interpreter(statechart, clock=clock)
    else:
        interpreter = Interpreter(statechart)

    initial_config = sorted(interpreter.configuration)
    print(f"  Initial configuration: {initial_config}")
    if realtime:
        logger.info(
            "Simulated clock at %gx speed; %gs wall-clock cap.",
            speed,
            max_wall_seconds,
        )
    else:
        print("  Mode: passive (single evaluation at t=0)")

    logger.info("Executing via sismic interpreter")
    if realtime:
        clock.start()
        steps, error = _run_realtime(interpreter, max_wall_seconds)
    else:
        steps, error = _execute_passive(interpreter)

    if error is not None:
        logger.warning("Execution skipped: %s", error)
        out_dir = write_artifacts(folder_name, statechart)
        logger.info("Wrote YAML + diagram to %s", out_dir)
        return

    final_config = sorted(interpreter.configuration)
    print(f"  Final configuration:   {final_config}")
    if realtime:
        if interpreter.final:
            logger.info("Reached a final configuration")
        else:
            logger.warning(
                "Stopped at the %gs wall-clock cap without reaching a "
                "final configuration",
                max_wall_seconds,
            )
    print()
    print_trace(steps)
    print()
    print_coverage(coverage_from_trace(steps))

    out_dir = write_artifacts(folder_name, statechart)
    logger.info("Wrote YAML + diagram to %s", out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
