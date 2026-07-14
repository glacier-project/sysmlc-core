/*
 * test_runtime_parallel.c - Exercises the generalized dispatch template with
 * a hand-written two-region parallel machine: fork on init, region-local
 * broadcast, group interrupt with reset-on-reentry, join (all-regions-final),
 * and independent per-region after/at timers. Mirrors microwave.sysml's
 * `cooking::heating` shape at the C level. See
 * docs/superpowers/specs/2026-07-14-statix-parallel-regions-design.md
 * Sec.4, Sec.5, Sec.6.
 */

#include "sc/sc_runtime.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

/*
 * States (ids), tree:
 *   0 root (composite, initial_child=1)
 *     1 idle (leaf)
 *     2 heating (PARALLEL, region_count=2, region_first=0 -> regions[0..1] = {3, 5})
 *       3 heater (composite region root, slot=1, initial_child=4)
 *         4 warming (leaf, slot=1)
 *         6 heater_done (leaf, slot=1, is_final=true)
 *       5 turntable (composite region root, slot=2, initial_child=7)
 *         7 rotating (leaf, slot=2)
 *         8 turntable_done (leaf, slot=2, is_final=true)
 *     9 paused (leaf)
 *    10 done (leaf, is_final=true)
 *
 * Transitions:
 *   4 --TIMEOUT--> 6              (heater's own after)
 *   7 --TIMEOUT--> 8              (turntable's own after)
 *   2 --COMPLETION--> 10          (join: gated on regions_all_final)
 *   2 --PAUSE--> 9                (group interrupt)
 *   9 --RESUME--> 2               (re-fork / reset)
 *   1 --START--> 2
 */
enum {
    S_ROOT = 0, S_IDLE = 1, S_HEATING = 2, S_HEATER = 3, S_WARMING = 4,
    S_TURNTABLE = 5, S_HEATER_DONE = 6, S_ROTATING = 7, S_TURNTABLE_DONE = 8,
    S_PAUSED = 9, S_DONE = 10, S_COUNT = 11,
};
enum { E_START = 1u, E_PAUSE = 2u, E_RESUME = 3u };

static const sc_state_id_t pw_regions[] = {S_HEATER, S_TURNTABLE};

static const sc_state_def_t pw_states[] = {
    /*                    entry           exit            parent            initial_child     final  slot region_first region_count */
    /* 0 root      */    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, S_IDLE,           false, 0u, SC_STATE_INVALID, 0u},
    /* 1 idle      */    {SC_ACTION_NONE, SC_ACTION_NONE, S_ROOT,           SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    /* 2 heating   */    {SC_ACTION_NONE, SC_ACTION_NONE, S_ROOT,           SC_STATE_INVALID, false, 0u, 0u,               2u},
    /* 3 heater    */    {SC_ACTION_NONE, SC_ACTION_NONE, S_HEATING,        S_WARMING,        false, 1u, SC_STATE_INVALID, 0u},
    /* 4 warming   */    {SC_ACTION_NONE, SC_ACTION_NONE, S_HEATER,         SC_STATE_INVALID, false, 1u, SC_STATE_INVALID, 0u},
    /* 5 turntable */    {SC_ACTION_NONE, SC_ACTION_NONE, S_HEATING,        S_ROTATING,       false, 2u, SC_STATE_INVALID, 0u},
    /* 6 heater_done */  {SC_ACTION_NONE, SC_ACTION_NONE, S_HEATER,         SC_STATE_INVALID, true,  1u, SC_STATE_INVALID, 0u},
    /* 7 rotating  */    {SC_ACTION_NONE, SC_ACTION_NONE, S_TURNTABLE,      SC_STATE_INVALID, false, 2u, SC_STATE_INVALID, 0u},
    /* 8 turntable_done */ {SC_ACTION_NONE, SC_ACTION_NONE, S_TURNTABLE,    SC_STATE_INVALID, true,  2u, SC_STATE_INVALID, 0u},
    /* 9 paused    */    {SC_ACTION_NONE, SC_ACTION_NONE, S_ROOT,           SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    /* 10 done     */    {SC_ACTION_NONE, SC_ACTION_NONE, S_ROOT,           SC_STATE_INVALID, true,  0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t pw_transitions[] = {
    {S_WARMING, SC_EVENT_TIMEOUT, SC_GUARD_NONE, SC_ACTION_NONE, S_HEATER_DONE},
    {S_ROTATING, SC_EVENT_TIMEOUT, SC_GUARD_NONE, SC_ACTION_NONE, S_TURNTABLE_DONE},
    {S_HEATING, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, S_DONE},
    {S_HEATING, E_PAUSE, SC_GUARD_NONE, SC_ACTION_NONE, S_PAUSED},
    {S_PAUSED, E_RESUME, SC_GUARD_NONE, SC_ACTION_NONE, S_HEATING},
    {S_IDLE, E_START, SC_GUARD_NONE, SC_ACTION_NONE, S_HEATING},
};

static const sc_machine_t pw_machine = {
    pw_transitions, pw_states,
    (uint16_t)(sizeof(pw_transitions) / sizeof(pw_transitions[0])),
    (sc_state_id_t)S_COUNT, S_ROOT, 3u, NULL, 0u, pw_regions, 2u, 3u,
};

static bool pw_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)g;
    (void)rt;
    (void)ev;
    return true;
}

static sc_status_t pw_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)a;
    (void)rt;
    (void)ev;
    return SC_STATUS_OK;
}

