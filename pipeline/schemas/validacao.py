"""Tipos da validação de citações legais (MCP anti-alucinação).

Vereditos possíveis de uma validação:
  confirmada            referência existe, vigente, e o texto alegado confere
  referencia_valida     referência existe e está vigente (sem texto p/ comparar)
  texto_divergente      referência existe, mas o texto alegado não confere
  revogado              dispositivo revogado na data consultada
  inexistente_na_data   dispositivo existe, mas não vigia na data consultada
  dispositivo_inexistente  a norma existe na base, o dispositivo não
  norma_fora_da_base    a base não conhece a norma — não é possível validar
  citacao_nao_reconhecida  o texto da citação não pôde ser interpretado
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CitacaoParseada(BaseModel):
    """Resultado do parse determinístico de uma citação textual."""

    tipo_norma: str | None = None     # lei_ordinaria, lei_complementar, decreto...
    numero_norma: str | None = None   # sem pontos de milhar ('10962')
    ano_norma: int | None = None
    id_canonico: str | None = None    # gramática do id_factory ('art5a_parun')
    rotulo: str | None = None         # forma legível ('art. 5º-A, parágrafo único')


class DispositivoConsultado(BaseModel):
    """Estado de um dispositivo numa data, vindo de fn_consultar_dispositivo."""

    norma: str
    urn_lexml: str | None = None
    id_canonico: str
    rotulo: str | None = None
    situacao: str                       # vigente | revogado | inexistente na data
    texto: str | None = None
    numero_versao: int | None = None
    vigente_de: date | None = None
    vigente_ate: date | None = None
    redacao_dada_por: str | None = None


class ResultadoValidacao(BaseModel):
    """Veredito da validação de uma citação (com ou sem texto alegado)."""

    veredito: str
    citacao: CitacaoParseada
    dispositivo: DispositivoConsultado | None = None
    similaridade: float | None = Field(
        default=None, description="0..1 entre texto alegado e oficial (normalizados)"
    )
    texto_oficial: str | None = None
    observacao: str | None = None
