"""Backend-neutral SysML part-graph access for the part assembler.

Verified syside part/connection API (2026-06-15), fixture
``models/sm-examples/part01-two-parts/part01.sysml``:

- top-level part usage: ``PartUsage`` whose ``.owner`` is a ``Package``.
- nested parts: ``usage.owned_features`` filtered to ``PartUsage``.
- a usage's definition: ``usage.owned_typings.collect()[0].type``.
- a part def's declared ports: ``part_def.owned_members`` filtered to
  ``PortUsage`` (their simple names; used for strict connection validation).
- exhibit (may be anonymous): ``part_def.owned_members`` filtered to
  ``ExhibitStateUsage``; ``exhibit.state_definitions`` filtered to
  model-declared ``StateDefinition`` qns; count drives the 0/1/>=2 rule.
- connection: ``usage.owned_features`` filtered to ``ConnectionUsage``
  (exclude ``SuccessionAsUsage``); ``conn.connector_ends`` -> 2 ends;
  ``end.owned_reference_subsetting.general.chaining_features`` ->
  ``[(PartUsage instance), (PortUsage port)]``.

Port binding (spec rosetta-parts-design.md §5.3, confirmed 2026-06-15):
``connect a.pa to b.pb`` routes a signal only if it is *sent via* ``pa``
on one end and *accepted via* ``pb`` on the other. The accept-side port is
``Trigger.via_port`` (already captured, read from the accepter's
``receiver_argument``). The send-side port is the *sender* port:
``SendActionUsage.sender_argument`` is a ``FeatureReferenceExpression`` whose
``.referent`` is the ``PortUsage`` (``send Pong via commPort`` ->
``sender_argument.referent.name == "commPort"``). This asymmetry is
SysML-correct: ``send via P`` names the sender's port, ``accept via P`` the
receiver's port.
"""
