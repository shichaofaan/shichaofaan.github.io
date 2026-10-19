from pathlib import Path

from fastapi.testclient import TestClient

from lineage_hub.api import app
from lineage_hub.linkers import sync_all
from lineage_hub.qa import answer_question
from lineage_hub.store import LineageStore


def test_fixture_sync_links_trade_gmv(tmp_path: Path):
    db = tmp_path / "lineage.db"
    store = LineageStore(db)
    report = sync_all(store, use_fixture=True, clear=True)
    assert report.dimensions >= 1
    assert report.ds_tasks == 2
    assert report.code_spans >= 1
    assert report.yuque_docs == 1

    bundle = store.dimension_bundle("trade_gmv")
    assert bundle is not None
    assert bundle["ds_tasks"]
    assert bundle["code_spans"]
    assert bundle["yuque_docs"]

    doctor = store.doctor_report()
    assert doctor["counts"]["dimensions"] >= 1
    # orphan task should show up as unlinked
    assert any("task_orphan" in x for x in doctor["unlinked_tasks"])
    store.close()


def test_graph_payload(tmp_path: Path, monkeypatch):
    db = tmp_path / "lineage.db"
    store = LineageStore(db)
    sync_all(store, use_fixture=True)
    graph = store.graph_for_dimension("trade_gmv")
    assert graph is not None
    kinds = {n.kind.value for n in graph.nodes}
    assert "dimension" in kinds
    assert "ds_task" in kinds
    assert "code_span" in kinds
    assert "yuque_doc" in kinds
    store.close()


def test_ask_template(tmp_path: Path):
    db = tmp_path / "lineage.db"
    store = LineageStore(db)
    sync_all(store, use_fixture=True)
    result = answer_question("trade_gmv 是怎么洗出来的？", store)
    assert result["dimension"] == "trade_gmv"
    assert result["citations"]
    assert "DolphinScheduler" in result["answer"]
    assert result["mode"] in {"template", "llm"}
    store.close()


def test_api_endpoints(tmp_path: Path, monkeypatch):
    db = tmp_path / "api.db"
    monkeypatch.setenv("LINEAGE_DB_PATH", str(db))
    # reload settings path via env; store reads get_settings each call
    from lineage_hub.config import Settings

    monkeypatch.setattr("lineage_hub.api.get_settings", lambda: Settings(lineage_db_path=db))

    client = TestClient(app)
    sync_resp = client.post("/sync", json={"fixture": True, "clear": True})
    assert sync_resp.status_code == 200
    assert sync_resp.json()["dimensions"] >= 1

    dim = client.get("/dimensions/trade_gmv")
    assert dim.status_code == 200
    body = dim.json()
    assert body["yuque_docs"]

    graph = client.get("/graph", params={"dimension": "trade_gmv"})
    assert graph.status_code == 200
    assert graph.json()["nodes"]

    ask = client.post("/ask", json={"question": "trade_gmv 如何清洗？"})
    assert ask.status_code == 200
    assert ask.json()["citations"]

    doctor = client.get("/doctor")
    assert doctor.status_code == 200
