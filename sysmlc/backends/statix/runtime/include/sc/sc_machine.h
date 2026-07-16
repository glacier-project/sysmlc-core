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
/// - SC_MACHINE_HAS_WHEN: define when the machine has a change (`when`)
///   trigger. No paired required macro, unlike SC_MACHINE_HAS_TIMER --
///   arming/condition/consumption are ordinary guards/actions through the
///   existing SC_MACHINE_GUARD/_ACTION switches. Instantiates a public
///   _settle.
///
/// No include guard on purpose. Do not include this header directly.
#if !defined(SC_MACHINE_PREFIX) || !defined(SC_MACHINE_DEF) || \
    !defined(SC_MACHINE_GUARD) || !defined(SC_MACHINE_ACTION) || \
    !defined(SC_MACHINE_ACTIVE_CAPACITY)
#error "sc/sc_machine.h: define SC_MACHINE_PREFIX/_DEF/_GUARD/_ACTION/_ACTIVE_CAPACITY first"
#endif
#if defined(SC_MACHINE_HAS_TIMER) && !defined(SC_MACHINE_TIMEOUT_DUE)
#error "sc/sc_machine.h: SC_MACHINE_HAS_TIMER requires SC_MACHINE_TIMEOUT_DUE"
#endif
#if defined(SC_MACHINE_HAS_TRACE) && !defined(SC_MACHINE_TRACE)
#error "sc/sc_machine.h: SC_MACHINE_HAS_TRACE requires SC_MACHINE_TRACE"
#endif

/// SC__TRACE_ENABLED must be defined unconditionally (design Sec.1): every
/// trace call site below writes `#if SC__TRACE_ENABLED(...)` regardless of
/// whether SC_MACHINE_HAS_TRACE is defined anywhere, so a consumer that never
/// enables tracing still needs this to expand to a valid constant `0`, not
/// leave an undefined function-like macro used as a bare identifier in `#if`.
#ifdef SC_MACHINE_HAS_TRACE
#ifndef SC_MACHINE_TRACE_MASK
#define SC_MACHINE_TRACE_MASK SC_TRACE_MASK_ALL
#endif
#define SC__TRACE_ENABLED(mask_) (((SC_MACHINE_TRACE_MASK) & (mask_)) != 0u)
#else
#define SC__TRACE_ENABLED(mask_) 0
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
static bool SC__FN(_is_ancestor)(const sc_machine_t *machine, sc_state_id_t scope,
                                 sc_state_id_t leaf);

static bool SC__FN(_has_final_descendant)(const sc_machine_t *machine, sc_state_id_t container)
{
    sc_state_id_t s;
    for (s = 0u; s < machine->state_count; ++s) {
        if (machine->states[s].is_final && SC__FN(_is_ancestor)(machine, container, s)) {
            return true;
        }
    }
    return false;
}

static bool SC__FN(_is_composite_completed)(const SC__T *sm, sc_state_id_t container)
{
    const sc_machine_t *machine = sm->runtime.machine;
    if (!SC__FN(_has_final_descendant)(machine, container)) {
        return true;
    }
    sc_state_id_t slot = machine->states[container].slot;
    sc_state_id_t leaf = sm->runtime.active[slot].leaf;
    return (leaf != SC_STATE_INVALID) && machine->states[leaf].is_final;
}

///
/// Intrinsically gates a completion transition sourced at a parallel state
/// on every direct region being in its own local final leaf (the join
/// contract, design Sec.6) -- not routed through the ordinary guard
/// mechanism, since guard_eval is defined before this file's SC__FN-mangled
/// helpers exist and cannot call one.
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
            if (enabled && (event_id == SC_EVENT_COMPLETION)) {
                if (machine->states[state].region_count > 0u) {
                    enabled = sc_runtime_regions_all_final(&sm->runtime, state);
                } else if (machine->states[state].initial_child != SC_STATE_INVALID) {
                    enabled = SC__FN(_is_composite_completed)(sm, state);
                }
            }
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
        if (event_id == SC_EVENT_COMPLETION) {
            if ((machine->states[s].region_count > 0u) &&
                !sc_runtime_regions_all_final(&sm->runtime, s)) {
                break;
            }
        }
        idx = SC__FN(_find_transition_at)(machine, s, event_id, sm, event);
        if (idx >= 0) {
            return idx;
        }
        s = machine->states[s].parent;
    }
    return -1;
}

