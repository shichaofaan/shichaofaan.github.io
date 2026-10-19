from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lineage_hub.models import (
    CodeSpan,
    Dimension,
    DsTask,
    Edge,
    Entity,
    GraphEdge,
    GraphNode,
    GraphPayload,
    NodeKind,
    Relation,
    YuqueDoc,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS dimension (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  aliases TEXT NOT NULL DEFAULT '[]',
  source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS entity (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  qualified_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ds_task (
  id TEXT PRIMARY KEY,
  project TEXT NOT NULL,
  workflow TEXT NOT NULL,
  task_name TEXT NOT NULL,
  task_type TEXT NOT NULL,
  script_ref TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  script_content TEXT NOT NULL DEFAULT '',
  ui_url TEXT NOT NULL DEFAULT '',
  raw_meta TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS code_span (
  id TEXT PRIMARY KEY,
  repo TEXT NOT NULL,
  path TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  language TEXT NOT NULL DEFAULT 'sql',
  excerpt TEXT NOT NULL DEFAULT '',
  excerpt_hash TEXT NOT NULL DEFAULT '',
  blob_url TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS yuque_doc (
  id TEXT PRIMARY KEY,
  book TEXT NOT NULL,
  slug TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT '',
  excerpt TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS edge (
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  rel TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  linker TEXT NOT NULL DEFAULT 'explicit',
  PRIMARY KEY (from_id, to_id, rel, linker)
);

CREATE TABLE IF NOT EXISTS sync_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class LineageStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def clear_all(self) -> None:
        for table in ("edge", "dimension", "entity", "ds_task", "code_span", "yuque_doc"):
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()

    def upsert_dimension(self, dim: Dimension) -> None:
        self._conn.execute(
            """
            INSERT INTO dimension (id, name, aliases, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              aliases=excluded.aliases,
              source=excluded.source
            """,
            (dim.id, dim.name, json.dumps(dim.aliases, ensure_ascii=False), dim.source),
        )
        self._conn.commit()

    def upsert_entity(self, entity: Entity) -> None:
        self._conn.execute(
            """
            INSERT INTO entity (id, type, qualified_name)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              type=excluded.type,
              qualified_name=excluded.qualified_name
            """,
            (entity.id, entity.type, entity.qualified_name),
        )
        self._conn.commit()

    def upsert_ds_task(self, task: DsTask) -> None:
        self._conn.execute(
            """
            INSERT INTO ds_task (
              id, project, workflow, task_name, task_type, script_ref,
              description, script_content, ui_url, raw_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              project=excluded.project,
              workflow=excluded.workflow,
              task_name=excluded.task_name,
              task_type=excluded.task_type,
              script_ref=excluded.script_ref,
              description=excluded.description,
              script_content=excluded.script_content,
              ui_url=excluded.ui_url,
              raw_meta=excluded.raw_meta
            """,
            (
                task.id,
                task.project,
                task.workflow,
                task.task_name,
                task.task_type,
                task.script_ref,
                task.description,
                task.script_content,
                task.ui_url,
                json.dumps(task.raw_meta, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def upsert_code_span(self, span: CodeSpan) -> None:
        self._conn.execute(
            """
            INSERT INTO code_span (
              id, repo, path, start_line, end_line, language,
              excerpt, excerpt_hash, blob_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              repo=excluded.repo,
              path=excluded.path,
              start_line=excluded.start_line,
              end_line=excluded.end_line,
              language=excluded.language,
              excerpt=excluded.excerpt,
              excerpt_hash=excluded.excerpt_hash,
              blob_url=excluded.blob_url
            """,
            (
                span.id,
                span.repo,
                span.path,
                span.start_line,
                span.end_line,
                span.language,
                span.excerpt,
                span.excerpt_hash,
                span.blob_url,
            ),
        )
        self._conn.commit()

    def upsert_yuque_doc(self, doc: YuqueDoc) -> None:
        self._conn.execute(
            """
            INSERT INTO yuque_doc (
              id, book, slug, title, url, updated_at, excerpt, body
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              book=excluded.book,
              slug=excluded.slug,
              title=excluded.title,
              url=excluded.url,
              updated_at=excluded.updated_at,
              excerpt=excluded.excerpt,
              body=excluded.body
            """,
            (
                doc.id,
                doc.book,
                doc.slug,
                doc.title,
                doc.url,
                doc.updated_at,
                doc.excerpt,
                doc.body,
            ),
        )
        self._conn.commit()

    def upsert_edge(self, edge: Edge) -> None:
        self._conn.execute(
            """
            INSERT INTO edge (from_id, to_id, rel, confidence, linker)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(from_id, to_id, rel, linker) DO UPDATE SET
              confidence=excluded.confidence
            """,
            (edge.from_id, edge.to_id, edge.rel.value, edge.confidence, edge.linker),
        )
        self._conn.commit()

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        for edge in edges:
            self.upsert_edge(edge)

    def get_dimension(self, name_or_id: str) -> Dimension | None:
        key = name_or_id.strip().lower()
        row = self._conn.execute(
            "SELECT * FROM dimension WHERE lower(id)=? OR lower(name)=?",
            (key, key),
        ).fetchone()
        if not row:
            # alias match
            rows = self._conn.execute("SELECT * FROM dimension").fetchall()
            for r in rows:
                aliases = json.loads(r["aliases"] or "[]")
                if key in {a.lower() for a in aliases} or key == r["name"].lower():
                    row = r
                    break
        if not row:
            return None
        return Dimension(
            id=row["id"],
            name=row["name"],
            aliases=json.loads(row["aliases"] or "[]"),
            source=row["source"],
        )

    def list_dimensions(self) -> list[Dimension]:
        rows = self._conn.execute("SELECT * FROM dimension ORDER BY id").fetchall()
        return [
            Dimension(
                id=r["id"],
                name=r["name"],
                aliases=json.loads(r["aliases"] or "[]"),
                source=r["source"],
            )
            for r in rows
        ]

    def get_ds_task(self, task_id: str) -> DsTask | None:
        row = self._conn.execute("SELECT * FROM ds_task WHERE id=?", (task_id,)).fetchone()
        return self._row_to_ds_task(row) if row else None

    def list_ds_tasks(self) -> list[DsTask]:
        rows = self._conn.execute("SELECT * FROM ds_task").fetchall()
        return [self._row_to_ds_task(r) for r in rows]

    def get_code_span(self, span_id: str) -> CodeSpan | None:
        row = self._conn.execute("SELECT * FROM code_span WHERE id=?", (span_id,)).fetchone()
        return self._row_to_code_span(row) if row else None

    def list_code_spans(self) -> list[CodeSpan]:
        rows = self._conn.execute("SELECT * FROM code_span").fetchall()
        return [self._row_to_code_span(r) for r in rows]

    def get_yuque_doc(self, doc_id: str) -> YuqueDoc | None:
        row = self._conn.execute("SELECT * FROM yuque_doc WHERE id=?", (doc_id,)).fetchone()
        return self._row_to_yuque(row) if row else None

    def list_yuque_docs(self) -> list[YuqueDoc]:
        rows = self._conn.execute("SELECT * FROM yuque_doc").fetchall()
        return [self._row_to_yuque(r) for r in rows]

    def list_entities(self) -> list[Entity]:
        rows = self._conn.execute("SELECT * FROM entity").fetchall()
        return [Entity(id=r["id"], type=r["type"], qualified_name=r["qualified_name"]) for r in rows]

    def list_edges(self) -> list[Edge]:
        rows = self._conn.execute("SELECT * FROM edge").fetchall()
        return [
            Edge(
                from_id=r["from_id"],
                to_id=r["to_id"],
                rel=Relation(r["rel"]),
                confidence=r["confidence"],
                linker=r["linker"],
            )
            for r in rows
        ]

    def neighbors(self, node_id: str) -> list[Edge]:
        rows = self._conn.execute(
            "SELECT * FROM edge WHERE from_id=? OR to_id=?",
            (node_id, node_id),
        ).fetchall()
        return [
            Edge(
                from_id=r["from_id"],
                to_id=r["to_id"],
                rel=Relation(r["rel"]),
                confidence=r["confidence"],
                linker=r["linker"],
            )
            for r in rows
        ]

    def dimension_bundle(self, name_or_id: str) -> dict[str, Any] | None:
        dim = self.get_dimension(name_or_id)
        if not dim:
            return None
        edges = self.neighbors(dim.id)
        related_ids = {e.to_id if e.from_id == dim.id else e.from_id for e in edges}
        # one-hop through entities
        for rid in list(related_ids):
            for e in self.neighbors(rid):
                edges.append(e)
                related_ids.add(e.to_id)
                related_ids.add(e.from_id)

        tasks = [t for t in self.list_ds_tasks() if t.id in related_ids]
        spans = [s for s in self.list_code_spans() if s.id in related_ids]
        docs = [d for d in self.list_yuque_docs() if d.id in related_ids]
        entities = [e for e in self.list_entities() if e.id in related_ids]
        return {
            "dimension": dim.model_dump(),
            "entities": [e.model_dump() for e in entities],
            "ds_tasks": [t.model_dump() for t in tasks],
            "code_spans": [s.model_dump() for s in spans],
            "yuque_docs": [d.model_dump() for d in docs],
            "edges": [e.model_dump() for e in edges],
        }

    def graph_for_dimension(self, name_or_id: str) -> GraphPayload | None:
        bundle = self.dimension_bundle(name_or_id)
        if not bundle:
            return None
        dim = bundle["dimension"]
        nodes: list[GraphNode] = [
            GraphNode(id=dim["id"], kind=NodeKind.DIMENSION, label=dim["name"], meta=dim)
        ]
        for e in bundle["entities"]:
            nodes.append(
                GraphNode(
                    id=e["id"],
                    kind=NodeKind.ENTITY,
                    label=e["qualified_name"],
                    meta=e,
                )
            )
        for t in bundle["ds_tasks"]:
            nodes.append(
                GraphNode(
                    id=t["id"],
                    kind=NodeKind.DS_TASK,
                    label=f"{t['workflow']}/{t['task_name']}",
                    meta=t,
                )
            )
        for s in bundle["code_spans"]:
            nodes.append(
                GraphNode(
                    id=s["id"],
                    kind=NodeKind.CODE_SPAN,
                    label=f"{s['path']}:{s['start_line']}-{s['end_line']}",
                    meta=s,
                )
            )
        for d in bundle["yuque_docs"]:
            nodes.append(
                GraphNode(
                    id=d["id"],
                    kind=NodeKind.YUQUE_DOC,
                    label=d["title"],
                    meta=d,
                )
            )
        edges = [
            GraphEdge(
                from_id=e["from_id"],
                to_id=e["to_id"],
                rel=e["rel"] if isinstance(e["rel"], str) else e["rel"].value,
                confidence=e["confidence"],
            )
            for e in bundle["edges"]
        ]
        return GraphPayload(dimension=dim["id"], nodes=nodes, edges=edges)

    def doctor_report(self) -> dict[str, Any]:
        dims = self.list_dimensions()
        tasks = self.list_ds_tasks()
        spans = self.list_code_spans()
        docs = self.list_yuque_docs()
        edges = self.list_edges()

        linked_task_ids = {e.to_id for e in edges if e.rel in {Relation.PRODUCES, Relation.CLEANS, Relation.TAGGED}}
        linked_task_ids |= {e.from_id for e in edges if e.rel in {Relation.PRODUCES, Relation.CLEANS, Relation.TAGGED}}
        linked_span_ids = {e.to_id for e in edges if e.to_id.startswith("code:")}
        linked_span_ids |= {e.from_id for e in edges if e.from_id.startswith("code:")}
        linked_doc_ids = {e.to_id for e in edges if e.to_id.startswith("yuque:")}
        linked_doc_ids |= {e.from_id for e in edges if e.from_id.startswith("yuque:")}

        unlinked_tasks = [t.id for t in tasks if t.id not in linked_task_ids]
        unlinked_spans = [s.id for s in spans if s.id not in linked_span_ids]
        unlinked_docs = [d.id for d in docs if d.id not in linked_doc_ids]

        weak_edges = [
            e.model_dump()
            for e in edges
            if e.confidence < 0.8 or e.linker == "field_match"
        ]

        incomplete_dims = []
        for dim in dims:
            bundle = self.dimension_bundle(dim.id) or {}
            missing = []
            if not bundle.get("ds_tasks"):
                missing.append("ds_task")
            if not bundle.get("code_spans"):
                missing.append("code_span")
            if not bundle.get("yuque_docs"):
                missing.append("yuque_doc")
            if missing:
                incomplete_dims.append({"dimension": dim.id, "missing": missing})

        return {
            "counts": {
                "dimensions": len(dims),
                "ds_tasks": len(tasks),
                "code_spans": len(spans),
                "yuque_docs": len(docs),
                "edges": len(edges),
            },
            "unlinked_tasks": unlinked_tasks,
            "unlinked_code_spans": unlinked_spans,
            "unlinked_docs": unlinked_docs,
            "weak_edges": weak_edges,
            "incomplete_dimensions": incomplete_dims,
        }

    @staticmethod
    def _row_to_ds_task(row: sqlite3.Row) -> DsTask:
        return DsTask(
            id=row["id"],
            project=row["project"],
            workflow=row["workflow"],
            task_name=row["task_name"],
            task_type=row["task_type"],
            script_ref=row["script_ref"],
            description=row["description"],
            script_content=row["script_content"],
            ui_url=row["ui_url"],
            raw_meta=json.loads(row["raw_meta"] or "{}"),
        )

    @staticmethod
    def _row_to_code_span(row: sqlite3.Row) -> CodeSpan:
        return CodeSpan(
            id=row["id"],
            repo=row["repo"],
            path=row["path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            language=row["language"],
            excerpt=row["excerpt"],
            excerpt_hash=row["excerpt_hash"],
            blob_url=row["blob_url"],
        )

    @staticmethod
    def _row_to_yuque(row: sqlite3.Row) -> YuqueDoc:
        return YuqueDoc(
            id=row["id"],
            book=row["book"],
            slug=row["slug"],
            title=row["title"],
            url=row["url"],
            updated_at=row["updated_at"],
            excerpt=row["excerpt"],
            body=row["body"],
        )
