# statix mapping: SysML → C

`statix` compiles a **flat** SysML v2 state machine into a self-contained,
static-memory, [*Power of 10*](statix/power_of_10_compliance.md)-compliant C
project: generated tables + generated guard/action/context code + a bundled
runtime kernel. This page documents, construct by construct, how a SysML state
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

## 1. The big picture

A `state def` becomes a generated C project with a stable file layout, where
`<prefix>` is the state def's simple name, lowercased:

| File | Contents |
|------|----------|
| `<prefix>_statechart_ids.h` | `enum`s: state / event / guard / action ids |
| `<prefix>_statechart_config.h` | machine declaration + queue capacity |
| `<prefix>_statechart_config.c` | per-state entry/exit table, transition table, `sc_machine_t` |
| `<prefix>_context.h` | the generated `<prefix>_context_t` (attributes) |
| `<prefix>_actions.c` | generated `sc_guard_eval` / `sc_action_exec` |
| `CMakeLists.txt` | builds the runtime + generated units |
| `include/sc/*.h`, `src/*.c` | the bundled runtime kernel |

Generation is **deterministic**: the same model yields byte-identical C.

## 2. States

Every leaf state becomes an `enum` constant (`<PREFIX>_STATE_<NAME>`), numbered
from 0 in declaration order. `<PREFIX>_STATE_COUNT` gives the total.

Each state also gets a row in the per-state table `sc_state_def_t[]`, holding its
entry-action and exit-action ids (`SC_ACTION_NONE` when absent). The runtime uses
this table to run `exit(source) → effect → entry(target)` on every transition.

**Only flat, leaf states are supported.** A composite or parallel state is
rejected (see §9).

## 3. Initial state and completion (eventless) transitions

`entry; then idle` selects `idle` as the initial state; it becomes the
`sc_machine_t.initial_state`. On `sc_runtime_init`, the runtime enters it, runs
its entry action, then settles completion transitions.

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

## 4. Triggers and signals

`accept E [via port]` is a **signal trigger**: `E` becomes an `enum` event id
(`<PREFIX>_EVENT_E`, numbered from 1), and the transition matches that id in
`sc_runtime_dispatch`. A named binding (`accept reading : E`) is accepted only
when the payload data is never read; **reading payload data** (`reading.value`)
is rejected — it belongs to the deferred send/RTC family (§9).

`after` / `at` / `when` triggers are rejected (§9).

## 5. Guards

A transition guard (`if <expr>`) becomes a `<PREFIX>_GUARD_*` id whose body is
the **lowered C boolean expression**, returned from the generated
`sc_guard_eval`. Supported expression forms:

| SysML | C |
|-------|---|
| `true` / `false` | `true` / `false` |
| integer / real literal | `0`, `1.0`, … |
| attribute reference `x` | `ctx->x` |
| chained reference `pt.x` | `ctx->pt.x` |
| `not a`, `-x` | `!a`, `-x` |
| `a and b`, `a or b` | `a && b`, `a || b` |
| `== != < <= > >=` | same |
| `+ - * /` | same (precedence preserved) |

A reference to anything that is not a machine attribute is rejected at
generation (loud), not silently mis-rendered.

## 6. Actions (entry / exit / transition effects)

State entry/exit actions and transition effects become `<PREFIX>_ACTION_*` ids
whose bodies are lowered C statements in the generated `sc_action_exec`. Only
`assign` is supported today; each `assign target := expr` becomes
`ctx->target = <expr>;`. Firing order follows the Sismic/SCXML reference:
`exit(source) → transition effect → entry(target)`.

`send` effects are rejected (§9).

## 7. Attributes and the context struct

Machine attributes become fields of the generated `<prefix>_context_t`, passed
to the runtime as `user_data`. Guards and actions cast it once and read/write
`ctx->field`.

- **scalar** attributes → a struct field with the mapped C type (§8);
- **composite attribute defs** (a structured `attribute def`) → a generated
  nested `struct`, emitted innermost-first, with the field initialized from its
  SysML defaults via a C designated initializer.

Attribute initial values are lowered to C initializers (`.counter = 0`,
`.pt = {.x = 0.5}`).

## 8. Type mapping

| SysML | C |
|-------|---|
| `Boolean` | `bool` |
| `Integer` | `int32_t` |
| `Real` | `double` *(provisional)* |
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

| Construct | Status |
|-----------|--------|
| composite / parallel / history states, deep entry | rejected (flat only) |
| `after` / `at` / `when` triggers | rejected (no timers/change events yet) |
| `send` effects, reading `accept` payload data | rejected (send/RTC family) |
| `then done` completion targets | rejected (no final-state model yet) |
| machine-level (state def) entry/do/exit actions | rejected (put on states) |
| non-inline / referenced `do` activities | rejected |
| asserted constraints | rejected |
| `String` / non-scalar, non-composite attributes | rejected |
| external / library function calls in expressions | rejected |

## 10. Forward notes (not settled)

- **Hardware side-effects.** Real firmware actions (GPIO, "turn the LED on") are
  not SysML `assign`s. They belong to the deferred send/external-call family and
  will eventually need external-call lowering (à la rosetta's `--python`
  calc-defs) or a hand-body escape hatch. The generated dispatch is structured
  so such a path can slot in without a rewrite.
- **`Real` representation** — see §8; `double` vs `float` vs fixed-point is a
  target decision, not a settled one.
- **Growth** — hierarchy, parallel, history, timers, and send→accept
  internal-event RTC are tracked future work for the runtime and the backend.

## 11. Cross-backend conformance

Because statix implements the same run-to-completion semantics as the Sismic
reference (`quake`), a lightweight conformance test drives the flat sm-examples
through both Sismic and the generated statix C and asserts they settle in the
same state. This is a thin slice of the broader cross-backend conformance idea
described in [positioning.md](statix/positioning.md); the full framework is
future work.
