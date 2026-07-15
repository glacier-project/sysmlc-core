cmake_minimum_required(VERSION 3.16)
project(statix_statecharts C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_compile_options(-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wdouble-promotion -Werror)

include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)

add_library(statix_statecharts STATIC
  src/sc_runtime_impl.c
  src/sm11/machine_mixed.c)
add_executable(sm11_machine_mixed_runner host/sm11/machine_mixed_runner.c)
target_link_libraries(sm11_machine_mixed_runner statix_statecharts)
