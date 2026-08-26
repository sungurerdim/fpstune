"""Utility modules for fpstune."""

from fpstune.utils.admin import is_admin, require_admin
from fpstune.utils.config import get_config_dir
from fpstune.utils.detect import GpuVendor, OsInfo, get_gpu_vendor, get_os_info
from fpstune.utils.logger import get_logger, setup_logging

__all__ = [
    "is_admin",
    "require_admin",
    "get_config_dir",
    "get_gpu_vendor",
    "get_os_info",
    "GpuVendor",
    "OsInfo",
    "get_logger",
    "setup_logging",
]
