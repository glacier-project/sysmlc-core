/*
 * test_runtime_trace.c - Exercises the SC_MACHINE_TRACE hook (design
 * docs/superpowers/specs/2026-07-16-statix-trace-hook-design.md). Uses a
 * small composite machine (root -> idle/running -> warming/hot) with no
 * timer/guard/parallel structure for the ENTER/EXIT ordering checks this
 * task adds; TRANSITION/GUARD/TIMER_CHECK coverage is added by later tasks
 * extending this same file.
 */
#define SC_RUNTIME_IMPLEMENTATION
#include "sc/sc_runtime.h"

#include <stdio.h>
#include <string.h>

static int g_failures = 0;

#define CHECK(cond)                                                                              \
    do {                                                                                         \
        if (!(cond)) {                                                                           \
            (void)printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                        \
            ++g_failures;                                                                        \
        }                                                                                         \
    } while (0)

/*
 * States: 0 root (composite, initial_child=1)
 *           1 idle (leaf)
 *           2 running (composite, initial_child=3)
 *             3 warming (leaf)
 *             4 hot (leaf)
 * Transitions: 1 --START--> 2 ; 3 --COMPLETION--> 4
 */
enum { S_ROOT = 0, S_IDLE = 1, S_RUNNING = 2, S_WARMING = 3, S_HOT = 4, S_COUNT = 5 };
enum { E_START = 1u };

