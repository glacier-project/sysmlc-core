/*
 * test_runtime_enqueue.c - Unit tests for sc_runtime_enqueue: id-only event
 * posting onto the runtime's bounded internal queue (send effect support).
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

#define QCAP 2u

static sc_event_t g_storage[QCAP];

static void test_enqueue_rejects_bad_args(void)
{
    sc_runtime_t rt = {0};
    CHECK(sc_runtime_enqueue(NULL, 1u) == SC_STATUS_INVALID_ARGUMENT);
    /* A machine with no internal-event queue rejects loudly, not crashes. */
    CHECK(sc_runtime_enqueue(&rt, 1u) == SC_STATUS_INVALID_ARGUMENT);
}

static void test_enqueue_posts_id_only_events(void)
{
    sc_runtime_t rt = {0};
    sc_event_queue_t queue;
    sc_event_t out;

    CHECK(sc_event_queue_init(&queue, g_storage, QCAP) == SC_STATUS_OK);
    rt.queue = &queue;

    CHECK(sc_runtime_enqueue(&rt, 7u) == SC_STATUS_OK);
    CHECK(sc_runtime_enqueue(&rt, 9u) == SC_STATUS_OK);
    CHECK(sc_runtime_enqueue(&rt, 11u) == SC_STATUS_QUEUE_FULL);

    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
    CHECK(out.id == 7u);
    CHECK(out.payload_len == 0u); /* id-only: payload never populated */
    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
    CHECK(out.id == 9u);
}

int main(void)
{
    test_enqueue_rejects_bad_args();
    test_enqueue_posts_id_only_events();

    if (g_failures == 0) {
        (void)printf("test_runtime_enqueue: OK\n");
        return 0;
    }
    (void)printf("test_runtime_enqueue: %d failure(s)\n", g_failures);
    return 1;
}
