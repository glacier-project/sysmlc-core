cmake_minimum_required(VERSION 3.16)
project(statix_runtime_tests C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(RUNTIME_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../../sysmlc/backends/statix/runtime)

add_compile_options(-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wdouble-promotion -Werror)

include_directories(${RUNTIME_DIR}/include)

add_library(sc_runtime STATIC
  ${RUNTIME_DIR}/src/sc_status.c
  ${RUNTIME_DIR}/src/sc_event_queue.c
  ${RUNTIME_DIR}/src/sc_runtime.c)

enable_testing()

add_executable(test_event_queue test_event_queue.c)
target_link_libraries(test_event_queue sc_runtime)
add_test(NAME test_event_queue COMMAND test_event_queue)

add_executable(test_runtime_simple test_runtime_simple.c)
target_link_libraries(test_runtime_simple sc_runtime)
add_test(NAME test_runtime_simple COMMAND test_runtime_simple)

add_executable(test_runtime_completion test_runtime_completion.c)
target_link_libraries(test_runtime_completion sc_runtime)
add_test(NAME test_runtime_completion COMMAND test_runtime_completion)

add_executable(test_runtime_enqueue test_runtime_enqueue.c)
target_link_libraries(test_runtime_enqueue sc_runtime)
add_test(NAME test_runtime_enqueue COMMAND test_runtime_enqueue)

add_executable(test_runtime_send test_runtime_send.c)
target_link_libraries(test_runtime_send sc_runtime)
add_test(NAME test_runtime_send COMMAND test_runtime_send)

add_executable(test_payload_f64 test_payload_f64.c)
target_link_libraries(test_payload_f64 sc_runtime)
add_test(NAME test_payload_f64 COMMAND test_payload_f64)

add_executable(test_runtime_payload test_runtime_payload.c)
target_link_libraries(test_runtime_payload sc_runtime)
add_test(NAME test_runtime_payload COMMAND test_runtime_payload)

add_executable(test_runtime_tick test_runtime_tick.c)
target_link_libraries(test_runtime_tick sc_runtime)
add_test(NAME test_runtime_tick COMMAND test_runtime_tick)
