/*
 * test_runtime_timer.c - Exercises the dispatch template's `_tick` entry
 * point and the entry-reset hooks with hand-written timed machines
 * (SC_MACHINE_HAS_TIMER): non-monotonic rejection, pre-deadline
 * SC_STATUS_NO_TRANSITION, the delivered-once latch consuming a false
 * guard, and self-loop periodic rearm.
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

/*
 * tm machine (unguarded, no self-loop): idle(0) --SC_EVENT_TIMEOUT--> done(1).
 * Timeout due at 5 ticks after entry (a literal-only case: no ctx needed).
 */
typedef struct {
    int unused;
} tm_context_t;

typedef struct {
    sc_runtime_t runtime;
} tm_t;

static const sc_state_def_t tm_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false},
};

static const sc_transition_t tm_transitions[] = {
    {0u, SC_EVENT_TIMEOUT, SC_GUARD_NONE, SC_ACTION_NONE, 1u},
};

static const sc_machine_t tm_machine = {
    tm_transitions, tm_states, 1u, 2u, 0u, 1u, NULL, 0u,
};

static bool tm_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)g;
    (void)rt;
    (void)ev;
    return false;
}

static sc_status_t tm_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)a;
    (void)rt;
    (void)ev;
    return SC_STATUS_OK;
}

static bool tm_timeout_due(sc_state_id_t state, const sc_runtime_t *rt)
{
    if (state != 0u) {
        return false;
    }
    return (rt->now - rt->state_entered_at) >= 5u;
}

#define SC_MACHINE_PREFIX tm
#define SC_MACHINE_DEF tm_machine
#define SC_MACHINE_GUARD tm_guard_eval
#define SC_MACHINE_ACTION tm_action_exec
#define SC_MACHINE_HAS_TIMER 1
#define SC_MACHINE_TIMEOUT_DUE tm_timeout_due
#include "sc/sc_machine.h"

/*
 * tg machine (guarded): idle(0) --SC_EVENT_TIMEOUT[if ready]--> done(1).
 * `ready` starts false: the deadline occurrence must be consumed at delivery
 * and never retried later, even after `ready` flips true and time advances.
 */
typedef struct {
    bool ready;
} tg_context_t;

typedef struct {
    sc_runtime_t runtime;
} tg_t;

static const sc_state_def_t tg_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false},
};

static const sc_transition_t tg_transitions[] = {
    {0u, SC_EVENT_TIMEOUT, 1u, SC_ACTION_NONE, 1u},
};

static const sc_machine_t tg_machine = {
    tg_transitions, tg_states, 1u, 2u, 0u, 1u, NULL, 0u,
};

static bool tg_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    const tg_context_t *ctx = (const tg_context_t *)rt->user_data;
    (void)ev;
    if (g == 1u) {
        return ctx->ready;
    }
    return false;
}

static sc_status_t tg_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)a;
    (void)rt;
    (void)ev;
    return SC_STATUS_OK;
}

static bool tg_timeout_due(sc_state_id_t state, const sc_runtime_t *rt)
{
    if (state != 0u) {
        return false;
    }
    return (rt->now - rt->state_entered_at) >= 5u;
}

#define SC_MACHINE_PREFIX tg
#define SC_MACHINE_DEF tg_machine
#define SC_MACHINE_GUARD tg_guard_eval
#define SC_MACHINE_ACTION tg_action_exec
#define SC_MACHINE_HAS_TIMER 1
#define SC_MACHINE_TIMEOUT_DUE tg_timeout_due
#include "sc/sc_machine.h"

/*
 * sl machine (timed self-loop): idle(0) --SC_EVENT_TIMEOUT--> idle(0), entry
 * action increments a counter. Each re-entry re-arms a fresh 5-tick deadline.
 */
typedef struct {
    int32_t entries;
} sl_context_t;

typedef struct {
    sc_runtime_t runtime;
} sl_t;

static const sc_state_def_t sl_states[] = {
    {1u, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false},
};

static const sc_transition_t sl_transitions[] = {
    {0u, SC_EVENT_TIMEOUT, SC_GUARD_NONE, SC_ACTION_NONE, 0u},
};

