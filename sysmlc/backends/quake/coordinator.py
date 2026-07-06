"""Runtime coordinator for quake part-system artifacts."""

from __future__ import annotations

import enum
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sismic.clock import SimulatedClock
from sismic.interpreter import Interpreter

from sysmlc.backends.quake.codegen import (
    ROUTER_CONTEXT_KEY,
    TICK_METADATA_KEY,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from typing import Any

    from sismic.model import Event, MacroStep

    from sysmlc.backends.quake.parts import QuakePartSystem
    from sysmlc.semantics.parts.routing import PortSignalRoute


@dataclass(frozen=True)
class CoordinatedStep:
    """A sismic macro step annotated with the part instance that ran it."""

    instance: str
    step: MacroStep


class StopReason(enum.Enum):
    """Why ``run_to_quiescence`` stopped driving the interpreters."""

    FINAL = "all final"
    QUIESCENT = "quiescent, not all final"
    TIME_BOUND = "reached time bound"
    STEP_CAP = "hit step cap"


class PartSystemCoordinator:
    """Drive one interpreter per part instance on a shared logical clock."""

    def __init__(self, system: QuakePartSystem) -> None:
        """Initialize the coordinator.

        Args:
            system: Built quake part-system artifact.
        """
        self._clock = SimulatedClock()
        self._routes = _route_map(system.routes)
        self._interpreters = {
            node.usage_name: Interpreter(
                system.statecharts[node.usage_name],
                initial_context={
                    ROUTER_CONTEXT_KEY: self._route_for(node.usage_name)
                },
                clock=self._clock,
            )
            for node in system.graph.parts
        }

    @property
    def clock(self) -> SimulatedClock:
        """The shared logical clock."""
        return self._clock

    @property
    def interpreters(self) -> Mapping[str, Interpreter]:
        """Interpreters keyed by part instance name."""
        return self._interpreters.copy()

    def run(
        self, *, max_steps: int = 1000, until: float | None = None
    ) -> tuple[tuple[CoordinatedStep, ...], StopReason]:
        """Run all machines until quiescence, a time bound, or the step cap.

        Args:
            max_steps: Safety cap on total macro steps.
            until: Simulated-time upper bound; events at exactly ``until``
                still run, and a bounded stop leaves the clock at ``until``.
                ``None`` runs to quiescence.

        Returns:
            The coordinated macro-step trace and the reason the run stopped.

        Raises:
            ValueError: If ``max_steps`` is less than one.
        """
        return run_to_quiescence(
            self._interpreters, self._clock, max_steps=max_steps, until=until
        )

    def _route_for(self, source: str) -> Callable[..., None]:
        """Return a route closure bound to one source part instance."""

        def route(signal: str, port: str, /, **payload: Any) -> None:
            """Deliver ``signal`` from ``port`` to its routed targets.

            The two parameters are positional-only so a payload attribute
            named ``signal`` or ``port`` passes through ``payload`` instead
            of clashing with them.
            """
            for edge in self._routes.get((source, port, signal), ()):
                self._interpreters[edge.target].queue(signal, **payload)

        return route


def run_to_quiescence(
    interpreters: Mapping[str, Interpreter],
    clock: SimulatedClock,
    *,
    max_steps: int = 1000,
    until: float | None = None,
) -> tuple[tuple[CoordinatedStep, ...], StopReason]:
    """Drive interpreters to quiescence, a time bound, or the step cap.

    Runs every interpreter to a fixpoint at the current clock instant, then
    advances the shared clock to the next scheduled event, repeating until
    all interpreters are final, no future event remains, the next event is
    past ``until``, or ``max_steps`` is reached. Single machines (one
    interpreter) and part systems (many) share this loop.

    Args:
        interpreters: Interpreters keyed by name, all sharing ``clock``.
        clock: The shared logical clock, advanced to each next event time.
        max_steps: Safety cap on total macro steps.
        until: Simulated-time upper bound; events at exactly ``until``
            still run, and a bounded stop leaves the clock at ``until``.
            ``None`` runs to quiescence.

    Returns:
        The coordinated macro-step trace and the reason the run stopped.

    Raises:
        ValueError: If ``max_steps`` is less than one.
    """
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")

    trace: list[CoordinatedStep] = []
    while True:
        capped = False
        while True:
            progressed = False
            for name, interpreter in interpreters.items():
                # A final machine never runs again.
                if interpreter.final:
                    continue
                step = interpreter.execute_once()
                if step is None:
                    continue
                trace.append(CoordinatedStep(name, step))
                progressed = True
                # Cap hit: keep the trace so far instead of raising.
                if len(trace) >= max_steps:
                    capped = True
                    break
            if capped or not progressed:
                break

        if capped:
            return tuple(trace), StopReason.STEP_CAP
        if all(interpreter.final for interpreter in interpreters.values()):
            return tuple(trace), StopReason.FINAL
        _purge_stale_ticks(interpreters.values())
        next_time = _next_system_event_time(interpreters.values(), clock.time)
        if next_time is None:
            return tuple(trace), StopReason.QUIESCENT
        if until is not None and next_time > until:
            # Leave the clock at the bound.
            if until > clock.time:
                clock.time = until
            return tuple(trace), StopReason.TIME_BOUND
        # Advance the clock to the next event, then settle again.
        clock.time = next_time


def _route_map(
    routes: tuple[PortSignalRoute, ...],
) -> dict[tuple[str, str, str], tuple[PortSignalRoute, ...]]:
    """Group routes by their ``(source, source_port, signal)`` key.

    The router looks up a send's targets by that key, so pre-indexing turns
    each delivery into a dict lookup instead of a scan over all routes.
    """
    grouped: dict[tuple[str, str, str], list[PortSignalRoute]] = defaultdict(
        list
    )
    for route in routes:
        grouped[(route.source, route.source_port, route.signal)].append(route)
    return {key: tuple(value) for key, value in grouped.items()}


def _purge_stale_ticks(interpreters: Iterable[Interpreter]) -> None:
    """Drop stale time-trigger events from the internal event queues.

    A time-trigger event is stale when the machine's own delivery rules
    would ignore it: its source state is no longer active, or its
    activation stamp no longer matches the state's counter. Left queued, a
    stale event makes the clock chase an instant where nothing happens.
    """
    for interpreter in interpreters:
        queue = _internal_queue(interpreter)
        if any(_is_stale_tick(event, interpreter) for _time, event in queue):
            queue[:] = [
                (time, event)
                for time, event in queue
                if not _is_stale_tick(event, interpreter)
            ]


def _is_stale_tick(event: Event, interpreter: Interpreter) -> bool:
    """Whether the machine would ignore this time-trigger event."""
    metadata = getattr(event, TICK_METADATA_KEY, None)
    if metadata is None:
        return False
    state_name, counter_name = metadata
    if state_name not in interpreter.configuration:
        return True
    return bool(event.n != interpreter.context[counter_name])


def _internal_queue(interpreter: Interpreter) -> list[tuple[float, Event]]:
    """The interpreter's private internal event queue, as a mutable list.

    sismic exposes no public accessor for pending events, so this is the one
    site that names the private ``_internal_queue`` attribute and asserts its
    ``(time, event)`` list shape. ``_queue_times`` reads it and the stale-tick
    purge rewrites it in place; the in-place rewrite relies on order-preserving
    filtering to keep sismic's queue in its scheduled order.
    """
    return cast("list[tuple[float, Event]]", interpreter._internal_queue)


def _next_system_event_time(
    interpreters: Iterable[Interpreter], current_time: float
) -> float | None:
    """Return the earliest future event time, or ``None`` if none remain.

    Only non-final interpreters count, so leftover timers of a machine that
    already terminated (sismic never cancels them) do not hold the clock back.
    """
    candidates = [
        candidate
        for interpreter in interpreters
        if not interpreter.final
        for candidate in _queue_times(interpreter)
        if candidate > current_time
    ]
    return min(candidates) if candidates else None


def _queue_times(interpreter: Interpreter) -> tuple[float, ...]:
    """Return the scheduled times in the interpreter's two event queues.

    The internal queue is read through ``_internal_queue``; the external queue
    has no public accessor either and is read the same private way.
    """
    times = [time for time, _event in _internal_queue(interpreter)]
    external = cast(
        "Sequence[tuple[float, Event]]", interpreter._external_queue
    )
    times.extend(time for time, _event in external)
    return tuple(times)
