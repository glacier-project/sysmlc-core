#ifndef SC_STATUS_H
#define SC_STATUS_H

/// @file sc_status.h
/// @brief Explicit status / return codes.
///
/// Power of 10 rule 7: every public function that can fail returns one of these
/// codes, and callers are expected to check it. SC_STATUS_OK is guaranteed to be
/// 0 so `if (status != SC_STATUS_OK)` is the canonical test.

#ifdef __cplusplus
extern "C" {
#endif

/// @brief Status / return codes; SC_STATUS_OK is guaranteed to be 0.
typedef enum sc_status_e {
    SC_STATUS_OK = 0,           ///< @brief Success.
    SC_STATUS_ERROR,            ///< @brief Unspecified failure.
    SC_STATUS_INVALID_ARGUMENT, ///< @brief A NULL pointer or out-of-range argument.
    SC_STATUS_QUEUE_FULL,       ///< @brief Event could not be enqueued.
    SC_STATUS_QUEUE_EMPTY,      ///< @brief No event available to dequeue.
    SC_STATUS_NO_TRANSITION,    ///< @brief Event did not enable any transition.
    SC_STATUS_STEP_LIMIT        ///< @brief Completion micro-step exceeded SC_MAX_RTC_STEPS.
} sc_status_t;

/// @brief Return a static, never-NULL, human-readable name for a status code.
/// @param status Status code to name.
/// @return Static non-NULL status name (bounded switch, no function pointers).
const char *sc_status_str(sc_status_t status);

#ifdef __cplusplus
}
#endif

#endif /* SC_STATUS_H */
