"""Where fpstune keeps the state it owns on disk.

What used to be here was a YAML profile tree — `Config`, ten nested models,
`load_config`/`save_config`/`load_profile`. Profiles were replaced by scope
(essential/recommended/complete), which is chosen in the UI and never persisted
to a file, so nothing had read `~/.fpstune/config.yaml` for some time.

The directory is the part that stayed live: eight modules put their own file in
it (`headroom.json`, benchmark captures, the NVIDIA profile
cache), each owning its own format.
"""

from __future__ import annotations

from pathlib import Path

from fpstune.utils import user_paths


def get_config_dir() -> Path:
    """Get the fpstune configuration directory.

    Returns:
        Path to ~/.fpstune/ directory, resolved by `user_paths` like every
        other profile root.
    """
    return user_paths.fpstune_home()
