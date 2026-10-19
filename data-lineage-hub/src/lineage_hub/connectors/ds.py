from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from lineage_hub.config import Settings
from lineage_hub.models import DsTask


class DolphinSchedulerConnector:
    """Fetch workflow/task definitions from DolphinScheduler Open API.

    When ``fixture_dir`` is set, loads JSON fixtures instead of calling the API.
    """

    def __init__(self, settings: Settings, fixture_dir: Path | None = None) -> None:
        self.settings = settings
        self.fixture_dir = fixture_dir

    def fetch_tasks(self) -> list[DsTask]:
        if self.fixture_dir:
            return self._from_fixture(self.fixture_dir)
        return self._from_api()

    def _from_fixture(self, fixture_dir: Path) -> list[DsTask]:
        path = fixture_dir / "tasks.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [self._to_task(item) for item in payload]

    def _from_api(self) -> list[DsTask]:
        if not self.settings.ds_token:
            raise RuntimeError("DS_TOKEN is required unless using --fixture")

        headers = {"token": self.settings.ds_token}
        base = self.settings.ds_api_url.rstrip("/")
        tasks: list[DsTask] = []

        with httpx.Client(base_url=base, headers=headers, timeout=60.0) as client:
            project_codes = self.settings.project_codes or self._list_project_codes(client)
            for project_code in project_codes:
                workflows = self._list_workflows(client, project_code)
                for wf in workflows:
                    wf_code = wf.get("code") or wf.get("id")
                    wf_name = wf.get("name") or str(wf_code)
                    process = self._get_process_definition(client, project_code, int(wf_code))
                    task_defs = process.get("taskDefinitionList") or process.get("tasks") or []
                    for td in task_defs:
                        tasks.append(
                            self._to_task(
                                {
                                    "project": str(project_code),
                                    "workflow": wf_name,
                                    "task_name": td.get("name") or td.get("taskName") or "unknown",
                                    "task_type": td.get("taskType") or td.get("type") or "SQL",
                                    "description": td.get("description") or "",
                                    "script_content": self._extract_script(td),
                                    "script_ref": str(td.get("code") or td.get("id") or ""),
                                    "raw_meta": td,
                                    "ui_url": self._ui_url(project_code, wf_code),
                                }
                            )
                        )
        return tasks

    def _list_project_codes(self, client: httpx.Client) -> list[int]:
        # Compatible with DS 3.x project paging endpoint
        resp = client.get("/projects", params={"pageNo": 1, "pageSize": 100})
        resp.raise_for_status()
        data = resp.json()
        total_list = (
            data.get("data", {}).get("totalList")
            if isinstance(data.get("data"), dict)
            else data.get("data")
        ) or []
        return [int(p["code"]) for p in total_list if "code" in p]

    def _list_workflows(self, client: httpx.Client, project_code: int) -> list[dict[str, Any]]:
        resp = client.get(
            f"/projects/{project_code}/process-definition",
            params={"pageNo": 1, "pageSize": 200},
        )
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data", {})
        if isinstance(payload, dict):
            return payload.get("totalList") or []
        return payload or []

    def _get_process_definition(
        self, client: httpx.Client, project_code: int, code: int
    ) -> dict[str, Any]:
        resp = client.get(f"/projects/{project_code}/process-definition/{code}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("data") or {}

    def _extract_script(self, task_def: dict[str, Any]) -> str:
        params = task_def.get("taskParams") or task_def.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return params
        for key in ("sql", "rawScript", "script", "resourceList"):
            val = params.get(key) if isinstance(params, dict) else None
            if isinstance(val, str) and val.strip():
                return val
        return json.dumps(params, ensure_ascii=False) if params else ""

    def _ui_url(self, project_code: int | str, workflow_code: int | str) -> str:
        base = self.settings.ds_ui_base_url.rstrip("/")
        return f"{base}/projects/{project_code}/workflow/definitions/{workflow_code}"

    def _to_task(self, item: dict[str, Any]) -> DsTask:
        project = str(item.get("project", "unknown"))
        workflow = str(item.get("workflow", "unknown"))
        task_name = str(item.get("task_name", "unknown"))
        task_id = item.get("id") or f"ds:{project}:{workflow}:{task_name}"
        return DsTask(
            id=str(task_id),
            project=project,
            workflow=workflow,
            task_name=task_name,
            task_type=str(item.get("task_type", "SQL")),
            script_ref=str(item.get("script_ref", "")),
            description=str(item.get("description", "")),
            script_content=str(item.get("script_content", "")),
            ui_url=str(item.get("ui_url", "")),
            raw_meta=item.get("raw_meta") or item,
        )
