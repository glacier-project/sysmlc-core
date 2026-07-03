/*
 * test_runtime_simple.c - Unit tests for the flat runtime dispatcher.
 *
 * Defines a small two-state machine inline together with its guard/action
 * implementations (the dispatch contract from sc_runtime.h). This exercises the
 * guard path (a transition that is blocked, then allowed) and the action path.
 *
 * No dynamic memory: the machine is static const and the context is a local.
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

/* --- model ids ----------------------------------------------------------- */

enum { TS_OFF = 0, TS_ON = 1, TS_COUNT = 2 };
enum { TE_ON = 1, TE_OFF = 2, TE_BOGUS = 3 };
enum { TG_ALLOW = 1 };
enum { TA_COUNT = 1 };

typedef struct test_ctx_s {
    bool allow;
    uint32_t count;
} test_ctx_t;

/* OFF --TE_ON [TG_ALLOW] / TA_COUNT--> ON;  ON --TE_OFF / TA_COUNT--> OFF */
static const sc_transition_t k_transitions[] = {
    {TS_OFF, TE_ON, TG_ALLOW, TA_COUNT, TS_ON},
    {TS_ON, TE_OFF, SC_GUARD_NONE, TA_COUNT, TS_OFF},
};

static const sc_machine_t k_machine = {
    k_transitions,
    (uint16_t)(sizeof(k_transitions) / sizeof(k_transitions[0])),
    TS_COUNT,
    TS_OFF,
};

/* --- dispatch contract (resolved at link time, no function pointers) ----- */

bool sc_guard_eval(sc_guard_id_t guard_id, const sc_runtime_t *runtime, const sc_event_t *event)
{
    const test_ctx_t *ctx = (const test_ctx_t *)runtime->user_data;
    (void)event;
    switch (guard_id) {
    case TG_ALLOW:
        return ctx->allow;
    default:
        return false;
    }
}

sc_status_t sc_action_exec(sc_action_id_t action_id, sc_runtime_t *runtime, const sc_event_t *event)
{
    test_ctx_t *ctx = (test_ctx_t *)runtime->user_data;
    (void)event;
    switch (action_id) {
    case TA_COUNT:
        ctx->count = ctx->count + 1u;
        return SC_STATUS_OK;
    default:
        return SC_STATUS_ERROR;
    }
}

/* --- tests --------------------------------------------------------------- */

static sc_state_id_t current(const sc_runtime_t *rt)
{
    sc_state_id_t state = SC_STATE_INVALID;
    (void)sc_runtime_get_state(rt, &state);
    return state;
}

static void test_init(void)
{
    sc_runtime_t rt;
    test_ctx_t ctx = {false, 0u};

    CHECK(sc_runtime_init(NULL, &k_machine, &ctx) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_init(&rt, NULL, &ctx) == SC_STATUS_INVALID_ARGUMENT);

    CHECK(sc_runtime_init(&rt, &k_machine, &ctx) == SC_STATUS_OK);
    CHECK(current(&rt) == TS_OFF);
}

static void test_bad_initial_state(void)
{
    /* A machine whose initial state is out of range must be rejected. */
    static const sc_machine_t bad = {k_transitions, 2u, TS_COUNT, (sc_state_id_t)TS_COUNT};
    sc_runtime_t rt;
    CHECK(sc_runtime_init(&rt, &bad, NULL) == SC_STATUS_INVALID_ARGUMENT);
}

static void test_guard_blocks_then_allows(void)
{
    sc_runtime_t rt;
    test_ctx_t ctx = {false, 0u};
    sc_event_t event;

    CHECK(sc_runtime_init(&rt, &k_machine, &ctx) == SC_STATUS_OK);

    /* Guard disabled: the transition must not fire. */
    (void)sc_event_init(&event, TE_ON);
    CHECK(sc_runtime_dispatch(&rt, &event) == SC_STATUS_NO_TRANSITION);
    CHECK(current(&rt) == TS_OFF);
    CHECK(ctx.count == 0u);

    /* Guard enabled: now it fires and runs the action. */
    ctx.allow = true;
    CHECK(sc_runtime_dispatch(&rt, &event) == SC_STATUS_OK);
    CHECK(current(&rt) == TS_ON);
    CHECK(ctx.count == 1u);
}

static void test_no_transition_and_unconditional(void)
{
    sc_runtime_t rt;
    test_ctx_t ctx = {true, 0u};
    sc_event_t event;

    CHECK(sc_runtime_init(&rt, &k_machine, &ctx) == SC_STATUS_OK);

    (void)sc_event_init(&event, TE_ON);
    CHECK(sc_runtime_dispatch(&rt, &event) == SC_STATUS_OK);
    CHECK(current(&rt) == TS_ON);

    /* Unknown event in this state: no transition, state preserved. */
    (void)sc_event_init(&event, TE_BOGUS);
    CHECK(sc_runtime_dispatch(&rt, &event) == SC_STATUS_NO_TRANSITION);
    CHECK(current(&rt) == TS_ON);

    /* Unconditional transition back to OFF. */
    (void)sc_event_init(&event, TE_OFF);
    CHECK(sc_runtime_dispatch(&rt, &event) == SC_STATUS_OK);
    CHECK(current(&rt) == TS_OFF);
    CHECK(ctx.count == 2u);
}

static void test_uninitialized_and_null(void)
{
    sc_runtime_t rt = {NULL, NULL, 0u, false};
    sc_event_t event;
    sc_state_id_t state;
    (void)sc_event_init(&event, TE_ON);

    CHECK(sc_runtime_dispatch(&rt, &event) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_dispatch(NULL, &event) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_get_state(&rt, &state) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_get_state(NULL, &state) == SC_STATUS_INVALID_ARGUMENT);
}

int main(void)
{
    test_init();
    test_bad_initial_state();
    test_guard_blocks_then_allows();
    test_no_transition_and_unconditional();
    test_uninitialized_and_null();

    if (g_failures == 0) {
        (void)printf("test_runtime_simple: OK\n");
        return 0;
    }
    (void)printf("test_runtime_simple: %d failure(s)\n", g_failures);
    return 1;
}
