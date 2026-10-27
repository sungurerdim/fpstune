#!/usr/bin/env bash
# Mutation testing for the two critical pure modules (P-MUTATION).
#
# Coverage says a line ran; mutation testing says the tests would notice if the
# line were wrong. The catalogue's violation example is the pair that makes this
# gate necessary — "95% coverage, 20% mutation score" — and this repository has
# the same shape available: `settings/applicability.py` holds the comparison
# truth C6's "verified" claim rests on, and a test that calls it without
# asserting the verdict passes while killing nothing.
#
# The modules are chosen because they are pure: no PowerShell, no registry, no
# hardware. A mutant in a pure module is decided by the tests alone, so a
# surviving one names a missing assertion rather than a flaky host.
#
#   bash scripts/mutation.sh                  run, floor 70
#   bash scripts/mutation.sh --min-score 80   a stricter floor
#   bash scripts/mutation.sh --list           the modules and the floor, no run
#
# Exit codes: 0 score at or above the floor, 1 below it, 2 the gate cannot run
# here (mutmut missing, wrong version, or no [tool.mutmut] configuration — that
# is not a verdict on the code), 3 the run itself failed.
#
# WHY MUTMUT 2.4.4 AND NOT 3.x
# 3.x refuses native Windows ("To run mutmut on Windows, please use the WSL",
# boxed/mutmut#397). fpstune ships to Windows 11 only, so its quality gates must
# run on Windows without WSL: 2.4.4 is the last Windows-native release and is
# pinned in pyproject's dev extra. The configuration shape in pyproject is the
# 2.4.4 one (`paths_to_mutate`, `runner`, `test_time_multiplier`).
#
# WHY THIS IS NOT A HOOK
# It mutates the tree in place while it runs and re-runs pytest per mutant: a
# pre-push run would cost more than the whole quality gate. It is a manual gate,
# run on the modules that carry risk. The two source files are copied to a
# temporary directory first and restored on exit, so an interrupted run cannot
# leave a mutation in the working tree.
set -euo pipefail
cd "$(dirname "$0")/.."

# mutmut 2.4.4 prints an emoji in its summary; the Windows console defaults to a
# legacy code page and dies with UnicodeEncodeError before the score is printed.
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

MIN_SCORE=80
LIST_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --min-score) MIN_SCORE="${2:?--min-score needs a number}"; shift 2 ;;
    --min-score=*) MIN_SCORE="${1#*=}"; shift ;;
    --list) LIST_ONLY=1; shift ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "mutation: unknown argument $1" >&2; exit 3 ;;
  esac
done

MODULES="src/fpstune/settings/applicability.py src/fpstune/settings/bulk_plan.py"

if [ "$LIST_ONLY" -eq 1 ]; then
  echo "mutation: floor ${MIN_SCORE}%"
  for module in $MODULES; do echo "  $module"; done
  exit 0
fi

# The installed version, read from the package rather than from a CLI flag: a
# 3.x binary refuses before it parses a command on Windows.
version=$(uv run --extra dev python -c 'import mutmut; print(getattr(mutmut, "__version__", ""))' 2>/dev/null || true)
if [ -z "$version" ]; then
  echo "mutation: mutmut is not importable — this gate cannot run (exit 2), which is" >&2
  echo "not a verdict on the code. Install the dev extra: uv sync --extra dev" >&2
  exit 2
fi
case "$version" in
  2.*) ;;
  *)
    echo "mutation: mutmut ${version} does not run on native Windows; this gate needs" >&2
    echo "the pinned 2.4.4 (uv sync --extra dev). WSL is deliberately not a dependency" >&2
    echo "of a Windows-only product. Exit 2: not a verdict on the code." >&2
    exit 2
    ;;
esac

# The configuration is the gate: without paths_to_mutate and a scoped runner,
# mutmut would mutate the whole tree and run the whole suite per mutant.
if ! uv run --extra dev python - <<'PY'
import tomllib

config = tomllib.load(open("pyproject.toml", "rb")).get("tool", {}).get("mutmut", {})
missing = [key for key in ("paths_to_mutate", "runner") if not config.get(key)]
raise SystemExit(1 if missing else 0)
PY
then
  echo "mutation: pyproject.toml has no [tool.mutmut] paths_to_mutate/runner (exit 2)." >&2
  exit 2
fi

# Restore the sources on every exit path: mutmut rewrites them in place.
backup=$(mktemp -d)
for module in $MODULES; do
  cp "$module" "$backup/$(basename "$module")"
done
restore() {
  for module in $MODULES; do
    cp "$backup/$(basename "$module")" "$module"
  done
  rm -rf "$backup"
}
trap restore EXIT

echo "mutation: mutmut ${version}, modules: ${MODULES}"
if ! uv run --extra dev mutmut run --no-progress --CI; then
  echo "mutation: the mutmut run failed (exit 3) — not a score." >&2
  exit 3
fi

count_ids() {
  uv run --extra dev mutmut result-ids "$1" 2>/dev/null | tr ' ' '\n' | grep -c '[0-9]' || true
}
killed=$(count_ids killed)
survived=$(count_ids survived)
timeout=$(count_ids timeout)
suspicious=$(count_ids suspicious)
skipped=$(count_ids untested)
total=$((killed + survived + timeout + suspicious + skipped))

# A timeout is a killed mutant: the tests did not finish because the mutation
# broke them. Skipped/untested are excluded from the denominator and reported:
# they mean mutmut could not decide, which is a gap, not a pass.
tested=$((total - skipped))
if [ "$tested" -le 0 ]; then
  echo "mutation: no mutants were decided — check paths_to_mutate and runner." >&2
  exit 3
fi
score=$((100 * (killed + timeout) / tested))

echo "mutation: killed ${killed}, survived ${survived}, timeout ${timeout}, suspicious ${suspicious}, skipped ${skipped}, total ${total}"
echo "mutation: score ${score}% (floor ${MIN_SCORE}%)"
if [ "$score" -lt "$MIN_SCORE" ]; then
  echo "mutation: RED — a surviving mutant is a test that passes without checking anything:" >&2
  uv run --extra dev mutmut results 2>/dev/null | grep -iE 'survived|not killed' >&2 || true
  exit 1
fi
echo "mutation: green"
exit 0

# MEASURED SCORE (2026-10-26, native Windows, mutmut 2.4.4)
#   before (branch/message tests missing): 132 killed, 133 survived -> 50%
#   after:                                231 killed,  34 survived, 2 timeout -> 87%
#     bulk_plan:      39 killed,   5 survived, 2 timeout  -> 89%
#     applicability: 192 killed,  29 survived, 0 timeout  -> 87%
# The floor is set just under the measured overall score, not aspirationally.
# The first run exposed the gap (50%); the tests added for it are in
# tests/test_settings/test_applicability.py. Residual survivors are mostly
# message text and defence lines the conditions cannot reach on a valid context;
# re-run and raise this floor after any further test work.
