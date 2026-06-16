"""Servidor MCP de validação — registro das tools e integração com Postgres.

Os testes de banco requerem LEGISLACAO_DATABASE_URL (mesmo padrão do
test_legislation_loader); criam uma norma de fixture via funções do motor
dentro de uma transação que é revertida ao final — nada persiste.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

# ── tools registradas (sem banco) ────────────────────────────────────────────

def test_tools_registradas():
    from pipeline.validacao.mcp_server import mcp

    nomes = {t.name for t in mcp._tool_manager.list_tools()}
    assert nomes == {
        "validar_citacao",
        "consultar_dispositivo",
        "buscar_dispositivos",
        "texto_consolidado",
        "listar_normas",
    }


def test_tools_documentadas():
    from pipeline.validacao.mcp_server import mcp

    for tool in mcp._tool_manager.list_tools():
        assert tool.description, f"tool {tool.name} sem docstring"


# ── integração com a base (skip sem Postgres) ────────────────────────────────

pytestmark_db = pytest.mark.skipif(
    not os.environ.get("LEGISLACAO_DATABASE_URL"),
    reason="requer Postgres (LEGISLACAO_DATABASE_URL)",
)


@pytest.fixture()
def conn_com_lei_teste():
    """Conexão com uma lei de fixture (não commitada — rollback no teardown)."""
    from db.legislacao import get_conn, init_legislacao_db

    init_legislacao_db()
    conn = get_conn()
    try:
        norma_id = conn.execute(
            "SELECT fn_criar_norma(%s,%s,%s::smallint,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                "lei_ordinaria", "99999", 2020, date(2020, 1, 1),
                "Lei de teste do MCP", None, "lei-teste-mcp", "federal",
                "federal", "urn:lex:br:federal:lei:2020;99999-teste-mcp", None,
            ),
        ).fetchone()[0]
        conn.execute(
            "SELECT fn_inserir_dispositivo(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                norma_id, "artigo", "Art. 1º", "art1",
                "É permitido o uso de fixture em testes de integração.",
                1, date(2020, 1, 1), None, None, None,
            ),
        )
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytestmark_db
class TestIntegracaoBase:
    def test_referencia_valida(self, conn_com_lei_teste):
        from pipeline.validacao.validador import validar_citacao

        r = validar_citacao(conn_com_lei_teste, "art. 1º da Lei 99.999/2020")
        assert r.veredito == "referencia_valida"
        assert "fixture" in r.texto_oficial

    def test_confirmada_e_divergente(self, conn_com_lei_teste):
        from pipeline.validacao.validador import validar_citacao

        ok = validar_citacao(
            conn_com_lei_teste, "art. 1º da Lei 99.999/2020",
            texto_alegado="É permitido o uso de fixture em testes de integração.",
        )
        assert ok.veredito == "confirmada"

        alucinado = validar_citacao(
            conn_com_lei_teste, "art. 1º da Lei 99.999/2020",
            texto_alegado="É proibido o uso de mocks em qualquer hipótese.",
        )
        assert alucinado.veredito == "texto_divergente"

    def test_dispositivo_inexistente(self, conn_com_lei_teste):
        from pipeline.validacao.validador import validar_citacao

        r = validar_citacao(conn_com_lei_teste, "art. 42 da Lei 99.999/2020")
        assert r.veredito == "dispositivo_inexistente"

    def test_busca_textual(self, conn_com_lei_teste):
        from pipeline.validacao.validador import buscar_dispositivos

        achados = buscar_dispositivos(conn_com_lei_teste, "fixture em testes")
        assert any(a["id_canonico"] == "art1" for a in achados)
