/*
 * test_event_queue.c - Unit tests for the fixed-size event queue.
 *
 * Uses a tiny inline check macro (no external test framework, no dynamic
 * memory). Returns non-zero on the first batch of failures so CTest reports a
 * failure. Storage for the queue is a static array.
 */

#include "sc/sc_event_queue.h"

#include <stdio.h>

static int g_failures = 0;

#define CHECK(cond)                                                                                \
    do {                                                                                           \
        if (!(cond)) {                                                                             \
            (void)printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                           \
            ++g_failures;                                                                          \
        }                                                                                          \
    } while (0)

#define QCAP 4u

static sc_event_t g_storage[QCAP];

static sc_event_t make_event(sc_event_id_t id)
{
    sc_event_t event;
    (void)sc_event_init(&event, id);
    return event;
}

static void test_init_rejects_bad_args(void)
{
    sc_event_queue_t queue;
    CHECK(sc_event_queue_init(NULL, g_storage, QCAP) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_event_queue_init(&queue, NULL, QCAP) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_event_queue_init(&queue, g_storage, 0u) == SC_STATUS_INVALID_ARGUMENT);
}

static void test_push_pop_fifo(void)
{
    sc_event_queue_t queue;
    sc_event_t out;
    uint16_t i;

    CHECK(sc_event_queue_init(&queue, g_storage, QCAP) == SC_STATUS_OK);
    CHECK(sc_event_queue_is_empty(&queue));
    CHECK(!sc_event_queue_is_full(&queue));
    CHECK(sc_event_queue_count(&queue) == 0u);

    /* Fill the queue. */
    for (i = 0u; i < QCAP; ++i) {
        sc_event_t event = make_event((sc_event_id_t)(10u + i));
        CHECK(sc_event_queue_push(&queue, &event) == SC_STATUS_OK);
    }
    CHECK(sc_event_queue_is_full(&queue));
    CHECK(sc_event_queue_count(&queue) == QCAP);

    /* One more push must be rejected (no overflow, no allocation). */
    {
        sc_event_t event = make_event(99u);
        CHECK(sc_event_queue_push(&queue, &event) == SC_STATUS_QUEUE_FULL);
    }

    /* Drain in FIFO order. */
    for (i = 0u; i < QCAP; ++i) {
        CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
        CHECK(out.id == (sc_event_id_t)(10u + i));
    }
    CHECK(sc_event_queue_is_empty(&queue));
    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_QUEUE_EMPTY);
}

static void test_wraparound(void)
{
    sc_event_queue_t queue;
    sc_event_t out;
    uint16_t i;

    CHECK(sc_event_queue_init(&queue, g_storage, QCAP) == SC_STATUS_OK);

    /* Push 3, pop 2, then push 3 more: forces head/back to wrap. */
    for (i = 0u; i < 3u; ++i) {
        sc_event_t event = make_event((sc_event_id_t)(i + 1u));
        CHECK(sc_event_queue_push(&queue, &event) == SC_STATUS_OK);
    }
    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
    CHECK(out.id == 1u);
    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
    CHECK(out.id == 2u);

    for (i = 0u; i < 3u; ++i) {
        sc_event_t event = make_event((sc_event_id_t)(i + 4u));
        CHECK(sc_event_queue_push(&queue, &event) == SC_STATUS_OK);
    }
    /* Expected remaining order: 3, 4, 5, 6. */
    CHECK(sc_event_queue_count(&queue) == QCAP);
    for (i = 0u; i < QCAP; ++i) {
        CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
        CHECK(out.id == (sc_event_id_t)(i + 3u));
    }
}

static void test_null_safety(void)
{
    CHECK(sc_event_queue_is_empty(NULL));
    CHECK(!sc_event_queue_is_full(NULL));
    CHECK(sc_event_queue_count(NULL) == 0u);
}

int main(void)
{
    test_init_rejects_bad_args();
    test_push_pop_fifo();
    test_wraparound();
    test_null_safety();

    if (g_failures == 0) {
        (void)printf("test_event_queue: OK\n");
        return 0;
    }
    (void)printf("test_event_queue: %d failure(s)\n", g_failures);
    return 1;
}
