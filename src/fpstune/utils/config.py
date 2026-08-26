"""Where fpstune keeps the state it owns on disk.

What used to be here was a YAML profile tree — `Config`, ten nested models,
`load_config`/`save_config`/`load_profile`. Profiles were replaced by scope
(essential/recommended/complete), which is chosen in the UI and never persisted
to a file, so nothing had read `~/.fpstune/config.yaml` for some time.

The directory is the part that stayed live: eight modules put their own file in
it (`originals.json`, `headroom.json`, benchmark captures, the NVIDIA profile
cache), each owning its own format.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_config_dir() -> Path:
    """Get the fpstune configuration directory.

    Returns:
        Path to ~/.fpstune/ directory.
    """
    # Windows: Use USERPROFILE, otherwise use home()
    home = Path(os.environ.get("USERPROFILE", "~")).expanduser() if os.name == "nt" else Path.home()

    config_dir = home / ".fpstune"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir
