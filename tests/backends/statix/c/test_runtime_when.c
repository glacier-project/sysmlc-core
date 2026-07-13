/*
 * test_runtime_when.c - Unit tests for the change-trigger (`when`) runtime
 * primitives: SC_MAX_WHEN_TRIGGERS, the when_armed array, and the bind-time
 * validation change that allows SC_STATE_INVALID as a transition's target
 * (the internal-transition sentinel used by `when`'s consumer transitions;
 * see sc_machine.h's _take_transition).
 */

#include "sc/sc_runtime.h"

#include <stdio.h>

static int g_failures = 0;

#define CHECK(cond)                                                                                \
    do {                                                                                           \
        if (!(cond)) {                                                                             \
            (void)printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                           \
            ++g_failures;                                                                          \
        }                                                                                          \
    } while (0)

static const sc_state_def_t g_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false},
};

/* A single internal (target = SC_STATE_INVALID) transition, sourced at the
 * machine's only state. Before the bind-validation fix, this table would
 * have been rejected: SC_STATE_INVALID (0xFFFFu) always exceeds state_count. */
static const sc_transition_t g_internal_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, SC_STATE_INVALID},
};

static const sc_machine_t g_internal_machine = {
    g_internal_transitions, g_states, 1u, 1u, 0u, 1u, NULL, 0u,
};

static void test_bind_accepts_internal_transition_target(void)
{
    sc_runtime_t runtime;
    CHECK(sc_runtime_bind(&runtime, &g_internal_machine, NULL) == SC_STATUS_OK);
}

static const sc_transition_t g_out_of_range_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, 5u},
};

static const sc_machine_t g_out_of_range_machine = {
    g_out_of_range_transitions, g_states, 1u, 1u, 0u, 1u, NULL, 0u,
};

static void test_bind_still_rejects_a_genuinely_out_of_range_target(void)
{
    sc_runtime_t runtime;
    /* A non-sentinel out-of-range target (5, with only 1 state) must still
     * be rejected -- the fix narrows the exception to SC_STATE_INVALID only. */
    CHECK(sc_runtime_bind(&runtime, &g_out_of_range_machine, NULL) ==
          SC_STATUS_INVALID_ARGUMENT);
}

static void test_bind_zeroes_every_when_armed_slot(void)
{
    sc_runtime_t runtime;
    uint16_t i;
    CHECK(sc_runtime_bind(&runtime, &g_internal_machine, NULL) == SC_STATUS_OK);
    for (i = 0u; i < (uint16_t)SC_MAX_WHEN_TRIGGERS; ++i) {
        CHECK(runtime.when_armed[i] == false);
    }
}

static void test_sc_max_when_triggers_has_the_documented_default(void)
{
    CHECK(SC_MAX_WHEN_TRIGGERS == 64u);
}

int main(void)
{
    test_bind_accepts_internal_transition_target();
    test_bind_still_rejects_a_genuinely_out_of_range_target();
    test_bind_zeroes_every_when_armed_slot();
    test_sc_max_when_triggers_has_the_documented_default();

    if (g_failures == 0) {
        (void)printf("test_runtime_when: OK\n");
        return 0;
    }
    (void)printf("test_runtime_when: %d failure(s)\n", g_failures);
    return 1;
}
