/*
 * test_runtime_tick.c - Unit tests for the abstract tick type and the safe
 * seconds-to-ticks conversion helper used by generated after/at machinery:
 * sc_seconds_to_ticks rejects negative or unrepresentable values instead of
 * performing an unsafe double-to-uint32_t cast, and sc_runtime_bind seeds the
 * new timer fields to their documented defaults.
 */

#include "sc/sc_event_queue.h"
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

static const sc_state_def_t g_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t g_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, 0u},
};

static const sc_machine_t g_machine = {
    g_transitions, g_states, 1u, 1u, 0u, 1u, NULL, 0u, NULL, 0u, 1u,
};

static void test_sc_time_t_is_a_32_bit_unsigned_tick(void)
{
    CHECK(sizeof(sc_time_t) == sizeof(uint32_t));
    CHECK(SC_TIME_MAX == (sc_time_t)0xFFFFFFFFu);
}

static void test_seconds_to_ticks_normal_values(void)
{
    sc_time_t ticks = 0u;
    CHECK(sc_seconds_to_ticks(0.0, &ticks) == true);
    CHECK(ticks == 0u);
    CHECK(sc_seconds_to_ticks(5.0, &ticks) == true);
    CHECK(ticks == (sc_time_t)(5u * SC_TICKS_PER_SECOND));
    CHECK(sc_seconds_to_ticks(120.0, &ticks) == true);
    CHECK(ticks == (sc_time_t)(120u * SC_TICKS_PER_SECOND));
}

static void test_seconds_to_ticks_rejects_negative(void)
{
    sc_time_t ticks = 42u;
    CHECK(sc_seconds_to_ticks(-0.001, &ticks) == false);
    /* A rejected conversion must not touch *out_ticks. */
    CHECK(ticks == 42u);
}

static void test_seconds_to_ticks_rejects_out_of_range(void)
{
    sc_time_t ticks = 7u;
    double too_large = ((double)SC_TIME_MAX / (double)SC_TICKS_PER_SECOND) + 1.0;
    CHECK(sc_seconds_to_ticks(too_large, &ticks) == false);
    CHECK(ticks == 7u);
}

static void test_seconds_to_ticks_rejects_null_out(void)
{
    CHECK(sc_seconds_to_ticks(1.0, NULL) == false);
}

static void test_bind_seeds_timer_fields_to_defaults(void)
{
    sc_runtime_t runtime;
    sc_activation_t active[1];
    CHECK(sc_runtime_bind(&runtime, &g_machine, NULL, active, 1u) == SC_STATUS_OK);
    CHECK(runtime.now == 0u);
    CHECK(runtime.active[0].entered_at == 0u);
    CHECK(runtime.active[0].timeout_delivered == false);
}

int main(void)
{
    test_sc_time_t_is_a_32_bit_unsigned_tick();
    test_seconds_to_ticks_normal_values();
    test_seconds_to_ticks_rejects_negative();
    test_seconds_to_ticks_rejects_out_of_range();
    test_seconds_to_ticks_rejects_null_out();
    test_bind_seeds_timer_fields_to_defaults();

    if (g_failures == 0) {
        (void)printf("test_runtime_tick: OK\n");
        return 0;
    }
    (void)printf("test_runtime_tick: %d failure(s)\n", g_failures);
    return 1;
}
