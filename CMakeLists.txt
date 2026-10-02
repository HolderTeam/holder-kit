cmake_minimum_required(VERSION 3.22)

project(holder_python LANGUAGES C CXX)

set(HOLDER_PYTHON_SANITIZE "" CACHE STRING
  "Sanitizers for the Python native shim (for example address,undefined)")

set(HOLDER_CORE_SDK "" CACHE PATH "Verified installed core SDK")
if(NOT "$ENV{HOLDER_CORE_SDK}" STREQUAL "")
  # pip can reuse its build directory across core promotions. Refresh the
  # environment selection rather than retaining an older cached SDK path.
  set(HOLDER_CORE_SDK "$ENV{HOLDER_CORE_SDK}")
endif()
file(TO_CMAKE_PATH "${HOLDER_CORE_SDK}" HOLDER_CORE_SDK)
set(HOLDER_PYTHON_CORE_SOURCE "" CACHE PATH "Explicit source-build development override")
if(HOLDER_PYTHON_CORE_SOURCE)
  set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
  add_subdirectory("${HOLDER_PYTHON_CORE_SOURCE}" holder-core EXCLUDE_FROM_ALL)
  set(holder_schema "${HOLDER_PYTHON_CORE_SOURCE}/schema/schema.sql")
else()
  if(NOT EXISTS "${HOLDER_CORE_SDK}/libholder-manifest.json")
    message(FATAL_ERROR "Missing core SDK. Run scripts/core-sdk.py resolve and fetch, then set HOLDER_CORE_SDK. No automatic source fallback is available.")
  endif()
  set(holder_DIR "${HOLDER_CORE_SDK}/lib/cmake/holder" CACHE PATH "Selected core CMake package" FORCE)
  find_package(holder CONFIG REQUIRED PATHS "${holder_DIR}" NO_DEFAULT_PATH)
  set(holder_schema "${HOLDER_CORE_SDK}/share/holder/schema/schema.sql")
  install(FILES "${HOLDER_CORE_SDK}/libholder-manifest.json" DESTINATION holder RENAME _core_build.json)
  if(WIN32)
    install(DIRECTORY "${HOLDER_CORE_SDK}/bin/" DESTINATION holder/.libs FILES_MATCHING PATTERN "*.dll")
    install(DIRECTORY "${HOLDER_CORE_SDK}/share/vcpkg-licenses/" DESTINATION holder/_licenses)
  endif()
endif()

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)

Python_add_library(_native MODULE WITH_SOABI src/native/module.c)
target_compile_features(_native PRIVATE c_std_11)
target_link_libraries(_native PRIVATE Holder::Core)
set_target_properties(_native PROPERTIES LINKER_LANGUAGE CXX)

if(HOLDER_PYTHON_SANITIZE)
  target_compile_options(_native PRIVATE
    -fsanitize=${HOLDER_PYTHON_SANITIZE}
    -fno-omit-frame-pointer
    -g
  )
  target_link_options(_native PRIVATE -fsanitize=${HOLDER_PYTHON_SANITIZE})
endif()

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  # CPython's PyType_Slot and PyModuleDef_Slot APIs require function pointers
  # to be stored as void pointers, which ISO-pedantic mode rejects by design.
  target_compile_options(_native PRIVATE -Wall -Wextra -Werror)
endif()

install(TARGETS _native
  LIBRARY DESTINATION holder
  RUNTIME DESTINATION holder
)

# Ship the schema from the selected core revision beside the Python package. The
# Python wrapper reads this resource at runtime, so installed packages never
# depend on the source checkout or an absolute development path.
install(FILES "${holder_schema}"
  DESTINATION holder
  RENAME _schema.sql
)
