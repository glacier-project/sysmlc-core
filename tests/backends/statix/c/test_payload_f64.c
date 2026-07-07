/*
 * test_payload_f64.c - Unit tests for the scalar Real payload slot:
 * sc_runtime_enqueue_f64 marshals a double into the event byte buffer and
 * sc_event_payload_f64 reads it back, bit-exact.
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

#define QCAP 2u

static sc_event_t g_storage[QCAP];

static void test_double_fits_the_payload_buffer(void)
{
    CHECK(sizeof(double) <= (size_t)SC_EVENT_PAYLOAD_SIZE);
    CHECK(sizeof(double) == 8u);
}

static void test_roundtrip_is_bit_exact(void)
{
    sc_runtime_t rt = {0};
    sc_event_queue_t queue;
    sc_event_t out;

    CHECK(sc_event_queue_init(&queue, g_storage, QCAP) == SC_STATUS_OK);
    rt.queue = &queue;

    CHECK(sc_runtime_enqueue_f64(&rt, 5u, 0.9) == SC_STATUS_OK);
    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
    CHECK(out.id == 5u);
    CHECK(out.payload_len == (uint8_t)sizeof(double));
    /* Same bytes in, same bytes out: exact equality is intended. */
    CHECK(sc_event_payload_f64(&out) == 0.9);

    CHECK(sc_runtime_enqueue_f64(&rt, 5u, -12345.6789) == SC_STATUS_OK);
    CHECK(sc_event_queue_pop(&queue, &out) == SC_STATUS_OK);
    CHECK(sc_event_payload_f64(&out) == -12345.6789);
}

static void test_defensive_reads_return_zero(void)
{
    sc_event_t idonly;
    CHECK(sc_event_payload_f64(NULL) == 0.0);
    CHECK(sc_event_init(&idonly, 1u) == SC_STATUS_OK);
    /* An id-only event (payload_len 0) reads as 0.0, never garbage. */
    CHECK(sc_event_payload_f64(&idonly) == 0.0);
}

static void test_enqueue_f64_rejects_and_fills(void)
{
    sc_runtime_t rt = {0};
    sc_event_queue_t queue;

    CHECK(sc_runtime_enqueue_f64(NULL, 1u, 1.0) == SC_STATUS_INVALID_ARGUMENT);
    CHECK(sc_runtime_enqueue_f64(&rt, 1u, 1.0) == SC_STATUS_INVALID_ARGUMENT);

    CHECK(sc_event_queue_init(&queue, g_storage, QCAP) == SC_STATUS_OK);
    rt.queue = &queue;
    CHECK(sc_runtime_enqueue_f64(&rt, 1u, 1.0) == SC_STATUS_OK);
    CHECK(sc_runtime_enqueue_f64(&rt, 1u, 2.0) == SC_STATUS_OK);
    CHECK(sc_runtime_enqueue_f64(&rt, 1u, 3.0) == SC_STATUS_QUEUE_FULL);
}

int main(void)
{
    test_double_fits_the_payload_buffer();
    test_roundtrip_is_bit_exact();
    test_defensive_reads_return_zero();
    test_enqueue_f64_rejects_and_fills();

    if (g_failures == 0) {
        (void)printf("test_payload_f64: OK\n");
        return 0;
    }
    (void)printf("test_payload_f64: %d failure(s)\n", g_failures);
    return 1;
}
