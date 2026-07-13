# statix mapping: SysML → C

`statix` compiles SysML v2 state definitions into a self-contained,
static-memory, [*Power of 10*](statix/power_of_10_compliance.md)-compliant C
project: one generated `.h`/`.c` unit per statechart, generated
guard/action/context code, a shared dispatch template, and a bundled runtime
kernel. This page documents, construct by construct, how a SysML state
definition maps to C — and what is rejected.

It mirrors [`quake-mapping.md`](quake-mapping.md) (→ Sismic) and
[`rosetta-mapping.md`](rosetta-mapping.md) (→ Lingua Franca). Where those target
simulation, statix targets **deployment**: the C is meant to cross-compile to a
microcontroller.

```bash
sysmlc statix build models/sm-examples/sm01-helloworld -e SM01::Machine -o out/
# out/ is a self-contained C project:
cmake -S out -B out/build && cmake --build out/build
```

Omit `-e` to build every `state def` in the model into one project:

```bash
sysmlc statix build models/sm-examples/sm01-helloworld -o out/
```

## 1. The big picture

A `state def` becomes one generated C unit with a stable file layout, where
`<prefix>` is the state def's qualified name sanitized to C identifier form
(`SM01::Machine` → `sm01_machine`). A whole-model build emits one such unit per
state definition.

| File                        | Contents                                                                                                   |
| --------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `<prefix>.h`                | public API, state/event/guard/action ids, context type, instance type                                      |
| `<prefix>.c`                | static tables, static guard/action switches, `context_init`, name helpers, dispatch-template instantiation |
| `<prefix>_runner.c`         | host-only smoke runner (`stdio`, argv events, state trace)                                                 |
| `include/sc/sc_machine.h`   | shared dispatch template instantiated per statechart                                                       |
| `include/sc/*.h`, `src/*.c` | bundled machine-agnostic runtime support                                                                   |
| `CMakeLists.txt`            | builds the runtime, generated statechart library, and runners                                              |

Generation is **deterministic**: the same model yields byte-identical C.

The public API is fully prefixed and safe to link with other generated
statecharts:

```c
void <prefix>_context_init(<prefix>_context_t *ctx);
sc_status_t <prefix>_init(<prefix>_t *sm, <prefix>_context_t *ctx);
sc_status_t <prefix>_dispatch(<prefix>_t *sm, const sc_event_t *event);
sc_status_t <prefix>_post(<prefix>_t *sm, sc_event_id_t event_id);
sc_state_id_t <prefix>_get_state(const <prefix>_t *sm);
const char *<prefix>_state_name(sc_state_id_t state);
const char *<prefix>_event_name(sc_event_id_t event);
```

## 2. States

Every leaf state becomes an `enum` constant (`<PREFIX>_STATE_<NAME>`), numbered
from 0 in declaration order. `<PREFIX>_STATE_COUNT` gives the total.

Each state also gets a row in the per-state table `sc_state_def_t[]`, holding its
entry-action and exit-action ids, `parent`, and `initial_child`. For a composite
state, `initial_child` is set and entered by descent; nested names are
root-relative dotted paths. Parallel or history states remain rejected (see §9).

## 3. Initial state and completion (eventless) transitions

`entry; then idle` selects `idle` as the initial state; it becomes the
`sc_machine_t.initial_state`. On `<prefix>_init`, the generated dispatch
instantiation enters it, runs its entry action, then settles completion
transitions.

A transition with **no trigger** (`transition first idle then running`) is an
eventless / *completion* transition. It carries the reserved
`SC_EVENT_COMPLETION` event id in the transition table. After init and after
every dispatch, the runtime fires enabled completion transitions in a **bounded
micro-step**:

- the bound is the generated `SC_MAX_RTC_STEPS`;
- a guarded eventless cycle (a modeling error) is surfaced as
  `SC_STATUS_STEP_LIMIT`, never an infinite loop.

This is what lets flat machines like sm01 (`idle → running` on completion) reach
their settled state without an external event.

A completion target (`then done`) synthesizes an absorbing leaf final state per
scope (named `done` at root, `<scope>::done` for nested scopes). Entering a final
state marks the machine (or enclosing composite) complete.
`<prefix>_is_final(const <prefix>_t *sm)` reports whether the machine has
*terminated* — that is, the active leaf is a root-scope final state.

## 3a. Internal event queue and self-sends (RTC)

When a machine includes a self-send (`send new E()` or `do send new E()`), statix generates an internal FIFO event queue (`sc_event_queue_t queue` with storage `sc_event_t queue_storage[8]`) inside `<prefix>_t`, and sets `#define SC_MACHINE_HAS_QUEUE 1` before including `sc/sc_machine.h`. The queue capacity defaults to 8 (`<PREFIX>_QUEUE_CAPACITY`). During `<prefix>_init`, `<prefix>_dispatch`, and `<prefix>_post`, an internal drain loop (`_drain_internal`) automatically dequeues and dispatches internal events until the queue is empty or the RTC step limit is reached. If an action enqueues an event when the queue is full, `sc_runtime_enqueue` returns `SC_STATUS_QUEUE_FULL` (drop-when-full semantics).

