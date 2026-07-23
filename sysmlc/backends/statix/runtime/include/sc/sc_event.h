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
#ifndef SC_EVENT_PAYLOAD_SIZE
#define SC_EVENT_PAYLOAD_SIZE 8u
#endif

/// @brief Event value with an id and bounded inline payload storage.
typedef struct sc_event_s {
    sc_event_id_t id; ///< @brief Event identifier.
    size_t payload_len; ///< @brief Valid bytes in payload: 0..SIZE.
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
    size_t i;
    if (event == NULL) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    event->id = id;
    event->payload_len = 0u;
    for (i = 0u; i < (size_t)SC_EVENT_PAYLOAD_SIZE; ++i) {
        event->payload[i] = 0u;
    }
    return SC_STATUS_OK;
}

/// @brief Copy bytes into the event payload.
/// @param event Event object to receive payload bytes.
/// @param data Source payload bytes; may be NULL only when len is 0.
/// @param len Number of bytes to copy.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT on invalid input.
static inline sc_status_t sc_event_set_payload(sc_event_t *event, const uint8_t *data, size_t len)
{
    size_t i;
    if ((event == NULL) || ((data == NULL) && (len > 0u))) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (len > (size_t)SC_EVENT_PAYLOAD_SIZE) {
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
/// @brief Read exactly `out_size` payload bytes into `out`.
///
/// Generic counterpart of sc_runtime_enqueue_payload: validates NULL and an
/// exact payload_len match BEFORE touching `*out` at all, so `*out` is left
/// completely untouched (never zeroed, never partially written) on any
/// failure path -- a deliberate, tested contract, not an implementation
/// detail. Producer and consumer are the same generated build, so byte
/// order/layout is not a portability concern (see sc_event_t's own doc
/// comment).
/// @param event Event to read, or NULL.
/// @param out Destination buffer; untouched if this call fails.
/// @param out_size Exact number of bytes to copy; must equal event->payload_len.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT on any mismatch.
static inline sc_status_t sc_event_payload_read(const sc_event_t *event, void *out, size_t out_size)
{
    const uint8_t *bytes;
    uint8_t *dest;
    size_t i;
    if ((event == NULL) || ((out == NULL) && (out_size > 0u))) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (event->payload_len != out_size) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    bytes = event->payload;
    dest = (uint8_t *)out;
    for (i = 0u; i < out_size; ++i) {
        dest[i] = bytes[i];
    }
    return SC_STATUS_OK;
}

/// @brief Read the event's single Real (double) payload value.
///
/// Thin wrapper over sc_event_payload_read, preserving this function's
/// original signature/behavior exactly (defensive: returns 0.0 on any
/// mismatch, including a NULL event) for every existing caller. Unreachable
/// in generated code for a whole-payload event -- the generator only emits
/// this read for an event whose one consistent read shape is the scalar
/// Real case.
/// @param event Event to read, or NULL.
/// @return The marshalled double, or 0.0 on any mismatch.
static inline double sc_event_payload_f64(const sc_event_t *event)
{
    double value = 0.0;
    (void)sc_event_payload_read(event, &value, sizeof(value));
    return value;
}

#ifdef __cplusplus
}
#endif

#endif /* SC_EVENT_H */
