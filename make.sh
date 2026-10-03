#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

print_usage() {
  cat <<'EOF'
Usage:
  ./make.sh [command] [BuildType] [args...]

Commands:
  help, -h, --help          Show this help without building or downloading
  setup [BuildType]        Create/reuse .venv and install the editable test extras
  build [BuildType]        Build and install the editable package (same as setup)
  test [BuildType] [args]  Build, then run pytest; forward args to pytest (default)
  typecheck [args]         Run strict mypy; forward args to mypy
  check [BuildType]        Build, run all tests, then strict mypy
  wheel [BuildType]        Build a wheel into out/make/wheels
  examples [name]          Run all examples, or lifecycle, records, pandas, graph
  sdk [core-ref]           Resolve and fetch an SDK (default latest-green)
  clean                   Remove only build/make and out/make

BuildType: RelWithDebInfo (default), Release, Debug, or MinSizeRel.
SDK builds use Release for Release/MinSizeRel, otherwise RelWithDebInfo.
Tests/builds reuse out/core-selection.json unless HOLDER_CORE_REF is supplied.
typecheck/examples use the installed package; run setup first in a new checkout.

Examples:
  ./make.sh --help
  ./make.sh
  ./make.sh test -k connections
  ./make.sh check
  ./make.sh wheel Release
  ./make.sh examples graph
  ./make.sh sdk <tag-or-full-SHA>
  HOLDER_PYTHON_CORE_SOURCE=../holder-core ./make.sh test Debug

Environment:
  HOLDER_PYTHON              Python for creating a venv (default python3)
  HOLDER_PYTHON_VENV         Virtualenv path (default .venv)
  BUILD_TYPE                Default CMake build type (default RelWithDebInfo)
  CMAKE_BUILD_PARALLEL_LEVEL Optional native build parallelism limit
  HOLDER_CORE_REF            Explicit core tag/SHA, or latest-green
  HOLDER_CORE_SDK            Use an already prepared SDK directory
  HOLDER_CORE_SDK_TOOL       Override the shared SDK tool in ../holder-core
  HOLDER_PYTHON_CORE_SOURCE  Explicit core source checkout; skips SDK fetching

Build/test/setup install .[test], including pandas, NetworkX and type stubs.
SDK selection/download and pip installation may require network access.
This script does not activate the venv in your shell: source .venv/bin/activate.
EOF
}

fail() {
  echo "${*}" >&2
  exit 2
}

MODE="${1:-test}"
if [ "$#" -gt 0 ]; then shift; fi
case "${MODE}" in
  help|-h|--help) print_usage; exit 0 ;;
  setup|build|test|typecheck|check|wheel|examples|sdk|clean) ;;
  *) print_usage >&2; fail "Unknown command: ${MODE}" ;;
esac

BUILD_TYPE="${BUILD_TYPE:-RelWithDebInfo}"
case "${MODE}" in
  setup|build|test|check|wheel)
    case "${1:-}" in
      Debug|Release|RelWithDebInfo|MinSizeRel) BUILD_TYPE="$1"; shift ;;
    esac
    ;;
esac
case "${BUILD_TYPE}" in
  Debug|Release|RelWithDebInfo|MinSizeRel) ;;
  *) fail "Invalid BUILD_TYPE: ${BUILD_TYPE}" ;;
esac
case "${MODE}" in
  setup|build|check|wheel|clean) [ "$#" -eq 0 ] || fail "Unexpected arguments for ${MODE}: $*" ;;
  sdk) [ "$#" -le 1 ] || fail "sdk accepts one core ref" ;;
  examples)
    [ "$#" -le 1 ] || fail "examples accepts one example name"
    case "${1:-all}" in
      all|lifecycle|records|pandas|graph) ;;
      *) fail "Unknown example: $1 (expected lifecycle, records, pandas, graph, or all)" ;;
    esac
    ;;
esac

VENV_DIR="${HOLDER_PYTHON_VENV:-.venv}"
VENV_PYTHON="${VENV_DIR}/bin/python"
if [ -x "${VENV_DIR}/Scripts/python.exe" ]; then
  VENV_PYTHON="${VENV_DIR}/Scripts/python.exe"
fi

require_venv() {
  [ -x "${VENV_PYTHON}" ] || fail "No virtualenv at ${VENV_DIR}. Run ./make.sh setup first."
}

prepare_venv() {
  if [ ! -x "${VENV_PYTHON}" ]; then
    [ ! -e "${VENV_DIR}" ] || fail "${VENV_DIR} exists but has no virtualenv Python; choose HOLDER_PYTHON_VENV."
    "${HOLDER_PYTHON:-python3}" -m venv "${VENV_DIR}"
    if [ -x "${VENV_DIR}/Scripts/python.exe" ]; then
      VENV_PYTHON="${VENV_DIR}/Scripts/python.exe"
    fi
  fi
  require_venv
}

