/*
 * sc_runtime.c - Flat statechart dispatcher.
 *
 * The dispatcher is a single bounded loop over a generated transition table.
 * It contains no recursion, no goto, no function pointers and no dynamic
 * memory. Guard and action behaviour is delegated to the generated
 * sc_guard_eval()/sc_action_exec() functions (resolved at link time).
 */

#include "sc/sc_runtime.h"

sc_status_t sc_runtime_init(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data)
{
    if ((runtime == NULL) || (machine == NULL) || (machine->transitions == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    /* The initial state must be a real state of the machine. */
    if (machine->initial_state >= machine->state_count) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    runtime->machine = machine;
    runtime->user_data = user_data;
    runtime->current_state = machine->initial_state;
    runtime->initialized = true;
    return SC_STATUS_OK;
}

sc_status_t sc_runtime_dispatch(sc_runtime_t *runtime, const sc_event_t *event)
{
    const sc_machine_t *machine;
    uint16_t limit;
    uint16_t i;

    if ((runtime == NULL) || (event == NULL) || (!runtime->initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    machine = runtime->machine;
    if ((machine == NULL) || (machine->transitions == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }

    /* Clamp the scan to the compile-time bound so the loop always terminates. */
    limit = machine->transition_count;
    if (limit > (uint16_t)SC_MAX_TRANSITIONS) {
        limit = (uint16_t)SC_MAX_TRANSITIONS;
    }

    for (i = 0u; i < limit; ++i) {
        const sc_transition_t *t = &machine->transitions[i];
        if ((t->source == runtime->current_state) && (t->event == event->id)) {
            bool enabled =
                (t->guard == SC_GUARD_NONE) ? true : sc_guard_eval(t->guard, runtime, event);
            if (enabled) {
                if (t->action != SC_ACTION_NONE) {
                    sc_status_t action_status = sc_action_exec(t->action, runtime, event);
                    if (action_status != SC_STATUS_OK) {
                        return action_status;
                    }
                }
                runtime->current_state = t->target;
                return SC_STATUS_OK;
            }
        }
    }

    return SC_STATUS_NO_TRANSITION;
}

sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state)
{
    if ((runtime == NULL) || (out_state == NULL) || (!runtime->initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    *out_state = runtime->current_state;
    return SC_STATUS_OK;
}
