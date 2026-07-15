/*
 * test_runtime_simple.c - Unit tests for machine-agnostic runtime helpers.
 *
 * Generated statechart units own dispatch; the shared runtime only binds an
 * instance to static machine data and exposes current-state access.
 */

#define SC_RUNTIME_IMPLEMENTATION
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

enum { TS_OFF = 0, TS_ON = 1, TS_COUNT = 2 };
enum { TE_ON = 1 };

static const sc_transition_t k_transitions[] = {
    {TS_OFF, TE_ON, SC_GUARD_NONE, SC_ACTION_NONE, TS_ON},
};

static const sc_state_def_t k_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_machine_t k_machine = {
    k_transitions,
    k_states,
    (uint16_t)(sizeof(k_transitions) / sizeof(k_transitions[0])),
    TS_COUNT,
    TS_OFF,
    1u,
    NULL,
    0u,
    NULL,
    0u,
    1u,
};

static void test_bind_and_get_state(void)
{
    sc_runtime_t rt;
    sc_activation_t active[1];
    sc_state_id_t state = SC_STATE_INVALID;

    CHECK(sc_runtime_bind(NULL, &k_machine, NULL, active, 1u) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_bind(&rt, NULL, NULL, active, 1u) == SC_STATUS_INVALID_ARGUMENT);

    CHECK(sc_runtime_bind(&rt, &k_machine, NULL, active, 1u) == SC_STATUS_OK);
    rt.active[0].leaf = TS_OFF;
    CHECK(sc_runtime_get_state(&rt, &state) == SC_STATUS_OK);
    CHECK(state == TS_OFF);
}

static void test_bad_initial_state(void)
{
    static const sc_machine_t bad = {k_transitions, k_states, 1u, TS_COUNT,
                                     (sc_state_id_t)TS_COUNT, 1u, NULL, 0u, NULL, 0u, 1u};
    sc_runtime_t rt;
    sc_activation_t active[1];
    CHECK(sc_runtime_bind(&rt, &bad, NULL, active, 1u) == SC_STATUS_INVALID_ARGUMENT);
}

static void test_uninitialized_and_null(void)
{
    sc_runtime_t rt = {0};
    sc_state_id_t state;

    CHECK(sc_runtime_get_state(&rt, &state) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_get_state(NULL, &state) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_get_state(&rt, NULL) == SC_STATUS_INVALID_ARGUMENT);
}

int main(void)
{
    test_bind_and_get_state();
    test_bad_initial_state();
    test_uninitialized_and_null();

    if (g_failures == 0) {
        (void)printf("test_runtime_simple: OK\n");
        return 0;
    }
    (void)printf("test_runtime_simple: %d failure(s)\n", g_failures);
    return 1;
}
