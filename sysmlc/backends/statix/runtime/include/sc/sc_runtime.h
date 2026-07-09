#ifndef SC_RUNTIME_H
#define SC_RUNTIME_H

/// @file sc_runtime.h
/// @brief Machine-agnostic statechart runtime support.
///
/// The generated <prefix>.c unit owns dispatch because it must call that
/// statechart's static guard/action switches without function pointers. This
/// shared runtime only defines common table shapes and the mutable instance
/// record that generated code embeds in its public <prefix>_t type.

#include "sc/sc_event.h"
#include "sc/sc_event_queue.h"
#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/// @brief Absolute upper bound on transitions scanned by generated dispatch.
///
/// Override at compile time with -DSC_MAX_TRANSITIONS=N if a chart legitimately
/// needs it.
#ifndef SC_MAX_TRANSITIONS
#define SC_MAX_TRANSITIONS 256u
#endif

/// @brief Upper bound on completion micro-steps after init and dispatch.
///
/// The generated dispatcher reports SC_STATUS_STEP_LIMIT when the bound is
/// exceeded. This is a nested bound, not a single macro-step budget: the
/// internal-event drain processes up to SC_MAX_RTC_STEPS queued events, and
/// each may settle up to SC_MAX_RTC_STEPS completion micro-steps, so the
/// worst case per dispatch is SC_MAX_RTC_STEPS * SC_MAX_RTC_STEPS transition
/// takes -- still a compile-time constant.
#ifndef SC_MAX_RTC_STEPS
#define SC_MAX_RTC_STEPS 64u
#endif

/// @brief Upper bound on hierarchy depth walked or entered in one step.
///
/// Bounds every parent/initial_child walk and sizes the fixed entry-path
/// buffer in the dispatch template. Override at compile time with
/// -DSC_MAX_DEPTH=N for an unusually deep chart.
#ifndef SC_MAX_DEPTH
#define SC_MAX_DEPTH 16u
#endif

/// @brief Hard limit on invariant rows a chart may declare.
///
/// A bind-time hard cap (not merely a loop cap): an over-large or corrupt table
/// is rejected rather than having trailing invariants silently skipped.
#ifndef SC_MAX_INVARIANTS
#define SC_MAX_INVARIANTS 256u
#endif

/// @brief Ticks per second for time-triggered (after/at) transitions.
///
/// A project-wide compile-time constant, like SC_MAX_TRANSITIONS et al.:
/// every machine in one build shares one tick resolution (sc_runtime.c is
/// compiled once into a shared static library, so this cannot be a
/// per-machine generated value). Override at compile time with
/// -DSC_TICKS_PER_SECOND=N for a different resolution.
#ifndef SC_TICKS_PER_SECOND
#define SC_TICKS_PER_SECOND 1000u
#endif

/// @brief One row of a generated transition table.
///
/// Represents `source -- event [guard] / action --> target`.
typedef struct sc_transition_s {
    sc_state_id_t source; ///< @brief Source state id.
    sc_event_id_t event; ///< @brief Trigger event id.
    sc_guard_id_t guard; ///< @brief Guard id, or SC_GUARD_NONE.
    sc_action_id_t action; ///< @brief Action id, or SC_ACTION_NONE.
    sc_state_id_t target; ///< @brief Target state id.
} sc_transition_t;

/// @brief Generated per-state row, indexed by state id.
typedef struct sc_state_def_s {
    sc_action_id_t entry_action;  ///< @brief Entry action id, or SC_ACTION_NONE.
    sc_action_id_t exit_action;   ///< @brief Exit action id, or SC_ACTION_NONE.
    sc_state_id_t parent;         ///< @brief Enclosing state id, or SC_STATE_INVALID at top level.
    sc_state_id_t initial_child;  ///< @brief Descend target if composite, else SC_STATE_INVALID.
    bool is_final;                ///< @brief True for a synthesized `then done` final state.
} sc_state_def_t;

/// @brief One asserted invariant: a guard checked while its scope is active.
typedef struct sc_invariant_s {
    sc_state_id_t scope; ///< @brief Owning state id, or SC_STATE_INVALID = root (always active).
    sc_guard_id_t guard; ///< @brief Guard id whose falsehood is a constraint violation.
} sc_invariant_t;

