# syside API reference

How this project reads, edits, and extends SysML models through
[syside](https://docs.sensmetry.com/python/latest/index.html). Part reference
(the APIs and the patterns we rely on), part audit (where current usage
diverges from the documented/recommended API and what to change).

**Pinned to syside `0.8.6` / Python 3.14.** API names below were checked
against the version installed in `.venv` unless a line says otherwise. Run
checks with `.venv/bin/python -m …` (never bare `uv run` — it prunes the dev
extra and syside disappears).

The read → edit → add → revalidate → evaluate patterns in §3–§7, plus the
audit's `cast`/`try_cast` and `.STD` recommendations, are exercised by the
test suite against the `charging-station` (with quantities) and `thermostat`
example models on syside 0.8.6 — including created nodes appearing in
`owned_members` and `append(name="str")` raising `TypeError`. Rows in §9
marked **unverified** were last checked on an earlier syside build on this
line and not re-run against 0.8.6 (CST byte spans,
`remove_relationship` → `False` on parsed rels, `member_element` no setter).

**Upstream docs**

| Page                                                                                    | Covers                                             |
| --------------------------------------------------------------------------------------- | -------------------------------------------------- |
| [Model Structure](https://docs.sensmetry.com/python/latest/structure.html)              | element model, accessors, modification constraints |
| [Low-Level API](https://docs.sensmetry.com/python/latest/low-level.html)                | documents, build state, sema reset, pipeline       |
| [Expression Evaluation](https://docs.sensmetry.com/python/latest/evaluation.html)       | `Compiler.evaluate`, supported stdlib functions    |
| [`syside` module reference](https://docs.sensmetry.com/python/latest/syside/index.html) | class/function index                               |
| [Automator: Advanced](https://docs.sensmetry.com/automator/advanced.html)               | threading, formatting, JSON, evaluation caveats    |

______________________________________________________________________

## 1. Conventions you must internalize

These cut across every section; getting them wrong is the source of most
syside confusion.

- **`snake_case` attributes.** syside renames the spec's Java-style
  `camelCase` to Python `snake_case` (`owned_members`, `feature_value`).
- **Optional returns on partial models.** Attributes that the spec calls
  required may still return `None`, because syside represents models that
  contain syntax errors. Treat `.name`, `.qualified_name`, `.direction`,
  expression accessors, etc. as nullable.
- **Multi-valued attributes are lazy.** Things like `owned_members`,
  `owned_relationships`, `operands`, `attribute_definitions` return a
  `LazyIterator`. Call **`.collect()`** to materialize a list. The iterator
  also offers `count`, `empty`, `for_each`, `at` if you don't need the list.
- **`isinstance` should use `.STD`.** syside avoids interface base classes and
  multiple inheritance for performance, so one spec type can map to several
  syside classes. Every class exposes a `.STD` tuple of the classes that the
  spec considers that type. Plain `isinstance(x, syside.ActionUsage)` is
  *narrower* than the spec; `isinstance(x, syside.ActionUsage.STD)` matches it.
  This only matters for the types whose `.STD` has more than one member — the
  codebase's affected sites are in [§8](#8-audit-current-usage-vs-recommended-api),
  the full list in [§10.9](#109-every-multi-type-std-in-this-catalog).
- **Narrow with `cast` / `try_cast`.** `node.cast(*types)` returns the node
  typed as the cast target and raises on mismatch; `node.try_cast(*types)`
  returns `None` instead. Both accept either a tuple or varargs of types.
  Prefer these over `assert isinstance(...)`, which is stripped under
  `python -O`.
- **CST-backed accessors are blind to created nodes.** Accessors backed by the
  concrete syntax tree (`feature_value_expression`, `owned_features`) only see
  what was *parsed*. Nodes you create through the low-level editing API
  ([§6](#6-adding--removing-nodes)) are invisible to them even after a full
  pipeline re-run. Read created/edited structure through the **semantic**
  accessors (`owned_relationships`, `owned_members`) instead. This is the
  single most expensive gotcha in the codebase.

______________________________________________________________________

## 2. The object model

```
Model ──┬── index            # symbol/static index (feed Stdlib, pipelines)
        ├── lib              # standard library handle
        ├── user_docs        # the editable documents (yields per-doc mutexes)
        └── elements(...)    # every Element, optionally filtered by kind
```

- **`Document`** is the atomic unit — one source file. A document owns the
  memory for its elements, which is why **elements cannot move between
  documents** (the editing API forbids it).
- **`Element`** is the AST node base. The class hierarchy maps 1:1 onto the
  KerML/SysML metamodel (`PartDefinition`, `AttributeUsage`,
  `TransitionUsage`, `LiteralRational`, …).
- **Definitions vs usages.** `XDefinition` declares a type; `XUsage` uses one.
  They expose features differently — e.g. a `StateDefinition` exposes
  `owned_attributes`, a `StateUsage` exposes `nested_attributes`
  (`semantics/statemachine/attributes.py:81` `scope_attributes`).
- **Relationships** are first-class elements (`FeatureValue`, `OwningMembership`,
  `Membership`, `FeatureTyping`). Reading and editing both go *through*
  relationships, not around them.
- **Expressions** are elements too (`OperatorExpression`, `LiteralInteger`,
  `FeatureReferenceExpression`, `TriggerInvocationExpression`).

`AstNode` convenience accessors worth knowing: `parent`, `document`,
`owned_elements`, `cast`/`try_cast`.

______________________________________________________________________

## 3. Loading & diagnostics

`sysmlc/sysml/loading.py`:

```python
sysml_files = syside.collect_files_recursively(str(model_dir))
model, diagnostics = syside.try_load_model(paths=sysml_files)

if diagnostics.contains_errors():
    raise ValueError(...)        # diagnostics.errors / .warnings are lists
```

- **`try_load_model(paths=…)`** returns `(model, diagnostics)` and never
  raises on model errors — you inspect `diagnostics`. `DiagnosticMessage`
  stringifies to a readable line. (`load_model(...)` exists too and raises;
  the codebase prefers the explicit form so it controls the message.)
- **The throwaway-probe pattern** (`sysml/quantities.py`): to parse a SysML
  fragment in isolation (e.g. a `"90 [s]"` override), write it into a tiny
  `package` in a temp dir, `load_model` it, and walk the result. This buys
  full SysML parsing — unit aliases, scientific notation — without
  reimplementing the grammar. Reuse it for any "parse this snippet" need.

______________________________________________________________________

## 4. Reading & querying

### Finding elements

```python
# sysml/queries.py — every element of a kind, library docs excluded
model.elements(
    syside.StateDefinition,
    include_subtypes=True,
    considered_document_kinds=syside.DocumentKind.MODEL,
)
```

- **`considered_document_kinds=syside.DocumentKind.MODEL`** excludes the
  standard library — almost always what you want when iterating user models.
- **Sort for determinism.** syside iteration order is not stable across runs;
  `iter_elements` sorts by `(qualified_name, path, name)`. Generated output
  must be reproducible, so always go through the sorted helper.

### Resolving by qualified name

```python
normalized = normalize_qualified_name("Thermostat::Thermostat")  # -> tuple
for element in model.elements(kind, ...):
    if element.matches_qualified_name(normalized):
        return element
```

`normalize_qualified_name` (`sysml/names.py`) splits a `"A::B"` string into the
segment tuple syside's matching APIs expect. `element.qualified_name`, `.name`,
and `.path` are the read-side identity accessors (any may be `None`).

### Traversal

`sysml/visitor.py` `ModelVisitor` wraps `iter_elements` + an `isinstance`
dispatch into typed `visit_*` hooks. Subclass it for a typed walk instead of
re-writing the dispatch ladder.

### Accessors — semantic vs CST

| Want                              | Use                                     | Notes                                  |
| --------------------------------- | --------------------------------------- | -------------------------------------- |
| Owned relationships               | `element.owned_relationships.collect()` | authoritative; sees created nodes      |
| Owned members                     | `element.owned_members.collect()`       | authoritative; sees created nodes      |
| Sema-derived / inherited features | `element.owned_features.collect()`      | CST-backed; **blind to created nodes** |
| Applied metadata                  | `element.metadata.collect()`            | see `sysml/metadata.py`                |
| Supertypes of a typing            | `typing.types.collect()`                |                                        |

The `owned_features` vs `owned_members` split is deliberate and correct:
read-only sema views that want inherited/implied features use `owned_features`
(`actions.py:27`, `states.py:66`, `codegen/python.py:123`); anything that must
also see low-level-created members uses `owned_members`
(`attributes.py:55`, the editing layer). See the comment at
`semantics/statemachine/attributes.py:53`.

### Reading a value

```python
# sysml/queries.py — feature_value(): owned FeatureValue first, CST fallback
for rel in attr.owned_relationships.collect():
    if isinstance(rel, syside.FeatureValue):
        return rel.value
return attr.feature_value_expression       # blind to created values
```

Always read the owned `FeatureValue` relationship first.
`feature_value_expression` is the CST accessor and will miss any value created
through editing. `FeatureValue` also carries `is_default` / `is_initial`
(`=` vs `default`/`:=` — see [§5](#5-editing-existing-nodes)).

### Expressions, operators, quantities

- **Operators are an enum — compare with `is`.**
  `expr.operator is syside.Operator.Quantity` (the `[unit]` operator). Never
  `== "["` (`sysml/quantities.py:124`).
- **A quantity `2 [min]`** is an `OperatorExpression(Quantity)` over
  `(magnitude_literal, unit_ref)`. `expr.operands.collect()` gives the pair;
  `unit_ref.referent` is the unit, and **`referent.types.collect()[0]`** is the
  unit *kind* (e.g. `ISQBase::DurationUnit`). See
  `quantity_parts` (`sysml/quantities.py:117`).
- **Literals** (`LiteralBoolean/Integer/Rational/String`) carry `.value`
  (a read *and* write accessor — [§5](#5-editing-existing-nodes)).
- **Scalar-quantity check:**
  `definition.specializes(("Quantities", "ScalarQuantityValue"))`
  (`attributes.py:66`).

### Source spans (CST)

Documented for syside 0.8.6 (not re-verified on this build):
`node.cst_node.start_byte` / `end_byte` are file byte offsets;
`node.cst_node.text(document_text)` needs the document text passed in; and
`document.url` is a `file:<path>` URI.

______________________________________________________________________

## 5. Editing existing nodes

The hard rule: **parsed structure can be mutated or extended, never replaced.**
You can change a literal's value, but you cannot swap one parsed node for
another of a different kind (`sysml/editing.py`).

```python
# Mutate a literal in place
existing = value_rel(attr).value          # the FeatureValue's expression
if isinstance(existing, syside.LiteralRational):
    existing.value = float(value)         # keep the declared rational kind
```

- **Only `default` / `:=` are overridable.** A plain `=` binding is fixed by
  the model; `FeatureValue.is_default` / `is_initial` gate it
  (`check_overridable`, `editing.py:48`). This mirrors the language's own
  redefinition rule.
- **Kind changes are refused.** A fractional override into a model-declared
  `LiteralInteger` can't be done by mutation (you'd have to replace the node);
  it raises with a hint to declare the default as a rational. This is a
  consequence of the mutate-not-replace rule, not a policy choice.
- **`Membership.member_element` has no setter** — you cannot retarget a
  membership (e.g. re-point a unit reference).

______________________________________________________________________

## 6. Adding & removing nodes

### Creating

There are **no element constructors**. You create a node by appending a
`(relationship_type, element_type)` pair to a container; syside allocates both.

```python
# sysml/editing.py — create a FeatureValue holding a fresh literal
new_rel, lit = attr.children.append(syside.FeatureValue, literal_class(value))
lit.value = value

# create a usage-local attribute, then name it
_membership, local = attr.children.append(
    syside.OwningMembership, syside.AttributeUsage
)
local.declared_name = field_name           # see the name= caveat below
```

- **`children` is a `NamespaceBody`.** Its full surface:
  `append`, `insert`, `at`, `pop`, `clear`, `extract`, `extract_element`,
  `extract_with_relationship`, `remove_element`, `remove_relationship`,
  `replace`, `relationships`, `elements`, `reserve`.
- **`append(rel_type, element_type)`** returns `(rel, element)` and lets syside
  allocate the element from the type — the form the codebase uses. A second
  overload takes an element *instance* plus `name: NameID`, but **`NameID` is
  an enum, not an arbitrary identifier**: `append(…, name="foo")` raises
  `TypeError`. To give a created node a plain string name, set
  **`element.declared_name`** afterward.
- **Created nodes are real AST** that sema processes (implied relationships
  appear after a pipeline re-run), and they are visible through
  `owned_relationships` / `owned_members` — but **not** through the CST
  accessors (`feature_value_expression`, `owned_features`). This asymmetry is
  the recurring trap; see [§1](#1-conventions-you-must-internalize).

### Removing

The project does not currently remove nodes, so the removal surface is
**not yet exercised here.** Known facts (syside 0.8.6, not re-verified):
`children.remove_relationship` returns `False` for *parsed* relationships —
they live outside the editable container. `NamespaceBody` also exposes
`extract*`, `remove_element`, `pop`, `replace`; their behavior on parsed vs
created nodes should be verified before relying on it.

### Modification constraints (from the Model Structure docs)

A modification raises if it would violate:

1. **Single ownership** → `ValueError`.
1. **Cross-document move** (an element changing documents) → `ValueError`.
1. **Type constraints** (wrong element type for the relationship) → `TypeError`.
1. **Parent must stay in the model** → `RuntimeError`.

### Evaluation is read-only

`Compiler.evaluate` runs on a read-only model and **cannot construct
elements**. The unit-scale trick in `editing.py:234` works because it
*temporarily mutates an existing literal* and restores it — it never creates a
node during evaluation.

______________________________________________________________________

## 7. Revalidating after edits

In-memory edits don't re-run sema on their own. The recipe
(`sysml/editing.py:283` `revalidate`):

```python
documents = list(model.user_docs)
for mutex in documents:
    with mutex.lock() as document:                 # docs are mutex-guarded
        syside.sema_reset(document)                # also resets resolved refs
        document.build_state = syside.BuildState.Parsed   # keep the parse

pipeline = syside.make_pipeline(
    syside.PipelineOptions(static_index=model.index, lib=model.lib)
)
options = syside.ScheduleOptions(
    syside.ValidationTiming.OnType, force_revalidation=True
)
result = syside.Executor().run(pipeline.schedule(documents, options))

for results in result.diagnostics:                 # per-document
    results.parser / results.sema / results.validation   # diagnostic stages
```

Caveats:

- **`build_state` choice.** `BuildState.Parsed` keeps the parse so in-memory
  AST edits survive — use it after editing the AST. Use `BuildState.Changed`
  only when the *source text* changed (forces a reparse, discarding AST edits).
  `BuildState` values: `Parsed`, `Indexed`, `Built`, `Validated`, `Changed`,
  `none`.
- **`sema_reset` is required.** Elements with `sema_state != SemaState.none`
  are skipped on re-run; resetting the document also reverts resolved
  references to placeholders.
- **`Executor.run` consumes the schedule.** Touching the schedule afterward
  raises `RuntimeError`.
- **syside validates value *types*, not unit *kinds*.** `String !conform Real`
  is caught; `3 [m]` in a `DurationValue` loads clean. That's why the project
  keeps its own unit-kind probe (`quantities.py`).

______________________________________________________________________

## 8. Audit: current usage vs recommended API

Every row checked against syside 0.8.6. Priority reflects correctness risk
*for this codebase today*, not abstract tidiness.

| #   | Area                                | Current pattern (file:line)                                                                             | Recommended                                                                                    | Priority     | Notes                                                                                                                                                                                                                   |
| --- | ----------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `isinstance` completeness           | `actions.py:31`, `visitor.py:128` use `isinstance(x, syside.ActionUsage)`                               | `…, syside.ActionUsage.STD` **or** a comment that excluding `FlowUsage` is intentional         | **Med**      | `ActionUsage.STD == (ActionUsage, FlowUsage)`; current check silently skips flow usages. Decide if that's wanted.                                                                                                       |
| 2   | `isinstance` completeness           | `visitor.py:124` `isinstance(x, syside.PartUsage)`                                                      | `…PartUsage.STD` or documented exclusion                                                       | Low          | `PartUsage.STD` adds `ConnectionUsage`; relevant once connections appear.                                                                                                                                               |
| 3   | `isinstance` completeness           | `constraints.py:24` `isinstance(m, syside.AssertConstraintUsage)`                                       | `…AssertConstraintUsage.STD` or documented exclusion                                           | Low          | `.STD` adds `SatisfyRequirementUsage`. Harmless today (no requirements), latent later.                                                                                                                                  |
| 4   | `isinstance` (all other sites)      | `AttributeUsage`, `StateDefinition`, `OperatorExpression`, literals, `MetadataUsage`, …                 | **no change**                                                                                  | —            | Their `.STD` is single-element; plain `isinstance` already matches the spec. Listed so nobody churns them.                                                                                                              |
| 5   | Type narrowing                      | `assert isinstance(...)` on syside nodes at `editing.py:85,205,239`, `quantities.py:107`                | `node.cast(*types)` / `try_cast`                                                               | Low          | `cast` raises a typed error and returns the narrowed node; `assert` is stripped under `python -O`. (`interface.py:83` asserts a *project* type — not applicable.)                                                       |
| 6   | Node naming                         | `editing.py:179-182` `append(OwningMembership, AttributeUsage)` then `local.declared_name = field_name` | **keep**                                                                                       | —            | `append`'s `name=` takes a `NameID` **enum**, not a string, and only on the instance overload; setting `declared_name` is the correct way to name a created node. Verified: `append(…, name="str")` raises `TypeError`. |
| 7   | Reading created values              | `queries.py:155` falls back to `feature_value_expression`                                               | **keep** (read owned `FeatureValue` first)                                                     | — (upstream) | CST accessor is blind to created nodes; the relationship-first read is the correct workaround. **Candidate upstream issue** — track for a syside fix.                                                                   |
| 8   | `owned_features` vs `owned_members` | split across `actions.py:27`/`states.py:66` (features) and `attributes.py:55`/editing (members)         | **keep**; documented in [§4](#4-reading--querying)                                             | —            | Correct as-is: features = sema-derived/CST (blind to edits), members = authoritative. Don't "unify" them.                                                                                                               |
| 9   | Operator compare                    | `quantities.py:124` `operator is not syside.Operator.Quantity`                                          | **keep**                                                                                       | —            | Confirmed correct: `operator` is an enum; `is` is right, `==`/string compare is wrong.                                                                                                                                  |
| 10  | Removal API                         | none (project never removes nodes)                                                                      | when needed, prefer `NamespaceBody.extract*/remove_*`; verify parsed-vs-created behavior first | Info         | `remove_relationship` returns `False` for parsed rels. Pre-work for parts/ports support.                                                                                                                                |

**Net:** the editing core is sound. The one finding with real bite is **#1**
(`ActionUsage` excluding `FlowUsage`) — decide whether that exclusion is
intentional and either adopt `.STD` or pin the decision with a comment.
Everything else is low-risk tidy-up or "keep, it's correct" confirmations.

______________________________________________________________________

## 9. Gotchas — hard-won facts (status vs 0.8.6)

| Fact                                                                                                                                                                     | Status                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------- |
| `expr.operator` is an enum (`syside.Operator.Quantity`); compare with `is`                                                                                               | verified                    |
| Literal nodes have `.value` setters; `feature_value_expression` does not, and elements have **no constructors**                                                          | verified                    |
| `children.append(Rel, Node)` creates AST sema processes; visible via `owned_relationships`/`owned_members`, **invisible** to `feature_value_expression`/`owned_features` | verified                    |
| `NamespaceBody.append` `name=` is a `NameID` **enum** (not a string); set `declared_name` to name a created node                                                         | verified                    |
| `children.remove_relationship` returns `False` for parsed relationships                                                                                                  | unverified                  |
| `Membership.member_element` has no setter                                                                                                                                | unverified                  |
| syside validates value types but **not** unit kinds                                                                                                                      | verified                    |
| `node.cst_node.start_byte/end_byte` are file byte spans; `.text()` needs the doc text; `document.url` is `file:<path>`                                                   | unverified                  |
| `AssertConstraintUsage ⊂ ConstraintUsage`; body via `.result_expression`                                                                                                 | unverified                  |
| A generated `<Name>.lf` cannot be lfc-compiled standalone (main-reactor name clash)                                                                                      | unverified (LF, not syside) |

"verified" = re-checked against the `.venv` install on 0.8.6;
"unverified" = recorded on an earlier syside build on this line, not re-run
against 0.8.6.

______________________________________________________________________

## 10. Element-kind catalog (state machines + parts)

The kinds the project may touch, beyond the ~30 it uses today — to front-load
the parts/ports/connections surface and the remaining state-machine surface.

**How this catalog was built.** The class list, base classes, `.STD`
tuples, and accessor *names* were introspected from syside 0.8.6 (175 `Element`
subclasses total; the relevant subset is below). The highest-traffic
state-machine accessors (`StateDefinition.is_parallel/entry_action/states`,
`TransitionUsage.source/target/guard_expressions/trigger_actions/effect_actions`,
`PartDefinition.owned_parts`) were also exercised on the `microwave` model and
returned real data. Accessor names not on that list are verified to *exist*,
not individually exercised.

Each table lists a kind's **immediate base** and its **distinctive**
accessors — the ones it adds on top of the inherited foundation. Read §10.1
first; most of what any kind can do is inherited from there.

### 10.1 Foundation accessors (inherited by nearly everything)

| Base             | Key accessors                                                                                                                                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **`Element`**    | identity: `name`, `qualified_name`, `short_name`, `declared_name`, `path`, `element_id`; navigation: `owner`, `owning_namespace`, `owning_membership`, `owned_relationships`; annotations: `metadata`, `comments`, `documentation`; `matches_qualified_name()`, `is_library_element` |
| **`Namespace`**  | `children` (the editable `NamespaceBody` — §6), `owned_members`, `owned_memberships`, `members`, `memberships`, `get_member()`, `get_membership()`, `owned_imports`                                                                                                                  |
| **`Type`**       | `heritage` (specializations), `type_relationships`, `specializes()`, `conforms()`, `features`, `owned_features`, `inherited_features`, `feature_memberships`, `is_abstract`, `multiplicity`, `inputs`, `outputs`, `end_features`                                                     |
| **`Feature`**    | `direction`, `feature_value`, `feature_value_expression` (CST-blind — §1), `types`, `owned_typings`, `owned_subsettings`, `owned_redefinitions`, `chaining_features`, `is_composite`, `is_read_only`, `is_derived`                                                                   |
| **`Definition`** | the `owned_<kind>` family: `owned_attributes`, `owned_parts`, `owned_ports`, `owned_actions`, `owned_states`, `owned_transitions`, `owned_connections`, `owned_constraints`, `owned_usages`, …; `is_variation`, `variants`                                                           |
| **`Usage`**      | `definitions`; the `nested_<kind>` family: `nested_attributes`, `nested_parts`, `nested_ports`, `nested_states`, `nested_actions`, …; `is_reference`, `is_variation`, `owning_definition`                                                                                            |

`Definition` exposes its members as `owned_<kind>`; the matching `Usage`
exposes them as `nested_<kind>` — the split `scope_attributes` relies on.

### 10.2 Relationships

| Kind                                              | Base                      | Distinctive accessors                                                                       |
| ------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------- |
| `Membership`                                      | `Relationship`            | `member_element`, `member_name`, `membership_owning_namespace` (no `member_element` setter) |
| `OwningMembership`                                | `Membership`              | `owned_member_element`, `owned_member_name`                                                 |
| `FeatureMembership`                               | `OwningMembership`        | `owned_member_feature`, `owning_type`                                                       |
| `FeatureValue`                                    | `OwningMembership`        | `value`, `is_default`, `is_initial`, `feature_with_value`                                   |
| `FeatureTyping`                                   | `Specialization`          | `type`, `typed_feature`                                                                     |
| `Specialization`                                  | `Relationship`            | `general`, `specific`, `owning_type`                                                        |
| `Subsetting`                                      | `Specialization`          | `subsetted_feature`, `subsetting_feature`                                                   |
| `Redefinition`                                    | `Subsetting`              | `redefined_feature`, `redefining_feature`                                                   |
| `ReferenceSubsetting`                             | `Subsetting`              | `referenced_feature`, `referencing_feature`                                                 |
| `FeatureChaining`                                 | `Relationship`            | `chaining_feature`, `feature_chained`                                                       |
| `Import` / `MembershipImport` / `NamespaceImport` | `Relationship` / `Import` | `imported_element`, `is_recursive`; `imported_membership`; `imported_namespace`             |

### 10.3 State machine

| Kind                          | Base                | Distinctive accessors                                                                                                                   |
| ----------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `StateDefinition`             | `ActionDefinition`  | `entry_action`, `do_action`, `exit_action`, `is_parallel`, `states`                                                                     |
| `StateUsage`                  | `ActionUsage`       | `entry_action`, `do_action`, `exit_action`, `is_parallel`, `state_definitions`                                                          |
| `ExhibitStateUsage`           | `StateUsage`        | `exhibited_state`, `event_occurrence`, `performed_action`                                                                               |
| `TransitionUsage`             | `ActionUsage`       | `source`, `target`, `guard_expressions`, `trigger_actions`, `effect_actions`, `payload`, `succession` (each also has a `…_member` form) |
| `SuccessionAsUsage`           | `ConnectorAsUsage`  | `guard_expression`, `trigger_steps`, `effect_steps`, `transition_step`                                                                  |
| `StateSubactionMembership`    | `FeatureMembership` | `action`, `kind` (entry/do/exit)                                                                                                        |
| `TransitionFeatureMembership` | `FeatureMembership` | `transition_feature`, `kind` (trigger/guard/effect)                                                                                     |

### 10.4 Actions

| Kind                                                              | Base                              | Distinctive accessors                                                                                            |
| ----------------------------------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `ActionDefinition`                                                | `OccurrenceDefinition`            | `actions`, `parameters`, `steps`                                                                                 |
| `ActionUsage` ⚠️`.STD`                                            | `OccurrenceUsage`                 | `action_definitions`, `parameters`, `owned_parameters` — `.STD`=(`ActionUsage`,`FlowUsage`)                      |
| `AcceptActionUsage`                                               | `ActionUsage`                     | `payload_argument`, `payload_parameter`, `receiver_argument`, `receiver_parameter`                               |
| `SendActionUsage`                                                 | `ActionUsage`                     | `payload_argument`, `receiver_argument`, `sender_argument` (+ `…_parameter`)                                     |
| `AssignmentActionUsage`                                           | `ActionUsage`                     | `referent`, `target_argument`, `value_expression`                                                                |
| `PerformActionUsage` ⚠️`.STD`                                     | `ActionUsage`                     | `performed_action`, `event_occurrence` — `.STD`=(`PerformActionUsage`,`ExhibitStateUsage`,`IncludeUseCaseUsage`) |
| `TerminateActionUsage`                                            | `ActionUsage`                     | `terminated_occurrence_argument`                                                                                 |
| `IfActionUsage`                                                   | `ActionUsage`                     | `if_argument`, `then_action`, `else_action`                                                                      |
| `LoopActionUsage` / `ForLoopActionUsage` / `WhileLoopActionUsage` | `ActionUsage` / `LoopActionUsage` | `body_action`; `loop_variable`, `seq_argument`; `while_argument`, `until_argument`                               |
| `FlowUsage`                                                       | `ConnectorAsUsage`                | `flow_ends`, `payload_feature`, `payload_types`, `source_output_feature`, `target_input_feature`                 |
| `TriggerInvocationExpression`                                     | `InvocationExpression`            | `kind` (`syside.TriggerKind.After/At/When`)                                                                      |

### 10.5 Parts / ports / connections

| Kind                                     | Base                                       | Distinctive accessors                                                                                          |
| ---------------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `PartDefinition`                         | `ItemDefinition`                           | (foundation only — use `owned_parts`/`owned_ports`/`owned_connections`)                                        |
| `PartUsage` ⚠️`.STD`                     | `ItemUsage`                                | `part_definitions` — `.STD`=(`PartUsage`,`ConnectionUsage`)                                                    |
| `PortDefinition`                         | `OccurrenceDefinition`                     | `conjugated_port_definition`                                                                                   |
| `PortUsage`                              | `OccurrenceUsage`                          | `port_definitions`                                                                                             |
| `ConjugatedPortDefinition`               | `PortDefinition`                           | `original_port_definition`, `owned_port_conjugator`                                                            |
| `ConnectionDefinition`                   | `PartDefinition`                           | `connection_ends`, `source`, `targets`, `related_elements`                                                     |
| `ConnectionUsage`                        | `ConnectorAsUsage`                         | `connection_definitions`, `part_definitions`, `item_definitions`                                               |
| `ConnectorAsUsage`                       | `Usage`                                    | `connector_ends`, **`declared_ends`** (has `try_append`/`try_insert`), `source`, `targets`, `related_features` |
| `Connector` ⚠️`.STD`                     | `Feature`                                  | same connector surface — `.STD`=(`Connector`,`ConnectorAsUsage`)                                               |
| `BindingConnector(AsUsage)` ⚠️`.STD`     | `Connector`/`ConnectorAsUsage`             | binds two features equal — `.STD`=(`BindingConnector`,`BindingConnectorAsUsage`)                               |
| `InterfaceDefinition` / `InterfaceUsage` | `ConnectionDefinition` / `ConnectionUsage` | `interface_ends`; `interface_definitions`                                                                      |
| `ItemUsage` ⚠️`.STD`                     | `OccurrenceUsage`                          | `item_definitions` — `.STD`=(`ItemUsage`,`ConnectionUsage`)                                                    |
| `ReferenceUsage`                         | `Usage`                                    | (foundation only)                                                                                              |

> **`declared_ends` is the connection-building entry point** — the Model
> Structure docs single it out as supporting `try_append()` / `try_insert()`,
> unlike the general `NamespaceBody`. Verify behavior on parsed vs created ends
> before relying on it (the §6 removal caveat applies).

### 10.6 Attributes / values / expressions

| Kind                                          | Base                                           | Distinctive accessors                                                                                                              |
| --------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `AttributeDefinition`                         | `Definition`                                   | (foundation; `owned_attributes` for fields)                                                                                        |
| `AttributeUsage`                              | `Usage`                                        | `attribute_definitions`                                                                                                            |
| `DataType` ⚠️`.STD`                           | `Classifier`                                   | `.STD`=(`DataType`,`AttributeDefinition`)                                                                                          |
| `EnumerationDefinition` / `EnumerationUsage`  | `AttributeDefinition` / `AttributeUsage`       | `enumerated_values`; `enumeration_definition`                                                                                      |
| `LiteralBoolean/Integer/Rational/String`      | `LiteralExpression`                            | `value` (read **and** write)                                                                                                       |
| `LiteralInfinity`, `NullExpression`           | `LiteralExpression` / `Expression`             | (no `value`)                                                                                                                       |
| `Expression` ⚠️`.STD`                         | `Step`                                         | `result`, `result_expression`, `function`, `is_model_level_evaluable` — `.STD`=(`Expression`,`CalculationUsage`,`ConstraintUsage`) |
| `OperatorExpression`                          | `InvocationExpression`                         | `operator` (enum — compare with `is`), `operands` (via base)                                                                       |
| `InvocationExpression`                        | `InstantiationExpression`                      | `operands`                                                                                                                         |
| `InstantiationExpression`                     | `Expression`                                   | `arguments`, `instantiated_type`                                                                                                   |
| `FeatureReferenceExpression`                  | `Expression`                                   | `referent`                                                                                                                         |
| `FeatureChainExpression`                      | `OperatorExpression`                           | `target_feature`                                                                                                                   |
| `Index/Select/Collect/Constructor Expression` | `OperatorExpression`/`InstantiationExpression` | (operator/argument surface only)                                                                                                   |

### 10.7 Constraints / requirements

| Kind                                         | Base                                       | Distinctive accessors                                                                            |
| -------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `ConstraintDefinition`                       | `OccurrenceDefinition`                     | `expressions`, `result`, `result_expression`, `is_model_level_evaluable`                         |
| `ConstraintUsage`                            | `OccurrenceUsage`                          | `constraint_definition`, `predicate`, `result_expression`                                        |
| `AssertConstraintUsage` ⚠️`.STD`             | `ConstraintUsage`                          | `asserted_constraint`, `is_negated` — `.STD`=(`AssertConstraintUsage`,`SatisfyRequirementUsage`) |
| `RequirementDefinition` / `RequirementUsage` | `ConstraintDefinition` / `ConstraintUsage` | `req_id`, `texts`, `required_constraints`, `assumed_constraints`, `subject_parameter`            |
| `SatisfyRequirementUsage`                    | `RequirementUsage`                         | `satisfied_requirement`, `satisfaction_subject`, `is_negated`                                    |

### 10.8 Metadata / comments

| Kind                       | Base                | Distinctive accessors                                                            |
| -------------------------- | ------------------- | -------------------------------------------------------------------------------- |
| `MetadataDefinition`       | `ItemDefinition`    | (foundation)                                                                     |
| `MetadataUsage`            | `ItemUsage`         | `metadata_definition`, `metaclass`, `about`, `annotated_elements`, `annotations` |
| `MetadataFeature` ⚠️`.STD` | `Feature`           | `metaclass`, `annotated_elements` — `.STD`=(`MetadataFeature`,`MetadataUsage`)   |
| `Comment`                  | `AnnotatingElement` | `body`, `locale`                                                                 |
| `Documentation`            | `Comment`           | `documented_element`                                                             |

### 10.9 Every multi-type `.STD` in this catalog

Use `isinstance(x, syside.Cls.STD)` (or accept the narrowing) for these — plain
`isinstance(x, syside.Cls)` is narrower than the spec:

```
ActionUsage          = (ActionUsage, FlowUsage)
PerformActionUsage   = (PerformActionUsage, ExhibitStateUsage, IncludeUseCaseUsage)
PartUsage            = (PartUsage, ConnectionUsage)
ItemUsage            = (ItemUsage, ConnectionUsage)
DataType             = (DataType, AttributeDefinition)
Expression           = (Expression, CalculationUsage, ConstraintUsage)
Connector            = (Connector, ConnectorAsUsage)
BindingConnector     = (BindingConnector, BindingConnectorAsUsage)
AssertConstraintUsage= (AssertConstraintUsage, SatisfyRequirementUsage)
MetadataFeature      = (MetadataFeature, MetadataUsage)
```

Every other kind in this catalog has a single-element `.STD`, so plain
`isinstance` already matches the spec.