static const sc_machine_t sl_machine = {
    sl_transitions, sl_states, 1u, 1u, 0u, 1u, NULL, 0u,
};

static bool sl_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)g;
    (void)rt;
    (void)ev;
    return false;
}

static sc_status_t sl_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    sl_context_t *ctx = (sl_context_t *)rt->user_data;
    (void)ev;
    if (a == 1u) {
        ctx->entries += 1;
        return SC_STATUS_OK;
    }
    return SC_STATUS_OK;
}

static bool sl_timeout_due(sc_state_id_t state, const sc_runtime_t *rt)
{
    (void)state;
    return (rt->now - rt->state_entered_at) >= 5u;
}

#define SC_MACHINE_PREFIX sl
#define SC_MACHINE_DEF sl_machine
#define SC_MACHINE_GUARD sl_guard_eval
#define SC_MACHINE_ACTION sl_action_exec
#define SC_MACHINE_HAS_TIMER 1
#define SC_MACHINE_TIMEOUT_DUE sl_timeout_due
#include "sc/sc_machine.h"

static void test_pre_deadline_is_no_transition(void)
{
    tm_context_t ctx = {0};
    tm_t sm;
    CHECK(tm_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(tm_get_state(&sm) == 0u);
    CHECK(tm_tick(&sm, 3u) == SC_STATUS_NO_TRANSITION);
    CHECK(tm_get_state(&sm) == 0u);
}

static void test_deadline_fires_exactly_at_threshold(void)
{
    tm_context_t ctx = {0};
    tm_t sm;
    CHECK(tm_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(tm_tick(&sm, 4u) == SC_STATUS_NO_TRANSITION);
    CHECK(tm_tick(&sm, 5u) == SC_STATUS_OK);
    CHECK(tm_get_state(&sm) == 1u);
}

static void test_non_monotonic_tick_is_rejected(void)
{
    tm_context_t ctx = {0};
    tm_t sm;
    CHECK(tm_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(tm_tick(&sm, 5u) == SC_STATUS_OK); /* fires, now done (1) */
    CHECK(tm_tick(&sm, 2u) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(tm_get_state(&sm) == 1u); /* unchanged by the rejected call */
}

static void test_false_guard_consumes_the_occurrence_permanently(void)
{
    tg_context_t ctx = {false};
    tg_t sm;
    CHECK(tg_init(&sm, &ctx) == SC_STATUS_OK);
    /* Deadline delivered at 5 with ready=false: consumed, no transition. */
    CHECK(tg_tick(&sm, 5u) == SC_STATUS_NO_TRANSITION);
    CHECK(tg_get_state(&sm) == 0u);
    /* ready flips true and time advances further: must still never fire,
     * because the latch (not the raw due-condition) gates delivery. */
    ctx.ready = true;
    CHECK(tg_tick(&sm, 50u) == SC_STATUS_NO_TRANSITION);
    CHECK(tg_get_state(&sm) == 0u);
}

static void test_self_loop_rearms_a_fresh_deadline_each_entry(void)
{
    sl_context_t ctx = {0};
    sl_t sm;
    CHECK(sl_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(ctx.entries == 1); /* initial entry */
    CHECK(sl_tick(&sm, 5u) == SC_STATUS_OK);
    CHECK(ctx.entries == 2);
    /* Only 2 ticks past the fresh deadline (7 < 5+5=10): must not fire. */
    CHECK(sl_tick(&sm, 7u) == SC_STATUS_NO_TRANSITION);
    CHECK(ctx.entries == 2);
    CHECK(sl_tick(&sm, 10u) == SC_STATUS_OK);
    CHECK(ctx.entries == 3);
}

int main(void)
{
    test_pre_deadline_is_no_transition();
    test_deadline_fires_exactly_at_threshold();
    test_non_monotonic_tick_is_rejected();
    test_false_guard_consumes_the_occurrence_permanently();
    test_self_loop_rearms_a_fresh_deadline_each_entry();

    if (g_failures == 0) {
        (void)printf("test_runtime_timer: OK\n");
        return 0;
    }
    (void)printf("test_runtime_timer: %d failure(s)\n", g_failures);
    return 1;
}
