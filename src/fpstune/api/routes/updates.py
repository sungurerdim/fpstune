"""Release check and self-update, each only when the user asks."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from fpstune.utils.updates import check_for_update, install_update

router = APIRouter(prefix="/update", tags=["Update"])


class UpdateStatus(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    can_install: bool
    url: str
    error: str | None = None


class UpdateInstallResult(BaseModel):
    installed: bool
    message: str


@router.get("/check", response_model=UpdateStatus)
async def check() -> UpdateStatus:
    result = await asyncio.to_thread(check_for_update)
    return UpdateStatus(
        current=result.current,
        latest=result.latest,
        update_available=result.update_available,
        can_install=bool(result.update_available and result.exe_url and result.sha256_url),
        url=result.url,
        error=result.error,
    )


@router.post("/install", response_model=UpdateInstallResult)
async def install() -> UpdateInstallResult:
    result = await asyncio.to_thread(check_for_update)
    installed, message = await asyncio.to_thread(install_update, result)
    return UpdateInstallResult(installed=installed, message=message)
