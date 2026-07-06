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

1. **Flat states + event-triggered transitions**
   - boost::sml: ✅
   - statix today: ✅
1. **Initial state**
   - boost::sml: ✅ (`*` prefix)
   - statix today: ✅
1. **Guards**
   - boost::sml: ✅ composable `&&` `||` `!`
   - statix today: ◐ one guard id/row
   - Direction: composite guards (gen-side)
1. **Transition effect / action**
   - boost::sml: ✅ multiple via `,`
   - statix today: ◐ one action id/row
   - Direction: action lists
1. **First-match / ordering semantics**
   - boost::sml: ✅
   - statix today: ✅ declaration order
1. **Unexpected event handling**
   - boost::sml: ✅ `unexpected_event<E>`
   - statix today: ✅ `SC_STATUS_NO_TRANSITION`
   - Direction: + wildcard catch-all (#11)
1. **Terminal state**
   - boost::sml: ✅ `X`, `is_terminated()`
   - statix today: ❌
   - Direction: **near-term**
1. **Anonymous / completion transitions**
   - boost::sml: ✅
   - statix today: ❌
   - Direction: **near-term** (bounded RTC)
1. **Internal transitions**
   - boost::sml: ✅ (no `= dst`)
   - statix today: ❌
   - Direction: with entry/exit (Stage 1)
1. **Self-transition (external)**
   - boost::sml: ✅ `= src`
   - statix today: ◐ target==source works, no exit/entry yet
   - Direction: with entry/exit
1. **Wildcard source state**
   - boost::sml: ✅ `_`
   - statix today: ❌
   - Direction: **near-term** (`SC_STATE_ANY`)
1. **Entry / exit actions**
   - boost::sml: ✅ `on_entry` / `on_exit`
   - statix today: ❌
   - Direction: Stage 1
1. **Hierarchical / composite states (submachine)**
   - boost::sml: ✅ `sm<...>`
   - statix today: ❌
   - Direction: Stage 1
1. **Orthogonal / parallel regions**
   - boost::sml: ✅ multiple `*` initials
   - statix today: ❌
   - Direction: Stage 3
1. **History (shallow)**
   - boost::sml: ✅
   - statix today: ❌
   - Direction: Stage 3
1. **Event deferral**
   - boost::sml: ✅ `defer`
   - statix today: ❌
   - Direction: bounded defer (later)
1. **Queue / re-post events**
   - boost::sml: ✅ `process` (dynamic queue)
   - statix today: ◐ fixed queue, caller-driven
   - Direction: mature in-action posting
1. **Typed event payload**
   - boost::sml: ✅ full C++ types
   - statix today: ◐ bounded byte payload placeholder
   - Direction: typed payload in generator
1. **Logging / visiting current states**
   - boost::sml: ✅ `logger`, `visit_current_states`
   - statix today: ❌
   - Direction: optional link-time trace hooks
1. **Exception handling**
   - boost::sml: ✅ `exception<E>`
   - statix today: ❌
   - Direction: **out of scope** (no C++ exceptions)
1. **Dependency injection**
   - boost::sml: ✅ `pool` / `try_get`
   - statix today: ❌ (single `user_data`)
   - Direction: **out of scope** (different model)
1. **Thread safety**
   - boost::sml: ✅ `thread_safe<lock>`
   - statix today: ❌ (caller's responsibility)
   - Direction: **out of scope** for the runtime
1. **Selectable dispatch (jump/switch/branch/fold)**
   - boost::sml: ✅ policy
   - statix today: ◐ one generated switch
   - Direction: optional jump-table emission

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

- **Exceptions (`exception<E>`)**
  - Why excluded: C, and Power of 10 forbids non-local control flow.
  - statix alternative: explicit `sc_status_t` returns from actions.
- **Dependency injection (`pool`, `try_get`)**
  - Why excluded: template machinery, hidden wiring.
  - statix alternative: one explicit `user_data` context pointer.
- **`thread_safe<lock>`**
  - Why excluded: the runtime takes no policy on concurrency.
  - statix alternative: caller owns locking around `sc_runtime_dispatch` (document it).
- **Dynamic `defer_queue` / `process_queue` (`std::queue`)**
  - Why excluded: dynamic allocation.
  - statix alternative: fixed-size `sc_event_queue` over caller storage.
- **Inline C++ DSL / generic lambdas**
  - Why excluded: requires a C++ compiler & TMP at the call site.
  - statix alternative: external IR + ahead-of-time C codegen.
- **Runtime-selectable dispatch strategies**
  - Why excluded: extra surface; one strategy is enough.
  - statix alternative: (optional) generator may emit a jump table later.

## The deeper difference: authoring model

- **Where the machine lives**: boost::sml uses inline C++ transition table; statix uses external `*.ir.json` IR (→ future SysML v2).
- **When it's resolved**: boost::sml resolves at compile time (template metaprogramming); statix resolves at build time (Python generator → C).
- **What ships**: boost::sml ships template-instantiated C++; statix ships plain, reviewable generated C99.
- **Target toolchain**: boost::sml targets C++14/17; statix targets C99 (freestanding-friendly).
- **Certification story**: boost::sml requires inspecting C++ + trusting the compiler; statix allows you to **audit the generated C directly**.

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
