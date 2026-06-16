"""Servidor MCP de validação de citações legais (anti-alucinação).

Expõe a Base de Legislação Estruturada como tools MCP, para que um LLM
valide referências a artigos de lei contra a fonte da verdade. Somente
leitura; nenhuma tool muda a base.

Transportes (mesmo código):
    amanuense mcp                 # stdio — uso local (Claude Code/Desktop)
    amanuense mcp --http          # streamable-http em 0.0.0.0:8765

Requer LEGISLACAO_DATABASE_URL apontando para a base estruturada.
"""
from __future__ import annotations

from datetime import date

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import validador

mcp = FastMCP(
    "amanuense-legislacao",
    # serviço interno (rede Docker, sem porta publicada): os clientes chegam
    # por hostname/IP do container, que a proteção de DNS rebinding rejeitaria
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    instructions=(
        "Valida afirmações sobre artigos de lei contra a Base de Legislação "
        "Estruturada do Amanuense (fonte da verdade, redações versionadas no "
        "tempo). Use validar_citacao antes de afirmar o conteúdo de qualquer "
        "dispositivo legal. Veredito 'norma_fora_da_base' significa que a "
        "base não cobre a norma — não que a citação esteja errada."
    ),
)


def _conn():
    from db.legislacao import get_conn

    return get_conn()


def _data(data_str: str | None) -> date | None:
    return date.fromisoformat(data_str) if data_str else None


@mcp.tool()
def validar_citacao(
    citacao: str, texto_alegado: str | None = None, data: str | None = None
) -> dict:
    """Valida uma citação legal contra a base estruturada.

    Args:
        citacao: referência textual, ex. "art. 5º-A, parágrafo único, da Lei 10.962/2004".
        texto_alegado: o texto que a IA afirmou ser o conteúdo do dispositivo
            (opcional — com ele o veredito também compara o conteúdo).
        data: valida a vigência nesta data (YYYY-MM-DD; padrão: hoje).

    Returns:
        veredito (confirmada | referencia_valida | texto_divergente | revogado |
        inexistente_na_data | dispositivo_inexistente | norma_fora_da_base |
        citacao_nao_reconhecida), o texto oficial vigente e os metadados de
        vigência/versão do dispositivo.
    """
    with _conn() as conn:
        return validador.validar_citacao(
            conn, citacao, texto_alegado, _data(data)
        ).model_dump(mode="json")


@mcp.tool()
def consultar_dispositivo(citacao: str, data: str | None = None) -> dict:
    """Retorna o texto oficial vigente de um dispositivo (na data, se informada).

    Args:
        citacao: referência textual, ex. "art. 2º, II, da Lei 10.962/2004".
        data: consulta a redação vigente nesta data (YYYY-MM-DD; padrão: hoje).
    """
    with _conn() as conn:
        resultado = validador.validar_citacao(conn, citacao, None, _data(data))
        if resultado.dispositivo is None:
            return resultado.model_dump(mode="json")
        return resultado.dispositivo.model_dump(mode="json")


@mcp.tool()
def buscar_dispositivos(termo: str, limite: int = 10) -> list[dict]:
    """Busca textual nas redações vigentes — encontra o artigo certo quando a
    citação está errada ou incompleta.

    Args:
        termo: trecho a procurar (ILIKE) no texto dos dispositivos vigentes.
        limite: máximo de resultados (padrão 10).
    """
    with _conn() as conn:
        return validador.buscar_dispositivos(conn, termo, limite)


@mcp.tool()
def texto_consolidado(norma: str, data: str | None = None) -> dict:
    """Texto integral consolidado de uma norma na data (máquina do tempo).

    Args:
        norma: referência à norma, ex. "Lei 10.962/2004".
        data: data da consolidação (YYYY-MM-DD; padrão: hoje).
    """
    with _conn() as conn:
        return validador.texto_consolidado(conn, norma, _data(data))


@mcp.tool()
def listar_normas() -> list[dict]:
    """Normas presentes na base estruturada — o escopo do que é validável."""
    with _conn() as conn:
        return validador.listar_normas(conn)


def serve(http: bool = False, host: str = "0.0.0.0", port: int = 8765) -> None:
    """Sobe o servidor MCP (stdio por padrão; streamable-http com http=True)."""
    if http:
        mcp.settings.host = host
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
