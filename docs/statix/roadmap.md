# statix roadmap: from flat states to full SysML v2 statechart coverage

This is the plan for growing the `statix` backend from its current flat subset to
the full SysML v2 statechart feature set that the shared sysmlc front-end already
delivers — the way the other backends (rosetta is the most complete) do — while
keeping every generated artifact and the runtime **static-memory, bounded,
function-pointer-free C99** fit for a microcontroller.

It supersedes the standalone repo's `sysmlv2_subset.md` (Stage 0–4), updated for
statix living inside sysmlc.

## Guiding principles

- **The invariant never changes.** Everything must remain expressible as static,
  bounded, function-pointer-free C under the strict warning set
  (`-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wdouble-promotion -Werror`). No malloc, no recursion, no function pointers, every loop bounded by
  a compile-time constant. See [power_of_10_compliance.md](power_of_10_compliance.md).
- **Sismic is the oracle.** quake (Sismic / SCXML run-to-completion) is the
  reference semantics. "Correct" means statix's compiled-C trace matches Sismic's
  on the same event sequence. Conformance is the per-feature gate, not unit tests
  alone — the iteration-1 conformance smoke test is the seed of that harness.
- **Semantics before expressiveness; hierarchy before the rest.** Pin precise
  hierarchical RTC that matches Sismic first; do not chase parallel regions,
  history, or timers ahead of it (see [positioning.md](positioning.md) §5, §9).
- **Backend + runtime job only.** The front-end already parses and delivers every
  feature below as neutral facts (`StateFact` / `TransitionFact` / the `Trigger`
  union / `CompositeValue` / `CompletionTarget` / `ConstraintFact`). Growing
  statix means consuming facts it currently rejects and lowering them to C — no
  front-end work.

## Current baseline (iteration 1)

Flat machines: leaf states, an initial substate, eventless *completion*
transitions, signal triggers, guards, entry/exit/effect `assign` actions,
Boolean/Integer/Real + composite attributes → a generated context struct, and a
bounded completion RTC micro-step (`SC_MAX_RTC_STEPS` + `SC_STATUS_STEP_LIMIT`).
Every richer construct is rejected loudly. See
[statix-mapping.md](../statix-mapping.md) for the supported set and the rejection
list this roadmap shrinks, phase by phase.

## The gap

Each row is a construct statix rejects today; the front-end delivers all of them.
"Oracle" is how quake/Sismic realizes it (what statix must match).

| #   | Construct                              | Example model | Oracle (quake/Sismic)                 | rosetta (LF)                  |
| --- | -------------------------------------- | ------------- | ------------------------------------- | ----------------------------- |
| A   | Composite (hierarchical) states        | sm08          | `CompoundState`, RTC entry/exit order | child reactor per scope       |
| B   | `then done` / final states             | sm10          | `FinalState` + completion             | `done` mode / `completed`     |
| C   | `do` activity (one-shot)               | sm12          | fused into `on_entry`                 | fused into entry reaction     |
| D   | Asserted constraints                   | sm17          | state `invariants`                    | Python `assert` woven in      |
| E   | Library + external function calls      | sm14, sm15    | whitelist → `math`; `--python`        | same; `--python`              |
| F   | `send` + internal-event RTC + payloads | sm11          | delayed/internal events, `event.x`    | self-scheduled action         |
| G   | Timers `after` / `at`                  | sm13, sm14    | delayed event + activation counter    | mode timer / scheduled action |
| H   | Change trigger `when`                  | sm16          | armed-flag + guarded consumer         | armed self-event (planned)    |
| I   | Parallel / orthogonal regions          | sm09          | `OrthogonalState`                     | one reactor per region        |
| J   | History (shallow/deep)                 | *(none yet)*  | Sismic history states                 | *(not in rosetta)*            |
| K   | String / state-scoped attributes       | sm11, sm17    | flat context / per-state              | companion dataclass / planned |

## The emission model: one self-contained unit per statechart (foundational)

**Multiple statecharts per build is a first-class scenario.** A model routinely
declares several `state def`s (SM01 has 3, SM11 has 7); parts/systems/compositions
put several machines in one image; real firmware runs several small machines side
by side.

Almost everything statix generated was already namespaced by `<prefix>`, so
machine *data* could coexist. The old blocker was the **dispatch contract**: the
runtime called fixed global symbols `sc_guard_eval` / `sc_action_exec`, and each
machine's generated action file defined them — link two machines and the
definitions collided. The tempting fix (a generic runtime calling
`machine->guard_fn(...)`) is a **function pointer**, which the invariant forbids
and which is exactly what separates statix from QP.

