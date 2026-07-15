#ifndef SC_EVENT_H
#define SC_EVENT_H

/// @file sc_event.h
/// @brief Event value type.
///
/// Safety notes:
/// - The payload is a fixed-size, inline byte buffer. There is no pointer to
///   external storage and no dynamic allocation: an event is a plain value that
///   can be copied by assignment and stored in a static queue.
/// - The payload is currently a placeholder for future typed event data. Its
///   size is bounded by a compile-time constant.

#include "sc/sc_status.h"
#include "sc/sc_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/// @brief Maximum payload size, in bytes.
#define SC_EVENT_PAYLOAD_SIZE 8u

/// @brief Event value with an id and bounded inline payload storage.
typedef struct sc_event_s {
    sc_event_id_t id; ///< @brief Event identifier.
    uint8_t payload_len; ///< @brief Valid bytes in payload: 0..SIZE.
    uint8_t payload[SC_EVENT_PAYLOAD_SIZE]; ///< @brief Inline payload bytes.
} sc_event_t;

/// @brief Initialize an event to the given id with an empty payload.
///
/// Header-only inline helper: no extra translation unit, no allocation, and a
/// single bounded loop.
/// @param event Event object to initialize.
/// @param id Event id to assign.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT if event is NULL.
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

/// @brief Copy bytes into the event payload.
/// @param event Event object to receive payload bytes.
/// @param data Source payload bytes; may be NULL only when len is 0.
/// @param len Number of bytes to copy.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT on invalid input.
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

/// @brief Read the event's single Real (double) payload value.
///
/// Counterpart of sc_runtime_enqueue_f64: copies sizeof(double) payload
/// bytes back into a double with a bounded loop. Defensive: returns 0.0
/// when the event is NULL or the payload is not exactly one marshalled
/// double (payload_len mismatch). Unreachable in generated code -- the
/// generator only emits this read for events whose every send marshals f64.
/// Producer and consumer are the same machine, so byte order is not a
/// portability concern for internally queued events.
/// @param event Event to read, or NULL.
/// @return The marshalled double, or 0.0 on any mismatch.
static inline double sc_event_payload_f64(const sc_event_t *event)
{
    double value = 0.0;
    uint8_t *bytes = (uint8_t *)&value;
    uint8_t i;
    if ((event == NULL) || (event->payload_len != (uint8_t)sizeof(double))) {
        return 0.0;
    }
    for (i = 0u; i < (uint8_t)sizeof(double); ++i) {
        bytes[i] = event->payload[i];
    }
    return value;
}

#ifdef __cplusplus
}
#endif

#endif /* SC_EVENT_H */
