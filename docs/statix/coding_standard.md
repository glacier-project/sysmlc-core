# Coding standard

This standard keeps the runtime small, explicit, and analyzable. It is a
practical companion to [power_of_10_compliance.md](power_of_10_compliance.md);
where they overlap, Power of 10 wins.

## Language and portability

- **C99**, strict (`-std=c99`, no compiler extensions). Rationale: C99 gives us
  `<stdint.h>` fixed-width types, `<stdbool.h>`, designated initializers, and
  `inline` while remaining available on essentially every embedded toolchain.
  We do not require C11 features.
- The runtime targets a **freestanding-friendly** subset: it uses only
  `<stdint.h>`, `<stdbool.h>`, and `<stddef.h>`. It does **not** use the heap,
  `<stdio.h>`, `<string.h>`, locale, or floating point. (Examples and tests may
  use `<stdio.h>` for reporting — that is host-only glue, never the runtime.)

## Types

- Use the standard headers for primitive widths and booleans:
  `<stdint.h>`, `<stdbool.h>`, and `<stddef.h>`. Do not create statix-owned
  aliases for `int32_t`, `uint32_t`, `bool`, or `size_t`; exact-width standard
  types are part of the portability contract.
- Create statix typedefs only for **domain** concepts whose representation may
  change centrally, e.g. `sc_state_id_t`, `sc_event_id_t`,
  `sc_transition_id_t`, `sc_action_id_t`, and `sc_guard_id_t`.
- Use the fixed-width id typedefs from `sc_types.h` (`sc_state_id_t`, …), never
  bare `int`/`unsigned`, in public APIs and generated tables.
- `0` is reserved as "none/invalid" for events, guards, and actions. Generated
  ids for those start at `1`. State ids start at `0`.
- Prefer value types that can be copied by assignment (e.g. `sc_event_t`) over
  pointer-shared mutable state.

## Functions

- Small and single-purpose. Validate arguments first; return
  `SC_STATUS_INVALID_ARGUMENT` for NULL/out-of-range input.
- Every fallible function returns `sc_status_t`. A pure accessor that cannot
  fail (e.g. `sc_event_queue_count`) may return its value directly but must
  still treat NULL defensively.
- Mark file-local functions `static`. Provide prototypes for all externally
  visible functions (`-Wmissing-prototypes` enforces this).

## Control flow

- No `goto`, no recursion, no `setjmp`/`longjmp`, no function pointers.
- Every loop has a compile-time bound (see Rule 2).
- `switch` statements over ids always have a `default` that fails safe.

## Pointers

- At most one level of indirection in APIs. No pointer-to-pointer parameters.
- `const`-qualify borrowed, read-only pointers (`const sc_machine_t *`).

## Preprocessor

- Allowed: include guards, simple object-like constants, sentinel macros.
- Avoid: function-like macros with control flow, token pasting, and
  conditional compilation in the runtime. (The tests' `CHECK` macro is the one
  deliberate exception, isolated to test code.)

## Naming

| Kind | Convention | Example |
|------|------------|---------|
| Public type | `sc_<noun>_t` | `sc_runtime_t` |
| Public function | `sc_<noun>_<verb>` | `sc_event_queue_push` |
| Status code | `SC_STATUS_<NAME>` | `SC_STATUS_QUEUE_FULL` |
| Constant / sentinel | `SC_<NAME>` | `SC_GUARD_NONE` |
| Generated state id | `<PREFIX>_STATE_<NAME>` | `APP_STATE_OFF` |
| Generated event id | `<PREFIX>_EVENT_<NAME>` | `APP_EVENT_TURN_ON` |

## Formatting

- Defined by [`.clang-format`](../.clang-format): 4-space indent, 100-column
  lines, Linux brace style (functions open on a new line, control blocks
  attach), pointers bind to the name.
- Run `tools/format.sh` to apply it; `tools/check_all.sh` verifies it.
- **Generated files (`examples/*/generated/`) are excluded** from clang-format:
  their layout is the emitter's responsibility, and reformatting them would
  break the "generated output matches committed files" check.

## Comments

- Explain *why*, especially for safety-relevant decisions (bounded loops, the
  no-function-pointer dispatch, fail-safe defaults). Avoid restating *what* the
  code already says.
- Generated public headers use Doxygen line comments, not block comments. Every
  public function declaration has `/// @brief`; every parameter has
  `/// @param`; every non-`void` return has `/// @return`. This keeps generated
  declarations readable and lets whole generated sections be wrapped safely in
  `/* ... */` during review without nesting block comments.
- Generated public structs, enums, and fields may use `/// @brief` or compact
  `///< @brief` comments when the documentation clarifies the generated API.
- Mark deferred work with `TODO:` and a one-line reason, e.g.
  `/* TODO: hierarchical entry/exit — see docs/sysmlv2_subset.md */`.

## Tests

- C tests use a tiny inline `CHECK` macro and return non-zero on failure; no
  external framework and no dynamic memory.
- Python tests use pytest. Keep the generator deterministic so emitter tests can
  assert on exact output.
