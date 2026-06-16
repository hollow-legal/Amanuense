"""Extração automática de leis a partir do HTML do Planalto (sprint 1 do MVP).

Fixtures reproduzem a marcação real do Planalto (windows-1252 na origem,
<p> por dispositivo, tachado <strike> para redação revogada, anotações
"(Incluído pela Lei nº ...)"), num recorte das duas leis do MVP:
Lei 13.455/2017 e Lei 10.962/2004 (alterada pela 13.455).
"""
from __future__ import annotations

from datetime import date

from pipeline.parsers.canonical_tree import build_canonical_tree
from pipeline.parsers.history_patterns import build_corpus_index
from pipeline.parsers.planalto_html import planalto_html_to_text
from scripts.extract_lei_planalto import LEIS_SPRINT1, extrair_lei

HTML_LEI_13455 = """
<html><head><title>L13455</title><style>p { margin: 0 }</style></head><body>
<p>Presidência da República</p>
<p>Casa Civil</p>
<p>Subchefia para Assuntos Jurídicos</p>
<p><strong>LEI Nº 13.455, DE 26 DE JUNHO DE 2017.</strong></p>
<p>Dispõe sobre a diferenciação de preços de bens e serviços oferecidos ao
público em função do prazo ou do instrumento de pagamento utilizado.</p>
<p>Art. 1º&nbsp; Fica autorizada a diferenciação de preços de bens e serviços
oferecidos ao público em função do prazo ou do instrumento de pagamento utilizado.</p>
<p>Parágrafo único.&nbsp; É nula a cláusula contratual, estabelecida no âmbito de
arranjos de pagamento ou de outros acordos para prestação de serviço de pagamento,
que proíba ou restrinja a diferenciação de preços facultada no <i>caput</i> deste artigo.</p>
<p>Art. 2º&nbsp; A Lei nº 10.962, de 11 de outubro de 2004, passa a vigorar
acrescida do seguinte art. 5º-A:</p>
<p>Art. 3º&nbsp; Esta Lei entra em vigor na data de sua publicação.</p>
<p>Brasília, 26 de junho de 2017; 196º da Independência e 129º da República.</p>
<p>Este texto não substitui o publicado no DOU de 27.6.2017</p>
</body></html>
"""

HTML_LEI_10962 = """
<html><body>
<p>Presidência da República</p>
<p><strong>LEI Nº 10.962, DE 11 DE OUTUBRO DE 2004.</strong></p>
<p>Dispõe sobre a oferta e as formas de afixação de preços de produtos e
serviços para o consumidor.</p>
<p>Art. 1º Esta Lei regula a oferta e as formas de afixação de preços de
produtos e serviços para o consumidor.</p>
<p>Art. 2º São admitidas as seguintes formas de afixação de preços em vendas
a varejo para o consumidor:</p>
<p>I - no comércio em geral, por meio de etiquetas ou similares afixados
diretamente nos bens expostos à venda, e em vitrines, mediante divulgação do
preço à vista em caracteres legíveis;</p>
<p>II - em auto-serviços, supermercados, hipermercados, mercearias ou
estabelecimentos comerciais onde o consumidor tenha acesso direto ao produto,
mediante a impressão ou afixação do preço do produto na embalagem.</p>
<p><strike>§ 1º Nos casos de divergência de preços, prevalecerá o de menor
valor.</strike></p>
<p>§ 1º Nos casos de divergência de preços para o mesmo produto entre
sistemas de informação de preços diferentes, o consumidor pagará o menor
dentre eles. (Redação dada pela Lei nº 13.455, de 2017)</p>
<p>§ 2º (VETADO).</p>
<p>Art. 5º-A.&nbsp; O fornecedor deve informar, em local e formato visíveis ao
consumidor, eventuais descontos oferecidos em função do prazo ou do
instrumento de pagamento utilizado. (Incluído pela Lei nº 13.455, de 2017)</p>
<p>Parágrafo único. Aplicam-se às infrações a este artigo as sanções
previstas na Lei nº 8.078, de 11 de setembro de 1990. (Incluído pela Lei nº
13.455, de 2017)</p>
<p>Art. 6º Esta Lei entra em vigor na data de sua publicação.</p>
<p>Este texto não substitui o publicado no DOU de 13.10.2004</p>
</body></html>
"""


def _docs_meta():
    return [
        {
            "documentId": "lei10962-2004", "authority": "federal",
            "type": "lei_ordinaria", "number": "10962", "year": 2004,
            "dataPublicacao": "2004-10-13", "dataVigor": "2004-10-13",
        },
        {
            "documentId": "lei13455-2017", "authority": "federal",
            "type": "lei_ordinaria", "number": "13455", "year": 2017,
            "dataPublicacao": "2017-06-27", "dataVigor": "2017-06-27",
        },
    ]


# ── planalto_html_to_text ────────────────────────────────────────────────────