fetch_sdk() {
  local sdk_build_type=RelWithDebInfo
  case "${BUILD_TYPE}" in Release|MinSizeRel) sdk_build_type=Release ;; esac
  export HOLDER_CORE_SDK
  HOLDER_CORE_SDK="$("${VENV_PYTHON}" scripts/core-sdk.py fetch --build-type "${sdk_build_type}")"
}

prepare_core() {
  if [ -n "${HOLDER_PYTHON_CORE_SOURCE:-}" ]; then
    [ -f "${HOLDER_PYTHON_CORE_SOURCE}/CMakeLists.txt" ] || fail "HOLDER_PYTHON_CORE_SOURCE must name a core source checkout."
    HOLDER_PYTHON_CORE_SOURCE="$(cd "${HOLDER_PYTHON_CORE_SOURCE}" && pwd)"
    CORE_BACKEND=source
  else
    CORE_BACKEND=sdk
    if [ -z "${HOLDER_CORE_SDK:-}" ]; then
      if [ ! -f out/core-selection.json ] || [ -n "${HOLDER_CORE_REF:-}" ]; then
        "${VENV_PYTHON}" scripts/core-sdk.py resolve
      fi
      fetch_sdk
    fi
    [ -f "${HOLDER_CORE_SDK}/libholder-manifest.json" ] || fail "HOLDER_CORE_SDK must name a prepared SDK containing libholder-manifest.json."
    export HOLDER_CORE_SDK
  fi
  BUILD_SETTINGS=(
    "--config-settings=build-dir=build/make/${CORE_BACKEND}/${BUILD_TYPE}/{wheel_tag}"
    "--config-settings=cmake.build-type=${BUILD_TYPE}"
    "--config-settings=cmake.define.HOLDER_PYTHON_CORE_SOURCE=${HOLDER_PYTHON_CORE_SOURCE:-}"
    "--config-settings=cmake.define.HOLDER_PYTHON_SANITIZE="
  )
  # Pass Windows SDK dependency paths as distinct pip arguments, including spaces.
  if [ "${CORE_BACKEND}" = sdk ] && [ -x "${VENV_DIR}/Scripts/python.exe" ]; then
    BUILD_SETTINGS+=(
      "--config-settings=cmake.define.CMAKE_TOOLCHAIN_FILE=${HOLDER_CORE_SDK}/vcpkg/scripts/buildsystems/vcpkg.cmake"
      "--config-settings=cmake.define.VCPKG_INSTALLED_DIR=${HOLDER_CORE_SDK}/vcpkg/installed"
      "--config-settings=cmake.define.VCPKG_TARGET_TRIPLET=x64-windows"
      "--config-settings=cmake.define.VCPKG_MANIFEST_MODE=OFF"
      "--config-settings=cmake.define.VCPKG_APPLOCAL_DEPS=OFF"
    )
  fi
}

build_editable() {
  prepare_venv
  prepare_core
  "${VENV_PYTHON}" -m pip install -e '.[test]' "${BUILD_SETTINGS[@]}"
}

case "${MODE}" in
  setup|build) build_editable ;;
  test)
    build_editable
    "${VENV_PYTHON}" -m pytest "$@"
    ;;
  check)
    build_editable
    "${VENV_PYTHON}" -m pytest
    "${VENV_PYTHON}" -m mypy
    ;;
  typecheck)
    require_venv
    "${VENV_PYTHON}" -m mypy "$@"
    ;;
  wheel)
    prepare_venv
    prepare_core
    "${VENV_PYTHON}" -m pip wheel --no-deps . --wheel-dir out/make/wheels "${BUILD_SETTINGS[@]}"
    ;;
  examples)
    require_venv
    case "${1:-all}" in
      lifecycle) "${VENV_PYTHON}" examples/card_lifecycle.py ;;
      records) "${VENV_PYTHON}" examples/detached_records.py ;;
      pandas) "${VENV_PYTHON}" examples/pandas_analysis.py ;;
      graph) "${VENV_PYTHON}" examples/graph_analysis.py ;;
      all)
        for example in card_lifecycle detached_records pandas_analysis graph_analysis; do
          "${VENV_PYTHON}" "examples/${example}.py"
        done
        ;;
    esac
    ;;
  sdk)
    prepare_venv
    "${VENV_PYTHON}" scripts/core-sdk.py resolve --core-ref "${1:-${HOLDER_CORE_REF:-latest-green}}"
    fetch_sdk
    echo "SDK ready: ${HOLDER_CORE_SDK}"
    ;;
  clean)
    for directory in build out; do
      [ ! -L "${directory}" ] && [ ! -L "${directory}/make" ] || fail "Refusing to clean symlinked ${directory}/make."
    done
    rm -rf -- "${SCRIPT_DIR}/build/make" "${SCRIPT_DIR}/out/make"
    echo "Removed build/make and out/make; virtualenv and SDK cache retained."
    ;;
esac