**A.0 is landed:** each statechart is now a self-contained `.h`/`.c` unit with a
fully **prefixed public API** (`<prefix>_context_init`, `<prefix>_init`,
`<prefix>_dispatch`, `<prefix>_post`, `<prefix>_get_state`, later
`<prefix>_tick`) and file-local `static` guard/action evaluation. N machines
link cleanly, no function pointers.

The dispatch algorithm itself lives in one audited C template,
`include/sc/sc_machine.h`, instantiated once per generated unit via
`SC_MACHINE_PREFIX`, `SC_MACHINE_DEF`, `SC_MACHINE_GUARD`, and
`SC_MACHINE_ACTION`. That keeps the algorithm centralized while preserving direct
calls to each unit's file-local static guard/action functions.

`sysmlc statix build <model>` with **no `-e`** generates one prefixed pair per
`state def` plus the shared runtime and one `CMakeLists.txt`; `-e <QN>` still
builds a single machine. A.0 also emits a **minimal host runner** per machine
(`init`, feed no-payload event ids from `argv`, print a state trace) as a
separate hosted-C target, while the generated statechart units and runtime stay
board-clean.

The full host-execution product story is a distinct increment: a `sysmlc statix run` command, virtual time, testbench scripts (`send` / `advance_ms` / `expect`),
JSON/CSV traces, and trace comparison against quake/Sismic. That belongs between
the emission-model work and the timed subset, so it can become the host
conformance driver for `after`/`at`/`when` without bloating A.0.

## The linchpin: static, bounded, hierarchical dispatch

Everything untimed rides on teaching the runtime to execute an OR-hierarchy with
correct UML entry/exit ordering, statically. Grow `sc_state_def_t` into a tree
node:

```c
typedef struct sc_state_def_s {
    sc_state_id_t parent;        /* enclosing state, or SC_STATE_NONE for root */
    sc_state_id_t initial_child; /* substate entered as target; NONE for leaf  */
    sc_action_id_t entry_action; /* SC_ACTION_NONE if absent */
    sc_action_id_t exit_action;
    uint8_t kind;                /* LEAF | COMPOSITE (| PARALLEL | FINAL later) */
} sc_state_def_t;
```

The active configuration stays a single leaf id; ancestors are recovered by
walking `parent`. Dispatch for event `e` in leaf `s`:

1. **Select (inner-first):** walk `s` up its ancestors (bounded by a generated
   `MAX_DEPTH`); the innermost state with an enabled matching transition wins.
1. **Fire:** with `lca = LCA(source, target)`, run exit actions from the current
   leaf up to (not including) `lca`; run the effect; run entry actions from just
   below `lca` down to `target`; if `target` is composite, descend into
   `initial_child` (bounded) to a leaf.
1. **Settle** completion transitions (the existing bounded micro-step).

Both loops are bounded by `MAX_DEPTH` (Rule 2); `LCA` is a bounded ancestor walk.
No recursion, no allocation, no function pointers. A function-pointer HSM
(QP-style) is rejected for exactly that reason. Deep entry (targeting a state
nested where its siblings are not) stays rejected until a later increment, as in
rosetta.

## Feature realizations (summary)

- **A Composite states** (landed) — table `parent`/`initial_child` columns
  walked by bounded LCA dispatch in `sc/sc_machine.h`; parallel and history
  remain out of scope.
- **B `then done` / final** — a generated `FINAL`-kind state per scope; entering
  it marks the enclosing composite complete and the completion micro-step fires
  its eventless exit; at the root, "complete" is a settled/terminal status the
  host loop observes. Parallel `then done` is a join (with I).
- **C `do` (one-shot)** — append a state's inline `do` (`assign`/`send`)
  statements to its entry sequence (entry then do); non-inline `do` stays
  rejected. Mostly a builder change.
- **D Asserted constraints** — generate `<prefix>_check_invariants(ctx, active)`
  returning a new `SC_STATUS_CONSTRAINT_VIOLATED`; call after each RTC step and
  on init; scoped constraints checked only when the owning state is active.
  Prefer a status return over C `assert()` (which compiles out under `NDEBUG`).
  `assert not constraint` negates.
- **E Functions + external** — reuse the shared `LIBRARY_FUNCTIONS` table
  re-targeted to C `math.h` (`fabs`/`fmax`/`fmin`/`sin`/`cos`/`tan`, mindful of
  `-Wdouble-promotion`); external `calc def`s become user-supplied C functions
  matched by name and declared in a generated `<prefix>_extern.h`. This is also
  the escape hatch for non-assignment hardware effects (a `do` that pokes GPIO is
  a call to a firmware-provided extern) — one feature covers both.
