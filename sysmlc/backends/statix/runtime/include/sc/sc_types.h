#ifndef SC_TYPES_H
#define SC_TYPES_H

/// @file sc_types.h
/// @brief Fundamental fixed-width types for the statix statechart runtime.
///
/// Safety notes (Power of 10 / MISRA-friendly):
/// - Only fixed-width integer types from <stdint.h> are used, so storage size
///   and value ranges are explicit and identical on every target.
/// - Identifiers are unsigned integers, never pointers, so transition tables
///   stay compact, deterministic, and free of function pointers.
/// - No implementation-defined widths (no bare `int`/`unsigned` in the API).

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/// @brief State identifier type.
///
/// 16 bits comfortably covers any realistic flat or hierarchical chart for an
/// embedded target while keeping generated tables small. Widen here (and only
/// here) if a target ever needs more than 65535 states/events.
typedef uint16_t sc_state_id_t;

/// @brief Event identifier type.
typedef uint16_t sc_event_id_t;

/// @brief Transition identifier type.
typedef uint16_t sc_transition_id_t;

/// @brief Guard identifier type.
typedef uint16_t sc_guard_id_t;

/// @brief Action identifier type.
typedef uint16_t sc_action_id_t;

/// @brief Sentinel guard id meaning a transition has no guard.
#define SC_GUARD_NONE ((sc_guard_id_t)0u)

/// @brief Sentinel action id meaning a transition has no action.
#define SC_ACTION_NONE ((sc_action_id_t)0u)

/// @brief Explicit "not a real state" marker for out-parameters.
#define SC_STATE_INVALID ((sc_state_id_t)0xFFFFu)

/// @brief Explicit "not a real event" marker.
#define SC_EVENT_INVALID ((sc_event_id_t)0u)

/// @brief Reserved event id for eventless (completion) transitions.
///
/// Distinct from SC_EVENT_INVALID: real signal events are generated starting at
/// 1, so this sentinel is chosen at the top of the range and never collides
/// with a signal.
#define SC_EVENT_COMPLETION ((sc_event_id_t)0xFFFFu)

#ifdef __cplusplus
}
#endif

#endif /* SC_TYPES_H */
