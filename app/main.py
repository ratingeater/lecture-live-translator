from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.models import StreamStartPayload
from app.services.batch import BatchTranscribeService
from app.services.realtime import RealtimeTranscriptionSession

settings = get_settings()
app = FastAPI(title=settings.app_name)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "default_project": settings.google_cloud_project or "",
            "default_target_language": settings.default_target_language,
            "default_source_language": settings.default_source_language,
        },
    )


@app.websocket("/ws/realtime")
async def websocket_realtime(websocket: WebSocket) -> None:
    await websocket.accept()
    session: RealtimeTranscriptionSession | None = None
    try:
        payload = StreamStartPayload.model_validate_json(await websocket.receive_text())
        session = RealtimeTranscriptionSession(
            settings=settings,
            payload=payload,
            event_loop=asyncio.get_running_loop(),
            sender=websocket.send_json,
        )
        session.start()
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            chunk = message.get("bytes")
            if chunk:
                session.push_audio(chunk)
    except WebSocketDisconnect:
        pass
    finally:
        if session is not None:
            session.close()


@app.post("/api/batch-transcribe")
async def batch_transcribe(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    speech_location: str = Form("global"),
    source_mode: str = Form("manual"),
    source_language: str = Form("en-US"),
    target_language: str = Form("zh-CN"),
):
    with NamedTemporaryFile(delete=False, suffix=Path(file.filename or "lecture").suffix) as handle:
        temp_path = Path(handle.name)
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)

    try:
        service = BatchTranscribeService(settings, project_id)
        return service.transcribe_file(
            input_path=temp_path,
            speech_location=speech_location,
            source_mode=source_mode,
            source_language=source_language,
            target_language=target_language,
        ).model_dump()
    finally:
        temp_path.unlink(missing_ok=True)
