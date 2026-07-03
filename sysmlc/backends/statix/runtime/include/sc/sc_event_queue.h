#ifndef SC_EVENT_QUEUE_H
#define SC_EVENT_QUEUE_H

/*
 * sc_event_queue.h - A fixed-size FIFO event queue.
 *
 * Safety notes:
 *   - The queue never allocates. The caller provides the backing storage as a
 *     fixed-size array of sc_event_t; the queue only tracks indices into it.
 *   - All operations are O(1) and bounded. There are no unbounded loops.
 *   - Every fallible operation returns an sc_status_t.
 *
 * Note: this header is an addition to the originally suggested header set. The
 * event queue has a public API, so it deserves its own public header rather
 * than being hidden inside sc_runtime.h.
 */

#include "sc/sc_event.h"
#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Queue control block. Holds only indices and a borrowed pointer to the
 * caller-owned storage array; it does not own the memory.
 */
typedef struct sc_event_queue_s {
    sc_event_t *storage; /* caller-provided array of `capacity` elements */
    uint16_t capacity;   /* number of elements in `storage`              */
    uint16_t head;       /* index of the oldest queued event             */
    uint16_t count;      /* number of events currently queued            */
} sc_event_queue_t;

/*
 * Initializes a queue over caller-provided storage.
 * Returns SC_STATUS_INVALID_ARGUMENT if any pointer is NULL or capacity is 0.
 */
sc_status_t sc_event_queue_init(sc_event_queue_t *queue, sc_event_t *storage, uint16_t capacity);

/*
 * Appends a copy of *event to the back of the queue.
 * Returns SC_STATUS_QUEUE_FULL if the queue is full.
 */
sc_status_t sc_event_queue_push(sc_event_queue_t *queue, const sc_event_t *event);

/*
 * Removes the oldest event and copies it into *out_event.
 * Returns SC_STATUS_QUEUE_EMPTY if the queue is empty.
 */
sc_status_t sc_event_queue_pop(sc_event_queue_t *queue, sc_event_t *out_event);

/* Returns true if the queue is empty (treats NULL as empty). */
bool sc_event_queue_is_empty(const sc_event_queue_t *queue);

/* Returns true if the queue is full (treats NULL as not full). */
bool sc_event_queue_is_full(const sc_event_queue_t *queue);

/* Returns the number of queued events (treats NULL as 0). */
uint16_t sc_event_queue_count(const sc_event_queue_t *queue);

#ifdef __cplusplus
}
#endif

#endif /* SC_EVENT_QUEUE_H */
