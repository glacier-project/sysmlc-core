/*
 * sc_runtime.c - Flat statechart dispatcher with entry/exit actions and a
 * bounded completion (eventless-transition) micro-step.
 *
 * No recursion, no goto, no function pointers, no dynamic memory. Every loop is
 * bounded by a compile-time constant. Guard/action behaviour is delegated to
 * the generated sc_guard_eval()/sc_action_exec() (resolved at link time).
 */

#include "sc/sc_runtime.h"

/* Runs a state's entry or exit action if it has one. */
static sc_status_t sc_run_state_action(sc_runtime_t *runtime, sc_action_id_t action,
                                       const sc_event_t *event)
{
    if (action == SC_ACTION_NONE) {
        return SC_STATUS_OK;
    }
    return sc_action_exec(action, runtime, event);
}

/* Finds the first enabled row matching (state, event_id); returns index or -1. */
static int32_t sc_find_transition(const sc_machine_t *machine, sc_state_id_t state,
                                  sc_event_id_t event_id, const sc_runtime_t *runtime,
                                  const sc_event_t *event)
{
    uint16_t limit = machine->transition_count;
    uint16_t i;
    if (limit > (uint16_t)SC_MAX_TRANSITIONS) {
        limit = (uint16_t)SC_MAX_TRANSITIONS;
    }
    for (i = 0u; i < limit; ++i) {
        const sc_transition_t *t = &machine->transitions[i];
        if ((t->source == state) && (t->event == event_id)) {
            bool enabled =
                (t->guard == SC_GUARD_NONE) ? true : sc_guard_eval(t->guard, runtime, event);
            if (enabled) {
                return (int32_t)i;
            }
        }
    }
    return -1;
}

/* Runs one transition: exit(source) -> effect -> entry(target); moves state. */
static sc_status_t sc_take_transition(sc_runtime_t *runtime, const sc_transition_t *t,
                                      const sc_event_t *event)
{
    const sc_machine_t *machine = runtime->machine;
    sc_status_t status;

    status = sc_run_state_action(runtime, machine->states[runtime->current_state].exit_action, event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    if (t->action != SC_ACTION_NONE) {
        status = sc_action_exec(t->action, runtime, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    runtime->current_state = t->target;
    return sc_run_state_action(runtime, machine->states[t->target].entry_action, event);
}

/* Fires completion transitions until none is enabled (bounded). */
static sc_status_t sc_run_completion(sc_runtime_t *runtime)
{
    const sc_machine_t *machine = runtime->machine;
    sc_event_t completion;
    uint16_t step;
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    for (step = 0u; step < (uint16_t)SC_MAX_RTC_STEPS; ++step) {
        int32_t idx = sc_find_transition(machine, runtime->current_state, SC_EVENT_COMPLETION,
                                         runtime, &completion);
        sc_status_t status;
        if (idx < 0) {
            return SC_STATUS_OK; /* quiescent */
        }
        status = sc_take_transition(runtime, &machine->transitions[idx], &completion);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_STEP_LIMIT; /* guarded eventless cycle: surface it */
}

sc_status_t sc_runtime_init(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data)
{
    sc_status_t status;
    sc_event_t completion;
    if ((runtime == NULL) || (machine == NULL) || (machine->transitions == NULL) ||
        (machine->states == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (machine->initial_state >= machine->state_count) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    runtime->machine = machine;
    runtime->user_data = user_data;
    runtime->current_state = machine->initial_state;
    runtime->initialized = true;

    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    status = sc_run_state_action(runtime, machine->states[machine->initial_state].entry_action,
                                 &completion);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return sc_run_completion(runtime);
}

sc_status_t sc_runtime_dispatch(sc_runtime_t *runtime, const sc_event_t *event)
{
    const sc_machine_t *machine;
    int32_t idx;
    sc_status_t status;

    if ((runtime == NULL) || (event == NULL) || (!runtime->initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    machine = runtime->machine;
    if ((machine == NULL) || (machine->transitions == NULL) || (machine->states == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }

    idx = sc_find_transition(machine, runtime->current_state, event->id, runtime, event);
    if (idx < 0) {
        return SC_STATUS_NO_TRANSITION;
    }
    status = sc_take_transition(runtime, &machine->transitions[idx], event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return sc_run_completion(runtime);
}

sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state)
{
    if ((runtime == NULL) || (out_state == NULL) || (!runtime->initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    *out_state = runtime->current_state;
    return SC_STATUS_OK;
}
