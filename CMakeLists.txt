cmake_minimum_required(VERSION 3.24)
project(DXWeaverNative VERSION 0.5.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(dxw_core STATIC
    src/native/dxw/CandidateScorer.cpp
    src/native/dxw/QsoStateMachine.cpp
    src/native/dxw/Ft8SlotClock.cpp
)
target_include_directories(dxw_core PUBLIC src/native)
if(MSVC)
  target_compile_options(dxw_core PRIVATE /W4 /permissive-)
else()
  target_compile_options(dxw_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

include(CTest)
if(BUILD_TESTING)
  include(FetchContent)
  FetchContent_Declare(
    googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.15.2.zip
  )
  set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(googletest)

  add_executable(dxw_native_tests
      tests/native/test_qso_state_machine.cpp
      tests/native/test_candidate_scorer.cpp
      tests/native/test_resilience.cpp
  )
  target_link_libraries(dxw_native_tests PRIVATE dxw_core GTest::gtest_main)
  include(GoogleTest)
  gtest_discover_tests(dxw_native_tests DISCOVERY_TIMEOUT 60)
endif()
