"""Execute quake statecharts and part systems on a shared discrete clock."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sismic.clock import SimulatedClock
from sismic.interpreter import Interpreter

from sysmlc.backends.quake.builder import build_statechart
from sysmlc.backends.quake.coordinator import (
    CoordinatedStep,
    PartSystemCoordinator,
    run_to_quiescence,
)
from sysmlc.backends.quake.parts import build_part_system

if TYPE_CHECKING:
    from collections.abc import Mapping

    import syside


@dataclass(frozen=True)
class RunReport:
    """The result of executing a statechart or part system to quiescence.

    Attributes:
        trace: The macro-step trace, each step annotated with the instance
            that ran it. A single machine's steps carry its own name.
        configurations: Final active-state configuration per instance name.
        clock_time: The logical time the shared clock reached.
        all_final: Whether every machine ended in a final configuration.
    """

    trace: tuple[CoordinatedStep, ...]
    configurations: dict[str, list[str]]
    clock_time: float
    all_final: bool

    def render(self) -> str:
        """Render the run as a human-readable multi-line report."""
        lines = ["trace:"]
        lines += [f"  {step.instance}: {step.step}" for step in self.trace]
        lines.append("final configuration:")
        for name in sorted(self.configurations):
            config = self.configurations[name]
            shown = ", ".join(config) if config else "(final)"
            lines.append(f"  {name}: {shown}")
        status = "all final" if self.all_final else "quiescent, not all final"
        lines.append(f"clock={self.clock_time} status={status}")
        return "\n".join(lines)


def run_state_def(
    model: syside.Model, state_def_qn: str, *, max_steps: int = 1000
) -> RunReport:
    """Execute a single state definition to quiescence.

    Args:
        model: Loaded syside model.
        state_def_qn: Qualified name of the ``state def`` to run.
        max_steps: Safety cap on total macro steps.

    Returns:
        The run report (trace, final configuration, clock time, all-final).

    Raises:
        RuntimeError: If ``max_steps`` is exceeded before quiescence.
    """
    name = state_def_qn.split("::")[-1]
    clock = SimulatedClock()
    statechart = build_statechart(model, state_def_qn)
    interpreters = {name: Interpreter(statechart, clock=clock)}
    trace = run_to_quiescence(interpreters, clock, max_steps=max_steps)
    return _report(interpreters, clock, trace)


def run_part_system(
    model: syside.Model, usage_qn: str, *, max_steps: int = 1000
) -> RunReport:
    """Execute a connected part system to quiescence.

    Args:
        model: Loaded syside model.
        usage_qn: Qualified name of the top-level part usage to run.
        max_steps: Safety cap on total macro steps.

    Returns:
        The run report (trace, final configurations, clock time, all-final).

    Raises:
        RuntimeError: If ``max_steps`` is exceeded before quiescence.
    """
    coordinator = PartSystemCoordinator(build_part_system(model, usage_qn))
    trace = coordinator.run(max_steps=max_steps)
    return _report(coordinator.interpreters, coordinator.clock, trace)


def _report(
    interpreters: Mapping[str, Interpreter],
    clock: SimulatedClock,
    trace: tuple[CoordinatedStep, ...],
) -> RunReport:
    """Package executed interpreters into a run report."""
    return RunReport(
        trace=trace,
        configurations={
            name: sorted(interpreter.configuration)
            for name, interpreter in interpreters.items()
        },
        clock_time=clock.time,
        all_final=all(
            interpreter.final for interpreter in interpreters.values()
        ),
    )
