/*
 * test_runtime_internal_transition.c - Exercises the dispatch template's
 * internal-transition branch (target = SC_STATE_INVALID) and the new
 * `_settle` entry point (SC_MACHINE_HAS_WHEN) directly, with a hand-written
 * machine that mirrors the shape a `when` trigger with a false `if` guard
 * lowers to: an armed bit, a real transition, and an internal consumer.
 */

#include "sc/sc_runtime.h"

#include <stdio.h>
#include <string.h>

static int g_failures = 0;

#define CHECK(cond)                                                                                \
    do {                                                                                           \
        if (!(cond)) {                                                                             \
            (void)printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                           \
            ++g_failures;                                                                          \
        }                                                                                          \
    } while (0)

/*
 * wn machine: idle(0), running(1). idle's entry arms when_armed[0].
 * Real: idle --COMPLETION[g1: armed && hot && enabled]--> running.
 * Consumer (internal): idle --COMPLETION[g2: armed && hot && !enabled]
 *                            /a2: armed=false--> (SC_STATE_INVALID).
 * g1/g2 are mutually exclusive (partitioned by `enabled`), so table order
 * between them does not matter for correctness.
 */
typedef struct {
    bool hot;
    bool enabled;
} wn_context_t;

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
} wn_t;

static const sc_state_def_t wn_states[] = {
    {1u, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u}, /* idle: entry arms */
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u}, /* running */
};

static const sc_transition_t wn_transitions[] = {
    {0u, SC_EVENT_COMPLETION, 1u, SC_ACTION_NONE, 1u},   /* real -> running */
    {0u, SC_EVENT_COMPLETION, 2u, 2u, SC_STATE_INVALID}, /* consumer, internal */
};

static const sc_machine_t wn_machine = {
    wn_transitions, wn_states, 2u, 2u, 0u, 1u, NULL, 0u, NULL, 0u, 1u,
};

static bool wn_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    const wn_context_t *ctx = (const wn_context_t *)rt->user_data;
    (void)ev;
    if (g == 1u) {
        return rt->when_armed[0] && ctx->hot && ctx->enabled;
    }
    if (g == 2u) {
        return rt->when_armed[0] && ctx->hot && !ctx->enabled;
    }
    return false;
}

static sc_status_t wn_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)ev;
    if (a == 1u) {
        rt->when_armed[0] = true;
        return SC_STATUS_OK;
    }
    if (a == 2u) {
        rt->when_armed[0] = false;
        return SC_STATUS_OK;
    }
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX wn
#define SC_MACHINE_DEF wn_machine
#define SC_MACHINE_GUARD wn_guard_eval
#define SC_MACHINE_ACTION wn_action_exec
#define SC_MACHINE_HAS_WHEN 1
#include "sc/sc_machine.h"

static void test_internal_transition_disarms_without_changing_state(void)
{
    wn_context_t ctx;
    wn_t sm;
    sc_time_t entered_at;
    ctx.hot = true;
    ctx.enabled = false; /* consumer fires during _init's own settle */
    CHECK(wn_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(wn_get_state(&sm) == 0u); /* still idle: internal, no exit/entry */
    CHECK(sm.runtime.when_armed[0] == false); /* consumer disarmed it */
    entered_at = sm.runtime.active[0].entered_at;
    CHECK(wn_settle(&sm) == SC_STATUS_OK); /* nothing armed anymore: no-op */
    CHECK(wn_get_state(&sm) == 0u);
    CHECK(sm.runtime.active[0].entered_at == entered_at); /* untouched by internal */
}

static void test_settle_fires_the_real_transition_after_external_mutation(void)
{
    wn_context_t ctx;
    wn_t sm;
    ctx.hot = false;
    ctx.enabled = true;
    CHECK(wn_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(wn_get_state(&sm) == 0u);
    ctx.hot = true; /* external mutation, no event/tick involved */
    CHECK(wn_settle(&sm) == SC_STATUS_OK);
    CHECK(wn_get_state(&sm) == 1u); /* running: real transition fired */
}

static void test_settle_rejects_null(void)
{
    CHECK(wn_settle(NULL) == SC_STATUS_INVALID_ARGUMENT);
}

static void test_settle_rejects_uninitialized(void)
{
    wn_t sm;
    (void)memset(&sm, 0, sizeof(sm));
    CHECK(wn_settle(&sm) == SC_STATUS_INVALID_ARGUMENT);
}

int main(void)
{
    test_internal_transition_disarms_without_changing_state();
    test_settle_fires_the_real_transition_after_external_mutation();
    test_settle_rejects_null();
    test_settle_rejects_uninitialized();

    if (g_failures == 0) {
        (void)printf("test_runtime_internal_transition: OK\n");
        return 0;
    }
    (void)printf("test_runtime_internal_transition: %d failure(s)\n", g_failures);
    return 1;
}
