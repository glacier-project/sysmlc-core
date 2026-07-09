/// @file sc_machine.h
/// @brief Shared statechart dispatch template, instantiated per machine.
///
/// A generated <prefix>.c defines its static const tables, a static
/// <prefix>_guard_eval and <prefix>_action_exec, then sets the SC_MACHINE_*
/// macros and includes this header once. That instantiates the machine's public
/// API (<prefix>_init/_dispatch/_post/_get_state) with the dispatch algorithm
/// below, calling the file-local static guard/action directly -- no function
/// pointers, one audited algorithm shared by every generated machine.
///
/// Required macros:
/// - SC_MACHINE_PREFIX: the machine prefix token, e.g. sm01_machine.
/// - SC_MACHINE_DEF: the static const sc_machine_t.
/// - SC_MACHINE_GUARD: the static guard evaluator.
/// - SC_MACHINE_ACTION: the static action executor.
///
/// Optional macros:
/// - SC_MACHINE_HAS_QUEUE: define when the machine's <prefix>_t embeds
///   `sc_event_queue_t queue` and `sc_event_t queue_storage[N]`; _init then
///   binds them as the internal-event queue used by send effects.
/// - SC_MACHINE_HAS_TIMER: define when the machine has a leaf-sourced
///   after/at transition; paired with the required-when-present
///   SC_MACHINE_TIMEOUT_DUE (a static bool(sc_state_id_t, const
///   sc_runtime_t *) function, never an inline macro body -- exactly the
///   SC_MACHINE_GUARD/_ACTION convention). Instantiates a public _tick.
///
/// No include guard on purpose. Do not include this header directly.
#if !defined(SC_MACHINE_PREFIX) || !defined(SC_MACHINE_DEF) || \
    !defined(SC_MACHINE_GUARD) || !defined(SC_MACHINE_ACTION)
#error "sc/sc_machine.h: define SC_MACHINE_PREFIX/_DEF/_GUARD/_ACTION first"
#endif
#if defined(SC_MACHINE_HAS_TIMER) && !defined(SC_MACHINE_TIMEOUT_DUE)
#error "sc/sc_machine.h: SC_MACHINE_HAS_TIMER requires SC_MACHINE_TIMEOUT_DUE"
#endif

#include "sc/sc_runtime.h"

#define SC__CAT2(a, b) a##b
#define SC__CAT(a, b) SC__CAT2(a, b)
#define SC__T SC__CAT(SC_MACHINE_PREFIX, _t)
#define SC__CTX SC__CAT(SC_MACHINE_PREFIX, _context_t)
#define SC__FN(suffix) SC__CAT(SC_MACHINE_PREFIX, suffix)

/// @brief Run a state's entry or exit action if it has one.
/// @param sm Statechart instance.
/// @param action Action id to execute, or SC_ACTION_NONE.
/// @param event Event associated with the action.
/// @return SC_STATUS_OK on success, or an action error status.
static sc_status_t SC__FN(_run_state_action)(SC__T *sm, sc_action_id_t action,
                                             const sc_event_t *event)
{
    if (action == SC_ACTION_NONE) {
        return SC_STATUS_OK;
    }
    return SC_MACHINE_ACTION(action, &sm->runtime, event);
}

/// @brief Find the first enabled transition sourced exactly at one state.
static int32_t SC__FN(_find_transition_at)(const sc_machine_t *machine,
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

/// @brief Inner-first selection: try the active leaf, then each ancestor.
static int32_t SC__FN(_find_transition)(const sc_machine_t *machine,
                                        sc_state_id_t leaf, sc_event_id_t event_id,
                                        const SC__T *sm, const sc_event_t *event)
{
    sc_state_id_t s = leaf;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        int32_t idx;
        if (s == SC_STATE_INVALID) {
            break;
        }
        idx = SC__FN(_find_transition_at)(machine, s, event_id, sm, event);
        if (idx >= 0) {
            return idx;
        }
        s = machine->states[s].parent;
    }
    return -1;
}

/// @brief Number of ancestors from a state up to the virtual root.
static sc_state_id_t SC__FN(_depth)(const sc_machine_t *machine, sc_state_id_t s)
{
    sc_state_id_t d = 0u;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        if (s == SC_STATE_INVALID) {
            break;
        }
        d = (sc_state_id_t)(d + 1u);
        s = machine->states[s].parent;
    }
    return d;
}

