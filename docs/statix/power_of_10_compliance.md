# Power of 10 compliance

This document tracks how the **C runtime** complies with
[*The Power of 10: Rules for Developing Safety-Critical Code*](https://spinroot.com/gerard/pdf/P10.pdf)
(G. J. Holzmann, NASA/JPL). Each rule lists the project's intent and how the
current scaffold meets it. The Python generator is a host-side build tool and is
not subject to these rules, but it is written to *produce* compliant C.

> Scope note: "the runtime" means everything under `include/sc/` and `src/`. The
> examples and C tests follow the same rules so the whole tree stays analyzable.

| #   | Rule                                                                      | Status | How statix complies                                                                                                                                                                                                                                                  |
| --- | ------------------------------------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | No `goto`, `setjmp`/`longjmp`, or recursion                               | ✅     | None are used anywhere in the runtime. Dispatch is a single `for` loop; there are no direct or mutually recursive calls. The generated dispatch is a flat `switch`.                                                                                                  |
| 2   | All loops have a fixed upper bound                                        | ✅     | The only runtime loops are the dispatch scan — bounded by `SC_MAX_TRANSITIONS` (a compile-time constant) — and the bounded payload copy in `sc_event.h`. Queue operations are O(1) with no loops.                                                                    |
| 3   | No dynamic memory after initialization                                    | ✅     | No `malloc`/`calloc`/`realloc`/`free`. Machine tables are `static const`; runtime instances and queue storage are caller-owned locals/statics.                                                                                                                       |
| 4   | Keep functions short (≈ one printed page)                                 | ✅     | Every public function is well under a page and does one thing. The largest is `sc_runtime_dispatch`.                                                                                                                                                                 |
| 5   | Use a minimum of two assertions per function (validate inputs)            | ◐      | Every public function validates its arguments up front and returns `SC_STATUS_INVALID_ARGUMENT` on bad input (a return-code form of defensive checking suitable for freestanding targets). A dedicated `SC_ASSERT` facility is planned; see *Open items*.            |
| 6   | Declare data objects at the smallest possible scope                       | ✅     | Loop and temporary variables are declared at block scope; there is **no hidden global mutable state** — the only mutable state is the caller-provided `sc_runtime_t`.                                                                                                |
| 7   | Check the return value of every non-void function; check parameters       | ✅     | Public APIs return `sc_status_t`. Callers (tests, example) check them; where a result is intentionally ignored it is cast to `(void)` to make the decision explicit.                                                                                                 |
| 8   | Limit the preprocessor to includes and simple macros                      | ✅     | Macros are header guards, the bounded-size constants (`SC_EVENT_PAYLOAD_SIZE`, `SC_MAX_TRANSITIONS`), sentinel ids, and the tests' `CHECK`. No conditional-compilation logic or token pasting in the runtime.                                                        |
| 9   | Restrict pointers: at most one level of dereference; no function pointers | ✅     | No function pointers (see the link-time dispatch contract in [architecture.md](architecture.md)). Pointers are shallow: `sc_runtime_t*`, `const sc_machine_t*`, `const sc_transition_t*`. No pointer-to-pointer in the API.                                          |
| 10  | Compile with all warnings on, zero warnings                               | ✅     | Built with `-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes -Wcast-qual -Wundef -Wdouble-promotion -Wpointer-arith` and `-Werror`. CI fails on any warning. A `.clang-tidy` config is provided (advisory). |

Legend: ✅ met · ◐ partially met (see notes) · ⬜ not yet addressed.

## Rule-by-rule detail

### Rule 1 — control flow

`sc_runtime_dispatch` uses a single bounded `for` loop with early `return` on a
match. There is no `goto`, no `continue` chain, no recursion. The generated
`sc_guard_eval`/`sc_action_exec` are flat `switch` statements with a `default`
case, making them total functions.

### Rule 2 — bounded loops

The dispatch loop is clamped:

```c
limit = machine->transition_count;
if (limit > (uint16_t)SC_MAX_TRANSITIONS) {
    limit = (uint16_t)SC_MAX_TRANSITIONS;
}
for (i = 0u; i < limit; ++i) { ... }
```

Even a malformed `transition_count` cannot cause an unbounded scan. Override
`SC_MAX_TRANSITIONS` at compile time if a chart legitimately needs more.

### Rule 3 — static memory

The event queue is the canonical example: the control block holds only indices
and a *borrowed* pointer to a caller-owned array. `sc_event_queue_init` takes the
storage and capacity from the caller; the queue never allocates.

### Rule 9 — no function pointers

The single most important structural decision. Instead of storing handler
pointers in the transition table, transitions store integer guard/action ids,
and the generated code turns those ids into calls via a `switch`. This keeps the
entire call graph statically known.

## Open items

These are deliberately deferred while the scaffold stabilizes:

- **Rule 5**: add a configurable `SC_ASSERT` macro (compiled out or routed to a
  target fault handler) to express internal invariants in addition to the
  argument checks already present.
- **Rules 1–2 under hierarchy**: when hierarchical states arrive, state
  entry/exit must walk a *bounded* ancestor chain — the depth bound will be a
  generated compile-time constant, preserving Rule 2. See
  [sysmlv2_subset.md](sysmlv2_subset.md).
