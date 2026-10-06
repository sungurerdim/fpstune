#!/usr/bin/env bash
# The project's local quality contract, in one place: the same checks CI's
# backend and frontend jobs and the lefthook pre-commit run, over the same scope
# (src + tests for Python, frontend/ for the UI). Tools that look for a repo's
# entry point (a Stop-hook gate, an editor task) call this instead of guessing
# a command line — `mypy .` type-checks tests under strict and `ruff format .`
# reformats code blocks inside docs, neither of which is the project's contract.
#
# The two blocks run side by side and share the machine: pytest gets the cores
# divided by the number of blocks, measured here, never `-n auto` — two layers
# each assuming the whole machine oversubscribe it. Run one after the other and
# single-process, the gate took 14-19 minutes, almost all of it pytest.
set -euo pipefail
cd "$(dirname "$0")/.."

blocks=2
cores=$(nproc 2>/dev/null || echo 2)
workers=$((cores / blocks))
((workers < 1)) && workers=1
echo "quality: $cores cores, $blocks blocks side by side, pytest -n $workers"

backend() {
  uv run ruff check src tests
  uv run ruff format --check src tests
  uv run mypy src
  uv run pytest --no-cov -q -n "$workers"
}

frontend() {
  cd frontend
  npm run lint --silent
  npx tsc --noEmit
  npm run test:run --silent
}

# Each block's output goes to its own log, so the two never interleave; a red
# block prints its own tail and the summary says which one it was.
backend_log=$(mktemp)
frontend_log=$(mktemp)
trap 'rm -f "$backend_log" "$frontend_log"' EXIT

start=$SECONDS
(set -euo pipefail; backend) >"$backend_log" 2>&1 &
backend_pid=$!
(set -euo pipefail; frontend) >"$frontend_log" 2>&1 &
frontend_pid=$!

status=0
for block in backend frontend; do
  pid_var="${block}_pid"
  log_var="${block}_log"
  if wait "${!pid_var}"; then
    echo "green: $block — $(grep -aE 'passed|Tests +[0-9]' "${!log_var}" | tail -1 | sed 's/\x1b\[[0-9;]*m//g')"
  else
    code=$?
    status=1
    echo "red: $block (exit=$code) — last lines:"
    tail -40 "${!log_var}"
  fi
done
echo "quality: $((SECONDS - start)) s"
exit "$status"
