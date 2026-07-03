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
/// exceeded.
#ifndef SC_MAX_RTC_STEPS
#define SC_MAX_RTC_STEPS 64u
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

/// @brief Generated per-state action table row, indexed by state id.
typedef struct sc_state_def_s {
    sc_action_id_t entry_action; ///< @brief Entry action id, or SC_ACTION_NONE.
    sc_action_id_t exit_action; ///< @brief Exit action id, or SC_ACTION_NONE.
} sc_state_def_t;

/// @brief Complete immutable machine definition generated as static const.
typedef struct sc_machine_s {
    const sc_transition_t *transitions; ///< @brief Generated transition table.
    const sc_state_def_t *states; ///< @brief Generated per-state table.
    uint16_t transition_count; ///< @brief Number of transition rows.
    sc_state_id_t state_count; ///< @brief Number of states.
    sc_state_id_t initial_state; ///< @brief Initial state id.
} sc_machine_t;

/// @brief Common mutable runtime state embedded by generated instances.
typedef struct sc_runtime_s {
    const sc_machine_t *machine; ///< @brief Borrowed immutable machine definition.
    void *user_data; ///< @brief Opaque caller-owned context pointer.
    sc_state_id_t current_state; ///< @brief Current active state id.
    bool initialized; ///< @brief True after successful runtime binding.
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

#ifdef __cplusplus
}
#endif

#endif /* SC_RUNTIME_H */
