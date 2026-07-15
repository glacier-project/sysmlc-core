cmake_minimum_required(VERSION 3.16)
project(statix_runtime_tests C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(RUNTIME_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../../sysmlc/backends/statix/runtime)

add_compile_options(-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wdouble-promotion -Werror)

include_directories(${RUNTIME_DIR}/include)

enable_testing()

add_executable(test_event_queue test_event_queue.c)
add_test(NAME test_event_queue COMMAND test_event_queue)

add_executable(test_runtime_simple test_runtime_simple.c)
add_test(NAME test_runtime_simple COMMAND test_runtime_simple)

add_executable(test_runtime_completion test_runtime_completion.c)
add_test(NAME test_runtime_completion COMMAND test_runtime_completion)

add_executable(test_runtime_enqueue test_runtime_enqueue.c)
add_test(NAME test_runtime_enqueue COMMAND test_runtime_enqueue)

add_executable(test_runtime_send test_runtime_send.c)
add_test(NAME test_runtime_send COMMAND test_runtime_send)

add_executable(test_payload_f64 test_payload_f64.c)
add_test(NAME test_payload_f64 COMMAND test_payload_f64)

add_executable(test_runtime_payload test_runtime_payload.c)
add_test(NAME test_runtime_payload COMMAND test_runtime_payload)

add_executable(test_runtime_tick test_runtime_tick.c)
add_test(NAME test_runtime_tick COMMAND test_runtime_tick)

add_executable(test_runtime_timer test_runtime_timer.c)
add_test(NAME test_runtime_timer COMMAND test_runtime_timer)

add_executable(test_runtime_when test_runtime_when.c)
add_test(NAME test_runtime_when COMMAND test_runtime_when)

add_executable(test_runtime_internal_transition test_runtime_internal_transition.c)
add_test(NAME test_runtime_internal_transition COMMAND test_runtime_internal_transition)

add_executable(test_runtime_activation test_runtime_activation.c)
add_test(NAME test_runtime_activation COMMAND test_runtime_activation)

add_executable(test_runtime_parallel test_runtime_parallel.c)
add_test(NAME test_runtime_parallel COMMAND test_runtime_parallel)
