"""Safety mechanisms for fpstune.

Rollback is handled by Windows System Restore. The manifest-based backup,
revert and settings-state modules were removed because their state store was
never written to, which made every backup empty and every revert a no-op.
"""

from fpstune.safety.restore import RestorePointManager

__all__ = ["RestorePointManager"]
