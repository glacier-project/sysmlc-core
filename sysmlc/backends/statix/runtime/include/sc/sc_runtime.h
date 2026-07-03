#ifndef SC_RUNTIME_H
#define SC_RUNTIME_H

/*
 * sc_runtime.h - Minimal, deterministic statechart dispatcher.
 *
 * This first version supports a *flat* state machine driven by a generated
 * transition table. Hierarchical states, parallel regions, history and timers
 * are intentionally not implemented yet (see docs/sysmlv2_subset.md).
 *
 * Safety notes (Power of 10):
 *   - No dynamic memory: machine definitions are generated `static const`
 *     tables and the runtime instance is a plain value owned by the caller.
 *   - No function pointers: guard/action dispatch is performed by integer ids
 *     resolved at link time through sc_guard_eval()/sc_action_exec() (see the
 *     "Application dispatch contract" below).
 *   - The dispatch loop is bounded by a compile-time constant.
 */

#include "sc/sc_event.h"
#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Absolute upper bound on the number of transitions the dispatcher will scan.
 * This guarantees the dispatch loop terminates even if a machine definition is
 * malformed (Power of 10 rule 2: every loop has a fixed upper bound). Override
 * at compile time with -DSC_MAX_TRANSITIONS=N if a chart legitimately needs it.
 */
#ifndef SC_MAX_TRANSITIONS
#define SC_MAX_TRANSITIONS 256u
#endif

/*
 * One row of the generated transition table.
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
 * A complete, immutable machine definition. Generated as `static const`.
 */
typedef struct sc_machine_s {
    const sc_transition_t *transitions; /* generated transition table       */
    uint16_t transition_count;          /* number of rows in `transitions`  */
    sc_state_id_t state_count;          /* number of states                 */
    sc_state_id_t initial_state;        /* state entered by sc_runtime_init */
} sc_machine_t;

/*
 * A live runtime instance. This is the only mutable runtime state and it is
 * owned entirely by the caller (no hidden globals).
 */
typedef struct sc_runtime_s {
    const sc_machine_t *machine; /* borrowed, immutable machine definition */
    void *user_data;             /* opaque application context (one level) */
    sc_state_id_t current_state; /* current active state                   */
    bool initialized;            /* guards against use-before-init         */
} sc_runtime_t;

/*
 * Initializes a runtime instance for `machine`, entering its initial state.
 * `user_data` is stored verbatim and handed back to guards/actions; it may be
 * NULL. Returns SC_STATUS_INVALID_ARGUMENT on a NULL/invalid machine.
 */
sc_status_t sc_runtime_init(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data);

/*
 * Processes a single event against the current state.
 *
 * Scans the transition table for the first row matching (current_state, event)
 * whose guard is enabled, runs its action, and moves to the target state.
 *
 * Returns:
 *   SC_STATUS_OK             a transition fired (state may have changed),
 *   SC_STATUS_NO_TRANSITION  no enabled transition matched (state unchanged),
 *   SC_STATUS_INVALID_ARGUMENT on NULL/uninitialized input,
 *   or the status returned by a failing action.
 */
sc_status_t sc_runtime_dispatch(sc_runtime_t *runtime, const sc_event_t *event);

/*
 * Writes the current state id to *out_state.
 * Returns SC_STATUS_INVALID_ARGUMENT on NULL/uninitialized input.
 */
sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state);

/*
 * ---------------------------------------------------------------------------
 * Application dispatch contract (NO FUNCTION POINTERS)
 * ---------------------------------------------------------------------------
 * The runtime never stores or calls function pointers. Instead, the generated
 * application code provides the two functions below, each implemented as a
 * single bounded `switch` over integer ids. They are resolved at link time.
 *
 * This keeps dispatch fully static and analyzable at the cost of one set of
 * guard/action functions per linked program (the common case for firmware).
 *
 * The runtime only calls sc_guard_eval() when a transition's guard id is not
 * SC_GUARD_NONE, and only calls sc_action_exec() when its action id is not
 * SC_ACTION_NONE, so the generated switches never need a "none" case.
 */

/* Returns true if `guard_id` is satisfied for the given runtime/event. */
bool sc_guard_eval(sc_guard_id_t guard_id, const sc_runtime_t *runtime, const sc_event_t *event);

/* Executes `action_id`. Returns SC_STATUS_OK on success. */
sc_status_t sc_action_exec(sc_action_id_t action_id, sc_runtime_t *runtime,
                           const sc_event_t *event);

#ifdef __cplusplus
}
#endif

#endif /* SC_RUNTIME_H */
