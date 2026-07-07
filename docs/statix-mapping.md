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
`<prefix>_dispatch` / `<prefix>_post`. A named binding (`accept reading : E`) may read the event's **single marshalled Real attribute** (`reading.value`) in the transition's guard and effect; chained reads (`reading.sample.value`), whole-payload capture, and non-Real payload data remain rejected (§9).

`after` / `at` / `when` triggers are rejected (§9).

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

| Construct                                              | Status                                                            |
| ------------------------------------------------------ | ----------------------------------------------------------------- |
| parallel / history states                              | rejected (composite/leaf supported)                               |
| `after` / `at` / `when` triggers                       | rejected (no timers/change events yet)                            |
| chained / whole / non-Real payload reads               | rejected (single Real attribute readable; rest is B.3)            |
| machine-level (state def) entry/do/exit actions        | rejected (put on states)                                          |
| non-inline / referenced `do` activities                | rejected                                                          |
| `String` / non-scalar, non-composite attributes        | rejected                                                          |
| external / non-allowlist function calls in expressions | rejected (allowlisted library calls supported)                    |

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
