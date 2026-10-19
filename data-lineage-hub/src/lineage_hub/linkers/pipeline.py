from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lineage_hub.config import Settings, get_settings
from lineage_hub.connectors import DolphinSchedulerConnector, GitCodeConnector, YuqueConnector
from lineage_hub.extractors import extract_dim_ids, extract_qualified_names
from lineage_hub.models import Dimension, Edge, Entity, Relation
from lineage_hub.store import LineageStore


@dataclass
class LinkReport:
    dimensions: int = 0
    ds_tasks: int = 0
    code_spans: int = 0
    yuque_docs: int = 0
    edges: int = 0
    notes: list[str] = field(default_factory=list)


def sync_all(
    store: LineageStore,
    settings: Settings | None = None,
    *,
    use_fixture: bool = False,
    fixture_root: Path | None = None,
    clear: bool = True,
) -> LinkReport:
    settings = settings or get_settings()
    root = fixture_root or Path(__file__).resolve().parents[3] / "tests" / "fixtures"

    ds_fixture = root / "ds" if use_fixture else None
    yuque_fixture = root / "yuque" if use_fixture else None
    git_paths = [root / "git_repo"] if use_fixture else None

    ds = DolphinSchedulerConnector(settings, fixture_dir=ds_fixture)
    git = GitCodeConnector(settings, repo_paths=git_paths)
    yuque = YuqueConnector(settings, fixture_dir=yuque_fixture)

    tasks = ds.fetch_tasks()
    spans = git.fetch_code_spans()
    docs = yuque.fetch_docs()

    if clear:
        store.clear_all()

    for task in tasks:
        store.upsert_ds_task(task)
    for span in spans:
        store.upsert_code_span(span)
    for doc in docs:
        store.upsert_yuque_doc(doc)

    report = run_linkers(store)
    report.ds_tasks = len(tasks)
    report.code_spans = len(spans)
    report.yuque_docs = len(docs)
    return report


def run_linkers(store: LineageStore) -> LinkReport:
    report = LinkReport()
    edges: list[Edge] = []

    tasks = store.list_ds_tasks()
    spans = store.list_code_spans()
    docs = store.list_yuque_docs()

    # Collect dim tags and create dimension nodes
    dim_sources: dict[str, set[str]] = {}

    def remember_dim(dim_id: str, source: str) -> None:
        dim_sources.setdefault(dim_id, set()).add(source)

    for task in tasks:
        for dim_id in extract_dim_ids(task.description, task.script_content, task.task_name):
            remember_dim(dim_id, "ds")
            edges.append(
                Edge(
                    from_id=dim_id,
                    to_id=task.id,
                    rel=Relation.TAGGED,
                    confidence=1.0,
                    linker="explicit",
                )
            )
            edges.append(
                Edge(
                    from_id=task.id,
                    to_id=dim_id,
                    rel=Relation.CLEANS,
                    confidence=1.0,
                    linker="explicit",
                )
            )

    for span in spans:
        for dim_id in extract_dim_ids(span.excerpt):
            remember_dim(dim_id, "git")
            edges.append(
                Edge(
                    from_id=dim_id,
                    to_id=span.id,
                    rel=Relation.TAGGED,
                    confidence=1.0,
                    linker="explicit",
                )
            )
            edges.append(
                Edge(
                    from_id=span.id,
                    to_id=dim_id,
                    rel=Relation.CLEANS,
                    confidence=1.0,
                    linker="explicit",
                )
            )

    for doc in docs:
        for dim_id in extract_dim_ids(doc.title, doc.excerpt, doc.body):
            remember_dim(dim_id, "yuque")
            edges.append(
                Edge(
                    from_id=dim_id,
                    to_id=doc.id,
                    rel=Relation.DOCUMENTS,
                    confidence=1.0,
                    linker="explicit",
                )
            )

    for dim_id, sources in dim_sources.items():
        store.upsert_dimension(
            Dimension(id=dim_id, name=dim_id, aliases=[], source=",".join(sorted(sources)))
        )

    # Entity extraction + field matching
    entity_to_nodes: dict[str, list[tuple[str, str]]] = {}

    def add_entity(qn: str, node_id: str, kind: str) -> None:
        entity_id = f"entity:{qn}"
        store.upsert_entity(Entity(id=entity_id, type="field_or_table", qualified_name=qn))
        entity_to_nodes.setdefault(qn, []).append((node_id, kind))
        edges.append(
            Edge(
                from_id=node_id,
                to_id=entity_id,
                rel=Relation.MENTIONS,
                confidence=0.7,
                linker="field_match",
            )
        )

    for task in tasks:
        for qn in extract_qualified_names(task.script_content):
            add_entity(qn, task.id, "ds")
    for span in spans:
        for qn in extract_qualified_names(span.excerpt):
            add_entity(qn, span.id, "git")
    for doc in docs:
        for qn in extract_qualified_names(doc.body or doc.excerpt or doc.title):
            add_entity(qn, doc.id, "yuque")

    # Link dimensions to entities when dim name appears in qualified name or vice versa
    dims = store.list_dimensions()
    for dim in dims:
        for qn, holders in entity_to_nodes.items():
            if dim.id in qn or dim.id.replace("_", "") in qn.replace("_", "").replace(".", ""):
                entity_id = f"entity:{qn}"
                edges.append(
                    Edge(
                        from_id=dim.id,
                        to_id=entity_id,
                        rel=Relation.MENTIONS,
                        confidence=0.55,
                        linker="field_match",
                    )
                )
                for node_id, _kind in holders:
                    # soft produce edge from task/code to dim via shared entity
                    if node_id.startswith("ds:"):
                        edges.append(
                            Edge(
                                from_id=node_id,
                                to_id=dim.id,
                                rel=Relation.PRODUCES,
                                confidence=0.55,
                                linker="field_match",
                            )
                        )

    store.upsert_edges(edges)
    report.dimensions = len(store.list_dimensions())
    report.edges = len(store.list_edges())
    report.notes.append(
        f"linked {report.dimensions} dimensions with {report.edges} edges "
        f"({sum(1 for e in store.list_edges() if e.linker == 'explicit')} explicit)"
    )
    return report
