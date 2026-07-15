/*
 * test_runtime_completion.c - Exercises the shared dispatch template with a
 * hand-written machine: initial-entry, entry/exit actions, the bounded
 * completion micro-step, and detectable exhaustion (SC_STATUS_STEP_LIMIT).
 */

#define SC_RUNTIME_IMPLEMENTATION
#include "sc/sc_runtime.h"

#include <assert.h>
#include <string.h>

typedef struct {
    bool entered_a;
    bool acted;
} tc_context_t;

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
} tc_t;

/* Machine: A(0, entry=act2) --completion/act1--> B(1). */
static const sc_state_def_t tc_states[] = {
    {2u, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t tc_transitions[] = {
    {0u, SC_EVENT_COMPLETION, SC_GUARD_NONE, 1u, 1u},
};

static const sc_machine_t tc_machine = {
    tc_transitions,
    tc_states,
    1u,
    2u,
    0u,
    1u,
    NULL,
    0u,
    NULL,
    0u,
    1u,
};

static bool tc_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)rt;
    (void)ev;
    return g == 1u;
}

static sc_status_t tc_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    tc_context_t *c = (tc_context_t *)rt->user_data;
    (void)ev;
    if (a == 1u) {
        c->acted = true;
    }
    if (a == 2u) {
        c->entered_a = true;
    }
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX tc
#define SC_MACHINE_DEF tc_machine
#define SC_MACHINE_GUARD tc_guard_eval
#define SC_MACHINE_ACTION tc_action_exec
#define SC_MACHINE_ACTIVE_CAPACITY 1u
#include "sc/sc_machine.h"

/* Cycle machine: A(0) --completion[guard true]--> A(0) => step limit. */
static const sc_state_def_t cy_states[] = {
    {SC_ACTION_NONE, SC_ACTION_NONE, SC_STATE_INVALID, SC_STATE_INVALID, false, 0u, SC_STATE_INVALID, 0u},
};

static const sc_transition_t cy_transitions[] = {
    {0u, SC_EVENT_COMPLETION, 1u, SC_ACTION_NONE, 0u},
};

static const sc_machine_t cy_machine = {
    cy_transitions,
    cy_states,
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

typedef struct {
    sc_runtime_t runtime;
    sc_activation_t active[1];
} cy_t;

typedef struct {
    int unused;
} cy_context_t;

static bool cy_guard_eval(sc_guard_id_t g, const sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)rt;
    (void)ev;
    return g == 1u;
}

static sc_status_t cy_action_exec(sc_action_id_t a, sc_runtime_t *rt, const sc_event_t *ev)
{
    (void)a;
    (void)rt;
    (void)ev;
    return SC_STATUS_OK;
}

#define SC_MACHINE_PREFIX cy
#define SC_MACHINE_DEF cy_machine
#define SC_MACHINE_GUARD cy_guard_eval
#define SC_MACHINE_ACTION cy_action_exec
#define SC_MACHINE_ACTIVE_CAPACITY 1u
#include "sc/sc_machine.h"

int main(void)
{
    assert(strcmp(sc_status_str(SC_STATUS_STEP_LIMIT), "?") != 0);

    tc_context_t c1 = {false, false};
    tc_t sm1;
    assert(tc_init(&sm1, &c1) == SC_STATUS_OK);
    assert(tc_get_state(&sm1) == 1u);
    assert(c1.entered_a && c1.acted);

    cy_context_t c2 = {0};
    cy_t sm2;
    assert(cy_init(&sm2, &c2) == SC_STATUS_STEP_LIMIT);
    return 0;
}
