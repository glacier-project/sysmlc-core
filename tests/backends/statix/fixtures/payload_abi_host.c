/*
 * payload_abi_host.c - A separate host translation unit, added as its own
 * executable target to a GENERATED project's CMakeLists.txt (linking
 * against, not recompiling, that project's statix_statecharts library).
 * Proves SC_EVENT_PAYLOAD_SIZE (set via target_compile_definitions(...
 * PUBLIC ...) on the library, because the project uses a >8-byte whole
 * payload type) genuinely propagates to a linked consumer's own
 * compilation -- not merely that one translation unit privately defining
 * the same macro happens to agree with itself.
 *
 * Deliberately does NOT define SC_RUNTIME_IMPLEMENTATION (the enqueue call
 * below executes inside the LIBRARY's own compiled copy of
 * sc_runtime_enqueue_payload) and does NOT define SC_EVENT_PAYLOAD_SIZE
 * directly (it must be inherited via the PUBLIC link).
 */
#include "sc/sc_event_queue.h"
#include "sc/sc_runtime.h"

#include <stdio.h>

static sc_event_t g_storage[2];

int main(void)
{
    sc_runtime_t rt = {0};
    sc_event_queue_t queue;
    sc_event_t out;
    sc_event_t probe;
    const double sent[2] = {10.0, 20.0};
    double received[2] = {0};
    int failures = 0;

    /* sizeof(event.payload), never sizeof(sc_event_t): the compiler is
     * free to pad the whole struct, which would make a sizeof(sc_event_t)
     * comparison flaky and prove nothing about the layout that matters. */
    if (sizeof(probe.payload) < sizeof(sent)) {
        (void)printf("FAIL: inherited SC_EVENT_PAYLOAD_SIZE too small "
                     "for a 2-double payload (got %zu bytes)\n",
                     sizeof(probe.payload));
        return 1;
    }
    if (sc_event_queue_init(&queue, g_storage, 2u) != SC_STATUS_OK) {
        (void)printf("FAIL: sc_event_queue_init\n");
        ++failures;
    }
    rt.queue = &queue;
    /* Calls into the LIBRARY's own compiled sc_runtime_enqueue_payload. */
    if (sc_runtime_enqueue_payload(&rt, 1u, sent, sizeof(sent)) != SC_STATUS_OK) {
        (void)printf("FAIL: sc_runtime_enqueue_payload\n");
        ++failures;
    }
    if (sc_event_queue_pop(&queue, &out) != SC_STATUS_OK) {
        (void)printf("FAIL: sc_event_queue_pop\n");
        ++failures;
    }
    /* Calls the HOST's own inline-compiled sc_event_payload_read (it's
     * static inline in sc_event.h) -- if the host disagreed with the
     * library about SC_EVENT_PAYLOAD_SIZE, this would read back garbage
     * or fail the length check, not silently succeed. */
    if (sc_event_payload_read(&out, received, sizeof(received)) != SC_STATUS_OK) {
        (void)printf("FAIL: sc_event_payload_read\n");
        ++failures;
    }
    if ((received[0] != 10.0) || (received[1] != 20.0)) {
        (void)printf("FAIL: roundtrip mismatch: %g %g\n",
                     received[0], received[1]);
        ++failures;
    }

    if (failures == 0) {
        (void)printf("payload_abi_host: OK\n");
        return 0;
    }
    (void)printf("payload_abi_host: %d failure(s)\n", failures);
    return 1;
}
