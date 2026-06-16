"""Regressão: nós DEFINICAO criados pelo domain-analyzer precisam de vigenciaMeta.

DEFINICAO está em NORMATIVE_TYPES, então o schema GraphNode rejeita o nó sem
vigência. O bug original (Lei 14.133, 12/06/2026) derrubava o pipeline no
caminho regex e silenciava o caminho LLM. A definição deve herdar a vigência
do artigo de origem, com fallback vigente/hoje quando o artigo não a tiver.
"""
import json
from pathlib import Path

import pytest

from pipeline.agents.domain_analyzer import DomainAnalyzerAgent

from tests.graph_contract import validate_intermediate_outputs

ART_ID = "disp:l14133:art6"
ART_VIGENCIA = {
    "dataInicio": "2021-04-01",
    "dataFim": None,
    "status": "vigente",
    "versaoAtiva": None,
    "ultimaVerificacao": "2026-06-12",
}

# < 200 chars e com match de DEFINICAO_RE: exercita só o caminho regex
TEXTO_REGEX = (
    "Para os fins desta Lei, considera-se Empresa Estatal a entidade dotada "
    "de personalidade jurídica de direito privado."
)

# > 200 chars com "entende-se" (sem "por", para não casar DEFINICAO_RE):
# exercita só o caminho LLM
TEXTO_LLM = (
    "Para os fins desta Lei, entende-se que os institutos da contratação "
    "direta se aplicam, no que couber, aos procedimentos auxiliares. " * 3
)


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _setup(tmp_path: Path, texto: str, art_vigencia: dict | None) -> tuple[Path, Path]:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    intermediate = tmp_path / "intermediate"
    intermediate.mkdir()

    art_node = {
        "id": ART_ID,
        "type": "artigo",
        "articleNumber": "6",
        "summary": "",
        "vigenciaMeta": art_vigencia,
    }
    _write(intermediate / "norm_analyzer.json", {
        "byDocument": {"l14133": {"nodes": [art_node]}},
        "processedDocIds": {"l14133": "hash-1"},
    })
    _write(intermediate / "corpus_texts_builder.json", {
        "texts": {ART_ID: {"textoCompleto": texto}},
    })
    _write(intermediate / "scan_manifest.json", {"documents": []})
    return intermediate, corpus_dir


def _run_and_load(intermediate: Path, corpus_dir: Path) -> dict:
    DomainAnalyzerAgent().run(intermediate, corpus_dir)
    return json.loads((intermediate / "domain_analyzer.json").read_text(encoding="utf-8"))


def _definicoes(out: dict) -> list[dict]:
    return [n for n in out["nodes"] if n["type"] == "definicao"]


def test_definicao_regex_herda_vigencia_do_artigo(tmp_path):
    intermediate, corpus_dir = _setup(tmp_path, TEXTO_REGEX, ART_VIGENCIA)
    out = _run_and_load(intermediate, corpus_dir)

    defs = _definicoes(out)
    assert defs, "regex DEFINICAO_RE deveria ter extraído uma definição"
    for d in defs:
        assert d["vigenciaMeta"] == ART_VIGENCIA


def test_definicao_sem_vigencia_no_artigo_usa_fallback_vigente(tmp_path):
    intermediate, corpus_dir = _setup(tmp_path, TEXTO_REGEX, art_vigencia=None)
    out = _run_and_load(intermediate, corpus_dir)

    defs = _definicoes(out)
    assert defs
    for d in defs:
        assert d["vigenciaMeta"] is not None
        assert d["vigenciaMeta"]["status"] == "vigente"


def test_definicao_via_llm_herda_vigencia_do_artigo(tmp_path, monkeypatch):
    intermediate, corpus_dir = _setup(tmp_path, TEXTO_LLM, ART_VIGENCIA)

    agent = DomainAnalyzerAgent()
    monkeypatch.setattr(agent.client, "call", lambda system, user: json.dumps({
        "definicoes": [{
            "termo": "Contratação Integrada",
            "definicao": "Regime em que o contratado elabora os projetos.",
            "textEvidence": "entende-se que",
        }],
    }))
    agent.run(intermediate, corpus_dir)
    out = json.loads((intermediate / "domain_analyzer.json").read_text(encoding="utf-8"))

    defs = _definicoes(out)
    assert any(d["name"] == "Contratação Integrada" for d in defs)
    for d in defs:
        assert d["vigenciaMeta"] == ART_VIGENCIA


@pytest.mark.parametrize("art_vigencia", [ART_VIGENCIA, None])
def test_todo_output_do_domain_analyzer_valida_no_schema(tmp_path, art_vigencia):
    """Guarda pré-deploy: o graph-builder valida cada nó com model_validate,
    então qualquer nó fora do schema aqui derrubaria o pipeline em produção."""
    intermediate, corpus_dir = _setup(tmp_path, TEXTO_REGEX, art_vigencia)
    _run_and_load(intermediate, corpus_dir)

    # o norm_analyzer.json daqui é fixture sintético (artigo mínimo), não
    # produto do agente — o output real é coberto em test_agent_output_schema
    (intermediate / "norm_analyzer.json").unlink()
    validate_intermediate_outputs(intermediate)
