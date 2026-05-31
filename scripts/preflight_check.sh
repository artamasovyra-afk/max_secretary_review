#!/usr/bin/env bash
set -Eeuo pipefail

missing=0

print_header() {
    printf 'max_secretary development preflight\n'
    printf '====================================\n'
}

check_command() {
    local name="$1"
    local command_name="${2:-$1}"
    local version_command="${3:-}"
    local path

    if path="$(command -v "$command_name" 2>/dev/null)"; then
        printf 'OK      %-16s %s\n' "$name" "$path"
        if [[ -n "$version_command" ]]; then
            # shellcheck disable=SC2086
            $version_command 2>/dev/null | head -n 1 | sed "s/^/        /" || true
        fi
    else
        printf 'MISSING %-16s install it before running local release checks\n' "$name"
        missing=1
    fi
}

check_pip() {
    local path

    if path="$(command -v pip 2>/dev/null)"; then
        printf 'OK      %-16s %s\n' "pip" "$path"
        pip --version 2>/dev/null | head -n 1 | sed 's/^/        /' || true
        return
    fi

    if python3 -m pip --version >/dev/null 2>&1; then
        printf 'OK      %-16s %s\n' "pip" "python3 -m pip"
        python3 -m pip --version 2>/dev/null | head -n 1 | sed 's/^/        /' || true
        return
    fi

    printf 'MISSING %-16s install pip for Python 3 before running backend checks\n' "pip"
    missing=1
}

check_docker_compose() {
    if ! command -v docker >/dev/null 2>&1; then
        printf 'MISSING %-16s docker CLI is missing, cannot check docker compose\n' "docker compose"
        missing=1
        return
    fi

    if docker compose version >/dev/null 2>&1; then
        printf 'OK      %-16s docker compose plugin available\n' "docker compose"
        docker compose version 2>/dev/null | head -n 1 | sed 's/^/        /' || true
    else
        printf 'MISSING %-16s install Docker Compose v2 plugin\n' "docker compose"
        missing=1
    fi
}

print_header
check_command "python3" "python3" "python3 --version"
check_pip
check_command "node" "node" "node --version"
check_command "npm" "npm" "npm --version"
check_command "docker" "docker" "docker --version"
check_docker_compose
check_command "git" "git" "git --version"
check_command "curl" "curl" "curl --version"
check_command "jq" "jq" "jq --version"

if [[ "$missing" -ne 0 ]]; then
    printf '\nPreflight failed: install missing tools or run full checks on VPS/CI.\n' >&2
    exit 1
fi

printf '\nPreflight passed: required local tools are available.\n'
