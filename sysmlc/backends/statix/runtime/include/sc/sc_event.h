#ifndef SC_EVENT_H
#define SC_EVENT_H

/*
 * sc_event.h - The event value type.
 *
 * Safety notes:
 *   - The payload is a fixed-size, inline byte buffer. There is no pointer to
 *     external storage and no dynamic allocation: an event is a plain value
 *     that can be copied by assignment and stored in a static queue.
 *   - The payload is currently a placeholder for future typed event data. Its
 *     size is bounded by a compile-time constant.
 */

#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum payload size, in bytes. Bounded at compile time on purpose. */
#define SC_EVENT_PAYLOAD_SIZE 8u

typedef struct sc_event_s {
    sc_event_id_t id;                       /* event identifier            */
    uint8_t payload_len;                    /* valid bytes: 0..SIZE        */
    uint8_t payload[SC_EVENT_PAYLOAD_SIZE]; /* inline, fixed-size payload  */
} sc_event_t;

/*
 * Initializes an event to the given id with an empty payload.
 *
 * Header-only inline helper: no extra translation unit, no allocation, and a
 * single bounded loop. Returns SC_STATUS_INVALID_ARGUMENT if event is NULL.
 */
static inline sc_status_t sc_event_init(sc_event_t *event, sc_event_id_t id)
{
    uint8_t i;
    if (event == NULL) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    event->id = id;
    event->payload_len = 0u;
    for (i = 0u; i < (uint8_t)SC_EVENT_PAYLOAD_SIZE; ++i) {
        event->payload[i] = 0u;
    }
    return SC_STATUS_OK;
}

/*
 * Copies up to SC_EVENT_PAYLOAD_SIZE bytes into the event payload.
 * Returns SC_STATUS_INVALID_ARGUMENT on NULL/oversized input.
 */
static inline sc_status_t sc_event_set_payload(sc_event_t *event, const uint8_t *data, uint8_t len)
{
    uint8_t i;
    if ((event == NULL) || ((data == NULL) && (len > 0u))) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (len > (uint8_t)SC_EVENT_PAYLOAD_SIZE) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    for (i = 0u; i < len; ++i) {
        event->payload[i] = data[i];
    }
    event->payload_len = len;
    return SC_STATUS_OK;
}

#ifdef __cplusplus
}
#endif

#endif /* SC_EVENT_H */
