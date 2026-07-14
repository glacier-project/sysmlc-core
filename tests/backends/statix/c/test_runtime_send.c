/*
 * test_runtime_send.c - Exercises the dispatch template's internal-event
 * drain with a hand-written sending machine (SC_MACHINE_HAS_QUEUE):
 * same-step self-send, unmatched-event drop, ping-pong step limit, and
 * queue-full propagation out of an action.
 */

#include "sc/sc_event_queue.h"
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
 * sn machine (mirrors SM11::MachineSelfSend, plus a drop probe):
 *   states: idle(0) armed(1) fired(2)
 *   idle  --completion/act1(send PING)--> armed
 *   armed --PING--> fired
 *   fired --GO/act2(send NOBODY)--> armed   (NOBODY matches nothing: dropped)
 */
#define SN_EVENT_PING ((sc_event_id_t)1u)
#define SN_EVENT_GO ((sc_event_id_t)2u)
#define SN_EVENT_NOBODY ((sc_event_id_t)3u)
#define SN_QCAP 4u

typedef struct {
    int unused;
} sn_context_t;

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
    sc_event_queue_t queue;
    sc_event_t queue_storage[SN_QCAP];
} sn_t;

static const sc_state_def_t sn_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t sn_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, 1u, 1u},
    {1u, SN_EVENT_PING, SC_GUARD_NONE, SC_ACTION_NONE, 2u},
    {2u, SN_EVENT_GO, SC_GUARD_NONE, 2u, 1u},
};

static const sc_machine_t sn_machine = {
    sn_transitions,
    sn_states,
    3u,
    3u,
    0u,
    1u,
    NULL,
    0u,
    NULL,
    0u,
    1u,
};

static bool sn_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)g;
    (void)rt;
    (void)ev;
    return false;
}

static sc_status_t sn_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)ev;
    if (a == 1u) {
        return sc_runtime_enqueue(rt, SN_EVENT_PING);
    }
    if (a == 2u) {
        return sc_runtime_enqueue(rt, SN_EVENT_NOBODY);
    }
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX sn
#define SC_MACHINE_DEF sn_machine
#define SC_MACHINE_GUARD sn_guard_eval
#define SC_MACHINE_ACTION sn_action_exec
#define SC_MACHINE_HAS_QUEUE 1
#include "sc/sc_machine.h"

/*
 * pp machine (ping-pong livelock): a(0) --PING/send PING--> a(0).
 * Each drained PING re-enqueues PING: the drain bound must trip.
 */
#define PP_EVENT_PING ((sc_event_id_t)1u)
#define PP_QCAP 4u

typedef struct {
    int unused;
} pp_context_t;

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
    sc_event_queue_t queue;
    sc_event_t queue_storage[PP_QCAP];
} pp_t;

static const sc_state_def_t pp_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t pp_transitions[] = {
    {0u, PP_EVENT_PING, SC_GUARD_NONE, 1u, 0u},
};

static const sc_machine_t pp_machine = {
    pp_transitions,
    pp_states,
    1u,
    1u,
    0u,
    1u,
    NULL,
    0u,
    NULL,
    0u,
    1u,
};

static bool pp_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)g;
    (void)rt;
    (void)ev;
    return false;
}

static sc_status_t pp_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)ev;
    if (a == 1u) {
        return sc_runtime_enqueue(rt, PP_EVENT_PING);
    }
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX pp
#define SC_MACHINE_DEF pp_machine
#define SC_MACHINE_GUARD pp_guard_eval
#define SC_MACHINE_ACTION pp_action_exec
#define SC_MACHINE_HAS_QUEUE 1
#include "sc/sc_machine.h"

/*
 * qf machine (queue-full): b(0) --GO/act1(enqueue 3x into capacity-2)--> b(0).
 */
#define QF_EVENT_GO ((sc_event_id_t)1u)
#define QF_EVENT_X ((sc_event_id_t)2u)
#define QF_QCAP 2u

typedef struct {
    int unused;
} qf_context_t;

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
    sc_event_queue_t queue;
    sc_event_t queue_storage[QF_QCAP];
} qf_t;

