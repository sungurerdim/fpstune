<!--
Title should follow Conventional Commits: feat: / fix: / refactor: / docs: / ci: / test:
Use `feat` only when a user can do something they could not before, and `fix`
only when something user-visible that was broken now works.
-->

## What and why

<!-- What changed, and what problem it solves. Link the issue with #N if there is one. -->

## How it was verified

<!--
The command you ran and what it printed — not "tests pass". If the change is
hardware-specific, say which hardware you ran it on, because that is the part
CI cannot cover.
-->

```
```

## Checklist

- [ ] `pytest tests/ -q` — 0 failed
- [ ] `cd frontend && npm run test:run` — 0 failed
- [ ] `ruff check src tests` and `mypy src` — clean
- [ ] Behaviour or interface changed → README / CLAUDE.md / docs updated to match
- [ ] Bug fix → a regression test that fails without the fix

## For a new or changed setting

<!-- Delete this section if the PR touches no SettingExecutor. -->

- [ ] `impact_scores` carries at least one numeric or range metric, not only `stability`
- [ ] `description` is 1–2 complete sentences ending with a period
- [ ] `current_impact` and `recommended_impact` follow `"State: consequence"`
- [ ] `risk_level="advanced"` → `risk_warning` is set and says what is traded away
- [ ] Values that hardware can report are derived from it, not hardcoded — or the
      comment says why a constant is correct here
- [ ] The setting cannot lower the machine's ceiling in any configuration
- [ ] Apply → detect → verify → reset round-trips on real hardware
