cmake_minimum_required(VERSION 3.20)
project(autonomous_fighter_muscles LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(autonomous_fighter_muscles SHARED
    src/input_executor.cpp
)

target_include_directories(autonomous_fighter_muscles
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
)

if (MSVC)
    target_compile_options(autonomous_fighter_muscles PRIVATE /W4 /O2)
else()
    target_compile_options(autonomous_fighter_muscles PRIVATE -Wall -Wextra -O2)
endif()
