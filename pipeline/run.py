from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Callable
import click
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()
console = Console()


def run_pipeline_with_callback(
    run_id: str,
    callback: Callable[[dict], None],
    agents: list[str] | None = None,
) -> None:
    """Programmatic pipeline entry point used by the API."""
    from .config import INTERMEDIATE_DIR, OUTPUT_DIR

    intermediate_dir = INTERMEDIATE_DIR / run_id
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    agents_to_run = agents or AGENT_SEQUENCE
    total = len(agents_to_run)

    for i, agent_name in enumerate(agents_to_run):
        callback({"type": "agent_start", "agent": agent_name, "index": i, "total": total})
        try:
            _run_agent(agent_name, intermediate_dir)
            callback({"type": "agent_done", "agent": agent_name, "index": i, "total": total})
        except Exception as e:
            callback({"type": "agent_error", "agent": agent_name, "message": str(e)})
            raise RuntimeError(f"Agent '{agent_name}' failed: {e}") from e

AGENT_SEQUENCE = [
    "corpus-scanner",
    "legislation-loader",
    "norm-analyzer",
    "hierarchy-analyzer",
    "revocation-analyzer",
    "implication-analyzer",
    "domain-analyzer",
    "graph-builder",
    "graph-reviewer",
    "tour-builder",
]


@click.group()
def cli() -> None:
    """Amanuense — pipeline de grafos de conhecimento jurídico."""


@cli.command()
@click.option("--agent", default=None, help="Run only this agent")
@click.option("--run-id", default=None, help="Resume existing run by ID")
@click.option("--resume", is_flag=True, help="Skip agents with existing output")
@click.option("--file", default=None, help="Process only this corpus file (by name)")
def run(agent: str | None, run_id: str | None, resume: bool, file: str | None) -> None:
    """Run the full pipeline or a single agent."""
    from .config import INTERMEDIATE_DIR, OUTPUT_DIR

    run_id = run_id or datetime.now().strftime("%Y%m%dT%H%M%S")
    intermediate_dir = INTERMEDIATE_DIR / run_id
    intermediate_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]run-id:[/bold blue] {run_id}")

    agents_to_run = [agent] if agent else AGENT_SEQUENCE

    for agent_name in agents_to_run:
        output_file = intermediate_dir / f"{agent_name.replace('-', '_')}.json"
        if resume and output_file.exists():
            console.print(f"[yellow]↷[/yellow] skipping {agent_name} (output exists)")
            continue
        _run_agent(agent_name, intermediate_dir)

    console.print("[bold green]Done.[/bold green]")


def _run_agent(name: str, intermediate_dir: Path) -> None:
    from .config import CORPUS_DIR, OUTPUT_DIR
    console.print(f"[bold]→[/bold] {name}")

    if name == "corpus-scanner":
        from .agents.corpus_scanner import CorpusScannerAgent
        CorpusScannerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "legislation-loader":
        from .agents.legislation_loader import LegislationLoaderAgent
        LegislationLoaderAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "norm-analyzer":
        from .agents.norm_analyzer import NormAnalyzerAgent
        NormAnalyzerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "hierarchy-analyzer":
        from .agents.hierarchy_analyzer import HierarchyAnalyzerAgent
        HierarchyAnalyzerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "revocation-analyzer":
        from .agents.revocation_analyzer import RevocationAnalyzerAgent
        RevocationAnalyzerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "implication-analyzer":
        from .agents.implication_analyzer import ImplicationAnalyzerAgent
        ImplicationAnalyzerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "domain-analyzer":
        from .agents.domain_analyzer import DomainAnalyzerAgent
        DomainAnalyzerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "graph-builder":
        from .graph.builder import GraphBuilder
        builder = GraphBuilder(intermediate_dir)
        builder.load_agents()
        builder.load_legislacao()
        builder.apply_vigency_updates()
        graph = builder.build()
        errors = builder.validate(graph)
        if errors:
            for err in errors:
                console.print(f"[yellow]⚠[/yellow]  {err}")
        builder.save(graph, OUTPUT_DIR)
    elif name == "graph-reviewer":
        from .agents.graph_reviewer import GraphReviewerAgent
        GraphReviewerAgent().run(intermediate_dir, CORPUS_DIR)
    elif name == "tour-builder":
        from .agents.tour_builder import TourBuilderAgent
        TourBuilderAgent().run(intermediate_dir, CORPUS_DIR)
    else:
        console.print(f"[dim]  (agent '{name}' not yet implemented)[/dim]")


