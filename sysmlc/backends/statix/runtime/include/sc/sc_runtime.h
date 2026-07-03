#ifndef SC_RUNTIME_H
#define SC_RUNTIME_H

/*
 * sc_runtime.h - Machine-agnostic statechart runtime support.
 *
 * The generated <prefix>.c unit owns dispatch because it must call that
 * statechart's static guard/action switches without function pointers. This
 * shared runtime only defines common table shapes and the mutable instance
 * record that generated code embeds in its public <prefix>_t type.
 */

#include "sc/sc_event.h"
#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Absolute upper bound on the number of transitions a generated dispatcher will
 * scan. Override at compile time with -DSC_MAX_TRANSITIONS=N if a chart
 * legitimately needs it.
 */
#ifndef SC_MAX_TRANSITIONS
#define SC_MAX_TRANSITIONS 256u
#endif

/*
 * Upper bound on completion (eventless) micro-steps taken after init and after
 * each dispatch. The generated dispatcher reports SC_STATUS_STEP_LIMIT when the
 * bound is exceeded.
 */
#ifndef SC_MAX_RTC_STEPS
#define SC_MAX_RTC_STEPS 64u
#endif

/*
 * One row of a generated transition table.
 *
 *   source -- event [guard] / action --> target
 *
 * guard == SC_GUARD_NONE   means the transition is always enabled.
 * action == SC_ACTION_NONE means the transition has no effect.
 */
typedef struct sc_transition_s {
    sc_state_id_t source;
    sc_event_id_t event;
    sc_guard_id_t guard;
    sc_action_id_t action;
    sc_state_id_t target;
} sc_transition_t;

/*
 * The generated per-state action table. One row per state, indexed by state id.
 */
typedef struct sc_state_def_s {
    sc_action_id_t entry_action;
    sc_action_id_t exit_action;
} sc_state_def_t;

/*
 * A complete, immutable machine definition. Generated as `static const`.
 */
typedef struct sc_machine_s {
    const sc_transition_t *transitions;
    const sc_state_def_t *states;
    uint16_t transition_count;
    sc_state_id_t state_count;
    sc_state_id_t initial_state;
} sc_machine_t;

/*
 * Common mutable runtime state. Generated <prefix>_t types embed this value.
 */
typedef struct sc_runtime_s {
    const sc_machine_t *machine;
    void *user_data;
    sc_state_id_t current_state;
    bool initialized;
} sc_runtime_t;

/*
 * Binds a runtime instance to an immutable generated machine definition and the
 * caller-owned context pointer. It does not run entry actions or completion
 * transitions; the generated statechart unit owns those machine-specific calls.
 */
sc_status_t sc_runtime_bind(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data);

/*
 * Writes the current state id to *out_state.
 * Returns SC_STATUS_INVALID_ARGUMENT on NULL/uninitialized input.
 */
sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state);

#ifdef __cplusplus
}
#endif

#endif /* SC_RUNTIME_H */
