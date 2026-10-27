"""Names vulture reports that are used, but not in a way it can see.

Run as part of the gate:

    uv run --extra dev vulture src/fpstune vulture_whitelist.py --min-confidence 80

`--min-confidence 80` is deliberate. At 60 vulture also reports pydantic fields
(the frontend reads them, Python never does), FastAPI route handlers and click
commands (both registered by decorator, never called by name) and ``ctypes``
structure fields (filled by Windows) — hundreds of true false positives, which
would turn a gate into a reading exercise. At 80 the only things it reports are
dead code by vulture's own definition: unused functions, variables and imports.

An entry belongs here only when the name is genuinely reachable and vulture
cannot follow the route — a callback looked up by string, a protocol method
called through a third-party hook, an attribute a test suite patches. Each one
gets a one-line reason, and the reason is why it is kept, not what it is.

No entries today: the gate is green at 80 without exemptions. Add one here
rather than lowering the confidence, and delete it in the same change that
removes the dynamic use.
"""
