#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REQUIREMENTS_FILE="$REPO_ROOT/backend/requirements.txt"
WHEELHOUSE_DIR="$REPO_ROOT/vendor/python-wheels"

log() {
    printf '\n== %s ==\n' "$1"
}

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    echo "Missing backend requirements file: $REQUIREMENTS_FILE" >&2
    exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python executable not found: $PYTHON_BIN" >&2
    echo "Set PYTHON_BIN=/path/to/python if needed." >&2
    exit 127
fi

log "Build Python wheelhouse"
echo "Repository: $REPO_ROOT"
echo "Requirements: $REQUIREMENTS_FILE"
echo "Wheelhouse: $WHEELHOUSE_DIR"
echo "Python: $("$PYTHON_BIN" --version)"

mkdir -p "$WHEELHOUSE_DIR"

"$PYTHON_BIN" -m pip wheel \
    -r "$REQUIREMENTS_FILE" \
    -w "$WHEELHOUSE_DIR"

WHEEL_COUNT="$(
    find "$WHEELHOUSE_DIR" -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d '[:space:]'
)"

log "Summary"
echo "wheel_files=$WHEEL_COUNT"
echo "wheelhouse_path=$WHEELHOUSE_DIR"
