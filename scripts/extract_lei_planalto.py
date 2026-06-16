#!/usr/bin/env python3
"""Extração automática de leis a partir do texto do Planalto.

Baixa (ou lê de arquivo local) o HTML compilado de uma lei no Planalto,
converte para o texto canônico (pipeline.parsers.planalto_html), grava em
corpus/parsed/<doc_id>.md e registra os metadados corretos no
corpus/registry.json — a partir daí o fluxo normal (corpus-scanner +
legislation-loader) monta a árvore canônica e carrega a base estruturada.

Uso:
    python scripts/extract_lei_planalto.py --sprint1        # as duas leis do MVP
    python scripts/extract_lei_planalto.py --url URL --doc-id lei10962-2004 \
        --numero 10962 --ano 2004 --publicacao 2004-10-13
    python scripts/extract_lei_planalto.py --html arquivo.htm --doc-id ... (offline)
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import click
from rich.console import Console

from pipeline.config import CORPUS_DIR
from pipeline.corpus_registry import load_registry, save_registry
from pipeline.parsers.planalto_html import planalto_html_to_text

console = Console()

# Leis do MVP (sprint 1 — Lei de Diferenciação de Preço e a lei que ela altera)
LEIS_SPRINT1 = [
    {
        "doc_id": "lei10962-2004",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l10.962.htm",
        "numero": "10962",
        "ano": 2004,
        "publicacao": "2004-10-13",
        "descricao": "Dispõe sobre a oferta e as formas de afixação de preços de produtos e serviços para o consumidor.",
    },
    {
        "doc_id": "lei13455-2017",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13455.htm",
        "numero": "13455",
        "ano": 2017,
        "publicacao": "2017-06-27",
        "descricao": "Dispõe sobre a diferenciação de preços de bens e serviços oferecidos ao público em função do prazo ou do instrumento de pagamento utilizado.",
    },
]


def _baixar(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Amanuense)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    # Planalto serve páginas antigas em windows-1252/latin-1
    for enc in ("utf-8", "windows-1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extrair_lei(
    *, doc_id: str, numero: str, ano: int, publicacao: str,
    tipo: str = "lei_ordinaria", descricao: str | None = None,
    url: str | None = None, html: str | None = None,
    corpus_dir: Path = CORPUS_DIR,
) -> Path:
    """Extrai uma lei e a registra no corpus. Retorna o caminho do parsed."""
    if html is None:
        if not url:
            raise ValueError("informe url ou html")
        console.print(f"[cyan]→[/cyan] baixando {url}")
        html = _baixar(url)

    texto = planalto_html_to_text(html)
    if len(texto.strip()) < 100:
        raise ValueError(f"{doc_id}: texto extraído muito curto ({len(texto)} chars)")

    parsed_path = corpus_dir / "parsed" / f"{doc_id}.md"
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text(texto, encoding="utf-8")

    registry = load_registry(corpus_dir)
    registry[doc_id] = {
        "authority": "federal",
        "type": tipo,
        "number": numero,
        "year": ano,
        "dataPublicacao": publicacao,
        "dataVigor": publicacao,
        "vigencyStatus": "vigente",
        "description": descricao or doc_id,
        "urlFonteOficial": url,
    }
    save_registry(corpus_dir, registry)

    n_linhas = len(texto.splitlines())
    console.print(f"[green]✓[/green] {doc_id}: {n_linhas} linhas → {parsed_path}")
    return parsed_path


@click.command()
@click.option("--sprint1", is_flag=True, help="Extrai as duas leis do MVP (13.455/2017 + 10.962/2004)")
@click.option("--url", help="URL da lei no Planalto")
@click.option("--html", "html_file", type=click.Path(exists=True), help="Arquivo HTML local (offline)")
@click.option("--doc-id", help="Identificador do documento no corpus")
@click.option("--tipo", default="lei_ordinaria", show_default=True)
@click.option("--numero", help="Número da lei sem pontos (ex: 13455)")
@click.option("--ano", type=int)
@click.option("--publicacao", help="Data de publicação (YYYY-MM-DD)")
@click.option("--descricao")
def main(sprint1, url, html_file, doc_id, tipo, numero, ano, publicacao, descricao):
    if sprint1:
        for lei in LEIS_SPRINT1:
            extrair_lei(**lei)
        return
    if not doc_id or not numero or not ano or not publicacao:
        raise click.UsageError("informe --doc-id, --numero, --ano e --publicacao (ou use --sprint1)")
    html = Path(html_file).read_text(encoding="utf-8") if html_file else None
    extrair_lei(
        doc_id=doc_id, tipo=tipo, numero=numero, ano=ano, publicacao=publicacao,
        descricao=descricao, url=url, html=html,
    )


if __name__ == "__main__":
    main()
