from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import syside
from sismic.helpers import coverage_from_trace
from sismic.interpreter import Interpreter

from sysml2frost import configure_logging
from sysml2frost.explore import iter_model_elements
from sysml2frost.loader import load_syside_model
from sysml2frost.sismic import build_statechart

if TYPE_CHECKING:
    from collections import Counter
    from collections.abc import Mapping

    from sismic.model import Statechart
    from sismic.model.steps import MacroStep

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


def resolve_state_def_qn(model: syside.Model) -> str:
    """Resolve the qualified name of the SysML state def to translate.

    Args:
        model: Loaded syside model.

    Returns:
        The qualified name of the only ``StateDefinition`` in the model.

    Raises:
        SystemExit: If the model contains zero or more than one
            ``StateDefinition``.
    """
    state_defs = iter_model_elements(model, syside.StateDefinition)
    if not state_defs:
        raise SystemExit("No StateDefinition found in the model.")
    if len(state_defs) > 1:
        qns = sorted(str(sd.qualified_name) for sd in state_defs)
        raise SystemExit(
            "Multiple StateDefinitions found; cannot auto-select.\n"
            "Candidates:\n  - " + "\n  - ".join(qns)
        )
    return str(state_defs[0].qualified_name)


def print_structure(statechart: Statechart) -> None:
    """Print a one-line-per-state summary of the built statechart.

    Args:
        statechart: A built ``sismic.model.Statechart``.
    """
    print(f"  Root: {statechart.root}")
    print("  States:")
    for state_name in sorted(statechart.states):
        parent = statechart.parent_for(state_name) or "(root)"
        print(f"    {state_name}  (parent: {parent})")
    print("  Transitions:")
    transitions = list(statechart.transitions)
    if not transitions:
        print("    (none)")
    for trans in transitions:
        event = trans.event or "<eventless>"
        print(f"    {trans.source} -> {trans.target}  [event: {event}]")


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

    print(f"Loading from {model_dir}")
    model = load_syside_model(model_dir)

    state_def_qn = resolve_state_def_qn(model)
    print(f"Building for {state_def_qn}")
    statechart = build_statechart(model, state_def_qn)

    print("\nStatechart structure:")
    print_structure(statechart)

    print("\nExecuting via sismic Interpreter...")
    interpreter = Interpreter(statechart)
    print(f"  Initial configuration: {sorted(interpreter.configuration)}")
    steps = interpreter.execute()
    print(f"  Final configuration:   {sorted(interpreter.configuration)}")
    print()
    print_trace(steps)
    print()
    print_coverage(coverage_from_trace(steps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
