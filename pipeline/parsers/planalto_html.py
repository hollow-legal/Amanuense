"""Conversor de HTML do Planalto → texto canônico (um dispositivo por linha).

As páginas do Planalto (planalto.gov.br/ccivil_03/...) publicam o texto
compilado das leis com a redação revogada em tachado (<strike>/<s>/<del> ou
style text-decoration). O tachado é REMOVIDO aqui — a redação vigente e as
anotações de histórico "(Incluído pela Lei nº ...)" são preservadas, no
formato que build_canonical_tree espera (um parágrafo HTML por linha).

Anti-alucinação: este módulo só transforma marcação em texto; nenhum
conteúdo é inferido. O que o parser estrutural não reconhecer continua
indo para a fila de revisão manual.
"""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

_STRIKE_TAGS = {"strike", "s", "del"}
_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}
_IGNORE_TAGS = {"script", "style", "head"}

_STRIKE_STYLE_RE = re.compile(r"text-decoration\s*:\s*[^;\"']*line-through", re.IGNORECASE)


class _PlanaltoExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.linhas: list[list[str]] = [[]]
        self._strike_depth = 0       # dentro de <strike>/<s>/<del>
        self._style_strike: list[str] = []  # tags abertas com line-through no style
        self._ignore_depth = 0

    # ── helpers ──────────────────────────────────────────────────────────
    def _nova_linha(self) -> None:
        if self.linhas[-1]:
            self.linhas.append([])

    @property
    def _suprimido(self) -> bool:
        return self._strike_depth > 0 or bool(self._style_strike) or self._ignore_depth > 0

    # ── HTMLParser hooks ─────────────────────────────────────────────────
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if tag in _STRIKE_TAGS:
            self._strike_depth += 1
            return
        style = dict(attrs).get("style") or ""
        if _STRIKE_STYLE_RE.search(style):
            self._style_strike.append(tag)
            return
        if tag in _BLOCK_TAGS:
            self._nova_linha()

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORE_TAGS:
            self._ignore_depth = max(0, self._ignore_depth - 1)
            return
        if tag in _STRIKE_TAGS:
            self._strike_depth = max(0, self._strike_depth - 1)
            return
        if self._style_strike and self._style_strike[-1] == tag:
            self._style_strike.pop()
            return
        if tag in _BLOCK_TAGS:
            self._nova_linha()

    def handle_data(self, data: str) -> None:
        if self._suprimido:
            return
        self.linhas[-1].append(data)


def _normalizar_linha(fragmentos: list[str]) -> str:
    texto = "".join(fragmentos)
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace("\xa0", " ").replace("​", "")
    # aspas/travessões tipográficos comuns no Planalto
    texto = texto.replace("“", '"').replace("”", '"').replace("’", "'")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


# Cabeçalhos/rodapés do site que não pertencem ao texto da norma
_RUIDO_RE = re.compile(
    r"^(Presidência da República|Casa Civil|Subchefia para Assuntos Jurídicos|"
    r"Secretaria.Geral|Este texto não substitui o publicado|Texto compilado|"
    r"Mensagem de veto|Brasília,|\*)",
    re.IGNORECASE,
)


def planalto_html_to_text(html: str) -> str:
    """Converte o HTML de uma lei do Planalto em texto canônico.

    Uma linha por bloco (parágrafo HTML); tachado removido; entidades
    decodificadas; ruído de cabeçalho/rodapé do site filtrado.
    """
    extractor = _PlanaltoExtractor()
    extractor.feed(html)
    extractor.close()

    linhas: list[str] = []
    for fragmentos in extractor.linhas:
        linha = _normalizar_linha(fragmentos)
        if not linha or _RUIDO_RE.match(linha):
            continue
        linhas.append(linha)
    return "\n".join(linhas)
