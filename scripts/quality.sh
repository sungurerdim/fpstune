#!/usr/bin/env bash
# The project's local quality contract, in one place: the same checks CI's
# backend and frontend jobs and the lefthook pre-commit run, over the same scope
# (src + tests for Python, frontend/ for the UI). Tools that look for a repo's
# entry point (a Stop-hook gate, an editor task) call this instead of guessing
# a command line — `mypy .` type-checks tests under strict and `ruff format .`
# reformats code blocks inside docs, neither of which is the project's contract.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest --no-cov -q

cd frontend
npm run lint --silent
npx tsc --noEmit
npm run test:run --silent
