#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${HOLDER_PYTHON_VENV:-${SCRIPT_DIR}/.venv}"
if [[ "${VENV_DIR}" != /* ]]; then VENV_DIR="${SCRIPT_DIR}/${VENV_DIR}"; fi

if [[ -n "${HOLDER_PYTHON:-}" ]]; then
  PYTHON_BIN="${HOLDER_PYTHON}"
elif [[ -x "${VENV_DIR}/bin/python" ]]; then
  PYTHON_BIN="${VENV_DIR}/bin/python"
elif [[ -x "${VENV_DIR}/Scripts/python.exe" ]]; then
  PYTHON_BIN="${VENV_DIR}/Scripts/python.exe"
else
  PYTHON_BIN=python3
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo 'Python 3.10 or newer is required. Install Python and set HOLDER_PYTHON if it is not named python3.' >&2
  exit 2
fi
if ! "${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo 'Python 3.10 or newer is required. Set HOLDER_PYTHON to a supported interpreter.' >&2
  exit 2
fi
exec "${PYTHON_BIN}" -B "${SCRIPT_DIR}/scripts/develop.py" "$@"