/// @brief Least common ancestor of two states (SC_STATE_INVALID = virtual root).
static sc_state_id_t SC__FN(_lca)(const sc_machine_t *machine, sc_state_id_t a,
                                  sc_state_id_t b)
{
    sc_state_id_t da = SC__FN(_depth)(machine, a);
    sc_state_id_t db = SC__FN(_depth)(machine, b);
    uint16_t guard;
    for (guard = 0u; (guard < (uint16_t)SC_MAX_DEPTH) && (da > db); ++guard) {
        a = machine->states[a].parent;
        da = (sc_state_id_t)(da - 1u);
    }
    for (guard = 0u; (guard < (uint16_t)SC_MAX_DEPTH) && (db > da); ++guard) {
        b = machine->states[b].parent;
        db = (sc_state_id_t)(db - 1u);
    }
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        if (a == b) {
            break;
        }
        a = machine->states[a].parent;
        b = machine->states[b].parent;
    }
    return a;
}

/// @brief Run exit actions from the active leaf up to (excluding) `stop`.
///
/// Returns SC_STATUS_INVALID_ARGUMENT if the walk terminates without meeting
/// `stop` (a corrupt tree: `stop` is not an ancestor of the active leaf, or the
/// depth bound was hit), rather than stopping silently at a truncated point.
static sc_status_t SC__FN(_exit_up_to)(SC__T *sm, sc_state_id_t from,
                                       sc_state_id_t stop, const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t s = from;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        sc_status_t status;
        if ((s == stop) || (s == SC_STATE_INVALID)) {
            break;
        }
        status = SC__FN(_run_state_action)(sm, machine->states[s].exit_action, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
        s = machine->states[s].parent;
    }
    if (s != stop) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    return SC_STATUS_OK;
}

