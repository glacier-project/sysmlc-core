/*
 * test_runtime_activation.c - Unit tests for the activation-array binding
 * contract (sc_runtime_bind) and the join intrinsic's backing helper
 * (sc_runtime_regions_all_final). See
 * docs/superpowers/specs/2026-07-14-statix-parallel-regions-design.md Sec.3.4, Sec.6.
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

/* Minimal single-activation machine (active_capacity == 1), the common case. */
static const sc_state_def_t g_flat_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t g_flat_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, 0u},
};

static const sc_machine_t g_flat_machine = {
    g_flat_transitions, g_flat_states, 1u, 1u, 0u, 1u, NULL, 0u, NULL, 0u, 1u,
};

static void test_bind_rejects_capacity_mismatch(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[2];
    CHECK(sc_runtime_bind(&runtime, &g_flat_machine, NULL, active, 2u) ==
          SC_STATUS_INVALID_ARGUMENT);
}

static void test_bind_rejects_null_active(void)
{
    sc_runtime_t runtime;
    CHECK(sc_runtime_bind(&runtime, &g_flat_machine, NULL, NULL, 1u) ==
          SC_STATUS_INVALID_ARGUMENT);
}

static void test_bind_clears_every_slot(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[1];
    active[0].leaf = 5u;
    active[0].entered_at = 99u;
    active[0].timeout_delivered = true;
    CHECK(sc_runtime_bind(&runtime, &g_flat_machine, NULL, active, 1u) == SC_STATUS_OK);
    CHECK(active[0].leaf == SC_STATE_INVALID);
    CHECK(active[0].entered_at == 0u);
    CHECK(active[0].timeout_delivered == false);
    CHECK(runtime.active == active);
    CHECK(runtime.active_capacity == 1u);
}

static void test_get_state_reads_slot_zero(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[1];
    sc_state_id_t state = SC_STATE_INVALID;
    CHECK(sc_runtime_bind(&runtime, &g_flat_machine, NULL, active, 1u) == SC_STATUS_OK);
    runtime.active[0].leaf = 0u;
    CHECK(sc_runtime_get_state(&runtime, &state) == SC_STATUS_OK);
    CHECK(state == 0u);
}

/* Machine for sc_runtime_regions_all_final: state 0 is a parallel container
 * with two regions (regions[] = {1, 3}); states 1/3 are "final" alternatives
 * for slot 1/2, states 2/4 are "not final" alternatives for the same slots. */
static const sc_state_id_t g_par_regions[] = {1u, 3u};

static const sc_state_def_t g_par_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, 0u, 2u}, /* 0: P */
    {SC_ACTION_NONE, SC_ACTION_NONE, 0u, SC_STATE_INVALID, true, 1u, SC_STATE_INVALID, 0u},  /* 1: A final */
    {SC_ACTION_NONE, SC_ACTION_NONE, 0u, SC_STATE_INVALID, false, 1u, SC_STATE_INVALID, 0u}, /* 2: A not final */
    {SC_ACTION_NONE, SC_ACTION_NONE, 0u, SC_STATE_INVALID, true, 2u, SC_STATE_INVALID, 0u},  /* 3: B final */
    {SC_ACTION_NONE, SC_ACTION_NONE, 0u, SC_STATE_INVALID, false, 2u, SC_STATE_INVALID, 0u}, /* 4: B not final */
};

static const sc_transition_t g_par_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, 0u},
};

static const sc_machine_t g_par_machine = {
    g_par_transitions, g_par_states, 1u, 5u, 0u, 1u, NULL, 0u, g_par_regions, 2u, 3u,
};

static void test_regions_all_final_true_when_both_regions_final(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[3];
    CHECK(sc_runtime_bind(&runtime, &g_par_machine, NULL, active, 3u) == SC_STATUS_OK);
    runtime.active[1].leaf = 1u; /* A final */
    runtime.active[2].leaf = 3u; /* B final */
    CHECK(sc_runtime_regions_all_final(&runtime, 0u) == true);
}

static void test_regions_all_final_false_when_one_region_not_final(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[3];
    CHECK(sc_runtime_bind(&runtime, &g_par_machine, NULL, active, 3u) == SC_STATUS_OK);
    runtime.active[1].leaf = 1u; /* A final */
    runtime.active[2].leaf = 4u; /* B NOT final */
    CHECK(sc_runtime_regions_all_final(&runtime, 0u) == false);
}

static void test_regions_all_final_false_when_region_not_entered(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[3];
    CHECK(sc_runtime_bind(&runtime, &g_par_machine, NULL, active, 3u) == SC_STATUS_OK);
    runtime.active[1].leaf = SC_STATE_INVALID; /* region not entered at all */
    runtime.active[2].leaf = 3u;
    CHECK(sc_runtime_regions_all_final(&runtime, 0u) == false);
}

int main(void)
{
    test_bind_rejects_capacity_mismatch();
    test_bind_rejects_null_active();
    test_bind_clears_every_slot();
    test_get_state_reads_slot_zero();
    test_regions_all_final_true_when_both_regions_final();
    test_regions_all_final_false_when_one_region_not_final();
    test_regions_all_final_false_when_region_not_entered();

    if (g_failures == 0) {
        (void)printf("test_runtime_activation: OK\n");
        return 0;
    }
    (void)printf("test_runtime_activation: %d failure(s)\n", g_failures);
    return 1;
}