## 4. Triggers and signals

`accept E [via port]` is a **signal trigger**: `E` becomes an `enum` event id
(`<PREFIX>_EVENT_E`, numbered from 1), and the transition matches that id in
`<prefix>_dispatch` / `<prefix>_post`. A named binding (`accept reading : E`) may read the event's single
marshalled Real value — either directly (`reading.value`) or one composite
hop deep (`reading.sample.value`) — in the transition's guard and effect;
deeper chains, whole-payload capture, and non-Real payload data remain
rejected (§9).

`after` / `at` triggers are supported (§4a); `when` (change) triggers are
supported too (§4b).

## 4a. Time triggers (`after`/`at`)

`accept after <duration>` and `accept at <instant>` compile to a **latch**,
not a scheduled event: a generated static `timeout_due(state, runtime)`
function (hooked in via `#define SC_MACHINE_TIMEOUT_DUE timeout_due`,
following the exact `guard_eval`/`action_exec` convention) recomputes the
due-condition against `sc_runtime_t.now`/`state_entered_at` on every call to
the new public `<prefix>_tick(sm, now)`. `after` is due once `now - entered_at >= duration`; `at` is due once `entered_at <= instant && now >= instant` (entering exactly at the instant still fires, as a zero-delay
occurrence). A `bool timeout_delivered` latch, set *before* any `if` guard
on the transition is evaluated, ensures the occurrence is checked **at most
once per state activation** — a false guard permanently consumes it for
that activation, exactly like an ordinary transition guard.

A literal duration/instant (`5 [s]`) folds to a compile-time tick constant
(`5u * SC_TICKS_PER_SECOND`); an attribute-driven one (`after pickDuration`,
`at deadline`) is converted at runtime via `sc_seconds_to_ticks`, which
rejects a negative or out-of-range value by making that occurrence
permanently non-due, never an unsafe cast or a silent wraparound.
`SC_TICKS_PER_SECOND` (default `1000u`) is a project-wide compile-time
constant in `sc_runtime.h`, like `SC_MAX_TRANSITIONS` — override with
`-DSC_TICKS_PER_SECOND=N`, the same mechanism, not a per-machine generated
value.

Only a **leaf** state may source an `after`/`at` transition, and at most one
per leaf; both are rejected at build time (§9). Host contract: `_dispatch`/
`_post` do not take a tick value, so `state_entered_at` reflects only the
last `_tick` call — call `_tick(sm, now)` with a current value immediately
before dispatching any event that might enter a timed state, whenever
timing precision matters. `sc_time_t` (`uint32_t`) wraps after ~49.7 days at
the default resolution; `_tick` rejects a non-monotonic value loudly
(`SC_STATUS_INVALID_ARGUMENT`) rather than silently corrupting state, so a
long-running host must rebase its tick counter and re-`_init` before wrap.

**Overriding `-DSC_TICKS_PER_SECOND`:** a literal duration/instant's build-time
range check validates against the *default* (`1000`), then emits a symbolic C
expression (`5u * SC_TICKS_PER_SECOND`) folded by the compiler at whatever
resolution the project is actually compiled with — for zero runtime cost. A
literal that was in-range at the default stays representable for any *larger*
override; a project compiling with a *smaller* `SC_TICKS_PER_SECOND` (or that
otherwise needs literals beyond ~4294967.295 default-resolution seconds) must
re-validate its own model, since the generated multiplication is unsigned and
wraps silently in C rather than failing at compile time. Same override
contract as `SC_MAX_TRANSITIONS` et al., stated loudly here because a silent
wrap in a due-condition is a correctness bug, not just a dropped event.

## 4b. Change triggers (`when`)

`accept when <condition> [if <guard>]` compiles to an ordinary eventless
(`SC_EVENT_COMPLETION`) transition guarded by a per-transition **armed bit**
(`runtime->when_armed[i]`, a project-wide `bool [SC_MAX_WHEN_TRIGGERS]` array,
default size `64`) conjoined with the watched condition and any user `if`.
Each source state's entry action sets its own transitions' armed bits `true`
*after* any user entry/`do` statements ("armed last", matching quake's own
convention) — one observation is armed per activation.

A guarded `when` (`if <guard>` present) emits a second, **internal**
transition alongside the real one: guard `armed && (condition) && !(guard)`, action `armed = false`, no target. The two guards are genuine
partitions of `condition` (split on `guard`/`!guard`), so table order
between them never matters. Internal transitions reuse `SC_STATE_INVALID`
as the target sentinel — `_take_transition` runs the action (if any) and
returns without exit/entry/`current_state` change, so a false guard at
delivery disarms the observation without re-running `on entry` (which would
re-arm it and undo the disarm in the same step).

