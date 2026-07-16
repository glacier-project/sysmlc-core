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
- Convert SI seconds to ticks safely for time-triggered (`after`/`at`)
  transitions (`sc_seconds_to_ticks`), and define the project-wide
  `SC_TICKS_PER_SECOND` tick resolution (default `1000u`, override with
  `-D`, like `SC_MAX_TRANSITIONS`).
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
  includes `sc/sc_machine.h` after setting four required `SC_MACHINE_*`
  macros (plus optional `SC_MACHINE_HAS_QUEUE`/`SC_MACHINE_HAS_TIMER` and
  the paired `SC_MACHINE_TIMEOUT_DUE` for sending/timed machines).
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
  no-payload event ids from command-line arguments, and print a state trace. A
  timed machine also accepts `tick:<uint>` arguments, calling `<prefix>_tick`
  instead of `_post`. A machine with a `when` (change) trigger additionally
  exposes a public `<prefix>_settle`, called directly by hand-written test
  harnesses rather than through the runner (the runner has no vocabulary for
  mutating an arbitrary context attribute by name). It may use hosted C
  facilities such as `<stdio.h>`; it is not part of the board runtime.
- **`CMakeLists.txt`** — builds the bundled runtime, every generated statechart
  unit, a combined static library, and one host runner executable per machine.

`sysmlc statix build <model> -o out/` emits one `<prefix>.h/.c` pair per
`state def` in the model. `-e <QN>` remains the focused single-statechart build.

## 3. statix backend (`sysmlc/backends/statix`)

Modeled on the `rosetta` backend. The generic `StateMachineDriver` pushes
neutral facts into `StatixBuilder`, which assembles a neutral `CProgram`; the
serializer renders it to C.

- **`builder.py`** — consumes the neutral facts and assembles `CProgram`. Every
  representational choice and every rejection lives here: history states,
  non-inline `do`, external sends, reading accept payload data beyond one Real attribute,
  external/non-allowlist function calls in expressions, non-scalar / non-composite
  attributes, and direct parallel-in-parallel (`wrap in composite`) are rejected loudly (never silently dropped). Orthogonal/parallel regions (`StateKind.PARALLEL`), composite states, `then done` finals,
  one-shot `do`, `send` self-events (id-only, or marshalling one readable Real payload attribute), asserted constraints, leaf-sourced `after`/`at` time triggers (at most one per leaf), and `when` (change triggers, sourced from a leaf state, no self-loops) are supported.
