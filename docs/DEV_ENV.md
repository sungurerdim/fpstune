# Developer environment on this Windows install

## The `.venv` junction

CPython's venv launcher fails for any environment created **inside**
`D:\GitHub\fpstune` on this machine:

```
No pyvenv.cfg file
exit code 106
```

The same interpreter creates a working venv under `D:\GitHub`,
`D:\GitHub\fpstune-test` and `D:\tmp`, so this is a path-specific launcher
problem, not a project one.

The supported layout is therefore:

```
%LOCALAPPDATA%\fpstune\venv     real environment
D:\GitHub\fpstune\.venv         junction -> the path above
```

Create or repair it with:

```cmd
scripts\setup_dev_env.cmd
```

or, without the wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_dev_env.ps1
```

The script refuses to delete a real (non-junction) `.venv`. Use `-Recreate` to
rebuild the external environment. It then runs `uv sync --locked --extra dev`
and prints the interpreter, pytest version and fpstune import path.

Why it works: the venv executable's real path is under `%LOCALAPPDATA%`, so the
launcher finds its `pyvenv.cfg`; `.venv` is only a directory junction pointing
at it.

## Execution policy

This machine has `LocalMachine = RemoteSigned`, so an unsigned local `.ps1` is
blocked. Do **not** change the machine policy for one script; the wrappers use
`-ExecutionPolicy Bypass` for their own process only:

```cmd
rem real sweep, asks for elevation through UAC
run_apply_sweep.cmd

rem print the selection, write nothing, no elevation needed
run_apply_sweep.cmd -DryRun
```

From an existing elevated PowerShell the equivalent is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_apply_sweep.ps1
```

The bypass is scoped to the child process and disappears when it exits.

## Normal gates

```powershell
uv sync --locked --extra dev --python 3.12
uv run --extra dev pytest --no-cov -q -n 8 -m "not timing"
uv run --extra dev ruff check src tests
```

`tests/test_quality_gate_env.py` keeps the `--extra dev` spelling honest.
