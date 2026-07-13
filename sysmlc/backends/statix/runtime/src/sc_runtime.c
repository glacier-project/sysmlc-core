/// @file sc_runtime.c
/// @brief Machine-agnostic runtime instance helpers.
///
/// No recursion, no goto, no function pointers, no dynamic memory. Generated
/// statechart units own dispatch so their guard/action calls can stay file-local
/// and direct.

#include "sc/sc_runtime.h"

/// @brief Bind runtime state to a generated machine and caller-owned context.
/// @param runtime Runtime instance to bind.
/// @param machine Immutable generated machine definition.
/// @param user_data Opaque caller-owned context pointer.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_runtime_bind(sc_runtime_t *runtime, const sc_machine_t *machine, void *user_data)
{
    sc_state_id_t i;
    if ((runtime == NULL) || (machine == NULL) || (machine->transitions == NULL) ||
        (machine->states == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (machine->initial_state >= machine->state_count) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (machine->max_depth > (sc_state_id_t)SC_MAX_DEPTH) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    for (i = 0u; i < machine->state_count; ++i) {
        sc_state_id_t parent = machine->states[i].parent;
        sc_state_id_t child = machine->states[i].initial_child;
        if ((parent != SC_STATE_INVALID) && (parent >= machine->state_count)) {
            return SC_STATUS_INVALID_ARGUMENT;
        }
        if ((child != SC_STATE_INVALID) && (child >= machine->state_count)) {
            return SC_STATUS_INVALID_ARGUMENT;
        }
    }
    for (i = 0u; i < machine->transition_count; ++i) {
        /* Dispatch always indexes states[t->source] directly. states[t->target]
         * too, except SC_STATE_INVALID: the internal-transition sentinel (no
         * exit, no entry, action-only -- see sc_machine.h's _take_transition),
         * used by `when`'s consumer transitions. */
        if (machine->transitions[i].source >= machine->state_count) {
            return SC_STATUS_INVALID_ARGUMENT;
        }
        if ((machine->transitions[i].target != SC_STATE_INVALID) &&
            (machine->transitions[i].target >= machine->state_count)) {
            return SC_STATUS_INVALID_ARGUMENT;
        }
    }
    if (machine->invariant_count > (uint16_t)SC_MAX_INVARIANTS) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if ((machine->invariant_count > 0u) && (machine->invariants == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    for (i = 0u; i < machine->invariant_count; ++i) {
        sc_state_id_t scope = machine->invariants[i].scope;
        if ((scope != SC_STATE_INVALID) && (scope >= machine->state_count)) {
            return SC_STATUS_INVALID_ARGUMENT;
        }
    }
    runtime->machine = machine;
    runtime->user_data = user_data;
    runtime->queue = NULL;
    runtime->current_state = machine->initial_state;
    runtime->now = 0u;
    runtime->state_entered_at = 0u;
    runtime->timeout_delivered = false;
    for (i = 0u; i < (sc_state_id_t)SC_MAX_WHEN_TRIGGERS; ++i) {
        runtime->when_armed[i] = false;
    }
    runtime->initialized = true;
    return SC_STATUS_OK;
}

/// @brief Write the current state id to an output pointer.
/// @param runtime Runtime instance to inspect.
/// @param out_state Destination for the current state id.
/// @return SC_STATUS_OK on success, or SC_STATUS_INVALID_ARGUMENT.
sc_status_t sc_runtime_get_state(const sc_runtime_t *runtime, sc_state_id_t *out_state)
{
    if ((runtime == NULL) || (out_state == NULL) || (!runtime->initialized)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    *out_state = runtime->current_state;
    return SC_STATUS_OK;
}

/// @brief Post an internal event to the runtime's queue (send effect support).
///
/// Meant for action bodies during a step: the generated dispatch drains the
/// queue before returning, so it is empty at dispatch boundaries. An event
/// hand-posted between dispatches is consumed at the start of the next
/// successful init/dispatch drain; a no-transition dispatch does not drain.
/// The event is id-only: its payload buffer is not populated.
/// @param runtime Runtime instance to post into.
/// @param event_id Event identifier to enqueue.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_FULL, or SC_STATUS_INVALID_ARGUMENT
///         (NULL runtime, or a machine with no internal-event queue).
sc_status_t sc_runtime_enqueue(sc_runtime_t *runtime, sc_event_id_t event_id)
{
    sc_event_t event;
    sc_status_t status;
    if ((runtime == NULL) || (runtime->queue == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    status = sc_event_init(&event, event_id);
    if (status != SC_STATUS_OK) {
        return status;
    }
    return sc_event_queue_push(runtime->queue, &event);
}

/// @brief Post an internal event carrying one Real (double) payload value.
///
/// The scalar Real payload slot: the double's object bytes are copied into
/// the event's inline payload buffer (bounded loop, no allocation) and read
/// back by sc_event_payload_f64 on the accepting side. Same contract as
/// sc_runtime_enqueue otherwise.
/// @param runtime Runtime instance to post into.
/// @param event_id Event identifier to enqueue.
/// @param value Payload value to marshal.
/// @return SC_STATUS_OK, SC_STATUS_QUEUE_FULL, or SC_STATUS_INVALID_ARGUMENT
///         (NULL runtime, a machine with no internal-event queue, or a
///         double too large for the payload buffer).
sc_status_t sc_runtime_enqueue_f64(sc_runtime_t *runtime, sc_event_id_t event_id, double value)
{
    sc_event_t event;
    const uint8_t *bytes = (const uint8_t *)&value;
    uint8_t i;
    sc_status_t status;
    if ((runtime == NULL) || (runtime->queue == NULL)) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    if (sizeof(double) > (size_t)SC_EVENT_PAYLOAD_SIZE) {
        return SC_STATUS_INVALID_ARGUMENT;
    }
    status = sc_event_init(&event, event_id);
    if (status != SC_STATUS_OK) {
        return status;
    }
    for (i = 0u; i < (uint8_t)sizeof(double); ++i) {
        event.payload[i] = bytes[i];
    }
    event.payload_len = (uint8_t)sizeof(double);
    return sc_event_queue_push(runtime->queue, &event);
}

/// @brief Convert SI seconds to ticks, rejecting negative or unrepresentable values.
/// @param seconds Duration/instant in SI seconds.
/// @param out_ticks Destination for the converted tick value.
/// @return true and writes *out_ticks on success; false (leaves *out_ticks
///         unset) if seconds is negative or would overflow sc_time_t at the
///         compiled SC_TICKS_PER_SECOND.
bool sc_seconds_to_ticks(double seconds, sc_time_t *out_ticks)
{
    double max_seconds;
    if (out_ticks == NULL) {
        return false;
    }
    if (seconds < 0.0) {
        return false;
    }
    max_seconds = (double)SC_TIME_MAX / (double)SC_TICKS_PER_SECOND;
    if (seconds > max_seconds) {
        return false;
    }
    *out_ticks = (sc_time_t)(seconds * (double)SC_TICKS_PER_SECOND);
    return true;
}
