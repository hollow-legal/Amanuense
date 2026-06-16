"""Validação de citações legais contra a Base de Legislação Estruturada.

Todas as operações são de leitura e determinísticas (anti-alucinação):
o texto oficial vem sempre de fn_consultar_dispositivo/fn_texto_consolidado;
a comparação com o texto alegado é por similaridade normalizada (difflib),
nunca por interpretação. O que a base não conhece retorna explicitamente
'norma_fora_da_base' — nunca um palpite.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

from ..schemas.validacao import (
    CitacaoParseada,
    DispositivoConsultado,
    ResultadoValidacao,
)
from .citacao import parse_citacao

# Acima deste valor o texto alegado é considerado fiel ao oficial
SIMILARIDADE_CONFIRMA = 0.92


def normalizar(texto: str) -> str:
    """Normalização para comparação: NFC, caixa baixa, espaços/pontuação colapsados."""
    texto = unicodedata.normalize("NFC", texto).lower()
    texto = re.sub(r"[\"'""''§º°]", "", texto)
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()


# ── consultas ────────────────────────────────────────────────────────────────

def listar_normas(conn) -> list[dict]:
    """Normas que a base conhece — o escopo honesto da validação."""
    rows = conn.execute(
        """SELECT n.id_norma, n.tipo, n.numero, n.ano, n.apelido, n.ementa,
                  n.urn_lexml, COUNT(d.id_dispositivo) AS dispositivos
           FROM norma n LEFT JOIN dispositivo d ON d.id_norma = n.id_norma
           GROUP BY n.id_norma ORDER BY n.ano, n.numero"""
    ).fetchall()
    return [
        {
            "id_norma": r[0], "tipo": r[1], "numero": r[2], "ano": r[3],
            "apelido": r[4], "ementa": r[5], "urn_lexml": r[6], "dispositivos": r[7],
        }
        for r in rows
    ]


def _resolver_norma(conn, cit: CitacaoParseada) -> tuple[int, str, str | None] | None:
    """Resolve (id_norma, descricao, urn) a partir da citação. None se fora da base."""
    if not cit.numero_norma:
        return None
    candidatos = conn.execute(
        """SELECT id_norma, tipo, numero, ano, urn_lexml FROM norma
           WHERE regexp_replace(numero, '[^0-9a-zA-Z]', '', 'g') = %s
           ORDER BY ano DESC""",
        (cit.numero_norma,),
    ).fetchall()
    for r in candidatos:
        if cit.ano_norma and r[3] != cit.ano_norma:
            continue
        if cit.tipo_norma and r[1] != cit.tipo_norma:
            continue
        return r[0], f"{r[1]} {r[2]}/{r[3]}", r[4]
    return None


def consultar_dispositivo(
    conn, norma_id: int, norma_desc: str, urn: str | None,
    id_canonico: str, data: date | None = None,
) -> DispositivoConsultado | None:
    """Estado de um dispositivo na data (fn_consultar_dispositivo). None se não existe."""
    row = conn.execute(
        "SELECT * FROM fn_consultar_dispositivo(%s, %s, %s)",
        (norma_id, id_canonico, data or date.today()),
    ).fetchone()
    if row is None:
        return None
    return DispositivoConsultado(
        norma=norma_desc, urn_lexml=urn, id_canonico=id_canonico,
        rotulo=row[0], situacao=row[1], texto=row[2], numero_versao=row[3],
        vigente_de=row[4], vigente_ate=row[5], redacao_dada_por=row[6],
    )


def buscar_dispositivos(conn, termo: str, limite: int = 10) -> list[dict]:
    """Busca textual nas redações vigentes — para achar o artigo certo."""
    rows = conn.execute(
        """SELECT n.tipo, n.numero, n.ano, d.id_canonico, d.numero_rotulo, dv.texto
           FROM dispositivo_versao dv
           JOIN dispositivo d ON d.id_dispositivo = dv.id_dispositivo
           JOIN norma n ON n.id_norma = d.id_norma
           WHERE dv.data_fim_vigencia IS NULL
             AND dv.evento != 'revogacao'
             AND dv.texto ILIKE %s
           ORDER BY n.ano, d.ordem_sequencial
           LIMIT %s""",
        (f"%{termo}%", limite),
    ).fetchall()
    return [
        {
            "norma": f"{r[0]} {r[1]}/{r[2]}", "id_canonico": r[3],
            "rotulo": r[4], "texto": r[5],
        }
        for r in rows
    ]


def texto_consolidado(conn, cit_norma: str, data: date | None = None) -> dict:
    """Texto consolidado de uma norma na data (fn_texto_consolidado)."""
    cit = parse_citacao(cit_norma)
    norma = _resolver_norma(conn, cit)
    if norma is None:
        return {"erro": "norma_fora_da_base", "normas_conhecidas": listar_normas(conn)}
    row = conn.execute(
        "SELECT fn_texto_consolidado(%s, %s)", (norma[0], data or date.today())
    ).fetchone()
    return {"norma": norma[1], "urn_lexml": norma[2], "data": str(data or date.today()),
            "texto": row[0]}


# ── veredito ─────────────────────────────────────────────────────────────────

def validar_citacao(
    conn, citacao: str, texto_alegado: str | None = None, data: date | None = None,
) -> ResultadoValidacao:
    """Valida uma citação legal (e opcionalmente o texto que a IA alegou)."""
    cit = parse_citacao(citacao)

    if cit.id_canonico is None or cit.numero_norma is None:
        return ResultadoValidacao(
            veredito="citacao_nao_reconhecida", citacao=cit,
            observacao="não foi possível interpretar norma e dispositivo da citação",
        )

    norma = _resolver_norma(conn, cit)
    if norma is None:
        return ResultadoValidacao(
            veredito="norma_fora_da_base", citacao=cit,
            observacao="a base estruturada não contém esta norma — validação impossível, "
                        "não significa que a citação esteja errada",
        )

    disp = consultar_dispositivo(conn, norma[0], norma[1], norma[2], cit.id_canonico, data)
    if disp is None:
        return ResultadoValidacao(
            veredito="dispositivo_inexistente", citacao=cit,
            observacao=f"a norma {norma[1]} existe na base, mas não tem {cit.rotulo}",
        )
    if disp.situacao == "revogado":
        return ResultadoValidacao(veredito="revogado", citacao=cit, dispositivo=disp)
    if disp.situacao != "vigente":
        return ResultadoValidacao(
            veredito="inexistente_na_data", citacao=cit, dispositivo=disp,
            observacao=f"dispositivo sem redação vigente em {data or date.today()}",
        )

    if texto_alegado is None:
        return ResultadoValidacao(
            veredito="referencia_valida", citacao=cit, dispositivo=disp,
            texto_oficial=disp.texto,
        )

    score = similaridade(texto_alegado, disp.texto or "")
    return ResultadoValidacao(
        veredito="confirmada" if score >= SIMILARIDADE_CONFIRMA else "texto_divergente",
        citacao=cit, dispositivo=disp, similaridade=round(score, 3),
        texto_oficial=disp.texto,
    )
