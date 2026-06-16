"""Contrato de schema dos outputs intermediários dos agentes.

Espelha exatamente o que o GraphBuilder.load_agents() consome, mas de forma
estrita: em produção o builder descarta silenciosamente nós/arestas que não
validam (perda de dados no grafo, sem derrubar o pipeline). Nos testes,
qualquer item fora do schema falha com o arquivo e o id do item.
"""
import json
from pathlib import Path

from pipeline.schemas import GraphEdge, GraphNode, Layer


def _load(intermediate: Path, name: str) -> dict | None:
    path = intermediate / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(model, item: dict, origem: str) -> None:
    try:
        model.model_validate(item)
    except Exception as e:
        raise AssertionError(
            f"{origem}: item '{item.get('id', '?')}' fora do schema "
            f"{model.__name__} — o graph-builder o descartaria em produção:\n{e}"
        ) from e


def validate_intermediate_outputs(intermediate: Path) -> None:
    """Valida todos os outputs intermediários presentes no diretório."""
    norm = _load(intermediate, "norm_analyzer.json")
    if norm:
        for doc_id, doc_info in norm.get("byDocument", {}).items():
            for n in doc_info.get("nodes", []):
                _validate(GraphNode, n, f"norm_analyzer.json ({doc_id})")

    domain = _load(intermediate, "domain_analyzer.json")
    if domain:
        for n in domain.get("nodes", []):
            _validate(GraphNode, n, "domain_analyzer.json")
        for e in domain.get("edges", []):
            _validate(GraphEdge, e, "domain_analyzer.json")

    hier = _load(intermediate, "hierarchy_analyzer.json")
    if hier:
        for e in hier.get("edges", []):
            _validate(GraphEdge, e, "hierarchy_analyzer.json")
        for layer in hier.get("layers", []):
            _validate(Layer, layer, "hierarchy_analyzer.json")

    for name in ("revocation_analyzer.json", "implication_analyzer.json"):
        data = _load(intermediate, name)
        if data:
            for e in data.get("edges", []):
                _validate(GraphEdge, e, name)
