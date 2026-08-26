"""DISM (Deployment Image Servicing and Management) operations for fpstune."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanupResult:
    """Cleanup operation result."""

    success: bool
    space_freed_mb: int
    message: str
    details: list[str]


class Dism:
    """Windows DISM and cleanup operations wrapper."""

    def __init__(self) -> None:
        """Initialize DISM wrapper."""
        self._available = sys.platform == "win32"

    @property
    def is_available(self) -> bool:
        """Check if DISM operations are available."""
        return self._available

    def _run_dism(self, *args: str, timeout: int = 600) -> tuple[bool, str]:
        """Run DISM command.

        Args:
            *args: DISM arguments.
            timeout: Timeout in seconds (default: 10 minutes).

        Returns:
            Tuple of (success, output).
        """
        if not self._available:
            return False, "Not available on this platform"

        try:
            # DISM requires elevation
            result = subprocess.run(
                ["dism.exe", "/Online", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,  # Windows-only
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Operation timed out"
        except Exception as e:
            return False, str(e)

    def component_cleanup(self) -> CleanupResult:
        """Run DISM component cleanup.

        This cleans up superseded components and reduces WinSxS folder size.
        Note: This may take several minutes.

        Returns:
            CleanupResult with operation status.
        """
        if not self._available:
            return CleanupResult(
                success=False,
                space_freed_mb=0,
                message="Not available on this platform",
                details=[],
            )

        # Get initial WinSxS size
        system_root = os.environ.get("SYSTEMROOT", "C:\\Windows")
        if not system_root or not Path(system_root).is_dir():
            return CleanupResult(
                success=False,
                space_freed_mb=0,
                message="Invalid SystemRoot path",
                details=[f"SystemRoot: {system_root}"],
            )
        winsxs_path = Path(system_root) / "WinSxS"
        initial_size = self._get_folder_size(winsxs_path)

        success, output = self._run_dism(
            "/Cleanup-Image",
            "/StartComponentCleanup",
            timeout=1800,  # 30 minutes max
        )

        # Get final size
        final_size = self._get_folder_size(winsxs_path)
        space_freed = max(0, initial_size - final_size)

        details = []
        if success:
            details.append(f"WinSxS initial size: {initial_size} MB")
            details.append(f"WinSxS final size: {final_size} MB")
            details.append(f"Space freed: {space_freed} MB")
        else:
            details.append(output)

        return CleanupResult(
            success=success,
            space_freed_mb=space_freed,
            message="Component cleanup completed" if success else "Component cleanup failed",
            details=details,
        )

    def clean_temp_files(self) -> CleanupResult:
        """Clean temporary files.

        Cleans the user temp folder (%TEMP%) and the Windows temp folder.
        Prefetch is deliberately not touched here: it is its own user-selectable
        setting (``cleanup:prefetch``), because clearing it costs a slower first
        launch and that is a choice, not a side effect of clearing temp files.

        Returns:
            CleanupResult with operation status.
        """
        details = []
        total_freed = 0

        # User temp folder
        user_temp = Path(tempfile.gettempdir())
        freed, count = self._clean_folder(user_temp)
        total_freed += freed
        details.append(f"User temp: {count} files, {freed} MB freed")

        # Windows temp folder
        if self._available:
            win_temp = Path(os.environ.get("SYSTEMROOT", "C:\\Windows")) / "Temp"
            freed, count = self._clean_folder(win_temp)
            total_freed += freed
            details.append(f"Windows temp: {count} files, {freed} MB freed")

        return CleanupResult(
            success=True,
            space_freed_mb=total_freed,
            message=f"Cleaned temporary files: {total_freed} MB freed",
            details=details,
        )

    def _get_folder_size(self, path: Path) -> int:
        """Get folder size in MB.

        Args:
            path: Path to folder.

        Returns:
            Size in MB.
        """
        if not path.exists():
            return 0

        total = 0
        try:
            for entry in path.rglob("*"):
                try:
                    if entry.is_file():
                        total += entry.stat().st_size
                except (PermissionError, OSError):
                    # Skip files we can't access (system files, locked files)
                    pass
        except (PermissionError, OSError) as e:
            import logging

            logging.getLogger(__name__).debug("Failed to calculate folder size for %s: %s", path, e)

        return total // (1024 * 1024)

    def _clean_folder(self, path: Path) -> tuple[int, int]:
        """Clean a folder's contents.

        Args:
            path: Path to folder.

        Returns:
            Tuple of (MB freed, files deleted).
        """
        if not path.exists():
            return 0, 0

        freed = 0
        count = 0

        try:
            for entry in path.iterdir():
                try:
                    if entry.is_file():
                        size = entry.stat().st_size
                        entry.unlink()
                        freed += size
                        count += 1
                    elif entry.is_dir():
                        size = self._get_folder_size(entry) * 1024 * 1024
                        shutil.rmtree(entry, ignore_errors=True)
                        if not entry.exists():
                            freed += size
                            count += 1
                except (PermissionError, OSError):
                    # Skip files we can't delete (in use, system files)
                    pass
        except (PermissionError, OSError) as e:
            import logging

            logging.getLogger(__name__).debug("Failed to clean folder %s: %s", path, e)

        return freed // (1024 * 1024), count
