"""Execute quake statecharts and part systems on a shared discrete clock."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sismic.clock import SimulatedClock
from sismic.exceptions import SismicError
from sismic.interpreter import Interpreter

from sysmlc.backends.quake.builder import build_statechart
from sysmlc.backends.quake.coordinator import (
    CoordinatedStep,
    PartSystemCoordinator,
    StopReason,
    run_to_quiescence,
)
from sysmlc.backends.quake.parts import build_part_system
from sysmlc.errors import ExecutionError

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
        finals: Whether each instance ended in a final configuration, keyed
            by instance name. An instance can be neither final nor active:
            one starved by the step cap never entered its initial state, so
            its configuration is empty too.
        clock_time: The logical time the shared clock reached.
        stop_reason: Why the run stopped (all final, quiescent, time bound,
            or the step cap).
    """

    trace: tuple[CoordinatedStep, ...]
    configurations: dict[str, list[str]]
    finals: dict[str, bool]
    clock_time: float
    stop_reason: StopReason

    @property
    def all_final(self) -> bool:
        """Whether every machine ended in a final configuration."""
        return self.stop_reason is StopReason.FINAL

    @property
    def hit_step_cap(self) -> bool:
        """Whether the run stopped at the ``max_steps`` safety cap."""
        return self.stop_reason is StopReason.STEP_CAP

    def render(self) -> str:
        """Render the run as a human-readable multi-line report."""
        lines = ["trace:"]
        lines += [f"  {step.instance}: {step.step}" for step in self.trace]
        lines.append("final configuration:")
        for name in sorted(self.configurations):
            config = self.configurations[name]
            if self.finals[name]:
                shown = "(final)"
            elif config:
                shown = ", ".join(config)
            else:
                shown = "(never ran)"
            lines.append(f"  {name}: {shown}")
        lines.append(f"clock={self.clock_time} status={self.stop_reason.value}")
        return "\n".join(lines)


def run_state_def(
    model: syside.Model,
    state_def_qn: str,
    *,
    max_steps: int = 1000,
    until: float | None = None,
    external: tuple[str, frozenset[str]] | None = None,
) -> RunReport:
    """Execute a single state definition to quiescence.

    Args:
        model: Loaded syside model.
        state_def_qn: Qualified name of the ``state def`` to run.
        max_steps: Safety cap on total macro steps.
        until: Simulated-time upper bound; events at exactly ``until``
            still run, and a bounded stop leaves the clock at ``until``.
            ``None`` runs to quiescence.
        external: Optional ``(module_stem, function_names)`` pair for
            external calc-def backing.

    Returns:
        The run report (trace, final configuration, clock time, stop reason).

    Raises:
        UnsupportedConstructError: If the model uses a construct the quake
            backend does not support.
        ExecutionError: If sismic rejects the model at runtime (an
            unevaluable guard or action, or nondeterministic transitions).
        ValueError: If ``max_steps`` is less than one.
    """
    name = state_def_qn.split("::")[-1]
    clock = SimulatedClock()
    statechart = build_statechart(model, state_def_qn, external=external)
    try:
        interpreters = {name: Interpreter(statechart, clock=clock)}
        trace, stop_reason = run_to_quiescence(
            interpreters, clock, max_steps=max_steps, until=until
        )
    except SismicError as error:
        raise ExecutionError(str(error)) from error
    return _report(interpreters, clock, trace, stop_reason)


def run_part_system(
    model: syside.Model,
    usage_qn: str,
    *,
    max_steps: int = 1000,
    until: float | None = None,
    external: tuple[str, frozenset[str]] | None = None,
) -> RunReport:
    """Execute a connected part system to quiescence.

    Args:
        model: Loaded syside model.
        usage_qn: Qualified name of the top-level part usage to run.
        max_steps: Safety cap on total macro steps.
        until: Simulated-time upper bound; events at exactly ``until``
            still run, and a bounded stop leaves the clock at ``until``.
            ``None`` runs to quiescence.
        external: Optional ``(module_stem, function_names)`` pair for
            external calc-def backing.

    Returns:
        The run report (trace, final configurations, clock time, stop reason).

    Raises:
        UnsupportedConstructError: If the model uses a construct the quake
            backend does not support.
        ExecutionError: If sismic rejects the model at runtime (an
            unevaluable guard or action, or nondeterministic transitions).
        ValueError: If ``max_steps`` is less than one.
    """
    system = build_part_system(model, usage_qn, external=external)
    try:
        coordinator = PartSystemCoordinator(system)
        trace, stop_reason = coordinator.run(max_steps=max_steps, until=until)
    except SismicError as error:
        raise ExecutionError(str(error)) from error
    return _report(
        coordinator.interpreters, coordinator.clock, trace, stop_reason
    )


def _report(
    interpreters: Mapping[str, Interpreter],
    clock: SimulatedClock,
    trace: tuple[CoordinatedStep, ...],
    stop_reason: StopReason,
) -> RunReport:
    """Package executed interpreters into a run report."""
    return RunReport(
        trace=trace,
        configurations={
            name: sorted(interpreter.configuration)
            for name, interpreter in interpreters.items()
        },
        finals={
            name: interpreter.final
            for name, interpreter in interpreters.items()
        },
        clock_time=clock.time,
        stop_reason=stop_reason,
    )