static bool pw_timeout_due(sc_state_id_t state, const sc_runtime_t *rt, sc_state_id_t activation_index)
{
    /* heater (slot 1) due at tick 4; turntable (slot 2) due at tick 6 --
     * independent per-region deadlines, the microwave 0.4s/0.6s shape. */
    sc_time_t deadline = (state == S_WARMING) ? 4u : 6u;
    return (rt->now - rt->active[activation_index].entered_at) >= deadline;
}

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[3];
} pw_t;

typedef struct {
    int unused;
} pw_context_t;

#define SC_MACHINE_PREFIX pw
#define SC_MACHINE_DEF pw_machine
#define SC_MACHINE_GUARD pw_guard_eval
#define SC_MACHINE_ACTION pw_action_exec
#define SC_MACHINE_HAS_TIMER 1
#define SC_MACHINE_TIMEOUT_DUE pw_timeout_due
#define SC_MACHINE_ACTIVE_CAPACITY 3u
#include "sc/sc_machine.h"

static bool pw_configuration_has(const pw_t *sm, sc_state_id_t state)
{
    sc_state_id_t n = pw_active_count(sm);
    sc_state_id_t i;
    for (i = 0u; i < n; ++i) {
        if (pw_active_state(sm, i) == state) {
            return true;
        }
    }
    return false;
}

int main(void)
{
    pw_context_t ctx;
    pw_t sm;

    /* Init lands in idle (not yet forked): one active leaf. */
    assert(pw_init(&sm, &ctx) == SC_STATUS_OK);
    assert(pw_get_state(&sm) == S_IDLE);
    assert(pw_active_count(&sm) == 1u);

    /* START forks: both regions active, trunk slot holds `heating` itself
     * (not a true leaf), so active_count reports exactly the two region
     * leaves, not three. */
    assert(pw_post(&sm, E_START) == SC_STATUS_OK);
    assert(pw_get_state(&sm) == S_HEATING);
    assert(pw_active_count(&sm) == 2u);
    assert(pw_configuration_has(&sm, S_WARMING));
    assert(pw_configuration_has(&sm, S_ROTATING));

    /* Group interrupt: PAUSE collapses both regions back to one trunk leaf. */
    assert(pw_post(&sm, E_PAUSE) == SC_STATUS_OK);
    assert(pw_get_state(&sm) == S_PAUSED);
    assert(pw_active_count(&sm) == 1u);

    /* RESUME re-forks: both regions RESTART from their own initial child
     * (reset-on-reentry), not resumed from wherever they left off. */
    assert(pw_post(&sm, E_RESUME) == SC_STATUS_OK);
    assert(pw_get_state(&sm) == S_HEATING);
    assert(pw_active_count(&sm) == 2u);
    assert(pw_configuration_has(&sm, S_WARMING));
    assert(pw_configuration_has(&sm, S_ROTATING));

    /* Tick to 4: only heater's timer is due. Broadcasting SC_EVENT_TIMEOUT
     * must not spuriously fire turntable's (due-ness gates candidacy, not a
     * transition guard -- design Sec.5). */
    assert(pw_tick(&sm, 4u) == SC_STATUS_OK);
    assert(pw_configuration_has(&sm, S_HEATER_DONE));
    assert(pw_configuration_has(&sm, S_ROTATING));
    assert(!pw_configuration_has(&sm, S_TURNTABLE_DONE));

    /* Tick to 6: turntable's timer is now due too. Join must not have fired
     * early -- heater alone reaching final does not satisfy regions_all_final. */
    assert(pw_tick(&sm, 6u) == SC_STATUS_OK);

    /* Both regions final -> join fires -> collapses to S_DONE, is_final. */
    assert(pw_get_state(&sm) == S_DONE);
    assert(pw_is_final(&sm) == true);
    assert(pw_active_count(&sm) == 1u);

    (void)printf("test_runtime_parallel: OK\n");
    return 0;
}
