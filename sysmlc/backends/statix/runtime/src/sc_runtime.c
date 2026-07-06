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
        /* Dispatch indexes states[t->source] and states[t->target] directly. */
        if ((machine->transitions[i].source >= machine->state_count) ||
            (machine->transitions[i].target >= machine->state_count)) {
            return SC_STATUS_INVALID_ARGUMENT;
        }
    }
    runtime->machine = machine;
    runtime->user_data = user_data;
    runtime->current_state = machine->initial_state;
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
