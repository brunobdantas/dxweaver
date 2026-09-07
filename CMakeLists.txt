cmake_minimum_required(VERSION 3.24)
project(DXWeaverNative VERSION 0.5.3 LANGUAGES CXX)

# GoogleTest 1.15 may use a newer dialect internally. The product core itself is
# explicitly pinned to strict C++11 below and is compiled independently from it.
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(dxw_core STATIC
    src/native/dxw/CandidateScorer.cpp
    src/native/dxw/CtyResolver.cpp
    src/native/dxw/Ft8SlotClock.cpp
    src/native/dxw/HistoryIndex.cpp
    src/native/dxw/HuntWatchdog.cpp
    src/native/dxw/QsoStateMachine.cpp
)
target_include_directories(dxw_core PUBLIC src/native)
set_target_properties(dxw_core PROPERTIES
    CXX_STANDARD 11
    CXX_STANDARD_REQUIRED YES
    CXX_EXTENSIONS NO
)
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
      tests/native/test_station_identity.cpp
      tests/native/test_history_index.cpp
      tests/native/test_cty_resolver.cpp
      tests/native/test_hunt_watchdog.cpp
  )
  set_target_properties(dxw_native_tests PROPERTIES
      CXX_STANDARD 14
      CXX_STANDARD_REQUIRED YES
      CXX_EXTENSIONS NO
  )
  target_link_libraries(dxw_native_tests PRIVATE dxw_core GTest::gtest_main)
  include(GoogleTest)
  gtest_discover_tests(dxw_native_tests DISCOVERY_TIMEOUT 60)
endif()
