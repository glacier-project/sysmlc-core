from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import sismic.io as sio
import syside
from sismic.exceptions import CodeEvaluationError
from sismic.helpers import coverage_from_trace
from sismic.interpreter import Interpreter

from sysml2frost import configure_logging
from sysml2frost.explore import iter_model_elements
from sysml2frost.loader import load_syside_model
from sysml2frost.logging_utils import PACKAGE_LOGGER_NAME
from sysml2frost.sismic import build_statechart

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

    A composite state is followed by its ``initial`` substate; children
    are printed indented beneath their parent.

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
    for child in sorted(statechart.children_for(name)):
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
        run_one(model, state_def_qn, folder_name)
    return 0


def run_one(model: syside.Model, state_def_qn: str, folder_name: str) -> None:
    """Build, execute, and persist the statechart for ``state_def_qn``.

    Writes the statechart YAML and the PlantUML diagram to
    ``output/sismic/<folder_name>/``.

    Args:
        model: Loaded syside model.
        state_def_qn: Qualified name of the SysML state def to run.
        folder_name: The example folder name; the output subdirectory.
    """
    logger.info("Building for %s", state_def_qn)
    statechart = build_statechart(model, state_def_qn)

    print("\nStatechart structure:")
    print_structure(statechart)

    logger.info("Executing via sismic interpreter")
    interpreter = Interpreter(statechart)
    initial_config = sorted(interpreter.configuration)
    print(f"  Initial configuration: {initial_config}")
    try:
        steps = interpreter.execute()
    except CodeEvaluationError as exc:
        logger.warning("Execution skipped: %s", exc)
        out_dir = write_artifacts(folder_name, statechart)
        logger.info("Wrote YAML + diagram to %s", out_dir)
        return
    final_config = sorted(interpreter.configuration)
    print(f"  Final configuration:   {final_config}")
    print()
    print_trace(steps)
    print()
    print_coverage(coverage_from_trace(steps))

    out_dir = write_artifacts(folder_name, statechart)
    logger.info("Wrote YAML + diagram to %s", out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
