# statix vs. boost::sml — feature comparison & extension roadmap

> **Migrated into sysmlc (2026-07).** statix is now a sysmlc backend; the
> `*.ir.json` IR referenced below is historical (it consumes sysmlc's neutral
> facts instead). The comparison and roadmap still stand.

[boost::sml](https://github.com/boost-ext/sml) is a mature, header-only C++14/17
state machine library. It is a useful yardstick for "what a statechart library
can do." This document inventories what `sml` offers, maps each feature onto
statix, and turns the gaps into a concrete, constraint-respecting extension plan.

**Read this first — the two libraries optimize for different things.** `sml`
expresses the machine *inline in C++* via heavy template metaprogramming and
resolves it at compile time. statix expresses the machine in an *external IR* and
generates plain, auditable C99 ahead of time, under
[The Power of 10](power_of_10_compliance.md). So a number of `sml` features are
not "missing" from statix — they are **deliberately out of scope** because they
rely on mechanisms (exceptions, function objects, dynamic containers, templates)
that a safety-critical static runtime must avoid. The interesting question is
which *statechart semantics* we can adopt without breaking those rules.

## At a glance

| #   | Statechart feature                            |             boost::sml              |               statix today                | Direction                            |
| --- | --------------------------------------------- | :---------------------------------: | :---------------------------------------: | ------------------------------------ |
| 1   | Flat states + event-triggered transitions     |                 ✅                  |                    ✅                     | —                                    |
| 2   | Initial state                                 |           ✅ (`*` prefix)           |                    ✅                     | —                                    |
| 3   | Guards                                        |    ✅ composable `&&` `\|\|` `!`    |            ◐ one guard id/row             | composite guards (gen-side)          |
| 4   | Transition effect / action                    |         ✅ multiple via `,`         |            ◐ one action id/row            | action lists                         |
| 5   | First-match / ordering semantics              |                 ✅                  |           ✅ declaration order            | —                                    |
| 6   | Unexpected event handling                     |      ✅ `unexpected_event<E>`       |       ✅ `SC_STATUS_NO_TRANSITION`        | + wildcard catch-all (#11)           |
| 7   | Terminal state                                |      ✅ `X`, `is_terminated()`      |                    ❌                     | **near-term**                        |
| 8   | Anonymous / completion transitions            |                 ✅                  |                    ❌                     | **near-term** (bounded RTC)          |
| 9   | Internal transitions                          |           ✅ (no `= dst`)           |                    ❌                     | with entry/exit (Stage 1)            |
| 10  | Self-transition (external)                    |             ✅ `= src`              | ◐ target==source works, no exit/entry yet | with entry/exit                      |
| 11  | Wildcard source state                         |               ✅ `_`                |                    ❌                     | **near-term** (`SC_STATE_ANY`)       |
| 12  | Entry / exit actions                          |      ✅ `on_entry` / `on_exit`      |                    ❌                     | Stage 1                              |
| 13  | Hierarchical / composite states (submachine)  |            ✅ `sm<...>`             |                    ❌                     | Stage 1                              |
| 14  | Orthogonal / parallel regions                 |      ✅ multiple `*` initials       |                    ❌                     | Stage 3                              |
| 15  | History (shallow)                             |                 ✅                  |                    ❌                     | Stage 3                              |
| 16  | Event deferral                                |             ✅ `defer`              |                    ❌                     | bounded defer (later)                |
| 17  | Queue / re-post events                        |    ✅ `process` (dynamic queue)     |       ◐ fixed queue, caller-driven        | mature in-action posting             |
| 18  | Typed event payload                           |          ✅ full C++ types          |    ◐ bounded byte payload placeholder     | typed payload in generator           |
| 19  | Logging / visiting current states             | ✅ `logger`, `visit_current_states` |                    ❌                     | optional link-time trace hooks       |
| 20  | Exception handling                            |          ✅ `exception<E>`          |                    ❌                     | **out of scope** (no C++ exceptions) |
| 21  | Dependency injection                          |        ✅ `pool` / `try_get`        |          ❌ (single `user_data`)          | **out of scope** (different model)   |
| 22  | Thread safety                                 |       ✅ `thread_safe<lock>`        |       ❌ (caller's responsibility)        | **out of scope** for the runtime     |
| 23  | Selectable dispatch (jump/switch/branch/fold) |              ✅ policy              |          ◐ one generated switch           | optional jump-table emission         |

✅ supported · ◐ partial / different mechanism · ❌ not yet

## Near-term extensions that fit statix's constraints

These are cheap, high-value, and each preserves every Power of 10 rule (no heap,
no recursion, no function pointers, bounded loops). They are the recommended next
features *before* the larger hierarchical work.

### A. Wildcard source state — "from any state" (#11)

Add a sentinel `SC_STATE_ANY` (e.g. `0xFFFEu`). A transition row whose `source`
is `SC_STATE_ANY` matches regardless of the current state — ideal for a global
`RESET`/`FAULT` handler. Runtime change is one clause in the existing bounded
loop:

```c
if (((t->source == runtime->current_state) || (t->source == SC_STATE_ANY))
    && (t->event == event->id)) { ... }
```

Generator: allow `"source": "_"` (or `"*"`) in a transition. No new memory, loop
stays bounded.

### B. Terminal states + `sc_runtime_is_terminated()` (#7)

Mark states as final in the IR (`"final": true`). The generator emits a bounded
`is_final` switch (or a generated bitset); the runtime gains:

```c
sc_status_t sc_runtime_is_terminated(const sc_runtime_t *rt, bool *out_done);
```

Pure data + one switch — trivially analyzable.

### C. Anonymous / completion transitions + run-to-completion (#8)

Reserve a completion pseudo-event. After a transition fires, the runtime runs a
**bounded** loop that re-dispatches the completion event so guard-only
transitions can chain. The loop is capped by a generated
`SC_MAX_RTC_STEPS` constant — which is exactly how we keep Rule 2 (bounded loops)
even for run-to-completion. This is the one feature here that adds a loop, so the
compile-time bound is mandatory.

### D. Optional trace hooks without function pointers (#19)

Mirror the existing [dispatch contract](../include/sc/sc_runtime.h): declare
weak/extern `sc_trace_transition(...)` / `sc_trace_no_transition(...)` that the
runtime calls if provided and that compile out otherwise (resolved at link time,
**no function pointers**). Gives `sml`-style logging/visiting for debugging and
HIL tests while staying static.

### E. Action lists and composite guards (#3, #4)

Keep the runtime's single guard-id / action-id per row, but let the **generator**
synthesize them: a transition with multiple actions emits one generated action id
whose body calls each effect in sequence; a `g1 && !g2` guard expression emits one
generated guard id whose body evaluates the expression. All complexity stays in
generated bodies that the compiler still sees as ordinary bounded switches.

## Explicitly out of scope (by design)

Not gaps to close — these conflict with the safety constraints and have a
statix-native alternative:

| boost::sml feature                                     | Why excluded                                      | statix alternative                                             |
| ------------------------------------------------------ | ------------------------------------------------- | -------------------------------------------------------------- |
| Exceptions (`exception<E>`)                            | C, and Power of 10 forbids non-local control flow | explicit `sc_status_t` returns from actions                    |
| Dependency injection (`pool`, `try_get`)               | template machinery, hidden wiring                 | one explicit `user_data` context pointer                       |
| `thread_safe<lock>`                                    | the runtime takes no policy on concurrency        | caller owns locking around `sc_runtime_dispatch` (document it) |
| Dynamic `defer_queue` / `process_queue` (`std::queue`) | dynamic allocation                                | fixed-size `sc_event_queue` over caller storage                |
| Inline C++ DSL / generic lambdas                       | requires a C++ compiler & TMP at the call site    | external IR + ahead-of-time C codegen                          |
| Runtime-selectable dispatch strategies                 | extra surface; one strategy is enough             | (optional) generator may emit a jump table later               |

## The deeper difference: authoring model

|                         | boost::sml                              | statix                                      |
| ----------------------- | --------------------------------------- | ------------------------------------------- |
| Where the machine lives | inline C++ transition table             | external `*.ir.json` IR (→ future SysML v2) |
| When it's resolved      | compile time (template metaprogramming) | build time (Python generator → C)           |
| What ships              | template-instantiated C++               | plain, reviewable generated C99             |
| Target toolchain        | C++14/17                                | C99 (freestanding-friendly)                 |
| Certification story     | inspect C++ + trust the compiler        | **audit the generated C directly**          |

For safety-critical work, generating auditable C from a small, validated model is
a feature, not a limitation: the artifact that runs on the target is exactly what
a reviewer (or a static analyzer, or a coverage tool) sees. statix should chase
boost::sml on *statechart expressiveness* (the table above) while keeping that
generated-C, static-memory posture as its differentiator.

## Suggested order of work

1. **Now (flat-model wins):** wildcard source (A), terminal states (B),
   completion transitions + bounded RTC (C), optional trace hooks (D).
1. **Stage 1 (hierarchy):** entry/exit actions, composite states, internal vs.
   external transitions — see [sysmlv2_subset.md](sysmlv2_subset.md).
1. **Generator polish:** action lists & composite guards (E), typed event
   payloads (#18).
1. **Stage 3+:** parallel regions, shallow history, bounded event deferral.
