"""Parse determinístico de citações legais textuais.

Transforma "art. 5º-A, parágrafo único, da Lei nº 10.962, de 2004" em
(tipo_norma, numero, ano) + id_canonico na gramática do id_factory
('art5a_parun'). Nenhuma inferência: o que não casa com os padrões
retorna campos None — o veredito vira 'citacao_nao_reconhecida'.
"""
from __future__ import annotations

import re

from ..parsers.history_patterns import parse_norma_ref
from ..schemas.validacao import CitacaoParseada
from ..utils.id_factory import (
    canon_alinea,
    canon_artigo,
    canon_inciso,
    canon_paragrafo,
)

# número de lei seguido de /ano ("Lei 13.455/2017") — complementa o
# NORMA_REF_RE de history_patterns, que só entende ", de 2017"
_NUMERO_BARRA_ANO_RE = re.compile(r"([\d.]+)\s*/\s*(\d{4})")

_ARTIGO_RE = re.compile(
    r"\bart(?:igo)?\.?\s*(\d+(?:\s*[º°])?(?:\s*-\s*[A-Za-z])?)", re.IGNORECASE
)
_PAR_UNICO_RE = re.compile(r"par[áa]grafo\s+[úu]nico", re.IGNORECASE)
_PARAGRAFO_RE = re.compile(r"(?:§|par[áa]grafo)\s*(\d+)\s*[º°]?", re.IGNORECASE)
_INCISO_KW_RE = re.compile(r"\binc(?:iso)?\.?\s*([IVXLCDM]+(?:\s*-\s*[A-Za-z])?)\b")
_INCISO_SOLTO_RE = re.compile(r"^([IVXLCDM]+(?:\s*-\s*[A-Za-z])?)$")
_ALINEA_RE = re.compile(
    r"(?:\bal[íi]nea|\bletra)\s*['\"”“]?([a-z])['\"”“]?\)?", re.IGNORECASE
)
_ALINEA_SOLTA_RE = re.compile(r"^['\"”“]?([a-z])['\"”“]?\)$")


def _limpar_numero(numero: str) -> str:
    return re.sub(r"\s*", "", numero).replace("º", "").replace("°", "").upper()


def parse_citacao(texto: str) -> CitacaoParseada:
    """Interpreta uma citação textual de dispositivo legal."""
    cit = CitacaoParseada()

    # ── norma ────────────────────────────────────────────────────────────
    ref = parse_norma_ref(texto)
    if ref:
        cit.tipo_norma = ref["tipo"]
        cit.numero_norma = ref["numero"]
        cit.ano_norma = ref["ano"]
        if cit.ano_norma is None:
            m = _NUMERO_BARRA_ANO_RE.search(texto)
            if m and m.group(1).replace(".", "") == cit.numero_norma:
                cit.ano_norma = int(m.group(2))

    # ── dispositivo ──────────────────────────────────────────────────────
    m_art = _ARTIGO_RE.search(texto)
    if not m_art:
        return cit
    numero_art = _limpar_numero(m_art.group(1))
    id_canonico = canon_artigo(numero_art)
    rotulo = [f"art. {numero_art}"]

    # só a parte depois do artigo descreve §/inciso/alínea; a parte da norma
    # ("da Lei nº ...") é cortada para não confundir os padrões soltos
    resto = texto[m_art.end():]
    resto = re.split(r"\b(?:d[ao]|,\s*d[ao])\s+(?:Lei|Decreto|Medida|Resolu)", resto)[0]

    if _PAR_UNICO_RE.search(resto):
        id_canonico = canon_paragrafo(id_canonico, "un")
        rotulo.append("parágrafo único")
    else:
        m = _PARAGRAFO_RE.search(resto)
        if m:
            id_canonico = canon_paragrafo(id_canonico, m.group(1))
            rotulo.append(f"§ {m.group(1)}º")

    m = _INCISO_KW_RE.search(resto)
    if not m:
        for segmento in (s.strip() for s in resto.split(",")):
            m = _INCISO_SOLTO_RE.match(segmento)
            if m:
                break
    if m:
        id_canonico = canon_inciso(id_canonico, _limpar_numero(m.group(1)))
        rotulo.append(f"inciso {m.group(1).strip()}")

    m = _ALINEA_RE.search(resto)
    if not m:
        for segmento in (s.strip() for s in resto.split(",")):
            m = _ALINEA_SOLTA_RE.match(segmento)
            if m:
                break
    if m:
        id_canonico = canon_alinea(id_canonico, m.group(1).lower())
        rotulo.append(f"alínea {m.group(1).lower()})")

    cit.id_canonico = id_canonico
    cit.rotulo = ", ".join(rotulo)
    return cit
