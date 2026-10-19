from __future__ import annotations

import re
from typing import Any

import httpx

from lineage_hub.config import Settings, get_settings
from lineage_hub.store import LineageStore

DIM_HINT = re.compile(r"\b([a-z][a-z0-9_]{2,})\b", re.IGNORECASE)


def _guess_dimension(question: str, store: LineageStore) -> str | None:
    dims = store.list_dimensions()
    q = question.lower()
    for dim in dims:
        if dim.id.lower() in q or dim.name.lower() in q:
            return dim.id
        for alias in dim.aliases:
            if alias.lower() in q:
                return dim.id
    # fallback: first token that matches a known dim-like word after keywords
    for match in DIM_HINT.finditer(question):
        token = match.group(1).lower()
        hit = store.get_dimension(token)
        if hit:
            return hit.id
    return dims[0].id if len(dims) == 1 else None


def _template_answer(bundle: dict[str, Any]) -> dict[str, Any]:
    dim = bundle["dimension"]
    refs: list[dict[str, str]] = []
    lines = [f"维度 **{dim['name']}**（id=`{dim['id']}`）的清洗链路如下：", ""]

    if bundle["ds_tasks"]:
        lines.append("### DolphinScheduler")
        for t in bundle["ds_tasks"]:
            lines.append(
                f"- 工作流 `{t['workflow']}` / 任务 `{t['task_name']}`"
                + (f" — [打开]({t['ui_url']})" if t.get("ui_url") else "")
            )
            refs.append(
                {
                    "type": "ds_task",
                    "label": f"{t['workflow']}/{t['task_name']}",
                    "url": t.get("ui_url") or "",
                }
            )
        lines.append("")
    else:
        lines.append("### DolphinScheduler\n- 未建链，请在任务描述或脚本中补充 `dim:` 标签。\n")

    if bundle["code_spans"]:
        lines.append("### Git 代码")
        for s in bundle["code_spans"]:
            loc = f"{s['path']}:{s['start_line']}-{s['end_line']}"
            lines.append(f"- `{s['repo']}/{loc}`" + (f" — [打开]({s['blob_url']})" if s.get("blob_url") else ""))
            if s.get("excerpt"):
                preview = s["excerpt"].strip().splitlines()[:5]
                lines.append("  ```sql")
                lines.extend(f"  {ln}" for ln in preview)
                lines.append("  ```")
            refs.append({"type": "code_span", "label": loc, "url": s.get("blob_url") or ""})
        lines.append("")
    else:
        lines.append("### Git 代码\n- 未建链，请在 SQL 文件头补充 `dim:` 标签。\n")

    if bundle["yuque_docs"]:
        lines.append("### 语雀文档")
        for d in bundle["yuque_docs"]:
            lines.append(f"- [{d['title']}]({d['url']})")
            if d.get("excerpt"):
                lines.append(f"  > {d['excerpt'][:200]}")
            refs.append({"type": "yuque_doc", "label": d["title"], "url": d["url"]})
        lines.append("")
    else:
        lines.append("### 语雀文档\n- 未建链，请在文档标题或首行补充 `dim:` 标签。\n")

    return {
        "dimension": dim["id"],
        "answer": "\n".join(lines),
        "citations": refs,
        "mode": "template",
    }


def _llm_polish(question: str, draft: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if not settings.openai_api_key:
        return draft
    system = (
        "你是数据血缘助手。只能根据给定检索结果回答「维度如何清洗」。"
        "必须保留所有引用链接，不得编造任务、文件或文档。"
        "若某源缺失，明确说未建链并提示补充 dim: 标签。"
    )
    user = (
        f"用户问题：{question}\n\n"
        f"检索草稿：\n{draft['answer']}\n\n"
        f"引用 JSON：{draft['citations']}"
    )
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return {
                **draft,
                "answer": content,
                "mode": "llm",
            }
    except Exception as exc:  # noqa: BLE001 — fall back to template
        return {**draft, "mode": "template", "llm_error": str(exc)}


def answer_question(
    question: str,
    store: LineageStore,
    settings: Settings | None = None,
    dimension: str | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    dim_id = dimension or _guess_dimension(question, store)
    if not dim_id:
        return {
            "dimension": None,
            "answer": (
                "无法从问题中识别维度。请直接指定维度名，"
                "或先运行 `lineage sync` / `lineage doctor` 建链。"
            ),
            "citations": [],
            "mode": "empty",
        }
    bundle = store.dimension_bundle(dim_id)
    if not bundle:
        return {
            "dimension": dim_id,
            "answer": f"维度 `{dim_id}` 尚未入库。请补充 `dim:{dim_id}` 标签后执行 `lineage sync`。",
            "citations": [],
            "mode": "missing",
        }
    draft = _template_answer(bundle)
    return _llm_polish(question, draft, settings)