A bare `when` (no `if`) needs no consumer: the real guard alone fully
disposes of the observation once taken.

Hosts must call the new `<prefix>_settle(sm)` after mutating context state
that a `when` condition reads, whenever no event dispatch already covers it
— an ordinary `_dispatch`/`_post` already runs the same completion
machinery internally. `_settle` mirrors `_init`'s tail exactly (no
"matched event" to compare against, so no `SC_STATUS_NO_TRANSITION`
branch): `_run_completion` → `_drain_internal` → `_check_invariants`.

Two `when` triggers on one source (armed simultaneously true) resolve by
**declaration order** — statix does not replicate quake/Sismic's
`NonDeterminismError`; this is a deliberate divergence, not a gap. A `when`
self-loop, and `when` sourced from a composite (non-leaf) state, are both
rejected at build time (§9) — composite sourcing is not rejected because
the mechanism requires it (the armed-bit array is per-transition, not a
single leaf-scoped scalar like `after`/`at`'s `state_entered_at`), but
because nothing in the corpus exercises it yet.

The generated `<prefix>.c` emits a compile-time bound check right after
includes, when the machine has any `when` trigger:

```c
#if SC_MAX_WHEN_TRIGGERS < 2u
#error "SC_MAX_WHEN_TRIGGERS too small for this generated machine"
#endif
```

so a `-DSC_MAX_WHEN_TRIGGERS` override smaller than a specific machine's own
count fails to compile rather than indexing `when_armed[]` out of bounds.

## 5. Guards

A transition guard (`if <expr>`) becomes a `<PREFIX>_GUARD_*` id whose body is
the **lowered C boolean expression**, returned from the generated static
`<prefix>_guard_eval`. Supported expression forms:

| SysML                    | C                           |
| ------------------------ | --------------------------- |
| `true` / `false`         | `true` / `false`            |
| integer / real literal   | `0`, `1.0`, …               |
| attribute reference `x`  | `ctx->x`                    |
| chained reference `pt.x` | `ctx->pt.x`                 |
| `not a`, `-x`            | `!a`, `-x`                  |
| `a and b`, `a or b`      | `a && b`, \`a               |
| `== != < <= > >=`        | same                        |
| `+ - * /`                | same (precedence preserved) |

A reference to anything that is not a machine attribute is rejected at
generation (loud), not silently mis-rendered.

## 6. Actions (entry / exit / transition effects)

State entry/exit actions and transition effects become `<PREFIX>_ACTION_*` ids
whose bodies are lowered C statements in the generated static
`<prefix>_action_exec`. Only `assign` is supported for general statements; each
`assign target := expr` becomes
`ctx->target = <expr>;`. A state's inline `do` activity runs **once** at
entry — its statements are appended after the entry action's, in
declaration order. Self-send statements (`send new E()`) and `do send new E()` are supported for internal events without payloads; each renders as `sc_runtime_enqueue(runtime, <EVENT_ID>);` after any assignment statements. External sends and payload-carrying sends remain rejected. Firing order follows the Sismic/SCXML reference:
`exit(source) → transition effect → entry(target)`.

## 6a. Asserted constraints (invariants)

An `assert constraint { <expr> }` becomes an invariant: a guard (the lowered C
boolean, reusing the `guard_eval` mechanism) plus a row in the generated
`sc_invariant_t[]` table pairing a **scope** with that guard. A root constraint
uses `SC_STATE_INVALID` (always active); a state-scoped constraint uses its owning
state id. `assert not constraint` wraps the expression as `!( <expr> )`.

After `<prefix>_init` and every `<prefix>_dispatch` settle (run-to-completion
done), the runtime evaluates the invariants whose scope is active — root always,
state-scoped only while the owning state is on the active configuration's ancestor
chain. The first false active invariant makes the call return
`SC_STATUS_CONSTRAINT_VIOLATED` (matching Sismic's `InvariantError` at the
macro-step boundary, including on a no-transition dispatch). Constraints whose
expression contains a function call are rejected (§9).

## 6b. Library function calls

Allowlisted `NumericalFunctions::abs/max/min` → `fabs`/`fmax`/`fmin` and `TrigFunctions::sin/cos/tan` → `sin`/`cos`/`tan`, all double-typed via `<math.h>` (linked with `-lm` when used). Real-only — a library result assigned to a non-Real attribute is rejected; external calc-defs and non-allowlist functions are rejected.

## 6c. Self-sends and payload marshalling

When a machine *reads* an event's payload, every `send` of that event must
marshal it: the constructor's single Real argument is copied into the event's
inline byte buffer (`sc_runtime_enqueue_f64`) and read back as
`sc_event_payload_f64(event)` in the accepting transition's guard/effect — a
scalar Real payload slot over the existing event buffer, same machine on both
ends. Sends of events whose payload is never read stay id-only with their
constructor arguments dropped, exactly as before. A read event with no
marshalling send, a send with the wrong argument shape, or a non-Real
argument is rejected loudly. `_post` and the host runner remain id-only:
payload-bearing events exist only as internal self-sends.

The readable path may also be **one composite hop deep**
(`reading.sample.value`, where `sample` is itself a composite machine
attribute): the marshalling `send` must pass that same composite attribute
as a bare argument (`send new Measurement(current, sample) to commPort`),
and the nested field it resolves to must be Real — checked mechanically
against the generated struct's own field types, not inferred. A chain three
or more segments deep (`reading.a.b.c`), or resolving to a non-Real field, is
rejected.

## 7. Attributes and the context struct

Machine attributes become fields of the generated `<prefix>_context_t`, passed
to `<prefix>_init` and then stored as runtime `user_data`. Guards and actions
cast it once and read/write `ctx->field`. `<prefix>_context_init` seeds model
defaults before initialization.

- **scalar** attributes → a struct field with the mapped C type (§8);
- **composite attribute defs** (a structured `attribute def`) → a generated
  nested `struct`, emitted innermost-first, with the field initialized from its
  SysML defaults via a C designated initializer.

Attribute initial values are lowered to C initializers (`.counter = 0`,
`.pt = {.x = 0.5}`).

## 8. Type mapping

| SysML                     | C                         |
| ------------------------- | ------------------------- |
| `Boolean`                 | `bool`                    |
| `Integer`                 | `int32_t`                 |
| `Real`                    | `double` *(provisional)*  |
| composite `attribute def` | generated nested `struct` |

**`Real → double` is provisional.** It is the faithful choice for iteration 1,
but many microcontroller targets have no FPU and the runtime is compiled with
`-Wdouble-promotion`. Whether `Real` should map to `double`, `float`, or a
fixed-point type is a genuine per-target decision to revisit — it is not settled.

The C type is inferred from the attribute's literal initializer
(`Boolean`/`Integer`/`Real`), so an attribute needs a default for statix to type
it in iteration 1.

## 9. Rejections

statix **never silently drops** a construct: anything outside the supported flat
subset raises `UnsupportedConstructError` with a clear message. Rejected in
iteration 1:

| Construct                                                      | Status                                                                                                   |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| parallel / history states                                      | rejected (composite/leaf supported)                                                                      |
| `when` sourced from a composite (non-leaf) state               | rejected (mirrors the after/at leaf-only rule, §4b)                                                      |
| `when` self-loop (target equals source)                        | rejected (a conservative guardrail, §4b)                                                                 |
| `after`/`at` sourced from a composite (non-leaf) state         | rejected (state_entered_at needs one unambiguous leaf)                                                   |
| a second `after`/`at` sourced from the same state              | rejected (at most one timer per leaf, §4a)                                                               |
| a literal duration/instant out of the representable tick range | rejected at build time (an out-of-range attribute-driven one is never-due at runtime instead, §4a)       |
| more than 65,533 distinct signal events in one machine         | rejected (the top of the 16-bit event id space is reserved for `SC_EVENT_TIMEOUT`/`SC_EVENT_COMPLETION`) |
| chains 3+ segments deep, whole, or non-Real payload reads      | rejected (2-segment Real chains supported; whole capture is future work)                                 |
| machine-level (state def) entry/do/exit actions                | rejected (put on states)                                                                                 |
| non-inline / referenced `do` activities                        | rejected                                                                                                 |
| `String` / non-scalar, non-composite attributes                | rejected                                                                                                 |
| external / non-allowlist function calls in expressions         | rejected (allowlisted library calls supported)                                                           |

## 10. Forward notes (not settled)

- **Hardware side-effects.** Real firmware actions (GPIO, "turn the LED on") are
  not SysML `assign`s. They belong to the deferred send/external-call family and
  will eventually need external-call lowering (à la rosetta's `--python`
  calc-defs) or a hand-body escape hatch. The generated dispatch is structured
  so such a path can slot in without a rewrite.
- **`Real` representation** — see §8; `double` vs `float` vs fixed-point is a
  target decision, not a settled one.
- **Growth** — parallel, history, and timers are tracked future work for the runtime and the backend.

## 11. Cross-backend conformance

Because statix implements the same run-to-completion semantics as the Sismic
reference (`quake`), a lightweight conformance test drives the flat sm-examples
through both Sismic and the generated statix C and asserts they settle in the
same state. This is a thin slice of the broader cross-backend conformance idea
described in [positioning.md](statix/positioning.md); the full framework is
future work.
