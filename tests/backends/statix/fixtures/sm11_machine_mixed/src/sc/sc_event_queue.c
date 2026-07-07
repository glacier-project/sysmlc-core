/// @file sc_event_queue.c
/// @brief Fixed-size FIFO over caller-provided storage.
///
/// Implemented as a circular buffer tracked by (head, count). The back index is
/// derived as (head + count) % capacity, so no separate tail is stored. All
/// arithmetic is on unsigned fixed-width types with explicit casts to satisfy
/// -Wconversion.

#include "sc/sc_event_queue.h"

/// @brief Initialize a queue over caller-provided storage.
/// @param queue Queue control block to initialize.
/// @param storage Caller-owned event array.
/// @param capacity Number of elements in storage.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT on invalid input.
sc_status_t sc_event_queue_init(sc_event_queue_t *queue, sc_event_t *storage, uint16_t capacity)
{
    if ((queue == NULL) || (storage == NULL) || (capacity == 0u)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    queue->storage = storage;
    queue->capacity = capacity;
    queue->head = 0u;
    queue->count = 0u;
    return SC_STATUS_OK;
}

/// @brief Append a copy of an event to the back of the queue.
/// @param queue Queue to push into.
/// @param event Event to copy into the queue.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_FULL, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_event_queue_push(sc_event_queue_t *queue, const sc_event_t *event)
{
    uint16_t back;
    if ((queue == NULL) || (event == NULL) || (queue->storage == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (queue->count >= queue->capacity) {
        return SC_STATUS_QUEUE_FULL;
    }
    back = (uint16_t)(((uint32_t)queue->head + (uint32_t)queue->count) % (uint32_t)queue->capacity);
    queue->storage[back] = *event;
    queue->count = (uint16_t)(queue->count + 1u);
    return SC_STATUS_OK;
}

/// @brief Pop the oldest event from the queue.
/// @param queue Queue to pop from.
/// @param out_event Destination for the popped event.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_EMPTY, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_event_queue_pop(sc_event_queue_t *queue, sc_event_t *out_event)
{
    if ((queue == NULL) || (out_event == NULL) || (queue->storage == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (queue->count == 0u) {
        return SC_STATUS_QUEUE_EMPTY;
    }
    *out_event = queue->storage[queue->head];
    queue->head = (uint16_t)(((uint32_t)queue->head + 1u) % (uint32_t)queue->capacity);
    queue->count = (uint16_t)(queue->count - 1u);
    return SC_STATUS_OK;
}

/// @brief Return whether the queue is empty; NULL is treated as empty.
/// @param queue Queue to inspect.
/// @return true when empty or NULL, otherwise false.
bool sc_event_queue_is_empty(const sc_event_queue_t *queue)
{
    if (queue == NULL) {
        return true;
    }
    return (queue->count == 0u);
}

/// @brief Return whether the queue is full; NULL is treated as not full.
/// @param queue Queue to inspect.
/// @return true when full, otherwise false.
bool sc_event_queue_is_full(const sc_event_queue_t *queue)
{
    if (queue == NULL) {
        return false;
    }
    return (queue->count >= queue->capacity);
}

/// @brief Return the number of queued events; NULL is treated as 0.
/// @param queue Queue to inspect.
/// @return Number of queued events.
uint16_t sc_event_queue_count(const sc_event_queue_t *queue)
{
    if (queue == NULL) {
        return 0u;
    }
    return queue->count;
}
