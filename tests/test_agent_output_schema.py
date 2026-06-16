"""Guarda pré-deploy: outputs de todos os agentes validam nos schemas do grafo.

A sequência completa de agentes roda sobre um corpus mínimo que exercita os
caminhos de cada um (definição, prazo, remissão, revogação, implicação via
LLM mockado). Qualquer nó/aresta fora do schema falha aqui — em produção o
graph-builder o descartaria silenciosamente do grafo.
"""
import json
from pathlib import Path

from pipeline.agents.domain_analyzer import DomainAnalyzerAgent
from pipeline.agents.hierarchy_analyzer import HierarchyAnalyzerAgent
from pipeline.agents.implication_analyzer import ImplicationAnalyzerAgent
from pipeline.agents.norm_analyzer import NormAnalyzerAgent
from pipeline.agents.revocation_analyzer import RevocationAnalyzerAgent
from pipeline.utils.claude_client import ClaudeClient

from tests.graph_contract import validate_intermediate_outputs

# doc-a é a Resolução BCB nº 99/2020: art. 1º tem definição + prazo (domain),
# art. 2º remete à Resolução 9/2020 (hierarchy), art. 3º revoga o próprio
# art. 2º (revocation, fonte = artigo que contém a sentença)
DOC_A = (
    "Art. 1º Para os fins desta Resolução, considera-se Instituição "
    "Participante a entidade autorizada, observado o prazo de 10 dias "
    "úteis para adesão.\n\n"
    "Art. 2º Aplica-se o disposto no art. 3º da Resolução BCB nº 9, de 2020.\n\n"
    "Art. 3º Fica revogado o art. 2º da Resolução BCB nº 99, de 2020.\n"
)


def _fake_llm(self, system: str, user: str, max_retries: int = 3) -> str:
    if "ARTIGOS CANDIDATOS" in user:  # implication-analyzer (batch, objeto por art_id)
        return json.dumps({
            "disp:doc-a:art1": [{
                "targetId": "disp:doc-b:art3",
                "edgeType": "obriga",
                "confidence": 0.95,
                "textEvidence": "observado o prazo de 10 dias úteis",
                "reasoning": "adesão obrigatória no prazo",
            }],
        })
    if user.startswith("DOCUMENTO:"):  # domain-analyzer (definições via LLM)
        return json.dumps({"definicoes": []})
    return "[]"  # norm-analyzer (summaries em batch)


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    corpus_dir = tmp_path / "corpus"
    parsed = corpus_dir / "parsed"
    parsed.mkdir(parents=True)
    (parsed / "doc-a.md").write_text(DOC_A, encoding="utf-8")

    intermediate = tmp_path / "intermediate"
    intermediate.mkdir()
    manifest = {
        "documents": [
            {
                "documentId": "doc-a",
                "parsedPath": "corpus/parsed/doc-a.md",
                "type": "resolucao",
                "number": "99",
                "year": 2020,
                "dataVigor": "2020-11-16",
                "fileHash": "hash-a",
            },
            {
                # referenciado por remissão/implicação; sem arquivo parseado
                "documentId": "doc-b",
                "parsedPath": "corpus/parsed/doc-b.md",
                "type": "resolucao",
                "number": "9",
                "year": 2020,
            },
        ]
    }
    (intermediate / "scan_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return intermediate, corpus_dir


def test_outputs_de_todos_os_agentes_validam_no_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(ClaudeClient, "call", _fake_llm)
    intermediate, corpus_dir = _setup(tmp_path)

    NormAnalyzerAgent().run(intermediate, corpus_dir)
    HierarchyAnalyzerAgent().run(intermediate, corpus_dir)
    RevocationAnalyzerAgent().run(intermediate, corpus_dir)
    ImplicationAnalyzerAgent().run(intermediate, corpus_dir)
    DomainAnalyzerAgent().run(intermediate, corpus_dir)

    # o corpus mínimo precisa ter exercitado cada agente, senão o guard é vazio
    norm = json.loads((intermediate / "norm_analyzer.json").read_text(encoding="utf-8"))
    norm_nodes = norm["byDocument"]["doc-a"]["nodes"]
    assert {n["type"] for n in norm_nodes} >= {"norma", "artigo"}

    domain = json.loads((intermediate / "domain_analyzer.json").read_text(encoding="utf-8"))
    assert {n["type"] for n in domain["nodes"]} >= {"definicao", "prazo"}

    hier = json.loads((intermediate / "hierarchy_analyzer.json").read_text(encoding="utf-8"))
    assert any(e["type"] == "remete_a" for e in hier["edges"])

    rev = json.loads((intermediate / "revocation_analyzer.json").read_text(encoding="utf-8"))
    assert rev["edges"], "revocation-analyzer deveria ter extraído a revogação"

    impl = json.loads((intermediate / "implication_analyzer.json").read_text(encoding="utf-8"))
    assert impl["edges"], "implication-analyzer deveria ter criado a aresta mockada"

    validate_intermediate_outputs(intermediate)
