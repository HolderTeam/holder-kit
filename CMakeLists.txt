cmake_minimum_required(VERSION 3.22)

project(holder_kit LANGUAGES C CXX)

set(HOLDER_KIT_SANITIZE "" CACHE STRING
  "Sanitizers for the Python native shim (for example address,undefined)")

set(HOLDER_CORE_SDK "" CACHE PATH "Verified installed core SDK")
if(NOT "$ENV{HOLDER_CORE_SDK}" STREQUAL "")
  # pip can reuse its build directory across core promotions. Refresh the
  # environment selection rather than retaining an older cached SDK path.
  set(HOLDER_CORE_SDK "$ENV{HOLDER_CORE_SDK}")
endif()
file(TO_CMAKE_PATH "${HOLDER_CORE_SDK}" HOLDER_CORE_SDK)
set(HOLDER_KIT_CORE_SOURCE "" CACHE PATH "Explicit source-build development override")
option(HOLDER_USE_SYSTEM_CORE "Link against the installed libholder shared library" OFF)
set(HOLDER_KIT_INSTALL_DIR "holderkit" CACHE STRING "Python package installation directory")
set(holder_core_target Holder::Core)
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
if(HOLDER_USE_SYSTEM_CORE)
  if(HOLDER_KIT_CORE_SOURCE OR HOLDER_CORE_SDK)
    message(FATAL_ERROR "System core cannot be combined with a source override or HOLDER_CORE_SDK")
  endif()
  find_package(holder 0.2.0 CONFIG REQUIRED)
  if(NOT TARGET Holder::Shared)
    message(FATAL_ERROR "System core requires libholder-dev exporting Holder::Shared")
  endif()
  set(holder_core_target Holder::Shared)
  if(NOT DEFINED holder_DATA_DIR)
    # The first Ubuntu core packages predate the exported resource paths.
    find_path(holder_DATA_DIR schema/schema.sql
      PATHS /usr/share/holder /usr/local/share/holder REQUIRED)
  endif()
  set(holder_schema "${holder_DATA_DIR}/schema/schema.sql")
  execute_process(
    COMMAND "${Python_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/system-core-build-info.py"
      --version "${holder_VERSION}" --schema "${holder_schema}"
      --output "${CMAKE_CURRENT_BINARY_DIR}/system-core-build.json"
    COMMAND_ERROR_IS_FATAL ANY)
  install(FILES "${CMAKE_CURRENT_BINARY_DIR}/system-core-build.json"
    DESTINATION "${HOLDER_KIT_INSTALL_DIR}" RENAME _core_build.json)
elseif(HOLDER_KIT_CORE_SOURCE)
  set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
  add_subdirectory("${HOLDER_KIT_CORE_SOURCE}" holder-core EXCLUDE_FROM_ALL)
  set(holder_schema "${HOLDER_KIT_CORE_SOURCE}/schema/schema.sql")
else()
  if(NOT EXISTS "${HOLDER_CORE_SDK}/libholder-manifest.json")
    message(FATAL_ERROR "Missing core SDK. Run scripts/core-sdk.py resolve and fetch, then set HOLDER_CORE_SDK. No automatic source fallback is available.")
  endif()
  set(holder_DIR "${HOLDER_CORE_SDK}/lib/cmake/holder" CACHE PATH "Selected core CMake package" FORCE)
  find_package(holder CONFIG REQUIRED PATHS "${holder_DIR}" NO_DEFAULT_PATH)
  set(holder_schema "${HOLDER_CORE_SDK}/share/holder/schema/schema.sql")
  install(FILES "${HOLDER_CORE_SDK}/libholder-manifest.json" DESTINATION "${HOLDER_KIT_INSTALL_DIR}" RENAME _core_build.json)
  if(WIN32)
    install(DIRECTORY "${HOLDER_CORE_SDK}/bin/" DESTINATION "${HOLDER_KIT_INSTALL_DIR}/.libs" FILES_MATCHING PATTERN "*.dll")
    install(DIRECTORY "${HOLDER_CORE_SDK}/share/vcpkg-licenses/" DESTINATION "${HOLDER_KIT_INSTALL_DIR}/_licenses")
  endif()
endif()

Python_add_library(_native MODULE WITH_SOABI src/native/module.c)
target_compile_features(_native PRIVATE c_std_11)
target_link_libraries(_native PRIVATE ${holder_core_target})
set_target_properties(_native PROPERTIES LINKER_LANGUAGE CXX)

if(HOLDER_KIT_SANITIZE)
  target_compile_options(_native PRIVATE
    -fsanitize=${HOLDER_KIT_SANITIZE}
    -fno-omit-frame-pointer
    -g
  )
  target_link_options(_native PRIVATE -fsanitize=${HOLDER_KIT_SANITIZE})
endif()

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  # CPython's PyType_Slot and PyModuleDef_Slot APIs require function pointers
  # to be stored as void pointers, which ISO-pedantic mode rejects by design.
  target_compile_options(_native PRIVATE -Wall -Wextra -Werror)
endif()

install(TARGETS _native
  LIBRARY DESTINATION "${HOLDER_KIT_INSTALL_DIR}"
  RUNTIME DESTINATION "${HOLDER_KIT_INSTALL_DIR}"
)
install(DIRECTORY src/holderkit/ DESTINATION "${HOLDER_KIT_INSTALL_DIR}"
  FILES_MATCHING PATTERN "*.py" PATTERN "py.typed")

# Ship the schema from the selected core revision beside the Python package. The
# Python wrapper reads this resource at runtime, so installed packages never
# depend on the source checkout or an absolute development path.
install(FILES "${holder_schema}"
  DESTINATION "${HOLDER_KIT_INSTALL_DIR}"
  RENAME _schema.sql
)