/// @brief Run entry actions outer-first from (excluding) `stop` down to `target`.
///
/// Collects `target`'s ancestor chain up to `stop` first; if the walk does not
/// actually reach `stop` (a corrupt tree, or the depth bound was hit) it enters
/// nothing and returns SC_STATUS_INVALID_ARGUMENT, rather than entering a
/// truncated path. `n` cannot exceed SC_MAX_DEPTH because the loop runs at most
/// SC_MAX_DEPTH times and appends before stepping, so `path[n]` is always in
/// bounds.
static sc_status_t SC__FN(_enter_down_to)(SC__T *sm, sc_state_id_t stop,
                                          sc_state_id_t target, const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t path[SC_MAX_DEPTH];
    uint16_t n = 0u;
    sc_state_id_t s = target;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        if ((s == stop) || (s == SC_STATE_INVALID)) {
            break;
        }
        if (n < (uint16_t)SC_MAX_DEPTH) {
            path[n] = s;
            n = (uint16_t)(n + 1u);
        }
        s = machine->states[s].parent;
    }
    if (s != stop) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    while (n > 0u) {
        sc_status_t status;
        n = (uint16_t)(n - 1u);
        status = SC__FN(_run_state_action)(sm, machine->states[path[n]].entry_action, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_OK;
}

/// @brief Descend into initial children until a leaf; write it to *out_leaf.
static sc_status_t SC__FN(_descend)(SC__T *sm, sc_state_id_t start,
                                    const sc_event_t *event, sc_state_id_t *out_leaf)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t cur = start;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        sc_state_id_t child = machine->states[cur].initial_child;
        sc_status_t status;
        if (child == SC_STATE_INVALID) {
            break;
        }
        cur = child;
        status = SC__FN(_run_state_action)(sm, machine->states[cur].entry_action, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    *out_leaf = cur;
    return SC_STATUS_OK;
}

/// @brief Take one transition: exit to scope, run effect, enter target, descend.
static sc_status_t SC__FN(_take_transition)(SC__T *sm, const sc_transition_t *t,
                                            const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t scope = (t->source == t->target)
                              ? machine->states[t->source].parent
                              : SC__FN(_lca)(machine, t->source, t->target);
    sc_state_id_t leaf;
    sc_status_t status = SC__FN(_exit_up_to)(sm, sm->runtime.current_state, scope, event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    if (t->action != SC_ACTION_NONE) {
        status = SC_MACHINE_ACTION(t->action, &sm->runtime, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    status = SC__FN(_enter_down_to)(sm, scope, t->target, event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    status = SC__FN(_descend)(sm, t->target, event, &leaf);
    if (status != SC_STATUS_OK) {
        return status;
    }
    sm->runtime.current_state = leaf;
    sm->runtime.state_entered_at = sm->runtime.now;
    sm->runtime.timeout_delivered = false;
    return SC_STATUS_OK;
}

/// @brief Fire completion transitions until none is enabled, bounded.
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

/// @brief Drain internally queued events (send effects), bounded.
///
/// Pops one queued event per step: unmatched events are dropped (Sismic drops
/// unmatched internal events); a matched one is taken and its completion
/// transitions settled before the next pop. SC_MAX_RTC_STEPS bounds the loop;
/// with _run_completion's own bound the worst case is quadratic in
/// SC_MAX_RTC_STEPS -- still a compile-time constant.
static sc_status_t SC__FN(_drain_internal)(SC__T *sm)
{
    const sc_machine_t *machine = sm->runtime.machine;
    uint16_t step;
    if (sm->runtime.queue == NULL) {
        return SC_STATUS_OK;
    }
    for (step = 0u; step < (uint16_t)SC_MAX_RTC_STEPS; ++step) {
        sc_event_t event;
        sc_status_t status;
        int32_t idx;
        if (sc_event_queue_is_empty(sm->runtime.queue)) {
            return SC_STATUS_OK;
        }
        status = sc_event_queue_pop(sm->runtime.queue, &event);
        if (status != SC_STATUS_OK) {
            return status;
        }
        idx = SC__FN(_find_transition)(machine, sm->runtime.current_state,
                                       event.id, sm, &event);
        if (idx < 0) {
            continue; /* Unmatched internal event: dropped. */
        }
        status = SC__FN(_take_transition)(sm, &machine->transitions[idx], &event);
        if (status != SC_STATUS_OK) {
            return status;
        }
        status = SC__FN(_run_completion)(sm);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_STEP_LIMIT;
}

/// @brief Whether `scope` is on the active configuration (ancestor chain of leaf).
static bool SC__FN(_is_ancestor)(const sc_machine_t *machine, sc_state_id_t scope,
                                 sc_state_id_t leaf)
{
    sc_state_id_t s = leaf;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        if (s == SC_STATE_INVALID) {
            break;
        }
        if (s == scope) {
            return true;
        }
        s = machine->states[s].parent;
    }
    return false;
}

/// @brief Validate active asserted invariants after a settled macro-step.
/// @return SC_STATUS_OK if all active invariants hold, else SC_STATUS_CONSTRAINT_VIOLATED.
static sc_status_t SC__FN(_check_invariants)(SC__T *sm)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_event_t completion;
    uint16_t k;
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    for (k = 0u; k < machine->invariant_count; ++k) {
        const sc_invariant_t *inv = &machine->invariants[k];
        bool active = (inv->scope == SC_STATE_INVALID) ||
                      SC__FN(_is_ancestor)(machine, inv->scope, sm->runtime.current_state);
        if (active && !SC_MACHINE_GUARD(inv->guard, &sm->runtime, &completion)) {
            return SC_STATUS_CONSTRAINT_VIOLATED;
        }
    }
    return SC_STATUS_OK;
}

/// @brief Initialize a statechart instance and settle completion transitions.
/// @param sm Statechart instance to initialize.
/// @param ctx Caller-owned generated context.
/// @return SC_STATUS_OK on success, or an error status.
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
#ifdef SC_MACHINE_HAS_QUEUE
    status = sc_event_queue_init(
        &sm->queue, sm->queue_storage,
        (uint16_t)(sizeof(sm->queue_storage) / sizeof(sm->queue_storage[0])));
    if (status != SC_STATUS_OK) {
        return status;
    }
    sm->runtime.queue = &sm->queue;
#endif
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    status = SC__FN(_run_state_action)(
        sm, SC_MACHINE_DEF.states[SC_MACHINE_DEF.initial_state].entry_action,
        &completion);
    if (status != SC_STATUS_OK) {
        return status;
    }
    {
        sc_state_id_t leaf;
        status = SC__FN(_descend)(sm, SC_MACHINE_DEF.initial_state, &completion, &leaf);
        if (status != SC_STATUS_OK) {
            return status;
        }
        sm->runtime.current_state = leaf;
        sm->runtime.state_entered_at = sm->runtime.now;
        sm->runtime.timeout_delivered = false;
    }
    status = SC__FN(_run_completion)(sm);
    if (status != SC_STATUS_OK) {
        return status;
    }
    status = SC__FN(_drain_internal)(sm);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return SC__FN(_check_invariants)(sm);
}

/// @brief Dispatch one event into a statechart instance.
/// @param sm Statechart instance receiving the event.
/// @param event Event to dispatch.
/// @return SC_STATUS_OK if a transition fired, SC_STATUS_NO_TRANSITION if none matched, or an error status.
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
        status = SC__FN(_check_invariants)(sm);
        return (status != SC_STATUS_OK) ? status : SC_STATUS_NO_TRANSITION;
    }
    status = SC__FN(_take_transition)(sm, &machine->transitions[idx], event);
    if (status != SC_STATUS_OK) {
        return status;
    }
    status = SC__FN(_run_completion)(sm);
    if (status != SC_STATUS_OK) {
        return status;
    }
    status = SC__FN(_drain_internal)(sm);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return SC__FN(_check_invariants)(sm);
}

/// @brief Dispatch one no-payload event by id.
/// @param sm Statechart instance receiving the event.
/// @param event_id Event identifier to dispatch.
/// @return SC_STATUS_OK if a transition fired, SC_STATUS_NO_TRANSITION if none matched, or an error status.
sc_status_t SC__FN(_post)(SC__T *sm, sc_event_id_t event_id)
{
    sc_event_t event;
    sc_status_t status = sc_event_init(&event, event_id);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return SC__FN(_dispatch)(sm, &event);
}

#ifdef SC_MACHINE_HAS_TIMER
/// @brief Advance virtual time and deliver a due after/at occurrence, if any.
///
/// The host must call this with a current tick value immediately before
/// dispatching any event that might enter a time-triggered state, whenever
/// that timer's precision matters: state_entered_at is stamped from the
/// last _tick call, not a live clock read.
/// @param sm Statechart instance to advance.
/// @param now Current absolute tick value; rejected as SC_STATUS_INVALID_ARGUMENT
///        if less than the value passed to the last _tick call.
/// @return SC_STATUS_OK if a transition fired, SC_STATUS_NO_TRANSITION if
///         nothing was due (or its `if` guard failed), or an error status.
sc_status_t SC__FN(_tick)(SC__T *sm, sc_time_t now)
{
    const sc_machine_t *machine;
    sc_status_t status;
    if ((sm == NULL) || (!sm->runtime.initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (now < sm->runtime.now) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    sm->runtime.now = now;
    machine = sm->runtime.machine;
    if (!sm->runtime.timeout_delivered &&
        SC_MACHINE_TIMEOUT_DUE(sm->runtime.current_state, &sm->runtime)) {
        sc_event_t timeout;
        int32_t idx;
        sm->runtime.timeout_delivered = true;
        (void)sc_event_init(&timeout, SC_EVENT_TIMEOUT);
        idx = SC__FN(_find_transition)(machine, sm->runtime.current_state,
                                       SC_EVENT_TIMEOUT, sm, &timeout);
        if (idx >= 0) {
            status = SC__FN(_take_transition)(sm, &machine->transitions[idx], &timeout);
            if (status != SC_STATUS_OK) {
                return status;
            }
            status = SC__FN(_run_completion)(sm);
            if (status != SC_STATUS_OK) {
                return status;
            }
            status = SC__FN(_drain_internal)(sm);
            if (status != SC_STATUS_OK) {
                return status;
            }
            status = SC__FN(_check_invariants)(sm);
            return (status != SC_STATUS_OK) ? status : SC_STATUS_OK;
        }
    }
    status = SC__FN(_check_invariants)(sm);
    return (status != SC_STATUS_OK) ? status : SC_STATUS_NO_TRANSITION;
}
#endif

/// @brief Return the current active state id.
/// @param sm Statechart instance to inspect.
/// @return Active state id, or SC_STATE_INVALID before initialization.
sc_state_id_t SC__FN(_get_state)(const SC__T *sm)
{
    sc_state_id_t state = SC_STATE_INVALID;
    if (sm == NULL) {
        return SC_STATE_INVALID;
    }
    (void)sc_runtime_get_state(&sm->runtime, &state);
    return state;
}

/// @brief Whether the machine has reached a root-level final state (terminated).
/// @param sm Statechart instance to inspect.
/// @return true if the active leaf is a root-scope final state, else false.
bool SC__FN(_is_final)(const SC__T *sm)
{
    const sc_machine_t *machine;
    sc_state_id_t s;
    if ((sm == NULL) || (!sm->runtime.initialized)) {
        return false;
    }
    machine = sm->runtime.machine;
    s = sm->runtime.current_state;
    if ((machine == NULL) || (s >= machine->state_count)) {
        return false;
    }
    return machine->states[s].is_final &&
           (machine->states[s].parent == SC_STATE_INVALID);
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
#ifdef SC_MACHINE_HAS_QUEUE
#undef SC_MACHINE_HAS_QUEUE
#endif
#ifdef SC_MACHINE_HAS_TIMER
#undef SC_MACHINE_HAS_TIMER
#undef SC_MACHINE_TIMEOUT_DUE
#endif
