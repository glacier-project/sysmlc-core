# Architecture

`statix` is a sysmlc backend: it turns SysML v2 state definitions into a
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
        │ 2. Generated C project                                          │
        │    <prefix>.h/.c       one readable unit per statechart         │
        │    <prefix>_runner.c   host-only smoke runner                   │
        │    CMakeLists.txt      runtime + generated units + runners      │
        └───────────────────────────┬───────────────────────────────────┘
                                     │ #include + link
        ┌───────────────────────────▼───────────────────────────────────┐
        │ 1. C runtime kernel (sc_runtime, bundled)                      │
        │    machine-agnostic runtime + dispatch template                │
        └───────────────────────────────────────────────────────────────┘
```

## 1. C runtime kernel (`sc_runtime`)

A small, **machine-agnostic** C99 library, shipped as package data and copied
into every generated project. It defines the shared runtime vocabulary and
portable support code, but contains no knowledge of any particular machine and
does not call generated guard/action code.

Responsibilities:

- Hold common state for a runtime instance (`sc_runtime_t`), owned by the
  generated `<prefix>_t` instance.
- Bind a runtime instance to a generated immutable `sc_machine_t` and caller-owned
  context.
- Expose machine-agnostic helpers such as current-state access.
- Provide a fixed-size FIFO event queue over caller storage
  (`sc_event_queue_*`).
- Define the shared vocabulary: fixed-width ids (`sc_types.h`), status codes
  (`sc_status.h`), and the event value type (`sc_event.h`).

What it deliberately does **not** do: allocate memory, recurse, use function
pointers, or contain any machine-specific `switch`. See
[power_of_10_compliance.md](power_of_10_compliance.md).

### The no-function-pointer dispatch contract

A safety-critical runtime must avoid function pointers, but it must still call
machine-specific guards and actions. statix resolves this with **per-statechart
dispatch orchestration** rather than runtime indirection:

- The shared runtime never declares or calls global `sc_guard_eval()` /
  `sc_action_exec()` hooks.
- Each generated `<prefix>.c` defines `static` guard/action switches and
  includes `sc/sc_machine.h` after setting four `SC_MACHINE_*` macros.
- `sc/sc_machine.h` is the single audited dispatch algorithm. It is instantiated
  once per generated unit and calls the file-local static guard/action switches
  directly.
- The public API is fully prefixed (`<prefix>_init`, `<prefix>_dispatch`,
  `<prefix>_post`, `<prefix>_get_state`), so several generated machines link
  cleanly into one firmware image.

The cost is a small dispatch template instantiated per generated statechart. The
benefit is that the algorithm lives in one C artifact while *all* control flow
remains statically analyzable: there is no indirect call anywhere, and no
generated global symbols collide.

## 2. Generated C project

Per-statechart C produced by the backend's `serialize.py`. The output is
deterministic — the same model always yields byte-identical C, so generated files
diff cleanly.

- **`<prefix>.h`** — generated public interface: ids, context structs, instance
  type, and documented API. Public declarations use Doxygen `/// @brief`,
  `@param`, and `@return` comments.
- **`<prefix>.c`** — static state/transition tables, generated context defaults,
  generated guard/action switches, state/event name helpers, and the
  `SC_MACHINE_*` glue that instantiates `sc/sc_machine.h`. Eventless transitions
  carry the reserved `SC_EVENT_COMPLETION` event id. Guard/action bodies are
  lowered directly from the SysML guard/effect/entry/exit expressions, so the
  model is the single source of truth.
- **`include/sc/sc_machine.h`** — shared, header-only dispatch template. It
  owns the flat dispatch algorithm (`init`, `dispatch`, `post`, `get_state`)
  and is included once per generated statechart unit.
- **`<prefix>_runner.c`** — host-only smoke runner: initialize the machine, feed
  no-payload event ids from command-line arguments, and print a state trace. It
  may use hosted C facilities such as `<stdio.h>`; it is not part of the board
  runtime.
- **`CMakeLists.txt`** — builds the bundled runtime, every generated statechart
  unit, a combined static library, and one host runner executable per machine.

`sysmlc statix build <model> -o out/` emits one `<prefix>.h/.c` pair per
`state def` in the model. `-e <QN>` remains the focused single-statechart build.

## 3. statix backend (`sysmlc/backends/statix`)

Modeled on the `rosetta` backend. The generic `StateMachineDriver` pushes
neutral facts into `StatixBuilder`, which assembles a neutral `CProgram`; the
serializer renders it to C.

- **`builder.py`** — consumes the neutral facts and assembles `CProgram`. Every
  representational choice and every rejection lives here: parallel, history,
  timers, `after`/`at`/`when`, non-inline `do`, external sends, payload-carrying sends,
  external/non-allowlist function calls in expressions, and non-scalar / non-composite
  attributes are rejected loudly (never silently dropped). Composite states, `then done` finals,
  one-shot `do`, self-sends (internal events without payloads), and asserted constraints are supported.
- **`codegen.py`** — a precedence-driven emitter that lowers guard/effect/
  attribute expression nodes to C, with attribute references resolved against
  the generated context struct, and allowlisted library function calls lowered
  to `<math.h>` C (rejecting external calc-defs and Integer-narrowing library
  assignments).
- **`program.py`** — the frozen `CProgram` / `CProject` dataclasses (states,
  events, guards, actions, transitions, context) — the neutral C model before
  text.
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
<prefix>_init ─► sc_runtime_bind
                   │ run entry(initial)
                   │ settle completion transitions (bounded by SC_MAX_RTC_STEPS)
                   ▼
caller pushes sc_event_t ─► sc_event_queue (static storage)
caller pops  sc_event_t  ─► <prefix>_dispatch
                              │ scan transition table (bounded loop)
                              │   match (current_state, event.id), check guard
                              │   run exit(source) -> effect -> entry(target)
                              │   settle completion transitions
                              ▼
                            current_state := target   (or NO_TRANSITION)
```

Everything on this path uses caller-owned, statically-sized storage.
