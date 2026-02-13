#!/usr/bin/env bash
# Run a command inside the project virtual environment.
# Usage: scripts/with-venv.sh <command> [args...]

set -euo pipefail

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    echo "Error: VIRTUAL_ENV is not set." >&2
    echo "Activate a virtual environment first, then rerun this command." >&2
    echo "Example: source /path/to/venv/bin/activate" >&2
    exit 1
fi

VENV_PATH="${VIRTUAL_ENV}"

if [[ $# -eq 0 ]]; then
    echo "Usage: scripts/with-venv.sh <command> [args...]" >&2
    exit 2
fi

if [[ ! -f "${VENV_PATH}/bin/activate" ]]; then
    echo "Error: virtual environment activation script not found at: ${VENV_PATH}/bin/activate" >&2
    echo "Ensure VIRTUAL_ENV points to a valid virtual environment path." >&2
    exit 1
fi

# shellcheck source=/dev/null
source "${VENV_PATH}/bin/activate"

exec "$@"
