"""Parse de citações legais e veredito de validação (MCP anti-alucinação)."""
from __future__ import annotations

from pipeline.validacao.citacao import parse_citacao
from pipeline.validacao.validador import (
    SIMILARIDADE_CONFIRMA,
    normalizar,
    similaridade,
    validar_citacao,
)


# ── parse_citacao ────────────────────────────────────────────────────────────

class TestParseCitacao:
    def test_artigo_simples(self):
        cit = parse_citacao("art. 1º da Lei nº 13.455, de 2017")
        assert cit.numero_norma == "13455"
        assert cit.ano_norma == 2017
        assert cit.tipo_norma == "lei_ordinaria"
        assert cit.id_canonico == "art1"

    def test_numero_barra_ano(self):
        cit = parse_citacao("art. 2º da Lei 10.962/2004")
        assert cit.numero_norma == "10962"
        assert cit.ano_norma == 2004
        assert cit.id_canonico == "art2"

    def test_artigo_com_sufixo_e_paragrafo_unico(self):
        cit = parse_citacao("art. 5º-A, parágrafo único, da Lei 10.962/2004")
        assert cit.id_canonico == "art5a_parun"

    def test_paragrafo_numerado(self):
        cit = parse_citacao("art. 2º, § 1º, da Lei 10.962/2004")
        assert cit.id_canonico == "art2_par1"

    def test_inciso_com_keyword(self):
        cit = parse_citacao("art. 2º, inciso II, da Lei 10.962/2004")
        assert cit.id_canonico == "art2_inc2"

    def test_inciso_solto_romano(self):
        cit = parse_citacao("art. 2º, II, da Lei 10.962/2004")
        assert cit.id_canonico == "art2_inc2"

    def test_paragrafo_inciso_alinea(self):
        cit = parse_citacao("art. 5º, § 2º, inciso III, alínea b, da Lei 13.455/2017")
        assert cit.id_canonico == "art5_par2_inc3_alib"

    def test_norma_antes_do_artigo(self):
        cit = parse_citacao("Lei 10.962/2004, art. 2º, II")
        assert cit.numero_norma == "10962"
        assert cit.id_canonico == "art2_inc2"

    def test_lei_complementar(self):
        cit = parse_citacao("art. 10 da Lei Complementar nº 95, de 1998")
        assert cit.tipo_norma == "lei_complementar"
        assert cit.numero_norma == "95"
        assert cit.id_canonico == "art10"

    def test_citacao_sem_dispositivo(self):
        cit = parse_citacao("Lei 10.962/2004")
        assert cit.numero_norma == "10962"
        assert cit.id_canonico is None

    def test_citacao_irreconhecivel(self):
        cit = parse_citacao("o princípio da boa-fé objetiva")
        assert cit.id_canonico is None
        assert cit.numero_norma is None


# ── similaridade ─────────────────────────────────────────────────────────────

class TestSimilaridade:
    OFICIAL = (
        "Fica autorizada a diferenciação de preços de bens e serviços oferecidos "
        "ao público em função do prazo ou do instrumento de pagamento utilizado."
    )

    def test_normalizar_ignora_caixa_pontuacao_espacos(self):
        assert normalizar("Texto,  com:  PONTUAÇÃO!") == normalizar("texto com pontuação")

    def test_texto_fiel_confirma(self):
        alegado = "fica autorizada a diferenciação de preços de bens e serviços oferecidos ao público em função do prazo ou do instrumento de pagamento utilizado"
        assert similaridade(alegado, self.OFICIAL) >= SIMILARIDADE_CONFIRMA

    def test_texto_alucinado_divergente(self):
        alegado = "É vedada a diferenciação de preços em função do instrumento de pagamento."
        assert similaridade(alegado, self.OFICIAL) < SIMILARIDADE_CONFIRMA


# ── veredito com conexão fake ────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    """Despacha execute() por trecho do SQL — sem Postgres."""

    def __init__(self, normas=None, dispositivo=None):
        self.normas = normas or []
        self.dispositivo = dispositivo

    def execute(self, sql, params=None):
        if "FROM norma" in sql and "WHERE regexp_replace" in sql:
            return FakeCursor(self.normas)
        if "fn_consultar_dispositivo" in sql:
            return FakeCursor([self.dispositivo] if self.dispositivo else [])
        raise AssertionError(f"SQL inesperado no fake: {sql[:60]}")


NORMA_10962 = (1, "lei_ordinaria", "10962", 2004, "urn:lex:br:federal:lei:2004;10962")
DISP_5A = (
    "Art. 5º-A.", "vigente",
    "O fornecedor deve informar, em local e formato visíveis ao consumidor, "
    "eventuais descontos oferecidos em função do prazo ou do instrumento de "
    "pagamento utilizado.",
    1, None, None, "lei_ordinaria 13455/2017",
)


class TestValidarCitacao:
    def test_citacao_nao_reconhecida(self):
        r = validar_citacao(FakeConn(), "o princípio da legalidade")
        assert r.veredito == "citacao_nao_reconhecida"

    def test_norma_fora_da_base(self):
        r = validar_citacao(FakeConn(normas=[]), "art. 5º da Lei 99.999/1999")
        assert r.veredito == "norma_fora_da_base"
        assert "não significa que a citação esteja errada" in r.observacao

    def test_dispositivo_inexistente(self):
        conn = FakeConn(normas=[NORMA_10962], dispositivo=None)
        r = validar_citacao(conn, "art. 77 da Lei 10.962/2004")
        assert r.veredito == "dispositivo_inexistente"

    def test_referencia_valida_sem_texto(self):
        conn = FakeConn(normas=[NORMA_10962], dispositivo=DISP_5A)
        r = validar_citacao(conn, "art. 5º-A da Lei 10.962/2004")
        assert r.veredito == "referencia_valida"
        assert r.texto_oficial.startswith("O fornecedor deve informar")
        assert r.dispositivo.situacao == "vigente"

    def test_confirmada_com_texto_fiel(self):
        conn = FakeConn(normas=[NORMA_10962], dispositivo=DISP_5A)
        r = validar_citacao(
            conn, "art. 5º-A da Lei 10.962/2004",
            texto_alegado="O fornecedor deve informar, em local e formato visíveis "
                          "ao consumidor, eventuais descontos oferecidos em função do "
                          "prazo ou do instrumento de pagamento utilizado.",
        )
        assert r.veredito == "confirmada"
        assert r.similaridade >= SIMILARIDADE_CONFIRMA

    def test_texto_divergente_alucinacao(self):
        conn = FakeConn(normas=[NORMA_10962], dispositivo=DISP_5A)
        r = validar_citacao(
            conn, "art. 5º-A da Lei 10.962/2004",
            texto_alegado="O fornecedor fica proibido de oferecer descontos em "
                          "função do instrumento de pagamento.",
        )
        assert r.veredito == "texto_divergente"
        assert r.texto_oficial is not None  # devolve o oficial p/ correção

    def test_revogado(self):
        disp = ("Art. 3º", "revogado", None, 2, None, None, "lei_ordinaria 13455/2017")
        conn = FakeConn(normas=[NORMA_10962], dispositivo=disp)
        r = validar_citacao(conn, "art. 3º da Lei 10.962/2004")
        assert r.veredito == "revogado"

    def test_filtra_por_ano_da_norma(self):
        # mesma numeração em ano diferente não resolve
        conn = FakeConn(normas=[NORMA_10962])
        r = validar_citacao(conn, "art. 1º da Lei 10.962/2010")
        assert r.veredito == "norma_fora_da_base"
