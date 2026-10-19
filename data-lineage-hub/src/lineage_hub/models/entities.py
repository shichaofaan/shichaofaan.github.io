from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeKind(StrEnum):
    DIMENSION = "dimension"
    ENTITY = "entity"
    DS_TASK = "ds_task"
    CODE_SPAN = "code_span"
    YUQUE_DOC = "yuque_doc"


class Relation(StrEnum):
    PRODUCES = "produces"
    CLEANS = "cleans"
    DOCUMENTS = "documents"
    MENTIONS = "mentions"
    ALIAS_OF = "alias_of"
    TAGGED = "tagged"


class Dimension(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    source: str = "manual"


class Entity(BaseModel):
    id: str
    type: str
    qualified_name: str


class DsTask(BaseModel):
    id: str
    project: str
    workflow: str
    task_name: str
    task_type: str
    script_ref: str = ""
    description: str = ""
    script_content: str = ""
    ui_url: str = ""
    raw_meta: dict[str, Any] = Field(default_factory=dict)


class CodeSpan(BaseModel):
    id: str
    repo: str
    path: str
    start_line: int
    end_line: int
    language: str = "sql"
    excerpt: str = ""
    excerpt_hash: str = ""
    blob_url: str = ""


class YuqueDoc(BaseModel):
    id: str
    book: str
    slug: str
    title: str
    url: str
    updated_at: str = ""
    excerpt: str = ""
    body: str = ""


class Edge(BaseModel):
    from_id: str
    to_id: str
    rel: Relation
    confidence: float = 1.0
    linker: str = "explicit"


class GraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    from_id: str
    to_id: str
    rel: str
    confidence: float = 1.0


class GraphPayload(BaseModel):
    dimension: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