/// @brief Complete immutable machine definition generated as static const.
typedef struct sc_machine_s {
    const sc_transition_t *transitions; ///< @brief Generated transition table.
    const sc_state_def_t *states; ///< @brief Generated per-state table.
    uint16_t transition_count; ///< @brief Number of transition rows.
    sc_state_id_t state_count; ///< @brief Number of states.
    sc_state_id_t initial_state; ///< @brief Initial state id.
    sc_state_id_t max_depth; ///< @brief Deepest root->leaf path in this chart.
    const sc_invariant_t *invariants; ///< @brief Generated invariant table (never NULL).
    uint16_t invariant_count; ///< @brief Number of invariant rows (may be 0).
} sc_machine_t;

/// @brief Common mutable runtime state embedded by generated instances.
typedef struct sc_runtime_s {
    const sc_machine_t *machine; ///< @brief Borrowed immutable machine definition.
    void *user_data; ///< @brief Opaque caller-owned context pointer.
    sc_event_queue_t *queue; ///< @brief Internal-event queue, or NULL if the machine sends nothing.
    sc_state_id_t current_state; ///< @brief Current active state id.
    bool initialized; ///< @brief True after successful runtime binding.
    sc_time_t now; ///< @brief Last value passed to _tick (0 until the first call).
    sc_time_t state_entered_at; ///< @brief When the current leaf was entered, in `now`'s units.
    bool timeout_delivered; ///< @brief Has this activation's after/at occurrence already been checked?
} sc_runtime_t;

/// @brief Bind runtime state to a generated machine and caller-owned context.
///
/// Does not run entry actions or completion transitions; generated statechart
/// units own those machine-specific calls.
/// @param runtime Runtime instance to bind.
/// @param machine Immutable generated machine definition.
/// @param user_data Opaque caller-owned context pointer.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_runtime_bind(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data);

/// @brief Write the current state id to an output pointer.
/// @param runtime Runtime instance to inspect.
/// @param out_state Destination for the current state id.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state);

/// @brief Post an internal event to the runtime's queue (send effect support).
///
/// Meant for action bodies during a step: the generated dispatch drains the
/// queue before returning, so it is empty at dispatch boundaries. An event
/// hand-posted between dispatches is consumed at the start of the next
/// successful init/dispatch drain; a no-transition dispatch does not drain.
/// The event is id-only: its payload buffer is not populated.
/// @param runtime Runtime instance to post into.
/// @param event_id Event identifier to enqueue.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_FULL, or SC_STATUS_INVALID_ARGUMENT
///         (NULL runtime, or a machine with no internal-event queue).
sc_status_t sc_runtime_enqueue(sc_runtime_t *runtime, sc_event_id_t event_id);

/// @brief Post an internal event carrying one Real (double) payload value.
///
/// The scalar Real payload slot: the double's object bytes are copied into
/// the event's inline payload buffer (bounded loop, no allocation) and read
/// back by sc_event_payload_f64 on the accepting side. Same contract as
/// sc_runtime_enqueue otherwise.
/// @param runtime Runtime instance to post into.
/// @param event_id Event identifier to enqueue.
/// @param value Payload value to marshal.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_FULL, or SC_STATUS_INVALID_ARGUMENT
///         (NULL runtime, a machine with no internal-event queue, or a
///         double too large for the payload buffer).
sc_status_t sc_runtime_enqueue_f64(sc_runtime_t *runtime, sc_event_id_t event_id, double value);

/// @brief Convert SI seconds to ticks, rejecting negative or unrepresentable values.
///
/// Used by generated timeout_due functions for attribute-driven (not
/// literal) after/at durations/instants, whose value is only known at
/// runtime: rejects out-of-range input *before* the cast that would
/// otherwise silently wrap, rather than catching a bad result afterward.
/// @param seconds Duration/instant in SI seconds.
/// @param out_ticks Destination for the converted tick value.
/// @return true and writes *out_ticks on success; false (leaves *out_ticks
///         unset) if seconds is negative or would overflow sc_time_t at the
///         compiled SC_TICKS_PER_SECOND.
bool sc_seconds_to_ticks(double seconds, sc_time_t *out_ticks);

#ifdef __cplusplus
}
#endif

#endif /* SC_RUNTIME_H */
