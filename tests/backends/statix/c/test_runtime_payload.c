/*
 * test_runtime_payload.c - A hand-written sending machine whose guard and
 * effect read the f64 payload through the internal-event drain: a value
 * above the threshold takes the transition and is captured bit-exact; a
 * value below drops the event (consumed, source state stays active).
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

/*
 * pl machine (mirrors MachineReadablePayloadGuard/Effect):
 *   states: idle(0) armed(1) fired(2)
 *   idle  --GO/act1(send MEAS carrying ctx->current)--> armed
 *   armed --MEAS [payload > 0.5] /act2(captured := payload)--> fired
 */
#define PL_EVENT_MEAS ((sc_event_id_t)1u)
#define PL_EVENT_GO ((sc_event_id_t)2u)
#define PL_QCAP 4u

typedef struct {
    double current;
    double captured;
} pl_context_t;

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
    sc_event_queue_t queue;
    sc_event_t queue_storage[PL_QCAP];
} pl_t;

static const sc_state_def_t pl_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t pl_transitions[] = {
    {0u, PL_EVENT_GO, SC_GUARD_NONE, 1u, 1u},
    {1u, PL_EVENT_MEAS, 1u, 2u, 2u},
};

static const sc_machine_t pl_machine = {
    pl_transitions,
    pl_states,
    2u,
    3u,
    0u,
    1u,
    NULL,
    0u,
    NULL,
    0u,
    1u,
};

static bool pl_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)rt;
    if (g == 1u) {
        return sc_event_payload_f64(ev) > 0.5;
    }
    return false;
}

static sc_status_t pl_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    pl_context_t *ctx = (pl_context_t *)rt->user_data;
    if (ctx == NULL) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (a == 1u) {
        return sc_runtime_enqueue_f64(rt, PL_EVENT_MEAS, ctx->current);
    }
    if (a == 2u) {
        ctx->captured = sc_event_payload_f64(ev);
    }
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX pl
#define SC_MACHINE_DEF pl_machine
#define SC_MACHINE_GUARD pl_guard_eval
#define SC_MACHINE_ACTION pl_action_exec
#define SC_MACHINE_HAS_QUEUE 1
#define SC_MACHINE_ACTIVE_CAPACITY 1u
#include "sc/sc_machine.h"

static void test_payload_above_threshold_fires_and_captures(void)
{
    pl_context_t ctx = {0.9, 0.0};
    pl_t sm;
    CHECK(pl_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(pl_get_state(&sm) == 0u);
    CHECK(pl_post(&sm, PL_EVENT_GO) == SC_STATUS_OK);
    /* GO -> armed, send drained, guard 0.9 > 0.5 -> fired, captured. */
    CHECK(pl_get_state(&sm) == 2u);
    CHECK(ctx.captured == 0.9); /* bit-exact roundtrip */
    CHECK(sc_event_queue_is_empty(sm.runtime.queue));
}

static void test_payload_below_threshold_consumes_event(void)
{
    pl_context_t ctx = {0.4, 0.0};
    pl_t sm;
    CHECK(pl_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(pl_post(&sm, PL_EVENT_GO) == SC_STATUS_OK);
    /* Guard false: the internal event is consumed, source stays active. */
    CHECK(pl_get_state(&sm) == 1u);
    CHECK(ctx.captured == 0.0);
    CHECK(sc_event_queue_is_empty(sm.runtime.queue));
}

int main(void)
{
    test_payload_above_threshold_fires_and_captures();
    test_payload_below_threshold_consumes_event();

    if (g_failures == 0) {
        (void)printf("test_runtime_payload: OK\n");
        return 0;
    }
    (void)printf("test_runtime_payload: %d failure(s)\n", g_failures);
    return 1;
}
