from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lineage_hub.config import get_settings
from lineage_hub.linkers import sync_all
from lineage_hub.qa import answer_question
from lineage_hub.store import LineageStore

app = FastAPI(title="data-lineage-hub", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"
WEB_DIST = WEB_ROOT / "dist"


def get_store() -> LineageStore:
    return LineageStore(get_settings().lineage_db_path)


class SyncRequest(BaseModel):
    fixture: bool = False
    clear: bool = True


class AskRequest(BaseModel):
    question: str
    dimension: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sync")
def sync(body: SyncRequest) -> dict[str, Any]:
    store = get_store()
    report = sync_all(store, use_fixture=body.fixture, clear=body.clear)
    store.close()
    return {
        "dimensions": report.dimensions,
        "ds_tasks": report.ds_tasks,
        "code_spans": report.code_spans,
        "yuque_docs": report.yuque_docs,
        "edges": report.edges,
        "notes": report.notes,
    }


@app.get("/dimensions")
def list_dimensions() -> list[dict[str, Any]]:
    store = get_store()
    dims = [d.model_dump() for d in store.list_dimensions()]
    store.close()
    return dims


@app.get("/dimensions/{name}")
def get_dimension(name: str) -> dict[str, Any]:
    store = get_store()
    bundle = store.dimension_bundle(name)
    store.close()
    if not bundle:
        raise HTTPException(status_code=404, detail=f"dimension not found: {name}")
    return bundle


@app.get("/graph")
def graph(dimension: str = Query(..., description="Dimension id or name")) -> dict[str, Any]:
    store = get_store()
    payload = store.graph_for_dimension(dimension)
    store.close()
    if not payload:
        raise HTTPException(status_code=404, detail=f"dimension not found: {dimension}")
    return payload.model_dump()


@app.get("/doctor")
def doctor() -> dict[str, Any]:
    store = get_store()
    report = store.doctor_report()
    store.close()
    return report


@app.post("/ask")
def ask(body: AskRequest) -> dict[str, Any]:
    store = get_store()
    result = answer_question(body.question, store, dimension=body.dimension)
    store.close()
    return result


def _mount_web() -> None:
    if WEB_DIST.exists() and (WEB_DIST / "index.html").exists():
        assets = WEB_DIST / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index_dist() -> FileResponse:
            return FileResponse(WEB_DIST / "index.html")

        return

    # Dev fallback: standalone static page without Vite build
    static_page = WEB_ROOT / "static.html"
    if static_page.exists():

        @app.get("/")
        def index_static() -> FileResponse:
            return FileResponse(static_page)


_mount_web()
