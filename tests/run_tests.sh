#!/usr/bin/env bash
# Ruff runner for Kayori v2

set -e

echo "Running Ruff checks..."

if command -v ruff >/dev/null 2>&1; then
    ruff_cmd=(ruff)
elif command -v python3 >/dev/null 2>&1 && python3 -m ruff --version >/dev/null 2>&1; then
    ruff_cmd=(python3 -m ruff)
elif command -v python >/dev/null 2>&1 && python -m ruff --version >/dev/null 2>&1; then
    ruff_cmd=(python -m ruff)
elif command -v uv >/dev/null 2>&1; then
    ruff_cmd=(uv run ruff)
else
    echo "Ruff is not available. Install it in your venv/pip environment or use uv." >&2
    exit 1
fi

"${ruff_cmd[@]}" check src/ examples/ tests/ "$@"
