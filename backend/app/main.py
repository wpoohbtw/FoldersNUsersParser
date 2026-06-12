from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_settings
from .db import Database
from .folder_parser_service import FolderParserService
from .import_service import ImportService

settings = load_settings()
db = Database(settings.db_path)
service = ImportService(settings, db)
folder_parser = FolderParserService(settings, db)

app = FastAPI(title="FoldersNUsersParser API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=settings.avatars_dir.parent), name="media")


class ItemActionRequest(BaseModel):
    item_ids: list[str] | None = None


class AccountActionRequest(BaseModel):
    account_ids: list[int]


class ChannelDeleteRequest(BaseModel):
    channel_ids: list[int]


class PhoneStartRequest(BaseModel):
    phone: str


class PhoneCodeRequest(BaseModel):
    flow_id: str
    code: str


class PhonePasswordRequest(BaseModel):
    flow_id: str
    password: str


class PhoneCancelRequest(BaseModel):
    flow_id: str


class FolderListenerRequest(BaseModel):
    account_id: int
    folder_id: str


@dataclass(slots=True)
class PortalUser:
    user_id: str = ""
    username: str = ""


def get_portal_user(
    x_portal_user_id: str = Header(default="", alias="X-Portal-User-Id"),
    x_portal_username: str = Header(default="", alias="X-Portal-Username"),
) -> PortalUser:
    user_id = x_portal_user_id.strip()
    username = x_portal_username.strip()
    if not user_id and not username:
        if settings.app_env == "production":
            raise HTTPException(status_code=401, detail="Portal user headers required")
        username = settings.portal_dev_username
    return PortalUser(
        user_id=user_id,
        username=username,
    )


@app.on_event("startup")
async def on_startup() -> None:
    db.init()
    await folder_parser.restore_running_listeners()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await folder_parser.stop_all()
    db.close()


@app.get("/api/v1/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/v1/me")
def current_user(portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    return {
        "portal_user_id": portal_user.user_id,
        "portal_username": portal_user.username,
    }


@app.get("/api/v1/accounts")
def list_accounts(portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    return {"items": service.list_accounts(portal_user_id=portal_user.user_id, portal_username=portal_user.username)}


@app.post("/api/v1/accounts/check")
async def check_accounts(payload: AccountActionRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    if not payload.account_ids:
        raise HTTPException(status_code=400, detail="Не выбраны аккаунты")
    return await service.check_accounts(payload.account_ids, portal_user_id=portal_user.user_id, portal_username=portal_user.username)


@app.get("/api/v1/folders/accounts/{account_id}/folders")
def list_saved_account_folders(account_id: int, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    try:
        folders = service.list_saved_account_folders(
            account_id,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"items": folders}


@app.post("/api/v1/folders/accounts/{account_id}/folders/refresh")
async def refresh_account_folders(account_id: int, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    try:
        folders = await service.list_account_folders(
            account_id,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"items": folders}


@app.post("/api/v1/folders/accounts/{account_id}/folders/{folder_id}/sync")
async def sync_account_folder_channels(account_id: int, folder_id: str, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    account = db.get_account(account_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    try:
        return await folder_parser.sync_folder_once(
            account,
            folder_id,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.get("/api/v1/folders/listener/status")
def get_folder_listener_status(account_id: int, folder_id: str, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    account = db.get_account(account_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    return folder_parser.get_listener_status(
        account_id,
        folder_id,
        portal_user_id=portal_user.user_id,
        portal_username=portal_user.username,
    )


@app.get("/api/v1/folders/listener/active")
def get_active_folder_listener(portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    return folder_parser.get_active_listener(
        portal_user_id=portal_user.user_id,
        portal_username=portal_user.username,
    )


@app.post("/api/v1/folders/listener/start")
async def start_folder_listener(payload: FolderListenerRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    account = db.get_account(payload.account_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    try:
        return await folder_parser.start_listener(
            account,
            payload.folder_id,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/api/v1/folders/listener/stop")
async def stop_folder_listener(payload: FolderListenerRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    account = db.get_account(payload.account_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not account:
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    return await folder_parser.stop_listener(
        payload.account_id,
        payload.folder_id,
        portal_user_id=portal_user.user_id,
        portal_username=portal_user.username,
    )


@app.get("/api/v1/folders/channels")
def list_folder_channels(
    account_id: int | None = None,
    folder_id: str = "",
    portal_user: PortalUser = Depends(get_portal_user),
) -> dict:
    if account_id is not None and not db.get_account(account_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username):
        raise HTTPException(status_code=404, detail="Аккаунт не найден")
    return {
        "items": folder_parser.list_channels(
            account_id=account_id,
            folder_id=folder_id,
            include_rejected=False,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    }


@app.get("/api/v1/folders/logs")
def list_folder_logs(portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    return {"items": folder_parser.list_logs(portal_user_id=portal_user.user_id, portal_username=portal_user.username)}


@app.delete("/api/v1/folders/logs")
def clear_folder_logs(portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    folder_parser.clear_logs(portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    return {"ok": True}


@app.get("/api/v1/channels")
def list_channels(portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    return {
        "items": folder_parser.list_channels(
            include_rejected=True,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    }


@app.post("/api/v1/channels/{channel_id}/approve")
def approve_channel(channel_id: int, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    folder_parser.approve_channel(channel_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    return {"ok": True}


@app.post("/api/v1/channels/{channel_id}/reject")
def reject_channel(channel_id: int, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    folder_parser.reject_channel(channel_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    return {"ok": True}


@app.post("/api/v1/channels/{channel_id}/reset")
def reset_channel(channel_id: int, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    folder_parser.reset_channel(channel_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    return {"ok": True}


@app.delete("/api/v1/channels")
def delete_channels(payload: ChannelDeleteRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    deleted = folder_parser.delete_channels(
        payload.channel_ids,
        portal_user_id=portal_user.user_id,
        portal_username=portal_user.username,
    )
    return {"deleted": deleted}


@app.post("/api/v1/imports/session/upload")
async def upload_sessions(files: list[UploadFile] = File(...), portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Файлы не переданы")

    saved_paths: list[Path] = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix != ".session":
            raise HTTPException(status_code=400, detail=f"Недопустимый формат: {upload.filename}")

        target = settings.uploads_dir / f"{uuid4().hex[:12]}_{Path(upload.filename or 'file').name}"
        with target.open("wb") as fh:
            shutil.copyfileobj(upload.file, fh)
        saved_paths.append(target)

    try:
        job_id = await service.import_session_files(
            saved_paths,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"job_id": job_id}


@app.post("/api/v1/imports/phone/start")
async def phone_start(payload: PhoneStartRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    try:
        return await service.start_phone_import(
            payload.phone,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/api/v1/imports/phone/code")
async def phone_code(payload: PhoneCodeRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    try:
        return await service.submit_phone_code(payload.flow_id, payload.code, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/api/v1/imports/phone/password")
async def phone_password(payload: PhonePasswordRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    try:
        return await service.submit_phone_password(payload.flow_id, payload.password, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/api/v1/imports/phone/cancel")
async def phone_cancel(payload: PhoneCancelRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    await service.cancel_phone_flow(payload.flow_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    return {"ok": True}


@app.get("/api/v1/imports/jobs/{job_id}")
def get_job(job_id: str, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    job = service.get_job(job_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not job:
        raise HTTPException(status_code=404, detail="Job не найден")
    return job


@app.get("/api/v1/imports/jobs/{job_id}/items")
def get_job_items(job_id: str, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    job = service.get_job(job_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not job:
        raise HTTPException(status_code=404, detail="Job не найден")
    return {"items": service.get_job_items(job_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)}


@app.post("/api/v1/imports/jobs/{job_id}/check")
async def check_job_items(job_id: str, payload: ItemActionRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    job = service.get_job(job_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not job:
        raise HTTPException(status_code=404, detail="Job не найден")
    try:
        return await service.check_job_items(
            job_id,
            payload.item_ids,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@app.post("/api/v1/imports/jobs/{job_id}/save")
async def save_job_items(job_id: str, payload: ItemActionRequest, portal_user: PortalUser = Depends(get_portal_user)) -> dict:
    job = service.get_job(job_id, portal_user_id=portal_user.user_id, portal_username=portal_user.username)
    if not job:
        raise HTTPException(status_code=404, detail="Job не найден")
    try:
        return await service.save_job_items(
            job_id,
            payload.item_ids,
            portal_user_id=portal_user.user_id,
            portal_username=portal_user.username,
        )
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
