#ifndef SC_TYPES_H
#define SC_TYPES_H

/*
 * sc_types.h - Fundamental fixed-width types for the statix statechart runtime.
 *
 * Safety notes (Power of 10 / MISRA-friendly):
 *   - Only fixed-width integer types from <stdint.h> are used, so storage size
 *     and value ranges are explicit and identical on every target.
 *   - Identifiers are unsigned integers, never pointers, so transition tables
 *     stay compact, deterministic, and free of function pointers.
 *   - No implementation-defined widths (no bare `int`/`unsigned` in the API).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Integer identifier types.
 *
 * 16 bits comfortably covers any realistic flat or hierarchical chart for an
 * embedded target while keeping generated tables small. Widen here (and only
 * here) if a target ever needs more than 65535 states/events.
 */
typedef uint16_t sc_state_id_t;
typedef uint16_t sc_event_id_t;
typedef uint16_t sc_guard_id_t;
typedef uint16_t sc_action_id_t;

/*
 * Reserved sentinel identifiers.
 *
 *   SC_GUARD_NONE   : a transition has no guard  -> it is always enabled.
 *   SC_ACTION_NONE  : a transition has no effect -> no action is executed.
 *   SC_STATE_INVALID: explicit "not a real state" marker for out-parameters.
 *   SC_EVENT_INVALID: explicit "not a real event" marker.
 *
 * Because 0 is reserved for "none"/"invalid" on guards, actions and events,
 * the code generator assigns those identifiers starting at 1. State ids start
 * at 0 (0 is a valid state); SC_STATE_INVALID uses the top of the range.
 */
#define SC_GUARD_NONE ((sc_guard_id_t)0u)
#define SC_ACTION_NONE ((sc_action_id_t)0u)
#define SC_STATE_INVALID ((sc_state_id_t)0xFFFFu)
#define SC_EVENT_INVALID ((sc_event_id_t)0u)

/*
 * Reserved event id for eventless (completion) transitions. Distinct from
 * SC_EVENT_INVALID: real signal events are generated starting at 1, so this
 * sentinel is chosen at the top of the range and never collides with a signal.
 */
#define SC_EVENT_COMPLETION ((sc_event_id_t)0xFFFFu)

#ifdef __cplusplus
}
#endif

#endif /* SC_TYPES_H */
