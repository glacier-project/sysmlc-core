from __future__ import annotations

import syside
from sismic.model import BasicState, CompoundState, Statechart, Transition

from sysml2frost.explore.model_queries import SysideModelQueries


class StatechartBuilder:
    """Build a sismic Statechart from a SysML state definition.

    ``StateUsage`` -> ``BasicState``;
    ``TransitionUsage`` -> eventless ``Transition``;
    ``StateDefinition`` -> ``CompoundState``
    """

    def __init__(self, model: syside.Model, state_def_qn: str) -> None:
        """Initialize the builder.

        Args:
            model: Loaded syside model containing the SysML state def.
            state_def_qn: Qualified name of the SysML ``state def`` to
                translate.
        """
        self._model = model
        self._state_def_qn = state_def_qn
        self._queries = SysideModelQueries(model)
        self._state_def: syside.StateDefinition
        self._statechart: Statechart

    def build(self) -> Statechart:
        """Construct and return the sismic Statechart.

        Returns:
            A sismic ``Statechart`` ready to feed into ``Interpreter``.

        Raises:
            ValueError: If ``state_def_qn`` does not resolve to a
                ``StateDefinition``, or if the definition's entry
                succession cannot be resolved.
        """
        self._state_def = self._queries.resolve_element_by_qn(
            syside.StateDefinition, self._state_def_qn
        )
        self._statechart = Statechart(name=self._state_def.name)
        self._add_root_compound()
        self._add_child_states()
        self._add_transitions()
        self._statechart.validate()
        return self._statechart

    def _add_root_compound(self) -> None:
        """Add the root ``CompoundState`` representing the state def."""
        initial = self._resolve_initial_state()
        self._statechart.add_state(
            CompoundState(self._state_def.name, initial=initial.name),
            parent=None,
        )

    def _add_child_states(self) -> None:
        """Add a ``BasicState`` for each owned ``StateUsage``."""
        root_name = self._state_def.name
        for state_usage in self._state_def.owned_states.collect():
            self._statechart.add_state(
                BasicState(state_usage.name), parent=root_name
            )

    def _add_transitions(self) -> None:
        """Add an eventless ``Transition`` for each owned transition."""
        for trans in self._state_def.owned_transitions.collect():
            source = trans.source
            target = trans.target
            assert source is not None and target is not None
            self._statechart.add_transition(
                Transition(source=source.name, target=target.name)
            )

    def _resolve_initial_state(self) -> syside.StateUsage:
        """Resolve the initial state targeted by the entry pseudostate.

        Returns:
            The ``StateUsage`` that the entry pseudostate transitions to.

        Raises:
            ValueError: If no entry pseudostate is declared, or if no
                succession from the entry pseudostate to a ``StateUsage``
                can be found.
        """
        entry = self._state_def.entry_action
        if entry is None:
            raise ValueError(
                f"State def {self._state_def.qualified_name} has no "
                "entry pseudostate; expected an "
                "`entry; then <state>;` declaration."
            )

        for feat in self._state_def.owned_features.collect():
            if not isinstance(feat, syside.SuccessionAsUsage):
                continue
            if feat.source is not entry:
                continue
            for target in feat.targets.collect():
                if isinstance(target, syside.StateUsage):
                    return target
        raise ValueError(
            f"No entry succession found for state def "
            f"{self._state_def.qualified_name}; expected an "
            f"`entry; then <state>;` declaration."
        )


def build_statechart(model: syside.Model, state_def_qn: str) -> Statechart:
    """Build a sismic Statechart from a SysML state definition.

    Args:
        model: Loaded syside model containing the SysML state def.
        state_def_qn: Qualified name of the SysML ``state def`` to
            translate.

    Returns:
        A sismic ``Statechart`` ready to feed into ``Interpreter``.

    Raises:
        ValueError: If ``state_def_qn`` does not resolve to a
            ``StateDefinition``, or if the definition's entry succession
            cannot be resolved.
    """
    return StatechartBuilder(model, state_def_qn).build()
