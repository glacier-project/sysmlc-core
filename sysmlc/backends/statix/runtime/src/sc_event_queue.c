/*
 * sc_event_queue.c - Fixed-size FIFO over caller-provided storage.
 *
 * Implemented as a circular buffer tracked by (head, count). The back index is
 * derived as (head + count) % capacity, so no separate tail is stored. All
 * arithmetic is on unsigned fixed-width types with explicit casts to satisfy
 * -Wconversion.
 */

#include "sc/sc_event_queue.h"

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

bool sc_event_queue_is_empty(const sc_event_queue_t *queue)
{
    if (queue == NULL) {
        return true;
    }
    return (queue->count == 0u);
}

bool sc_event_queue_is_full(const sc_event_queue_t *queue)
{
    if (queue == NULL) {
        return false;
    }
    return (queue->count >= queue->capacity);
}

uint16_t sc_event_queue_count(const sc_event_queue_t *queue)
{
    if (queue == NULL) {
        return 0u;
    }
    return queue->count;
}
