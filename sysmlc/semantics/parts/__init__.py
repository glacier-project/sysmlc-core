"""Backend-neutral SysML part-graph access for the part assembler.

Verified syside part/connection API (2026-06-15) against the bundled
``sm-examples/part01-two-parts`` corpus model:

- top-level part usage: ``PartUsage`` whose ``.owner`` is a ``Package``.
- nested parts: ``usage.owned_features`` filtered to ``PartUsage``.
- a usage's definition: ``usage.owned_typings.collect()[0].type``.
- a part def's declared ports: ``part_def.owned_members`` filtered to
  ``PortUsage`` (their simple names; used for strict connection validation).
- exhibit (may be anonymous): ``part_def.owned_members`` filtered to
  ``ExhibitStateUsage``; ``exhibit.state_definitions`` filtered to
  model-declared ``StateDefinition`` qns; count drives the 0/1/>=2 rule.
- connection: ``usage.owned_features`` filtered to ``ConnectionUsage``
  (exclude ``SuccessionAsUsage``); ``conn.related_features`` -> 2 endpoint features;
  ``feature.chaining_features`` ->
  ``[(PartUsage instance), (PortUsage port)]``.

Port transport:
``interface a.pa to b.pb`` establishes eligible port peers. Named interfaces
(``interface c : I connect a.pa to b.pb``) and connections semantically typed
by an interface definition (``connection c : I connect a.pa to b.pb``) have
the same eligibility. Classification uses resolved interface definitions,
including indirect specialization of ``Interfaces::Interface``.

Generic structural connections (``connect a.pa to b.pb``) never route signals.
They remain legal structural relationships, including connections between
parts or mixed endpoints, and do not enter the execution graph. A structural
link alongside an interface between the same ports has no routing effect.
``PartGraph.interfaces`` contains only resolved interface endpoint pairs.
A sender without a matching interface route retains the existing warning
that its signal is never delivered.

An eligible interface routes a signal only if it is *sent via* ``pa``
on one end and *accepted via* ``pb`` on the other. The accept-side port is
``Trigger.via_port`` (already captured, read from the accepter's
``receiver_argument``). The send-side port is the *sender* port:
``SendActionUsage.sender_argument`` is a ``FeatureReferenceExpression`` whose
``.referent`` is the ``PortUsage`` (``send Pong via commPort`` ->
``sender_argument.referent.name == "commPort"``). This asymmetry is
SysML-correct: ``send via P`` names the sender's port, ``accept via P`` the
receiver's port.
"""