static const sc_state_def_t qf_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t qf_transitions[] = {
    {0u, QF_EVENT_GO, SC_GUARD_NONE, 1u, 0u},
};

static const sc_machine_t qf_machine = {
    qf_transitions,
    qf_states,
    1u,
    1u,
    0u,
    1u,
    NULL,
    0u,
    NULL,
    0u,
    1u,
};

static bool qf_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)g;
    (void)rt;
    (void)ev;
    return false;
}

static sc_status_t qf_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    sc_status_t status;
    (void)ev;
    if (a == 1u) {
        status = sc_runtime_enqueue(rt, QF_EVENT_X);
        if (status != SC_STATUS_OK) {
            return status;
        }
        status = sc_runtime_enqueue(rt, QF_EVENT_X);
        if (status != SC_STATUS_OK) {
            return status;
        }
        /* Third push into a capacity-2 queue must report QUEUE_FULL. */
        return sc_runtime_enqueue(rt, QF_EVENT_X);
    }
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX qf
#define SC_MACHINE_DEF qf_machine
#define SC_MACHINE_GUARD qf_guard_eval
#define SC_MACHINE_ACTION qf_action_exec
#define SC_MACHINE_HAS_QUEUE 1
#include "sc/sc_machine.h"

static void test_self_send_consumed_same_step(void)
{
    sn_context_t ctx = {0};
    sn_t sm;
    /* init: enter idle -> completion idle->armed fires send PING ->
     * drain pops PING -> armed->fired. Settles in fired within init. */
    CHECK(sn_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(sn_get_state(&sm) == 2u);
    CHECK(sc_event_queue_is_empty(sm.runtime.queue));
}

static void test_unmatched_internal_event_dropped(void)
{
    sn_context_t ctx = {0};
    sn_t sm;
    CHECK(sn_init(&sm, &ctx) == SC_STATUS_OK); /* settles in fired (2). */
    /* fired --GO/send NOBODY--> armed: the drained NOBODY matches nothing
     * and is dropped silently; the step still succeeds. */
    CHECK(sn_post(&sm, SN_EVENT_GO) == SC_STATUS_OK);
    CHECK(sn_get_state(&sm) == 1u);
    CHECK(sc_event_queue_is_empty(sm.runtime.queue));
}

static void test_no_transition_dispatch_does_not_drain(void)
{
    sn_context_t ctx = {0};
    sn_t sm;
    CHECK(sn_init(&sm, &ctx) == SC_STATUS_OK); /* settles in fired (2). */
    /* Hand-post an internal event between dispatches, then dispatch an
     * event that matches nothing: the documented contract is that a
     * no-transition dispatch does not drain -- the event stays queued. */
    CHECK(sc_runtime_enqueue(&sm.runtime, SN_EVENT_NOBODY) == SC_STATUS_OK);
    CHECK(sn_post(&sm, SN_EVENT_PING) == SC_STATUS_NO_TRANSITION);
    CHECK(!sc_event_queue_is_empty(sm.runtime.queue));
    /* The next successful step's drain drops it. */
    CHECK(sn_post(&sm, SN_EVENT_GO) == SC_STATUS_OK);
    CHECK(sn_get_state(&sm) == 1u);
    CHECK(sc_event_queue_is_empty(sm.runtime.queue));
}

static void test_ping_pong_hits_step_limit(void)
{
    pp_context_t ctx = {0};
    pp_t sm;
    CHECK(pp_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(pp_post(&sm, PP_EVENT_PING) == SC_STATUS_STEP_LIMIT);
}

static void test_queue_full_propagates(void)
{
    qf_context_t ctx = {0};
    qf_t sm;
    CHECK(qf_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(qf_post(&sm, QF_EVENT_GO) == SC_STATUS_QUEUE_FULL);
}

int main(void)
{
    test_self_send_consumed_same_step();
    test_unmatched_internal_event_dropped();
    test_no_transition_dispatch_does_not_drain();
    test_ping_pong_hits_step_limit();
    test_queue_full_propagates();

    if (g_failures == 0) {
        (void)printf("test_runtime_send: OK\n");
        return 0;
    }
    (void)printf("test_runtime_send: %d failure(s)\n", g_failures);
    return 1;
}