static const sc_state_def_t tr_states[] = {
    /*              entry           exit            parent      initial_child  final  slot region_first region_count */
    /* 0 root    */ {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, S_IDLE,   false, 0u, SC_STATE_INVALID, 0u},
    /* 1 idle    */ {SC_ACTION_NONE, SC_ACTION_NONE, S_ROOT,           SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    /* 2 running */ {SC_ACTION_NONE, SC_ACTION_NONE, S_ROOT,           S_WARMING, false, 0u, SC_STATE_INVALID, 0u},
    /* 3 warming */ {SC_ACTION_NONE, SC_ACTION_NONE, S_RUNNING,        SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    /* 4 hot     */ {SC_ACTION_NONE, SC_ACTION_NONE, S_RUNNING,        SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t tr_transitions[] = {
    {S_IDLE, E_START, SC_GUARD_NONE, SC_ACTION_NONE, S_RUNNING},
    {S_WARMING, SC_EVENT_COMPLETION, SC_GUARD_NONE, SC_ACTION_NONE, S_HOT},
};

static const sc_machine_t tr_machine = {
    tr_transitions, tr_states, 2u, S_COUNT, S_ROOT, 3u, NULL, 0u, NULL, 0u, 1u,
};

static bool tr_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{ (void)g; (void)rt; (void)ev; return true; }

static sc_status_t tr_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{ (void)a; (void)rt; (void)ev; return SC_STATUS_OK; }

/* Ordered log of every ENTER/EXIT trace call this test session records --
 * tracer-owned static storage, never touching runtime/user_data. */
#define TR_LOG_CAPACITY 16
static sc_trace_kind_t g_log_kind[TR_LOG_CAPACITY];
static sc_state_id_t g_log_state[TR_LOG_CAPACITY];
static sc_state_id_t g_log_activation_index[TR_LOG_CAPACITY];
static sc_state_id_t g_log_source[TR_LOG_CAPACITY];
static sc_state_id_t g_log_target[TR_LOG_CAPACITY];
static int32_t g_log_transition_index[TR_LOG_CAPACITY];
static sc_action_id_t g_log_action[TR_LOG_CAPACITY];
static int g_log_count = 0;

static void tr_trace(sc_trace_kind_t kind, const sc_runtime_t *runtime,
                      const sc_event_t *event, const sc_trace_data_t *data)
{
    (void)runtime;
    (void)event;
    if (g_log_count < TR_LOG_CAPACITY) {
        g_log_kind[g_log_count] = kind;
        g_log_state[g_log_count] = data->state;
        g_log_activation_index[g_log_count] = data->activation_index;
        g_log_source[g_log_count] = data->source;
        g_log_target[g_log_count] = data->target;
        g_log_transition_index[g_log_count] = data->transition_index;
        g_log_action[g_log_count] = data->action;
        ++g_log_count;
    }
}


typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
} tr_t;

typedef struct {
    int unused;
} tr_context_t;

#define SC_MACHINE_PREFIX tr
#define SC_MACHINE_DEF tr_machine
#define SC_MACHINE_GUARD tr_guard_eval
#define SC_MACHINE_ACTION tr_action_exec
#define SC_MACHINE_ACTIVE_CAPACITY 1u
#define SC_MACHINE_HAS_TRACE 1
#define SC_MACHINE_TRACE tr_trace
#include "sc/sc_machine.h"

static void test_init_traces_the_initial_state_enter(void)
{
    tr_context_t ctx;
    tr_t sm;
    g_log_count = 0;
    CHECK(tr_init(&sm, &ctx) == SC_STATUS_OK);
    /* S_ROOT is entered as the initial state, then S_IDLE is entered as its initial child. */
    CHECK(g_log_count == 2);
    CHECK(g_log_kind[0] == SC_TRACE_ENTER);
    CHECK(g_log_state[0] == S_ROOT);
    CHECK(g_log_kind[1] == SC_TRACE_ENTER);
    CHECK(g_log_state[1] == S_IDLE);
}

static void test_transition_traces_exit_then_enter_in_order(void)
{
    tr_context_t ctx;
    tr_t sm;
    CHECK(tr_init(&sm, &ctx) == SC_STATUS_OK);
    g_log_count = 0;
    CHECK(tr_post(&sm, E_START) == SC_STATUS_OK);
    /* Log: TRANSITION (idle->running), EXIT idle, ENTER running, ENTER warming,
     * TRANSITION (warming->hot), EXIT warming, ENTER hot. */
    CHECK(g_log_count == 7);
    CHECK(g_log_kind[0] == SC_TRACE_TRANSITION);
    CHECK(g_log_source[0] == S_IDLE);
    CHECK(g_log_target[0] == S_RUNNING);
    CHECK(g_log_transition_index[0] == 0);
    CHECK(g_log_action[0] == SC_ACTION_NONE);
    CHECK(g_log_activation_index[0] == 0u);

    CHECK(g_log_kind[1] == SC_TRACE_EXIT);
    CHECK(g_log_state[1] == S_IDLE);
    CHECK(g_log_kind[2] == SC_TRACE_ENTER);
    CHECK(g_log_state[2] == S_RUNNING);
    CHECK(g_log_kind[3] == SC_TRACE_ENTER);
    CHECK(g_log_state[3] == S_WARMING);

    CHECK(g_log_kind[4] == SC_TRACE_TRANSITION);
    CHECK(g_log_source[4] == S_WARMING);
    CHECK(g_log_target[4] == S_HOT);
    CHECK(g_log_transition_index[4] == 1);
}

static void test_completion_transition_traces_a_transition_row(void)
{
    tr_context_t ctx;
    tr_t sm;
    CHECK(tr_init(&sm, &ctx) == SC_STATUS_OK);
    CHECK(tr_post(&sm, E_START) == SC_STATUS_OK);
    g_log_count = 0;
    {
        tr_t sm2;
        tr_context_t ctx2;
        CHECK(tr_init(&sm2, &ctx2) == SC_STATUS_OK);
        g_log_count = 0;
        CHECK(tr_post(&sm2, E_START) == SC_STATUS_OK);
        CHECK(g_log_count == 7);
        CHECK(g_log_kind[4] == SC_TRACE_TRANSITION);
        CHECK(g_log_source[4] == S_WARMING);
        CHECK(g_log_target[4] == S_HOT);
        CHECK(g_log_transition_index[4] == 1);
        CHECK(tr_get_state(&sm2) == S_HOT);
    }
}

int main(void)
{
    test_init_traces_the_initial_state_enter();
    test_transition_traces_exit_then_enter_in_order();
    test_completion_transition_traces_a_transition_row();

    if (g_failures == 0) {
        (void)printf("test_runtime_trace: OK\n");
        return 0;
    }
    (void)printf("test_runtime_trace: %d failure(s)\n", g_failures);
    return 1;
}

