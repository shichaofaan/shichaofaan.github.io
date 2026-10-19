from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from lineage_hub.config import get_settings
from lineage_hub.linkers import sync_all
from lineage_hub.qa import answer_question
from lineage_hub.store import LineageStore

app = typer.Typer(help="Trace dimension cleaning via DS × Git × Yuque", no_args_is_help=True)
dim_app = typer.Typer(help="Dimension queries")
app.add_typer(dim_app, name="dim")
console = Console()


def _store(db_path: Path | None = None) -> LineageStore:
    settings = get_settings()
    path = db_path or settings.lineage_db_path
    return LineageStore(path)


@app.command("sync")
def sync_cmd(
    fixture: bool = typer.Option(False, "--fixture", help="Use built-in mock fixtures"),
    db: Path | None = typer.Option(None, "--db", help="SQLite path"),
    no_clear: bool = typer.Option(False, "--no-clear", help="Do not wipe store before sync"),
) -> None:
    """Pull DS / Git / Yuque and rebuild lineage edges."""
    store = _store(db)
    report = sync_all(store, use_fixture=fixture, clear=not no_clear)
    table = Table(title="Sync complete")
    table.add_column("metric")
    table.add_column("count", justify="right")
    table.add_row("dimensions", str(report.dimensions))
    table.add_row("ds_tasks", str(report.ds_tasks))
    table.add_row("code_spans", str(report.code_spans))
    table.add_row("yuque_docs", str(report.yuque_docs))
    table.add_row("edges", str(report.edges))
    console.print(table)
    for note in report.notes:
        console.print(f"[dim]{note}[/dim]")
    store.close()


@dim_app.command("show")
def dim_show(
    name: str = typer.Argument(..., help="Dimension id or name"),
    db: Path | None = typer.Option(None, "--db"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show DS tasks, code spans, and Yuque docs for a dimension."""
    store = _store(db)
    bundle = store.dimension_bundle(name)
    if not bundle:
        console.print(f"[red]Dimension not found:[/red] {name}")
        raise typer.Exit(code=1)
    if as_json:
        console.print_json(json.dumps(bundle, ensure_ascii=False))
        store.close()
        return

    dim = bundle["dimension"]
    console.print(Panel(f"[bold]{dim['name']}[/bold]  id={dim['id']}  source={dim['source']}"))

    t = Table(title="DolphinScheduler tasks")
    t.add_column("workflow")
    t.add_column("task")
    t.add_column("type")
    t.add_column("ui")
    for task in bundle["ds_tasks"]:
        t.add_row(task["workflow"], task["task_name"], task["task_type"], task.get("ui_url") or "")
    console.print(t)

    c = Table(title="Git code spans")
    c.add_column("repo")
    c.add_column("path")
    c.add_column("lines")
    c.add_column("url")
    for span in bundle["code_spans"]:
        c.add_row(
            span["repo"],
            span["path"],
            f"{span['start_line']}-{span['end_line']}",
            span.get("blob_url") or "",
        )
    console.print(c)

    d = Table(title="Yuque docs")
    d.add_column("title")
    d.add_column("url")
    for doc in bundle["yuque_docs"]:
        d.add_row(doc["title"], doc["url"])
    console.print(d)
    store.close()


@dim_app.command("list")
def dim_list(db: Path | None = typer.Option(None, "--db")) -> None:
    store = _store(db)
    dims = store.list_dimensions()
    table = Table(title="Dimensions")
    table.add_column("id")
    table.add_column("name")
    table.add_column("source")
    for dim in dims:
        table.add_row(dim.id, dim.name, dim.source)
    console.print(table)
    store.close()


@app.command("doctor")
def doctor_cmd(db: Path | None = typer.Option(None, "--db")) -> None:
    """Report missing tags and broken links."""
    store = _store(db)
    report = store.doctor_report()
    console.print_json(json.dumps(report, ensure_ascii=False))
    incomplete = report.get("incomplete_dimensions") or []
    if incomplete:
        console.print(f"[yellow]{len(incomplete)} dimension(s) missing some sources[/yellow]")
    else:
        console.print("[green]All dimensions have DS + Git + Yuque links[/green]")
    store.close()


@app.command("ask")
def ask_cmd(
    question: str = typer.Argument(..., help="Natural language question"),
    dimension: str | None = typer.Option(None, "--dimension", "-d"),
    db: Path | None = typer.Option(None, "--db"),
) -> None:
    """Phase A: answer how a dimension is cleaned, with citations."""
    store = _store(db)
    result = answer_question(question, store, dimension=dimension)
    console.print(Markdown(result["answer"]))
    if result.get("citations"):
        console.print("\n[bold]Citations[/bold]")
        for c in result["citations"]:
            console.print(f"- ({c['type']}) {c['label']} {c.get('url') or ''}")
    store.close()


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    db: Path | None = typer.Option(None, "--db"),
) -> None:
    """Start FastAPI server for Phase C/B/A HTTP APIs."""
    if db:
        import os

        os.environ["LINEAGE_DB_PATH"] = str(db)
    uvicorn.run("lineage_hub.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