/// @brief Inner-first selection bounded at (excluding) `stop` -- one region's own search.
static int32_t SC__FN(_find_transition_bounded)(const sc_machine_t *machine,
                                                sc_state_id_t leaf, sc_state_id_t stop,
                                                sc_event_id_t event_id,
                                                const SC__T *sm, const sc_event_t *event)
{
    sc_state_id_t s = leaf;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        int32_t idx;
        if ((s == SC_STATE_INVALID) || (s == stop)) {
            break;
        }
        if (event_id == SC_EVENT_COMPLETION) {
            if ((machine->states[s].region_count > 0u) &&
                !sc_runtime_regions_all_final(&sm->runtime, s)) {
                break;
            }
        }
        idx = SC__FN(_find_transition_at)(machine, s, event_id, sm, event);
        if (idx >= 0) {
            return idx;
        }
        s = machine->states[s].parent;
    }
    return -1;
}

/// @brief Walk up from `leaf` to the nearest ancestor whose own parent is a
/// parallel container; return that parent (the fork point owning `leaf`'s
/// region), or SC_STATE_INVALID if `leaf` is not inside any region.
static sc_state_id_t SC__FN(_region_boundary)(const sc_machine_t *machine, sc_state_id_t leaf)
{
    sc_state_id_t s = leaf;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        sc_state_id_t parent;
        if (s == SC_STATE_INVALID) {
            break;
        }
        parent = machine->states[s].parent;
        if ((parent != SC_STATE_INVALID) && (machine->states[parent].region_count > 0u)) {
            return parent;
        }
        s = parent;
    }
    return SC_STATE_INVALID;
}

/// @brief One selected (activation slot, transition row index) pair.
#ifndef SC_MACHINE_SELECTED_T_DEFINED
#define SC_MACHINE_SELECTED_T_DEFINED
typedef struct sc_selected_s {
    sc_state_id_t slot;
    int32_t transition;
} sc_selected_t;
#endif

