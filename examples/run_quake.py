from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import syside
from sismic.clock import SimulatedClock
from sismic.exceptions import CodeEvaluationError
from sismic.helpers import coverage_from_trace
from sismic.interpreter import Interpreter

from sysmlc import configure_logging
from sysmlc.backends.quake import build_statechart
from sysmlc.backends.quake.coordinator import StopReason, run_to_quiescence
from sysmlc.errors import UnsupportedConstructError
from sysmlc.logging import PACKAGE_LOGGER_NAME
from sysmlc.sysml.loading import load_model
from sysmlc.sysml.queries import iter_elements

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Mapping

    from sismic.model import Statechart
    from sismic.model.steps import MacroStep

logger = logging.getLogger(f"{PACKAGE_LOGGER_NAME}.run_quake")

SM_EXAMPLES_DIR = (
    Path(__file__).resolve().parent.parent / "models" / "sm-examples"
)


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
    state_defs = iter_elements(model, syside.StateDefinition)
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


def print_coverage(coverage: Mapping[str, Counter[str]]) -> None:
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

    model = load_model(model_dir)

    state_def_qns = resolve_state_def_qns(model)
    logger.info("Found %d StateDefinition(s) in the model", len(state_def_qns))
    for state_def_qn in state_def_qns:
        print()
        print("=" * 72)
        print(state_def_qn)
        print("=" * 72)
        run_one(model, state_def_qn)
    return 0


def run_one(model: syside.Model, state_def_qn: str) -> None:
    """Build, execute, and report on the statechart for ``state_def_qn``.

    Executes on the shared discrete-event loop: the clock jumps to each next
    scheduled event, so a time-triggered machine settles on its own and a
    machine with no timer settles at t=0. Prints the statechart structure,
    the macro-step trace, and state/transition coverage. A machine that
    cannot be built (an unsupported construct) or cannot be evaluated (an
    incomplete model) is reported and skipped; one that never settles is
    cut off at the macro-step cap and reported with its trace so far.

    Args:
        model: Loaded syside model.
        state_def_qn: Qualified name of the SysML state def to run.
    """
    logger.info("Building for %s", state_def_qn)
    try:
        statechart = build_statechart(model, state_def_qn)
    except UnsupportedConstructError as error:
        logger.warning("Build skipped: %s", error)
        return

    print("\nStatechart structure:")
    print_structure(statechart)

    clock = SimulatedClock()
    name = state_def_qn.split("::")[-1]
    logger.info("Executing via the shared discrete-event loop")
    try:
        # The constructor already runs the preamble, so an incomplete
        # model can fail here as well as during execution.
        interpreter = Interpreter(statechart, clock=clock)
        print(f"  Initial configuration: {sorted(interpreter.configuration)}")
        trace, stop_reason = run_to_quiescence({name: interpreter}, clock)
    except CodeEvaluationError as error:
        logger.warning("Execution skipped: %s", error)
        return
    steps = [coordinated.step for coordinated in trace]

    print(f"  Final configuration:   {sorted(interpreter.configuration)}")
    if stop_reason is StopReason.STEP_CAP:
        logger.warning("Stopped at the macro-step safety cap before settling")
    elif interpreter.final:
        logger.info("Reached a final configuration")
    else:
        logger.info("Quiescent without reaching a final configuration")
    print()
    print_trace(steps)
    print()
    print_coverage(coverage_from_trace(steps))


if __name__ == "__main__":
    raise SystemExit(main())
