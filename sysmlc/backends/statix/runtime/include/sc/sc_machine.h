/*
 * sc/sc_machine.h - Shared statechart dispatch, instantiated per machine.
 *
 * A generated <prefix>.c defines its static const tables, a static
 * <prefix>_guard_eval and <prefix>_action_exec, then sets the SC_MACHINE_*
 * macros and includes this header ONCE. That instantiates the machine's public
 * API (<prefix>_init/_dispatch/_post/_get_state) with the dispatch algorithm
 * below, calling the file-local static guard/action directly -- no function
 * pointers, one audited algorithm shared by every generated machine.
 *
 * Required macros (the generated unit defines them before including):
 *   SC_MACHINE_PREFIX  the machine prefix token, e.g. sm01_machine
 *   SC_MACHINE_DEF     the static const sc_machine_t, e.g. sm01_machine_machine
 *   SC_MACHINE_GUARD   the static guard evaluator, e.g. sm01_machine_guard_eval
 *   SC_MACHINE_ACTION  the static action executor, e.g. sm01_machine_action_exec
 *
 * No include guard on purpose. Do not include this header directly.
 */
#if !defined(SC_MACHINE_PREFIX) || !defined(SC_MACHINE_DEF) || \
    !defined(SC_MACHINE_GUARD) || !defined(SC_MACHINE_ACTION)
#error "sc/sc_machine.h: define SC_MACHINE_PREFIX/_DEF/_GUARD/_ACTION first"
#endif

#include "sc/sc_runtime.h"

#define SC__CAT2(a, b) a##b
#define SC__CAT(a, b) SC__CAT2(a, b)
#define SC__T SC__CAT(SC_MACHINE_PREFIX, _t)
#define SC__CTX SC__CAT(SC_MACHINE_PREFIX, _context_t)
#define SC__FN(suffix) SC__CAT(SC_MACHINE_PREFIX, suffix)

/* Runs a state's entry or exit action if it has one. */
static sc_status_t SC__FN(_run_state_action)(SC__T *sm, sc_action_id_t action,
                                             const sc_event_t *event)
{
    if (action == SC_ACTION_NONE) {
        return SC_STATUS_OK;
    }
    return SC_MACHINE_ACTION(action, &sm->runtime, event);
}

/* First enabled row matching (state, event_id); index or -1. */
static int32_t SC__FN(_find_transition)(const sc_machine_t *machine,
                                        sc_state_id_t state, sc_event_id_t event_id,
                                        const SC__T *sm, const sc_event_t *event)
{
    uint16_t limit = machine->transition_count;
    uint16_t i;
    if (limit > (uint16_t)SC_MAX_TRANSITIONS) {
        limit = (uint16_t)SC_MAX_TRANSITIONS;
    }
    for (i = 0u; i < limit; ++i) {
        const sc_transition_t *t = &machine->transitions[i];
        if ((t->source == state) && (t->event == event_id)) {
            bool enabled = (t->guard == SC_GUARD_NONE)
                               ? true
                               : SC_MACHINE_GUARD(t->guard, &sm->runtime, event);
            if (enabled) {
                return (int32_t)i;
            }
        }
    }
    return -1;
}

/* One transition: exit(source) -> effect -> entry(target); moves state. */
static sc_status_t SC__FN(_take_transition)(SC__T *sm, const sc_transition_t *t,
                                            const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_status_t status = SC__FN(_run_state_action)(
        sm, machine->states[sm->runtime.current_state].exit_action, event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    if (t->action != SC_ACTION_NONE) {
        status = SC_MACHINE_ACTION(t->action, &sm->runtime, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    sm->runtime.current_state = t->target;
    return SC__FN(_run_state_action)(
        sm, machine->states[t->target].entry_action, event);
}

/* Fires completion transitions until none is enabled (bounded). */
static sc_status_t SC__FN(_run_completion)(SC__T *sm)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_event_t completion;
    uint16_t step;
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    for (step = 0u; step < (uint16_t)SC_MAX_RTC_STEPS; ++step) {
        int32_t idx = SC__FN(_find_transition)(
            machine, sm->runtime.current_state, SC_EVENT_COMPLETION, sm, &completion);
        sc_status_t status;
        if (idx < 0) {
            return SC_STATUS_OK;
        }
        status = SC__FN(_take_transition)(sm, &machine->transitions[idx], &completion);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_STEP_LIMIT;
}

sc_status_t SC__FN(_init)(SC__T *sm, SC__CTX *ctx)
{
    sc_status_t status;
    sc_event_t completion;
    if ((sm == NULL) || (ctx == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    status = sc_runtime_bind(&sm->runtime, &SC_MACHINE_DEF, ctx);
    if (status != SC_STATUS_OK) {
        return status;
    }
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    status = SC__FN(_run_state_action)(
        sm, SC_MACHINE_DEF.states[SC_MACHINE_DEF.initial_state].entry_action,
        &completion);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return SC__FN(_run_completion)(sm);
}

sc_status_t SC__FN(_dispatch)(SC__T *sm, const sc_event_t *event)
{
    const sc_machine_t *machine;
    int32_t idx;
    sc_status_t status;
    if ((sm == NULL) || (event == NULL) || (!sm->runtime.initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    machine = sm->runtime.machine;
    if ((machine == NULL) || (machine->transitions == NULL) ||
        (machine->states == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    idx = SC__FN(_find_transition)(machine, sm->runtime.current_state, event->id,
                                   sm, event);
    if (idx < 0) {
        return SC_STATUS_NO_TRANSITION;
    }
    status = SC__FN(_take_transition)(sm, &machine->transitions[idx], event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return SC__FN(_run_completion)(sm);
}

sc_status_t SC__FN(_post)(SC__T *sm, sc_event_id_t event_id)
{
    sc_event_t event;
    sc_status_t status = sc_event_init(&event, event_id);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return SC__FN(_dispatch)(sm, &event);
}

sc_state_id_t SC__FN(_get_state)(const SC__T *sm)
{
    sc_state_id_t state = SC_STATE_INVALID;
    if (sm == NULL) {
        return SC_STATE_INVALID;
    }
    (void)sc_runtime_get_state(&sm->runtime, &state);
    return state;
}

#undef SC__CAT2
#undef SC__CAT
#undef SC__T
#undef SC__CTX
#undef SC__FN
#undef SC_MACHINE_PREFIX
#undef SC_MACHINE_DEF
#undef SC_MACHINE_GUARD
#undef SC_MACHINE_ACTION