class TestPlanaltoHtmlToText:
    def test_um_dispositivo_por_linha(self):
        texto = planalto_html_to_text(HTML_LEI_13455)
        linhas = texto.splitlines()
        assert any(ln.startswith("Art. 1º") for ln in linhas)
        assert any(ln.startswith("Parágrafo único.") for ln in linhas)
        assert any(ln.startswith("Art. 3º") for ln in linhas)

    def test_remove_tachado(self):
        texto = planalto_html_to_text(HTML_LEI_10962)
        assert "prevalecerá o de menor" not in texto  # redação revogada (strike)
        assert "o consumidor pagará o menor" in texto  # redação vigente

    def test_remove_tachado_via_style(self):
        html = '<p><span style="text-decoration: line-through">antigo</span> novo</p>'
        assert planalto_html_to_text(html).strip() == "novo"

    def test_preserva_anotacoes_de_historico(self):
        texto = planalto_html_to_text(HTML_LEI_10962)
        assert "(Redação dada pela Lei nº 13.455, de 2017)" in texto
        assert "(Incluído pela Lei nº 13.455, de 2017)" in texto

    def test_filtra_ruido_do_site(self):
        texto = planalto_html_to_text(HTML_LEI_13455)
        assert "Presidência da República" not in texto
        assert "Este texto não substitui" not in texto
        assert "Brasília," not in texto

    def test_normaliza_nbsp_e_espacos(self):
        texto = planalto_html_to_text(HTML_LEI_13455)
        assert "\xa0" not in texto
        assert "  " not in texto


# ── Integração com a árvore canônica ─────────────────────────────────────────

class TestArvoreCanonicaDasLeis:
    def test_lei_13455_estrutura(self):
        texto = planalto_html_to_text(HTML_LEI_13455)
        docs = _docs_meta()
        norma = build_canonical_tree(
            "lei13455-2017", texto, docs[1], build_corpus_index(docs)
        )
        ids = [a.id_canonico for a in norma.dispositivos]
        assert ids == ["art1", "art2", "art3"]
        art1 = norma.dispositivos[0]
        assert art1.filhos[0].id_canonico == "art1_parun"
        assert "Fica autorizada a diferenciação de preços" in art1.texto_original

    def test_lei_10962_art_5a_incluido_pela_13455(self):
        texto = planalto_html_to_text(HTML_LEI_10962)
        docs = _docs_meta()
        norma = build_canonical_tree(
            "lei10962-2004", texto, docs[0], build_corpus_index(docs)
        )
        art5a = next(d for d in norma.dispositivos if d.id_canonico == "art55a" or d.numero == "5-A")
        # dispositivo incluído pela 13.455: evento resolvido contra o corpus
        ev = art5a.historico[0]
        assert ev.evento == "redacao_original"
        assert ev.norma_alteradora_doc_id == "lei13455-2017"
        assert ev.data_efeito == date(2017, 6, 27)
        assert ev.confiavel is True

    def test_lei_10962_incisos_do_art2(self):
        texto = planalto_html_to_text(HTML_LEI_10962)
        docs = _docs_meta()
        norma = build_canonical_tree(
            "lei10962-2004", texto, docs[0], build_corpus_index(docs)
        )
        art2 = next(d for d in norma.dispositivos if d.id_canonico == "art2")
        tipos = [f.tipo for f in art2.filhos]
        assert tipos.count("inciso") == 2
        # § 1º com redação dada pela 13.455 vira evento de alteração confiável
        par1 = next(f for f in art2.filhos if f.tipo == "paragrafo" and f.numero == "1")
        assert any(
            ev.evento == "alteracao" and ev.norma_alteradora_doc_id == "lei13455-2017"
            for ev in par1.historico
        )

    def test_vetado_vai_para_revisao(self):
        texto = planalto_html_to_text(HTML_LEI_10962)
        docs = _docs_meta()
        norma = build_canonical_tree(
            "lei10962-2004", texto, docs[0], build_corpus_index(docs)
        )
        assert any(i.motivo == "nao_interpretar" for i in norma.review_queue)


# ── extrair_lei (corpus em tmp_path, offline) ────────────────────────────────

class TestExtrairLei:
    def test_grava_parsed_e_registry(self, tmp_path):
        parsed = extrair_lei(
            doc_id="lei13455-2017", numero="13455", ano=2017,
            publicacao="2017-06-27", html=HTML_LEI_13455, corpus_dir=tmp_path,
        )
        assert parsed.exists()
        assert "Art. 1º" in parsed.read_text(encoding="utf-8")

        from pipeline.corpus_registry import load_registry
        registry = load_registry(tmp_path)
        meta = registry["lei13455-2017"]
        assert meta["type"] == "lei_ordinaria"
        assert meta["number"] == "13455"
        assert meta["year"] == 2017
        assert meta["authority"] == "federal"

    def test_texto_curto_falha(self, tmp_path):
        import pytest
        with pytest.raises(ValueError, match="muito curto"):
            extrair_lei(
                doc_id="x", numero="1", ano=2000, publicacao="2000-01-01",
                html="<p>oi</p>", corpus_dir=tmp_path,
            )

    def test_presets_sprint1(self):
        ids = {lei["doc_id"] for lei in LEIS_SPRINT1}
        assert ids == {"lei10962-2004", "lei13455-2017"}
        for lei in LEIS_SPRINT1:
            assert lei["url"].startswith("https://www.planalto.gov.br/")