@cli.command()
@click.option("--with-demo", is_flag=True, help="Aplica também o seed de demonstração (LGPD)")
def initdb(with_demo: bool) -> None:
    """Inicializa a base de legislação estruturada (PostgreSQL)."""
    import sys
    from db.legislacao import database_url, init_legislacao_db, legislacao_enabled

    if not legislacao_enabled():
        console.print("[red]ERROR:[/red] LEGISLACAO_DATABASE_URL não definida (ver .env.example)")
        sys.exit(1)
    console.print(f"[bold blue]initdb[/bold blue] {database_url()}")
    applied = init_legislacao_db(with_demo=with_demo)
    if applied:
        for f in applied:
            console.print(f"[green]✓[/green] aplicado: db/sql/{f}")
    else:
        console.print("[yellow]↷[/yellow] nada a aplicar (schema já inicializado)")


@cli.command()
@click.option("--http", is_flag=True, help="Transporte streamable-http em vez de stdio")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8765, show_default=True)
def mcp(http: bool, host: str, port: int) -> None:
    """Servidor MCP de validação de citações legais (anti-alucinação)."""
    import sys
    from db.legislacao import legislacao_enabled

    if not legislacao_enabled():
        console.print("[red]ERROR:[/red] LEGISLACAO_DATABASE_URL não definida (ver .env.example)")
        sys.exit(1)
    from .validacao.mcp_server import serve

    if http:
        console.print(f"[bold blue]mcp[/bold blue] streamable-http em {host}:{port}")
    serve(http=http, host=host, port=port)


@cli.command()
@click.argument("graph_path", default="output/knowledge-graph.json")
def validate(graph_path: str) -> None:
    """Validate a knowledge-graph.json file."""
    import json
    import sys
    path = Path(graph_path)
    if not path.exists():
        console.print(f"[red]ERROR:[/red] {path} not found")
        sys.exit(1)
    data = json.loads(path.read_text())
    node_ids = {n["id"] for n in data.get("nodes", [])}
    errors = []
    for edge in data.get("edges", []):
        if edge["source"] not in node_ids:
            errors.append(f"Dangling source: {edge['source']}")
        if edge["target"] not in node_ids:
            errors.append(f"Dangling target: {edge['target']}")
    review_count = sum(
        1 for x in data.get("nodes", []) + data.get("edges", [])
        if x.get("review_required")
    )
    if errors:
        for e in errors:
            console.print(f"[red]ERROR:[/red] {e}")
        sys.exit(1)
    console.print(
        f"[green]OK[/green] — {len(node_ids)} nodes, "
        f"{len(data.get('edges', []))} edges, "
        f"{review_count} pending review"
    )


@cli.command()
@click.option("--port", default=8080, help="HTTP server port")
def serve(port: int) -> None:
    """Serve the frontend viewer at http://localhost:<port>"""
    import subprocess
    import sys
    import webbrowser
    from pathlib import Path as _Path
    frontend_dir = _Path(__file__).parent.parent / "frontend"
    if not frontend_dir.exists():
        console.print("[red]ERROR:[/red] frontend/ directory not found — build the frontend first")
        return
    console.print(f"[bold blue]Serving[/bold blue] http://localhost:{port}")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    webbrowser.open(f"http://localhost:{port}/index.html")
    subprocess.run(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(frontend_dir)],
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
