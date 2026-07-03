/*
 * test_runtime_completion.c - Exercises the grown runtime: initial-entry,
 * entry/exit actions, the bounded completion (eventless) micro-step, and
 * detectable exhaustion (SC_STATUS_STEP_LIMIT).
 *
 * Defines its own dispatch contract (sc_guard_eval/sc_action_exec) inline.
 */

#include "sc/sc_runtime.h"

#include <assert.h>
#include <string.h>

typedef struct {
    bool entered_a;
    bool acted;
} ctx_t;

bool sc_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)rt;
    (void)ev;
    return g == 1u; /* guard 1 == always true (for the cycle machine) */
}

sc_status_t sc_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    ctx_t *c = (ctx_t *)rt->user_data;
    (void)ev;
    if (a == 1u) {
        c->acted = true;
    }
    if (a == 2u) {
        c->entered_a = true;
    }
    return SC_STATUS_OK;
}

int main(void)
{
    assert(strcmp(sc_status_str(SC_STATUS_STEP_LIMIT), "?") != 0);

    /* Machine 1: A --completion/act 1--> B, with A.entry = act 2. */
    {
        static const sc_transition_t t1[] = {
            {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, 1u, 1u},
        };
        static const sc_state_def_t s1[] = {
            {2u, SC_ACTION_NONE},
            {SC_ACTION_NONE, SC_ACTION_NONE},
        };
        static const sc_machine_t m1 = {t1, s1, 1u, 2u, 0u};
        ctx_t c1 = {false, false};
        sc_runtime_t rt1;
        assert(sc_runtime_init(&rt1, &m1, &c1) == SC_STATUS_OK);
        assert(rt1.current_state == 1u);
        assert(c1.entered_a && c1.acted);
    }

    /* Machine 2: A --completion[guard 1 true]--> A (cycle) => step limit. */
    {
        static const sc_transition_t t2[] = {
            {0u, SC_EVENT_COMPLETION, 1u, SC_ACTION_NONE, 0u},
        };
        static const sc_state_def_t s2[] = {
            {SC_ACTION_NONE, SC_ACTION_NONE},
        };
        static const sc_machine_t m2 = {t2, s2, 1u, 1u, 0u};
        ctx_t c2 = {false, false};
        sc_runtime_t rt2;
        assert(sc_runtime_init(&rt2, &m2, &c2) == SC_STATUS_STEP_LIMIT);
    }

    return 0;
}