- **F send / internal-event RTC / payloads** — `send` pushes to the internal
  queue; the macro-step drains it bounded by `SC_MAX_RTC_STEPS`; payload structs
  ride in the event's fixed inline buffer, `memcpy`d in on send and read typed on
  accept (reject payloads over `SC_EVENT_PAYLOAD_SIZE`).
- **G Timers `after`/`at`** — `sc_runtime_tick(rt, elapsed)`; timers armed on
  entry, disarmed on exit, stale expiries invalidated by a per-source activation
  counter (Sismic's mechanism); expiry posts a synthetic event. Per-instance
  armed-timer state is a fixed array sized by a generated `MAX_TIMERS`.
  **Document where the timed subset diverges from LF logical time** — conformance
  compares event order + settled state, not absolute timing.
- **H `when`** — evaluate the monitored condition in the RTC micro-step; an armed
  flag re-armed on entry gives edge semantics; a guarded `when` consumes on a
  false guard.
- **I Parallel regions** — the active config becomes one leaf per region:
  `sc_state_id_t active[SC_MAX_REGIONS]` (generated size, still static). Fork on
  entry, broadcast events to each region, join on all-final, group interrupt on a
  transition sourced at the parallel state. The one feature that adds per-instance
  mutable arrays; deliberately last.
- **J History** — a fixed slot per history-bearing composite records the last
  active child/leaf; restore on re-entry via a history pseudostate. Needs a new
  `sm`-example (none exercises history today) before it can be conformance-gated.
- **K String / scoped attributes** — String → fixed-size `char[N]` buffers;
  state-scoped attributes → namespaced context fields. Opportunistic.

## Phased roadmap

Conformance-gated, hierarchy before advanced features, untimed before timed.

| Phase   | Theme                      | Features                                                                                                                       | Corpus                                                   | Runtime delta                                                                                        |
| ------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **A.0** | Emission model             | **landed:** one prefixed `.c`/`.h` per statechart; whole-model build; host runners; no global dispatch symbols                 | SM01 multi-`state def` project compiles, links, and runs | prefixed public API; static guard/action; shared `sc/sc_machine.h` dispatch template                 |
| **A**   | UML core (untimed)         | **composite (landed)**, then done/final, one-shot do, constraints, functions/extern                                            | sm08, sm10, sm12, sm14, sm17                             | state tree + LCA dispatch + MAX_DEPTH; final states; invariant check + new status                  |
| **B**   | Internal-event RTC         | `send` + internal queue drain + payloads                                                                                       | sm11                                                     | generalize the bounded micro-step; typed payloads in the event buffer                                |
| **B.5** | Host execution & testbench | `sysmlc statix run`; virtual-time testbench DSL; state/context expectations; JSON/CSV traces; statix-vs-quake trace comparison | sm01-sm17 reusable scripted traces                       | hosted runner tooling only; board-clean generated units unchanged                                    |
| **C**   | Timed subset               | `after`/`at`, `when`                                                                                                           | sm13, sm16, sm14(full)                                   | `sc_runtime_tick`; timer table + activation counters; armed-flag observers; documented LF divergence |
| **D**   | Concurrency & memory       | parallel regions, history                                                                                                      | sm09, + a new history model                              | per-instance `active[]` / `history[]` arrays sized by generated `#define`s                           |

Cross-cutting every phase: a trace-equivalence test vs Sismic ships with each
feature; each transition table row carries a comment tracing it to its SysML
element id; a CI grep asserts no `malloc`/`calloc`/`realloc`/`free` in the
generated project or runtime; the rejection table in
[statix-mapping.md](../statix-mapping.md) shrinks by exactly the row a phase
closes.

## Out of scope (for safety)

Rejected by design and kept loud: dynamically created/destroyed states or
regions, unbounded event-deferral queues, recursive submachine expansion without
a static depth bound, nested-parallel regions (wrap in a composite), and anything
requiring heap allocation or function-pointer dispatch.

## Decisions to confirm per phase

- **Runtime shape for hierarchy** — table-driven tree dispatch (recommended)
  versus per-model flattening when Phase A grows beyond the flat A.0 template.
- **Timed correspondence (Phase C)** — a timed model conforms to Sismic event
  *order* + settled state (recommended), given LF logical time and MCU wall-clock
  genuinely differ.
- **History corpus (Phase D)** — add an `sm`-example exercising history before
  building it, so it can be conformance-gated.
