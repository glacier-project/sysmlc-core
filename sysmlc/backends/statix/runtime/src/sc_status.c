/// @file sc_status.c
/// @brief Human-readable names for status codes.
///
/// A bounded switch keeps this free of function pointers and trivially
/// analyzable. The default case ensures the function is total.

#include "sc/sc_status.h"

/// @brief Return a static, never-NULL, human-readable name for a status code.
/// @param status Status code to name.
/// @return Static non-NULL status name.
const char *sc_status_str(sc_status_t status)
{
    switch (status) {
    case SC_STATUS_OK:
        return "SC_STATUS_OK";
    case SC_STATUS_ERROR:
        return "SC_STATUS_ERROR";
    case SC_STATUS_INVALID_ARGUMENT:
        return "SC_STATUS_INVALID_ARGUMENT";
    case SC_STATUS_QUEUE_FULL:
        return "SC_STATUS_QUEUE_FULL";
    case SC_STATUS_QUEUE_EMPTY:
        return "SC_STATUS_QUEUE_EMPTY";
    case SC_STATUS_NO_TRANSITION:
        return "SC_STATUS_NO_TRANSITION";
    case SC_STATUS_STEP_LIMIT:
        return "SC_STATUS_STEP_LIMIT";
    default:
        return "SC_STATUS_UNKNOWN";
    }
}
