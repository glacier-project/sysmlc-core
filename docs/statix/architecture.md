# Architecture

`statix` is a sysmlc backend: it turns a flat SysML v2 state machine into a
self-contained, static-memory C project. It separates the system into layers
with a clear boundary between the shared sysmlc front-end and the C it emits.

```
        ┌───────────────────────────────────────────────────────────────┐
        │ 4. sysmlc shared front-end                                     │
        │    syside parses SysML v2; StateMachineDriver walks it and      │
        │    pushes neutral facts (StateFact / TransitionFact / ...)      │
        └───────────────────────────┬───────────────────────────────────┘
                                     │ neutral facts
        ┌───────────────────────────▼───────────────────────────────────┐
        │ 3. statix backend  (sysmlc/backends/statix)                    │
        │    builder.py    facts -> CProgram (all rejections live here)  │
        │    codegen.py    lower guard/effect/attr expressions to C      │
        │    program.py    the neutral CProgram model                    │
        │    serialize.py  deterministic CProgram -> C text              │
        └───────────────────────────┬───────────────────────────────────┘
                                     │ generates + copies runtime
        ┌───────────────────────────▼───────────────────────────────────┐
        │ 2. Generated C project  (per machine)                          │
        │    *_ids.h              enums / integer ids                    │
        │    *_config.{h,c}       static const state + transition tables │
        │    *_context.h          the generated application context      │
        │    *_actions.c          generated guard/action dispatch        │
        │    CMakeLists.txt       builds the runtime + generated units   │
        └───────────────────────────┬───────────────────────────────────┘
                                     │ #include + link
        ┌───────────────────────────▼───────────────────────────────────┐
        │ 1. C runtime kernel (sc_runtime, bundled)                      │
        │    generic, machine-agnostic, static-memory dispatcher         │
        └───────────────────────────────────────────────────────────────┘
```

## 1. C runtime kernel (`sc_runtime`)

A small, **machine-agnostic** C99 library, shipped as package data and copied
into every generated project. It knows how to *execute* a machine but contains
no knowledge of any particular machine.

Responsibilities:

- Hold the current state of a runtime instance (`sc_runtime_t`).
- On init, enter the initial state, run its entry action, and settle any
  eventless (completion) transitions (`sc_runtime_init`).
- Dispatch an event: find the first enabled transition for
  `(current_state, event)`, run `exit(source) -> effect -> entry(target)`, then
  settle completion transitions (`sc_runtime_dispatch`).
- Bound the completion micro-step by `SC_MAX_RTC_STEPS` and surface a guarded
  eventless cycle as `SC_STATUS_STEP_LIMIT` rather than looping forever.
- Provide a fixed-size FIFO event queue over caller storage
  (`sc_event_queue_*`).
- Define the shared vocabulary: fixed-width ids (`sc_types.h`), status codes
  (`sc_status.h`), and the event value type (`sc_event.h`).

What it deliberately does **not** do: allocate memory, recurse, use function
pointers, or contain any machine-specific `switch`. See
[power_of_10_compliance.md](power_of_10_compliance.md).

### The no-function-pointer dispatch contract

A safety-critical runtime must avoid function pointers, but it must still call
machine-specific guards and actions. statix resolves this by **link-time
binding** rather than runtime indirection:

- The kernel declares `sc_guard_eval()` and `sc_action_exec()` in
  `sc_runtime.h` but does not define them.
- The generated `*_actions.c` defines them as a single bounded `switch` over
  integer ids.
- The linker connects the two.

The cost is one set of guard/action functions per linked program — the normal
situation for firmware. The benefit is that *all* control flow is statically
analyzable: there is no indirect call anywhere.

## 2. Generated C project

Per-machine C produced by the backend's `serialize.py`. The output is
deterministic — the same model always yields byte-identical C, so generated
files diff cleanly.

- **`*_ids.h`** — `enum`s assigning a stable integer id to every state, event,
  guard, and action.
- **`*_config.{h,c}`** — a `static const sc_state_def_t[]` per-state entry/exit
  table and a `static const sc_transition_t[]` transition table, plus the
  `sc_machine_t` that points at them. No code, just data. Eventless transitions
  carry the reserved `SC_EVENT_COMPLETION` event id.
- **`*_context.h`** — the generated `<prefix>_context_t` struct: one field per
  machine attribute (composite attribute defs become nested structs), passed as
  the runtime's `user_data`.
- **`*_actions.c`** — the **fully generated** `sc_guard_eval` / `sc_action_exec`
  dispatch. Unlike a hand-stub library, the guard/action bodies are lowered
  directly from the SysML guard/effect/entry/exit expressions, so the model is
  the single source of truth. (Non-assignment hardware side-effects — GPIO and
  the like — are future work; see the send/external-call family in
  [statix-mapping.md](../statix-mapping.md).)
- **`CMakeLists.txt`** — builds the bundled runtime plus the generated units
  into one static library.

## 3. statix backend (`sysmlc/backends/statix`)

Modeled on the `rosetta` backend. The generic `StateMachineDriver` pushes
neutral facts into `StatixBuilder`, which assembles a neutral `CProgram`; the
serializer renders it to C.

- **`builder.py`** — consumes the neutral facts and assembles `CProgram`. Every
  representational choice and every rejection lives here: hierarchy, parallel,
  history, timers, `after`/`at`/`when`, `send`, `then done`, and non-scalar /
  non-composite attributes are rejected loudly (never silently dropped).
- **`codegen.py`** — a precedence-driven emitter that lowers guard/effect/
  attribute expression nodes to C, with attribute references resolved against
  the generated context struct.
- **`program.py`** — the frozen `CProgram` dataclasses (states, events, guards,
  actions, transitions, context) — the neutral model before text.
- **`serialize.py`** — renders `CProgram` to the generated C files and the
  CMake project.

## 4. sysmlc shared front-end

The SysML v2 importer is **not** statix-specific: it is sysmlc's shared
`StateMachineDriver`, the same front-end that feeds quake (→ Sismic) and rosetta
(→ Lingua Franca). statix consumes the same neutral facts, so its meaning is
anchored to the same Sismic/SCXML run-to-completion reference the other backends
use.

## Data flow (runtime)

```
sc_runtime_init ─► enter initial state
                     │ run entry(initial)
                     │ settle completion transitions (bounded by SC_MAX_RTC_STEPS)
                     ▼
caller pushes sc_event_t ─► sc_event_queue (static storage)
caller pops  sc_event_t  ─► sc_runtime_dispatch
                              │ scan transition table (bounded loop)
                              │   match (current_state, event.id), check guard
                              │   run exit(source) -> effect -> entry(target)
                              │   settle completion transitions
                              ▼
                            current_state := target   (or NO_TRANSITION)
```

Everything on this path uses caller-owned, statically-sized storage.
