cmake_minimum_required(VERSION 3.22)

project(holder_python LANGUAGES C CXX)

set(HOLDER_PYTHON_SANITIZE "" CACHE STRING
  "Sanitizers for the native extension and holder-core (for example address,undefined)")

if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/submodules/holder-core/CMakeLists.txt")
  message(FATAL_ERROR
    "Missing holder-core. Run: git submodule update --init --recursive")
endif()

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
if(HOLDER_PYTHON_SANITIZE)
  set(HOLDER_CORE_SANITIZE "${HOLDER_PYTHON_SANITIZE}" CACHE STRING "" FORCE)
endif()
# Build the pinned core for the extension, but do not inherit its SDK install
# rules into the Python wheel.
add_subdirectory(submodules/holder-core holder-core EXCLUDE_FROM_ALL)

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

# Ship the schema from the pinned core revision beside the Python package. The
# Python wrapper reads this resource at runtime, so installed packages never
# depend on the source checkout or an absolute development path.
install(FILES submodules/holder-core/schema/schema.sql
  DESTINATION holder
  RENAME _schema.sql
)
