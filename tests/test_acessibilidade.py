"""
Testes automatizados de acessibilidade.

Nao substituem o teste manual com leitor de tela, previsto para a Quinzena 6, mas
travam as regressoes que mais acontecem: alguem trocar uma cor e quebrar o
contraste, ou o CSS divergir da paleta validada.

Criterios cobertos aqui: 1.4.1, 1.4.3, 1.4.11, 3.1.1, 1.1.1 e 2.4.1.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from painel import cores, risco

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "painel" / "static" / "painel" / "painel.css"
TEMPLATES = RAIZ / "painel" / "templates" / "painel"


class TestContraste:
    """Criterios 1.4.3 (texto, 4,5:1) e 1.4.11 (nao textual, 3:1), nivel AA."""

    @pytest.mark.parametrize("classe", list(cores.TARJAS))
    def test_tarja_atinge_contraste_de_texto(self, classe):
        par = cores.TARJAS[classe]
        razao = cores.contraste(par["texto"], par["fundo"])
        assert razao >= cores.CONTRASTE_MINIMO_TEXTO, (
            f"A tarja {classe} tem contraste {razao:.2f}:1, abaixo do minimo "
            f"{cores.CONTRASTE_MINIMO_TEXTO}:1 exigido pelo nivel AA."
        )

    @pytest.mark.parametrize("nome", list(cores.GRAFICO))
    def test_cor_de_grafico_atinge_contraste_nao_textual(self, nome):
        razao = cores.contraste(cores.GRAFICO[nome], cores.BRANCO)
        assert razao >= cores.CONTRASTE_MINIMO_GRAFICO, (
            f"A cor de grafico {nome} tem contraste {razao:.2f}:1 contra o branco, "
            f"abaixo do minimo {cores.CONTRASTE_MINIMO_GRAFICO}:1."
        )

    @pytest.mark.parametrize(
        "nome,cor",
        [("texto", cores.TEXTO), ("secundario", cores.TEXTO_SECUNDARIO),
         ("link", cores.LINK), ("foco", cores.FOCO)],
    )
    def test_texto_de_interface_atinge_contraste(self, nome, cor):
        razao = cores.contraste(cor, cores.BRANCO)
        assert razao >= cores.CONTRASTE_MINIMO_TEXTO, f"{nome}: {razao:.2f}:1"

    def test_borda_atinge_contraste_nao_textual(self):
        assert cores.contraste(cores.BORDA, cores.BRANCO) >= cores.CONTRASTE_MINIMO_GRAFICO

    def test_calculo_de_contraste_confere_com_valores_conhecidos(self):
        """Ancora a formula: preto sobre branco e 21:1, cor sobre si mesma e 1:1."""
        assert cores.contraste("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
        assert cores.contraste("#777777", "#777777") == pytest.approx(1.0, abs=0.01)


class TestCssSincronizadoComAPaleta:
    """
    O CSS repete os hexadecimais de painel/cores.py. Se divergirem, a cor exibida
    deixa de ser a cor validada, e o teste de contraste passaria a medir outra
    coisa. Este teste impede a divergencia.
    """

    def test_css_existe(self):
        assert CSS.exists()

    @pytest.mark.parametrize("hexcor", sorted(cores.todos_os_hex()))
    def test_cada_cor_da_paleta_aparece_no_css(self, hexcor):
        conteudo = CSS.read_text(encoding="utf-8").upper()
        assert hexcor in conteudo, (
            f"{hexcor} esta em painel/cores.py mas nao no CSS. "
            "A paleta e o CSS precisam usar os mesmos valores."
        )

    def test_css_nao_tem_cor_fora_da_paleta(self):
        conteudo = CSS.read_text(encoding="utf-8").upper()
        encontradas = set(re.findall(r"#[0-9A-F]{6}\b", conteudo))
        fora = encontradas - cores.todos_os_hex()
        assert not fora, f"Cores no CSS que nao estao na paleta validada: {sorted(fora)}"

    def test_css_declara_foco_visivel(self):
        """Criterio 2.4.7 Foco Visivel, nivel AA."""
        conteudo = CSS.read_text(encoding="utf-8")
        assert "focus-visible" in conteudo
        assert "outline" in conteudo


class TestTemplates:
    def test_base_declara_idioma_portugues(self):
        """Criterio 3.1.1 Idioma da Pagina, nivel A."""
        html = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        assert "<html lang=" in html
        assert "pt-br" in html

    def test_base_tem_link_de_pulo(self):
        """Criterio 2.4.1 Ignorar Blocos, nivel A."""
        html = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        assert 'class="pular"' in html
        assert 'href="#conteudo"' in html

    def test_base_tem_marcos_semanticos(self):
        html = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        for marco in ("<header", "<nav", "<main", "<footer"):
            assert marco in html

    def test_cada_grafico_tem_tabela_equivalente(self):
        """
        Criterio 1.1.1 Conteudo Nao Textual, nivel A. Cada canvas precisa de uma
        alternativa textual, e a adotada no projeto e a tabela com os mesmos dados.
        """
        html = (TEMPLATES / "painel.html").read_text(encoding="utf-8")
        canvas = html.count("<canvas")
        tabelas_alternativas = html.count("Ver os dados do gráfico em tabela")
        assert canvas > 0
        assert tabelas_alternativas == canvas, (
            f"{canvas} graficos, mas {tabelas_alternativas} tabelas alternativas."
        )

    def test_canvas_tem_rotulo_acessivel(self):
        html = (TEMPLATES / "painel.html").read_text(encoding="utf-8")
        for bloco in re.findall(r"<canvas[^>]*>", html):
            assert 'role="img"' in bloco, bloco
            assert "aria-labelledby=" in bloco, bloco

    def test_todo_select_tem_label(self):
        html = (TEMPLATES / "painel.html").read_text(encoding="utf-8")
        ids_select = set(re.findall(r'<select[^>]*id="([^"]+)"', html))
        ids_label = set(re.findall(r'<label[^>]*for="([^"]+)"', html))
        assert ids_select <= ids_label, f"Selects sem label: {ids_select - ids_label}"

    def test_tabelas_tem_cabecalho_com_escopo(self):
        html = (TEMPLATES / "painel.html").read_text(encoding="utf-8")
        assert 'scope="col"' in html

    def test_tabelas_tem_caption(self):
        html = (TEMPLATES / "painel.html").read_text(encoding="utf-8")
        assert html.count("<caption>") >= html.count("<table")


class TestUsoDaCor:
    """
    Criterio 1.4.1 Uso da Cor, nivel A. E o criterio mais importante deste
    projeto: um painel de risco que use so vermelho, amarelo e verde exclui quem
    nao distingue essas cores.
    """

    def test_javascript_escreve_o_rotulo_dentro_da_tarja(self):
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(encoding="utf-8")
        assert "span.textContent = r.rotulo" in js, (
            "O JavaScript precisa escrever o rotulo textual na tarja de risco, "
            "senao o nivel passaria a depender apenas da cor."
        )

    def test_api_devolve_rotulo_textual_junto_da_classe(self, db, escolas):
        from painel.models import IndiceRisco

        IndiceRisco.objects.create(
            escola=escolas[0], ano=2024, score=0.9,
            classe=risco.CLASSE_ALTO, versao=risco.VERSAO,
        )
        from rest_framework.test import APIClient

        resposta = APIClient().get("/api/risco/")
        item = resposta.json()["results"][0]
        assert item["rotulo"] == "Risco alto"

    def test_pagina_renderizada_traz_texto_do_nivel(self, client, db, escolas):
        from painel.models import IndiceRisco

        IndiceRisco.objects.create(
            escola=escolas[2], ano=2024, score=0.95,
            classe=risco.CLASSE_ALTO, versao=risco.VERSAO,
        )
        resposta = client.get(reverse("escola-detalhe", args=[escolas[2].pk]))
        assert "Risco alto" in resposta.content.decode()


class TestEstadoSemDados:
    """
    Um grafico vazio nao pode ficar como canvas em branco: com role="img" o leitor
    de tela anunciaria uma imagem que nao informa nada, e para quem ve parece
    defeito. Acontece de verdade neste projeto enquanto o INSE do INEP nao esta
    carregado.
    """

    def test_javascript_trata_serie_vazia(self):
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(encoding="utf-8")
        assert "marcarSemDados" in js
        assert "canvas.hidden = true" in js

    def test_javascript_explica_o_motivo_do_grafico_vazio(self):
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(encoding="utf-8")
        assert "INSE" in js and "indisponível" in js

    def test_tabela_alternativa_tambem_diz_que_esta_vazia(self):
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(encoding="utf-8")
        assert "Sem dados" in js

    def test_nao_exibe_sem_dado_com_simbolo_de_porcentagem(self):
        """A funcao porcentagem() existe para nao renderizar 'sem dado%'."""
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(encoding="utf-8")
        assert "function porcentagem" in js
        assert 'numero(a.distorcao_media) + "%"' not in js

    def test_api_devolve_nulo_quando_indicador_nao_existe(self, api_client_db):
        """
        Com indicadores parciais, o resumo precisa devolver null em vez de zero.
        Zero seria uma afirmacao falsa: significaria distorcao nula, e nao ausente.
        """
        from painel.models import Escola, IndicadorAnual

        escola = Escola.objects.create(
            co_entidade=42, nome="Escola Parcial", uf="SP", rede=Escola.Rede.ESTADUAL
        )
        IndicadorAnual.objects.create(
            escola=escola, ano=2024, taxa_abandono=5.0, taxa_reprovacao=3.0,
            distorcao_idade_serie=None, inse=None,
        )
        dados = api_client_db.get("/api/indicadores/resumo/").json()
        assert dados["agregados"]["abandono_medio"] == 5.0
        assert dados["agregados"]["distorcao_media"] is None
        assert dados["agregados"]["inse_medio"] is None


class TestEstaticosProntosParaDeploy:
    """
    Regressao de um erro que so aparecia no deploy, encontrado em 28/09/2026.

    O CompressedManifestStaticFilesStorage reescreve referencias dentro dos
    arquivos estaticos no collectstatic. O Chart.js minificado trazia
    `//# sourceMappingURL=chart.umd.js.map`, um arquivo que nao foi distribuido.
    O collectstatic nao conseguia resolver a referencia e saia com codigo 1. Como
    o build.sh usa `set -o errexit`, isso abortava o deploy no Render.

    Em desenvolvimento nada falhava, porque ali o storage simples e usado.
    """

    def _arquivos_estaticos(self, sufixos=(".js", ".css")):
        base = RAIZ / "painel" / "static"
        return [p for p in base.rglob("*") if p.suffix in sufixos]

    def test_nenhum_estatico_referencia_sourcemap_ausente(self):
        problemas = []
        for arquivo in self._arquivos_estaticos():
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
            for referencia in re.findall(
                r"sourceMappingURL=(\S+)", texto
            ):
                if referencia.startswith("data:"):
                    continue  # sourcemap embutido, nao ha arquivo a resolver
                if not (arquivo.parent / referencia).exists():
                    problemas.append(f"{arquivo.name} aponta para {referencia}, que nao existe")
        assert not problemas, (
            "Referencia de sourcemap sem arquivo correspondente faz o "
            "collectstatic falhar e aborta o deploy: " + "; ".join(problemas)
        )

    def test_chartjs_esta_vendorizado_e_nao_em_cdn(self):
        """
        O Chart.js precisa estar no repositorio. Em CDN, uma falha de rede durante
        a avaliacao deixaria o painel sem graficos.
        """
        vendor = RAIZ / "painel" / "static" / "painel" / "vendor" / "chart.umd.min.js"
        assert vendor.exists()
        assert vendor.stat().st_size > 100_000

        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        assert "vendor/chart.umd.min.js" in base
        assert "cdn." not in base and "unpkg" not in base


class TestRenderizacaoLimpa:
    """
    Regressao de um erro que chegou a producao em 29/09/2026.

    Comentario de template do Django, `{# ... #}`, so funciona em UMA linha.
    Escrito em duas, o Django nao o reconhece e imprime o texto na pagina. Cinco
    comentarios de acessibilidade apareciam como texto no topo do painel, no ar.

    Os testes anteriores liam o codigo-fonte dos templates e por isso nao viam
    nada de errado. Este renderiza de verdade e confere a saida, que e o unico
    lugar onde esse defeito aparece.
    """

    ROTAS = ["/", "/sobre/"]

    def _render(self, client, rota):
        resposta = client.get(rota)
        assert resposta.status_code == 200, f"{rota} respondeu {resposta.status_code}"
        return resposta.content.decode()

    @pytest.mark.parametrize("rota", ROTAS)
    def test_nenhuma_sintaxe_de_template_vaza_para_a_pagina(self, client, db, escolas, rota):
        html = self._render(client, rota)
        vazamentos = [
            marca
            for marca in ("{#", "#}", "{% comment %}", "{% endcomment %}", "{% if", "{% for", "{{ ")
            if marca in html
        ]
        assert not vazamentos, (
            f"Sintaxe de template apareceu no HTML renderizado de {rota}: {vazamentos}. "
            "Comentario {# #} do Django so vale em uma linha; use {% comment %} para varias."
        )

    def test_detalhe_da_escola_tambem_renderiza_limpo(self, client, db, escolas):
        html = self._render(client, f"/escola/{escolas[0].pk}/")
        assert "{#" not in html and "{%" not in html

    @pytest.mark.parametrize("rota", ROTAS)
    def test_pagina_nao_mostra_texto_de_comentario_de_codigo(self, client, db, escolas, rota):
        """
        Os comentarios do projeto explicam criterios da WCAG. Se algum vazar, o
        texto tecnico aparece para o usuario final.
        """
        html = self._render(client, rota)
        for frase in ("criterio 3.1.1", "Link de pulo:", "Regiao de status", "Aviso deliberado"):
            assert frase not in html, f"Texto de comentario visivel em {rota}: {frase!r}"