/// @brief Collect this step's candidate transitions for `event_id`.
///
/// Phase 1: each active region (slot > 0) tries its own bounded inner-first
/// search, stopped at (excluding) the parallel state that owns it. Phase 2
/// (trunk/group) is tried only if phase 1 found nothing at all -- exploits
/// the single-fork-level restriction (design Sec.4.2): region-local sources
/// never share an ancestor with each other, only with the trunk above the
/// one active fork point, so no cross-region shadowing bookkeeping is
/// needed. Pinned against Sismic's own broadcast semantics (design Sec.4.1).
static uint16_t SC__FN(_select)(const SC__T *sm, sc_event_id_t event_id,
                                const sc_event_t *event, sc_selected_t *out)
{
    const sc_machine_t *machine = sm->runtime.machine;
    uint16_t count = 0u;
    sc_state_id_t i;
    for (i = 0u; i < (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY; ++i) {
        sc_state_id_t leaf = sm->runtime.active[i].leaf;
        sc_state_id_t stop;
        int32_t idx;
        if (leaf == SC_STATE_INVALID) {
            continue;
        }
        stop = SC__FN(_region_boundary)(machine, leaf);
        if (stop == SC_STATE_INVALID) {
            continue;
        }
        idx = SC__FN(_find_transition_bounded)(machine, leaf, stop, event_id, sm, event);
        if (idx >= 0) {
            out[count].slot = i;
            out[count].transition = idx;
            ++count;
        }
    }
    if (count > 0u) {
        return count;
    }
    {
        int32_t idx = SC__FN(_find_transition)(machine, sm->runtime.active[0].leaf,
                                               event_id, sm, event);
        if (idx >= 0) {
            out[0].slot = 0u;
            out[0].transition = idx;
            return 1u;
        }
    }
    return 0u;
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
#if SC__TRACE_ENABLED(SC_TRACE_MASK_EXIT)
        {
            const sc_trace_data_t trace_data = {
                .state = s, .activation_index = machine->states[s].slot,
            };
            SC_MACHINE_TRACE(SC_TRACE_EXIT, &sm->runtime, event, &trace_data);
        }
#endif
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
#if SC__TRACE_ENABLED(SC_TRACE_MASK_ENTER)
        {
            const sc_trace_data_t trace_data = {
                .state = path[n], .activation_index = machine->states[path[n]].slot,
            };
            SC_MACHINE_TRACE(SC_TRACE_ENTER, &sm->runtime, event, &trace_data);
        }
#endif
        status = SC__FN(_run_state_action)(sm, machine->states[path[n]].entry_action, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_OK;
}


/// @brief Descend an ordinary (non-parallel) chain into initial children
/// until a leaf or a parallel container is reached; write it to *out_leaf.
/// Never forks -- callers detect region_count > 0 on the result and fork
/// themselves (design Sec.4.4).
static sc_status_t SC__FN(_descend_chain)(SC__T *sm, sc_state_id_t start,
                                          const sc_event_t *event, sc_state_id_t *out_leaf)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t cur = start;
    uint16_t guard;
    for (guard = 0u; guard < (uint16_t)SC_MAX_DEPTH; ++guard) {
        sc_state_id_t child;
        sc_status_t status;
        if (machine->states[cur].region_count > 0u) {
            break;
        }
        child = machine->states[cur].initial_child;
        if (child == SC_STATE_INVALID) {
            break;
        }
        cur = child;
#if SC__TRACE_ENABLED(SC_TRACE_MASK_ENTER)
        {
            const sc_trace_data_t trace_data = {
                .state = cur, .activation_index = machine->states[cur].slot,
            };
            SC_MACHINE_TRACE(SC_TRACE_ENTER, &sm->runtime, event, &trace_data);
        }
#endif
        status = SC__FN(_run_state_action)(sm, machine->states[cur].entry_action, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    *out_leaf = cur;
    return SC_STATUS_OK;
}


/// @brief Descend into `start`, forking into every region if it (or the
/// chain below it) lands on a parallel container. Writes the trunk-level
/// result (a true leaf, or a parallel container's own id -- design Sec.4.4,
/// Sec.7) to *out_leaf, and writes every forked region's own leaf into its
/// own activation slot.
static sc_status_t SC__FN(_descend)(SC__T *sm, sc_state_id_t start,
                                    const sc_event_t *event, sc_state_id_t *out_leaf)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_status_t status = SC__FN(_descend_chain)(sm, start, event, out_leaf);
    sc_state_id_t cur = *out_leaf;
    sc_state_id_t r;
    if (status != SC_STATUS_OK) {
        return status;
    }
    if (machine->states[cur].region_count == 0u) {
        return SC_STATUS_OK;
    }
    for (r = 0u; r < machine->states[cur].region_count; ++r) {
        sc_state_id_t root = machine->regions[(size_t)(machine->states[cur].region_first + r)];
        sc_state_id_t region_leaf;
        sc_state_id_t slot;
#if SC__TRACE_ENABLED(SC_TRACE_MASK_ENTER)
        {
            const sc_trace_data_t trace_data = {
                .state = root, .activation_index = machine->states[root].slot,
            };
            SC_MACHINE_TRACE(SC_TRACE_ENTER, &sm->runtime, event, &trace_data);
        }
#endif
        status = SC__FN(_run_state_action)(sm, machine->states[root].entry_action, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
        status = SC__FN(_descend_chain)(sm, root, event, &region_leaf);
        if (status != SC_STATUS_OK) {
            return status;
        }
        slot = machine->states[root].slot;
        sm->runtime.active[slot].leaf = region_leaf;
        sm->runtime.active[slot].entered_at = sm->runtime.now;
        sm->runtime.active[slot].timeout_delivered = false;
    }

    return SC_STATUS_OK;
}

/// @brief Fire a region-local transition against one activation slot.
static sc_status_t SC__FN(_take_transition_region)(SC__T *sm, sc_state_id_t slot,
                                                   const sc_transition_t *t,
                                                   const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t scope;
    sc_state_id_t leaf;
    sc_status_t status;
#if SC__TRACE_ENABLED(SC_TRACE_MASK_TRANSITION)
    {
        const sc_trace_data_t trace_data = {
            .source = t->source, .target = t->target,
            .transition_index = (int32_t)(t - machine->transitions),
            .action = t->action, .activation_index = slot,
        };
        SC_MACHINE_TRACE(SC_TRACE_TRANSITION, &sm->runtime, event, &trace_data);
    }
#endif
    if (t->target == SC_STATE_INVALID) {
        if (t->action != SC_ACTION_NONE) {
            return SC_MACHINE_ACTION(t->action, &sm->runtime, event);
        }
        return SC_STATUS_OK;
    }

    scope = (t->source == t->target)
                ? machine->states[t->source].parent
                : SC__FN(_lca)(machine, t->source, t->target);
    status = SC__FN(_exit_up_to)(sm, sm->runtime.active[slot].leaf, scope, event);
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
    if ((machine->states[leaf].region_count == 0u) ||
        (machine->states[machine->regions[machine->states[leaf].region_first]].slot != slot)) {
        sm->runtime.active[slot].leaf = leaf;
        sm->runtime.active[slot].entered_at = sm->runtime.now;
        sm->runtime.active[slot].timeout_delivered = false;
    }
    return SC_STATUS_OK;
}

/// @brief Fire a group transition sourced at (or above) an active parallel state.
///
/// Exits every currently active region under the fork point once each
/// (clearing their slots), then does one ordinary single-chain trunk exit
/// (unmodified `_exit_up_to`, starting from wherever the trunk actually sits
/// -- the fork point's own id, per `_descend`'s Sec.4.4 contract), one
/// effect, one entry (forking again via `_descend` if the target is itself
/// parallel). Matches Sismic's single multi-state MicroStep phase order
/// (design Sec.4.1).
static sc_status_t SC__FN(_take_transition_group)(SC__T *sm, const sc_transition_t *t,
                                                  const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_state_id_t scope;
    sc_state_id_t leaf;
    sc_status_t status;
    sc_state_id_t i;
#if SC__TRACE_ENABLED(SC_TRACE_MASK_TRANSITION)
    {
        const sc_trace_data_t trace_data = {
            .source = t->source, .target = t->target,
            .transition_index = (int32_t)(t - machine->transitions),
            .action = t->action, .activation_index = 0u,
        };
        SC_MACHINE_TRACE(SC_TRACE_TRANSITION, &sm->runtime, event, &trace_data);
    }
#endif
    if (t->target == SC_STATE_INVALID) {
        if (t->action != SC_ACTION_NONE) {
            return SC_MACHINE_ACTION(t->action, &sm->runtime, event);
        }
        return SC_STATUS_OK;
    }

    scope = (t->source == t->target)
                ? machine->states[t->source].parent
                : SC__FN(_lca)(machine, t->source, t->target);
    for (i = 1u; i < (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY; ++i) {
        if (sm->runtime.active[i].leaf == SC_STATE_INVALID) {
            continue;
        }
        status = SC__FN(_exit_up_to)(
            sm, sm->runtime.active[i].leaf,
            SC__FN(_region_boundary)(machine, sm->runtime.active[i].leaf), event);
        if (status != SC_STATUS_OK) {
            return status;
        }
        sm->runtime.active[i].leaf = SC_STATE_INVALID;
        sm->runtime.active[i].entered_at = 0u;
        sm->runtime.active[i].timeout_delivered = false;
    }
    status = SC__FN(_exit_up_to)(sm, sm->runtime.active[0].leaf, scope, event);
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
    if ((machine->states[leaf].region_count == 0u) ||
        (machine->states[machine->regions[machine->states[leaf].region_first]].slot != 0u)) {
        sm->runtime.active[0].leaf = leaf;
        sm->runtime.active[0].entered_at = sm->runtime.now;
        sm->runtime.active[0].timeout_delivered = false;
    }
    return SC_STATUS_OK;
}

/// @brief Fire every row `_select` returned, region-local rows by their own
/// slot, the one possible group row (always reported at slot 0) via the
/// group path. `_select` guarantees these two cases are mutually exclusive.
static sc_status_t SC__FN(_fire_selected)(SC__T *sm, const sc_selected_t *selected,
                                          uint16_t count, const sc_event_t *event)
{
    const sc_machine_t *machine = sm->runtime.machine;
    uint16_t k;
    for (k = 0u; k < count; ++k) {
        sc_status_t status;
        const sc_transition_t *row = &machine->transitions[(size_t)selected[k].transition];
        status = (SC__FN(_region_boundary)(machine, row->source) == SC_STATE_INVALID)
                     ? SC__FN(_take_transition_group)(sm, row, event)
                     : SC__FN(_take_transition_region)(sm, selected[k].slot, row, event);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_OK;
}

static sc_status_t SC__FN(_run_completion)(SC__T *sm)
{
    sc_event_t completion;
    uint16_t step;
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    for (step = 0u; step < (uint16_t)SC_MAX_RTC_STEPS; ++step) {
        sc_selected_t selected[SC_MACHINE_ACTIVE_CAPACITY];
        uint16_t count = SC__FN(_select)(sm, SC_EVENT_COMPLETION, &completion, selected);
        sc_status_t status;
        if (count == 0u) {
            return SC_STATUS_OK;
        }
        status = SC__FN(_fire_selected)(sm, selected, count, &completion);
        if (status != SC_STATUS_OK) {
            return status;
        }
    }
    return SC_STATUS_STEP_LIMIT;
}

static sc_status_t SC__FN(_drain_internal)(SC__T *sm)
{
    uint16_t step;
    if (sm->runtime.queue == NULL) {
        return SC_STATUS_OK;
    }
    for (step = 0u; step < (uint16_t)SC_MAX_RTC_STEPS; ++step) {
        sc_event_t event;
        sc_status_t status;
        sc_selected_t selected[SC_MACHINE_ACTIVE_CAPACITY];
        uint16_t count;
        if (sc_event_queue_is_empty(sm->runtime.queue)) {
            return SC_STATUS_OK;
        }
        status = sc_event_queue_pop(sm->runtime.queue, &event);
        if (status != SC_STATUS_OK) {
            return status;
        }
        count = SC__FN(_select)(sm, event.id, &event, selected);
        status = SC__FN(_fire_selected)(sm, selected, count, &event);
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

static sc_status_t SC__FN(_check_invariants)(SC__T *sm)
{
    const sc_machine_t *machine = sm->runtime.machine;
    sc_event_t completion;
    uint16_t k;
    (void)sc_event_init(&completion, SC_EVENT_COMPLETION);
    for (k = 0u; k < machine->invariant_count; ++k) {
        const sc_invariant_t *inv = &machine->invariants[k];
        bool active = (inv->scope == SC_STATE_INVALID);
        if (!active) {
            sc_state_id_t i;
            for (i = 0u; i < (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY; ++i) {
                sc_state_id_t leaf = sm->runtime.active[i].leaf;
                if ((leaf != SC_STATE_INVALID) &&
                    SC__FN(_is_ancestor)(machine, inv->scope, leaf)) {
                    active = true;
                    break;
                }
            }
        }
        if (active && !SC_MACHINE_GUARD(inv->guard, &sm->runtime, &completion)) {
            return SC_STATUS_CONSTRAINT_VIOLATED;
        }
    }
    return SC_STATUS_OK;
}

sc_status_t SC__FN(_init)(SC__T *sm, SC__CTX *ctx)
{
    sc_status_t status;
    sc_event_t completion;
    if ((sm == NULL) || (ctx == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    status = sc_runtime_bind(&sm->runtime, &SC_MACHINE_DEF, ctx, sm->active,
                             (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY);
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
#if SC__TRACE_ENABLED(SC_TRACE_MASK_ENTER)
    {
        const sc_trace_data_t trace_data = {
            .state = SC_MACHINE_DEF.initial_state,
            .activation_index = SC_MACHINE_DEF.states[SC_MACHINE_DEF.initial_state].slot,
        };
        SC_MACHINE_TRACE(SC_TRACE_ENTER, &sm->runtime, &completion, &trace_data);
    }
#endif
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
        if ((SC_MACHINE_DEF.states[leaf].region_count == 0u) ||
            (SC_MACHINE_DEF.states[SC_MACHINE_DEF.regions[SC_MACHINE_DEF.states[leaf].region_first]].slot != 0u)) {
            sm->runtime.active[0].leaf = leaf;
            sm->runtime.active[0].entered_at = sm->runtime.now;
            sm->runtime.active[0].timeout_delivered = false;
        }
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

sc_status_t SC__FN(_dispatch)(SC__T *sm, const sc_event_t *event)
{
    const sc_machine_t *machine;
    sc_selected_t selected[SC_MACHINE_ACTIVE_CAPACITY];
    uint16_t count;
    sc_status_t status;
    if ((sm == NULL) || (event == NULL) || (!sm->runtime.initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    machine = sm->runtime.machine;
    if ((machine == NULL) || (machine->transitions == NULL) ||
        (machine->states == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    count = SC__FN(_select)(sm, event->id, event, selected);
    if (count == 0u) {
        status = SC__FN(_check_invariants)(sm);
        return (status != SC_STATUS_OK) ? status : SC_STATUS_NO_TRANSITION;
    }
    status = SC__FN(_fire_selected)(sm, selected, count, event);
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

#ifdef SC_MACHINE_HAS_WHEN
/// @brief Re-check completion transitions after external context mutation.
///
/// Hosts must call this after mutating context state that a `when` (change
/// trigger) condition reads, whenever no event dispatch already covers it --
/// an ordinary _dispatch/_post call already runs _run_completion internally
/// and needs no extra _settle call.
/// @param sm Statechart instance to settle.
/// @return SC_STATUS_OK on success (including "nothing to settle"), or an
///         error status.
sc_status_t SC__FN(_settle)(SC__T *sm)
{
    sc_status_t status;
    if ((sm == NULL) || (!sm->runtime.initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
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
#endif

#ifdef SC_MACHINE_HAS_TIMER
sc_status_t SC__FN(_tick)(SC__T *sm, sc_time_t now)
{
    const sc_machine_t *machine;
    sc_status_t status;
    sc_state_id_t due[SC_MACHINE_ACTIVE_CAPACITY];
    uint16_t due_count = 0u;
    sc_state_id_t i;
    sc_event_t timeout;
    bool fired_any = false;
    if ((sm == NULL) || (!sm->runtime.initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (now < sm->runtime.now) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    sm->runtime.now = now;
    machine = sm->runtime.machine;
    (void)sc_event_init(&timeout, SC_EVENT_TIMEOUT);
    for (i = 0u; i < (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY; ++i) {
        sc_activation_t *a = &sm->runtime.active[i];
        if ((a->leaf == SC_STATE_INVALID) || a->timeout_delivered) {
            continue;
        }
        if (SC_MACHINE_TIMEOUT_DUE(a->leaf, &sm->runtime, i)) {
            a->timeout_delivered = true;
            due[due_count] = i;
            ++due_count;
        }
    }
    for (i = 0u; i < (sc_state_id_t)due_count; ++i) {
        sc_state_id_t slot = due[i];
        int32_t idx = SC__FN(_find_transition_at)(machine, sm->runtime.active[slot].leaf,
                                                  SC_EVENT_TIMEOUT, sm, &timeout);
        if (idx >= 0) {
            status = SC__FN(_take_transition_region)(
                sm, slot, &machine->transitions[(size_t)idx], &timeout);
            if (status != SC_STATUS_OK) {
                return status;
            }
            fired_any = true;
        }
    }
    if (!fired_any) {
        status = SC__FN(_check_invariants)(sm);
        return (status != SC_STATUS_OK) ? status : SC_STATUS_NO_TRANSITION;
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
#endif

/// @brief Return the current active state id.
///
/// For a non-parallel machine, always a true leaf (unchanged behavior). For
/// a parallel-bearing machine, while a parallel container is forked, this
/// returns *the container's own id*, not a leaf -- use `_active_count`/
/// `_active_state` to see the actual active leaves (design Sec.7).
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
    s = sm->runtime.active[0].leaf;
    if ((machine == NULL) || (s >= machine->state_count)) {
        return false;
    }
    return machine->states[s].is_final &&
           ((machine->states[s].parent == SC_STATE_INVALID) ||
            (machine->states[s].parent == machine->initial_state));
}

/// @brief Number of currently active TRUE leaves.
///
/// Excludes a forked parallel container's own bookkeeping entry in slot 0
/// (it is never itself a leaf) -- Sismic's own configuration never lists an
/// orthogonal state's own name either, only its regions' actual leaves
/// (design Sec.8).
/// @param sm Statechart instance to inspect.
/// @return Count of active true leaves, or 0 before initialization.
sc_state_id_t SC__FN(_active_count)(const SC__T *sm)
{
    const sc_machine_t *machine;
    sc_state_id_t i;
    sc_state_id_t count = 0u;
    if ((sm == NULL) || (!sm->runtime.initialized)) {
        return 0u;
    }
    machine = sm->runtime.machine;
    for (i = 0u; i < (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY; ++i) {
        sc_state_id_t leaf = sm->runtime.active[i].leaf;
        if ((leaf != SC_STATE_INVALID) && (machine->states[leaf].region_count == 0u)) {
            ++count;
        }
    }
    return count;
}

/// @brief The k-th currently active true leaf, in ascending slot order.
///
/// A compacting, filtered index -- NOT raw `active[k]` (design Sec.8): slot
/// `k` itself may be invalid or hold a non-leaf fork-point marker while a
/// later slot holds a valid leaf.
/// @param sm Statechart instance to inspect.
/// @param index Which active leaf to return, `0 <= index < _active_count(sm)`.
/// @return The index-th active leaf, or SC_STATE_INVALID if out of range.
sc_state_id_t SC__FN(_active_state)(const SC__T *sm, sc_state_id_t index)
{
    const sc_machine_t *machine;
    sc_state_id_t i;
    sc_state_id_t seen = 0u;
    if ((sm == NULL) || (!sm->runtime.initialized)) {
        return SC_STATE_INVALID;
    }
    machine = sm->runtime.machine;
    for (i = 0u; i < (sc_state_id_t)SC_MACHINE_ACTIVE_CAPACITY; ++i) {
        sc_state_id_t leaf = sm->runtime.active[i].leaf;
        if ((leaf != SC_STATE_INVALID) && (machine->states[leaf].region_count == 0u)) {
            if (seen == index) {
                return leaf;
            }
            ++seen;
        }
    }
    return SC_STATE_INVALID;
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
#ifdef SC_MACHINE_HAS_WHEN
#undef SC_MACHINE_HAS_WHEN
#endif
#undef SC__TRACE_ENABLED
#ifdef SC_MACHINE_HAS_TRACE
#undef SC_MACHINE_HAS_TRACE
#undef SC_MACHINE_TRACE
#undef SC_MACHINE_TRACE_MASK
#endif
#undef SC_MACHINE_ACTIVE_CAPACITY