- **`codegen.py`** — a precedence-driven emitter that lowers guard/effect/
  attribute expression nodes to C, with attribute references resolved against
  the generated context struct, allowlisted library function calls lowered
  to `<math.h>` C (rejecting external calc-defs and Integer-narrowing library
  assignments), and transition-scoped payload reads (`reading.value` → the event's marshalled f64 slot).
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

## Concurrency Model and Join Intrinsic

When the model includes parallel states, `statix` represents the concurrent active configuration using:

- **`active[]`**: A statically-sized `sc_activation_t active[<PREFIX>_ACTIVE_CAPACITY]` array inside `sc_runtime_t`. Every orthogonal region is allocated a dedicated activation slot.
- **`regions[]`**: A flat, generated array in `<prefix>.c` storing the state IDs of all region roots contiguously. For a parallel state, `region_first` points to its first region root in `regions[]`, and `region_count` gives the region count.
- **Join Intrinsic (`sc_runtime_regions_all_final`)**: When evaluating a completion (`__completion__`) transition sourced at a parallel state, the runtime checks if all region roots mapped under that parallel state have active descendants that are final leaf states.

## Header-Only C Runtime Packaging

To make integrating `statix`-generated code into firmware projects as frictionless as possible, the entire C runtime library is packaged header-only:

- **`sc/sc_machine.h`**: Instantiated inline per generated statechart.
- **`sc/sc_status.h` & `sc/sc_event_queue.h`**: Define small utility functions with `static inline` linkage.
- **`sc/sc_runtime.h`**: Uses an **stb-style implementation gate**. It declares all functions unconditionally, but only defines them in the translation unit that defines `SC_RUNTIME_IMPLEMENTATION` before inclusion.

Exactly one translation unit per link unit must do:

```c
#define SC_RUNTIME_IMPLEMENTATION
#include "sc/sc_runtime.h"
```

Generated projects emit this one-liner unit automatically as `src/sc_runtime_impl.c`. Non-CMake or custom integrations must add that same define to exactly one of their own source files.

## Data flow (runtime)

```
<prefix>_init ─► sc_runtime_bind (allocates static active[<PREFIX>_ACTIVE_CAPACITY] slots)
                   │ run entry(initial) -> _descend (forks regions across active slots)
                   │ settle completion transitions (bounded by SC_MAX_RTC_STEPS, checks all-final join)
                   ▼
caller pushes sc_event_t ─► sc_event_queue (static storage)
caller pops  sc_event_t  ─► <prefix>_dispatch
                              │ _select scans active slots (broadcasts across regions / checks group interrupt)
                              │   if group interrupt: _exit_up_to all regions -> effect -> entry(target) -> _descend
                              │   if region-local: _take_transition_region per slot
                              │ _run_completion: loop bounded by SC_MAX_RTC_STEPS (settle join/completion)
                              ▼
                            active slots updated to new leaves   (or NO_TRANSITION)
```

Everything on this path uses caller-owned, statically-sized storage (`no recursion, no dynamic memory`).

## Compile-Time Tracing Hook (`SC_MACHINE_TRACE`)

To support observability and runtime debugging without sacrificing the strict safety constraints (no recursion, no dynamic memory allocation, no function pointers), `statix` provides a compile-time-gated tracing mechanism.

### The Trace Callback Contract

A statechart generated by `statix` or manually instantiated via `sc/sc_machine.h` can optionally invoke a user-defined tracing callback. This callback must match the following signature:

```c
void trace_callback(sc_trace_kind_t kind, const sc_runtime_t *runtime,
                    const sc_event_t *event, const sc_trace_data_t *data);
```

- **Observational Only**: The callback must be synchronous and strictly observational. It must never mutate the runtime context, its active states, or user-data, and it must never re-enter the runtime API (e.g., calling `_dispatch`, `_post`, `_tick`, or `_init` is strictly forbidden during a trace callback).
- **Traced Events (`sc_trace_kind_t`)**:
  - `SC_TRACE_ENTER`: Fired immediately before a state's entry action runs.
  - `SC_TRACE_EXIT`: Fired immediately before a state's exit action runs.
  - `SC_TRACE_TRANSITION`: Fired immediately before a transition fires (reports source, target, transition index, and transition action).
  - `SC_TRACE_GUARD`: Fired whenever a transition guard or invariant is evaluated (reports guard ID and bool pass/fail result).
  - `SC_TRACE_TIMER_CHECK`: Fired whenever a timeout-due check is evaluated (reports state ID, activation index, and bool due/not-due result).

### Compile-Time Masking and Performance

Tracing call sites are gated using preprocessor macros (`#if SC__TRACE_ENABLED(...)`). If a trace kind is masked out at compile time, the entire call block is omitted from compilation, incurring zero runtime cost (no branching, no register saving, and no function call overhead even under `-O0`).

The bitmask is configured via the `SC_MACHINE_TRACE_MASK` preprocessor definition. The available bitmask constants are:

```c
#define SC_TRACE_MASK_ENTER       (1u << 0)
#define SC_TRACE_MASK_EXIT        (1u << 1)
#define SC_TRACE_MASK_TRANSITION  (1u << 2)
#define SC_TRACE_MASK_GUARD       (1u << 3)
#define SC_TRACE_MASK_TIMER_CHECK (1u << 4)
#define SC_TRACE_MASK_ALL         ((1u << 5) - 1u)
```

### Generated default Tracer and Custom Overrides

By default, every translation unit generated by `statix` (e.g., `src/<prefix>.c`) embeds a default `printf`-based `trace_hook` and binds it as the machine's `SC_MACHINE_TRACE` callback:

- **Mask Configuration**: By default, `<PREFIX>_TRACE_MASK` is defined to `SC_TRACE_MASK_ALL`. For untimed machines, `SC_TRACE_MASK_TIMER_CHECK` is automatically stripped from the available mask at compile time.
- **Zero Cost Disabling**: You can define `<PREFIX>_TRACE_MASK` to `0` (e.g., `-DMICROWAVE_MICROWAVE_BEHAVIOR_TRACE_MASK=0` or setting it to `0u` before the compilation unit is built). In this case, the compiler strips the default `trace_hook` code, all formatting strings, and the `<stdio.h>` header inclusion entirely.
