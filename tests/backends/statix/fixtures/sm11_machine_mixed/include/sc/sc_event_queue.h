#ifndef SC_EVENT_QUEUE_H
#define SC_EVENT_QUEUE_H

/// @file sc_event_queue.h
/// @brief Fixed-size FIFO event queue.
///
/// Safety notes:
/// - The queue never allocates. The caller provides the backing storage as a
///   fixed-size array of sc_event_t; the queue only tracks indices into it.
/// - All operations are O(1) and bounded. There are no unbounded loops.
/// - Every fallible operation returns an sc_status_t.

#include "sc/sc_event.h"
#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/// @brief Queue control block over caller-owned event storage.
typedef struct sc_event_queue_s {
    sc_event_t *storage; ///< @brief Caller-provided array of capacity elements.
    uint16_t capacity; ///< @brief Number of elements in storage.
    uint16_t head; ///< @brief Index of the oldest queued event.
    uint16_t count; ///< @brief Number of events currently queued.
} sc_event_queue_t;

/// @brief Initialize a queue over caller-provided storage.
/// @param queue Queue control block to initialize.
/// @param storage Caller-owned event array.
/// @param capacity Number of elements in storage.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT on invalid input.
sc_status_t sc_event_queue_init(sc_event_queue_t *queue, sc_event_t *storage, uint16_t capacity);

/// @brief Append a copy of an event to the back of the queue.
/// @param queue Queue to push into.
/// @param event Event to copy into the queue.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_FULL, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_event_queue_push(sc_event_queue_t *queue, const sc_event_t *event);

/// @brief Pop the oldest event from the queue.
/// @param queue Queue to pop from.
/// @param out_event Destination for the popped event.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_EMPTY, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_event_queue_pop(sc_event_queue_t *queue, sc_event_t *out_event);

/// @brief Return whether the queue is empty; NULL is treated as empty.
/// @param queue Queue to inspect.
/// @return true when empty or NULL, otherwise false.
bool sc_event_queue_is_empty(const sc_event_queue_t *queue);

/// @brief Return whether the queue is full; NULL is treated as not full.
/// @param queue Queue to inspect.
/// @return true when full, otherwise false.
bool sc_event_queue_is_full(const sc_event_queue_t *queue);

/// @brief Return the number of queued events; NULL is treated as 0.
/// @param queue Queue to inspect.
/// @return Number of queued events.
uint16_t sc_event_queue_count(const sc_event_queue_t *queue);

#ifdef __cplusplus
}
#endif

#endif /* SC_EVENT_QUEUE_H */
