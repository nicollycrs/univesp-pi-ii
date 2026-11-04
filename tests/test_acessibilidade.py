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
        """
        Conta `<caption` sem o fecho porque a legenda do ranking leva um id: ela
        e reescrita pelo JavaScript quando um grupo da matriz esta selecionado,
        ja que a ordenacao muda.
        """
        html = (TEMPLATES / "painel.html").read_text(encoding="utf-8")
        assert html.count("<caption") >= html.count("<table")


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


class TestMetodologiaFielAoCodigo:
    """
    A pagina /sobre/ e a prestacao de contas do projeto. Se ela descrever um
    metodo que o codigo nao executa mais, o problema nao e cosmetico: e a
    aplicacao afirmando algo falso sobre si mesma.
    """

    def _html(self, client):
        resposta = client.get(reverse("sobre"))
        assert resposta.status_code == 200
        # O HTML quebra linha no meio das frases; normalizar o espaco em branco
        # deixa o teste olhar para o texto, e nao para a formatacao do template.
        return re.sub(r"\s+", " ", resposta.content.decode())

    def test_pesos_exibidos_batem_com_os_do_codigo(self, client, db):
        """
        A tabela de pesos e escrita a mao no template. Este teste existe para
        que ela nao fique para tras quando painel/risco.py mudar.
        """
        html = self._html(client)
        for componente, peso in risco.PESOS.items():
            exibido = f"{peso:.2f}".replace(".", ",")
            assert exibido in html, (
                f"O peso {exibido} do componente {componente!r} nao aparece em "
                "/sobre/. Atualize a tabela de painel/templates/painel/sobre.html."
            )

    def test_soma_dos_pesos_e_um(self):
        assert sum(risco.PESOS.values()) == pytest.approx(1.0)

    def test_as_duas_versoes_do_indice_sao_explicadas(self, client, db):
        """
        O painel deixa alternar entre o indice de regras e a previsao. As duas
        precisam estar descritas aqui, ou o seletor oferece uma escolha que a
        pessoa nao tem como entender.
        """
        html = self._html(client)
        assert "baseado em regras" in html.lower()
        assert "quartil superior de abandono" in html

    def test_limites_do_modelo_estao_declarados(self, client, db):
        html = self._html(client)
        assert "uma única transição futura" in html
        assert "posição relativa" in html

    def test_validacao_contra_o_ano_observado_e_declarada(self, client, db):
        """
        O modelo deixou de ser so promessa: as previsoes de 2025 foram
        confrontadas com o publicado. A pagina precisa trazer o numero medido,
        e nao apenas o da particao de teste, que e mais generoso.
        """
        html = self._html(client)
        assert "conferido contra a realidade" in html
        assert "19.889 escolas" in html
        assert "0,598" in html

    def test_substituicao_do_inse_e_declarada(self, client, db):
        """
        O componente socioeconomico nao e o INSE: e um proxy municipal do IBGE.
        A pagina precisa dizer isso com todas as letras, senao o painel deixa
        entender que usa um indicador por escola que ele nao usa.
        """
        html = self._html(client)
        assert "não é publicado de forma cruzável" in html
        assert "Máscaras dos Códigos de Escola" in html
        assert "salário médio mensal dos trabalhadores formais" in html.lower()

    def test_limite_de_granularidade_e_declarado(self, client, db):
        """
        A consequencia mais importante da troca: dentro de um mesmo municipio o
        componente nao diferencia escola nenhuma. Omitir isso seria vender uma
        precisao que o dado nao tem.
        """
        html = self._html(client)
        assert "Escolas do mesmo município recebem o mesmo valor" in html

    def test_componente_socioeconomico_nao_se_chama_inse(self, client, db):
        """
        O nome importa: chamar o proxy municipal de INSE seria atribuir ao
        projeto uma fonte que ele nao conseguiu usar.
        """
        html = self._html(client)
        linha = "Contexto socioeconômico do município"
        assert linha in html
        # O INSE so pode aparecer na pagina explicando por que NAO foi usado.
        assert "INSE, nível socioeconômico</th>" not in html


class TestReflow:
    """
    Criterio 1.4.10 Reflow, nivel AA: a pagina precisa ser usavel a 320 px sem
    rolagem horizontal.

    Estes testes travam um defeito real, encontrado em 19/10/2026 medindo a
    pagina renderizada. O <nav> do cabecalho e um item flexivel, e o tamanho
    minimo automatico de um item flexivel e a largura do seu conteudo. Com
    `justify-content: space-between` empurrando a navegacao para a direita, a
    lista nunca quebrava linha: transbordava a faixa, o <body> ficava mais largo
    que a janela, e TODA a pagina herdava rolagem horizontal, filtros e tabelas
    inclusive. O sintoma aparecia longe da causa, e por isso fica registrado.
    """

    def _css(self):
        return CSS.read_text(encoding="utf-8")

    def test_navegacao_do_cabecalho_pode_encolher(self):
        assert ".topo nav { min-width: 0; }" in self._css(), (
            "Sem min-width zero o <nav> nao encolhe, transborda a faixa e deixa "
            "a pagina inteira com rolagem horizontal."
        )

    def test_campos_do_formulario_podem_encolher(self):
        """
        Mesma armadilha nos filtros: base flexivel de varios rem sem min-width
        zero nao encolhe abaixo dela.
        """
        css = self._css()
        bloco = css[css.index(".campo {"):css.index(".campo {") + 400]
        assert "min-width: 0" in bloco
        assert "max-width: 100%" in bloco

    def test_select_tem_largura_declarada(self):
        """
        Um <select> sem largura se dimensiona pela opcao mais longa. A opcao
        "Previsão para o ano seguinte (modelo preditivo)" sozinha passa de
        320 px.
        """
        assert ".campo select { width: 100%; }" in self._css()

    def test_matriz_colapsa_em_uma_coluna(self):
        css = self._css()
        assert ".matriz { grid-template-columns: 1fr; }" in css
        assert ".matriz-cartao { grid-column: auto; grid-row: auto; }" in css

    def test_posicao_na_grade_nao_usa_estilo_inline(self):
        """
        O JavaScript posiciona os cartoes por variavel CSS, e nao por
        grid-column inline. Estilo inline vence media query, e a grade deixaria
        de colapsar em tela estreita.
        """
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(
            encoding="utf-8"
        )
        assert "style.gridColumn" not in js
        assert "style.gridRow" not in js
        assert 'setProperty("--col"' in js


class TestPaginaDaEscola:
    """
    Regressao de um defeito encontrado em 27/10/2026, depois que o modelo
    preditivo entrou.

    Cada escola passou a ter uma linha de indice POR VERSAO em cada ano: a do
    indice baseado em regras e a da previsao. A pagina da escola listava as duas
    sem distinguir, entao o mesmo ano aparecia duas vezes, com valores
    diferentes e nenhuma explicacao, enquanto a legenda afirmava que a tabela
    inteira era de uma versao so.
    """

    @pytest.fixture
    def escola_com_duas_leituras(self, escolas):
        from painel.models import IndiceRisco

        escola = escolas[0]
        for versao, score in (("regras-v1", 0.587), ("modelo-v1", 0.800)):
            IndiceRisco.objects.update_or_create(
                escola=escola, ano=2024, versao=versao,
                defaults={"score": score, "classe": "alto"},
            )
        return escola

    def _html(self, client, escola):
        resposta = client.get(f"/escola/{escola.pk}/")
        assert resposta.status_code == 200
        return re.sub(r"\s+", " ", resposta.content.decode())

    def test_historico_so_traz_anos_observados(self, client, db, escola_com_duas_leituras):
        """
        A tabela do historico e so da versao baseada em regras: e a unica que
        descreve um ano que de fato aconteceu.
        """
        html = self._html(client, escola_com_duas_leituras)
        assert "Trajetória observada" in html
        assert "0,587" in html  # indice de 2024
        # O numero da previsao nao pode aparecer dentro da tabela do historico.
        tabela = html[html.index("Trajetória observada"):html.index("<h2>Previsão")]
        assert "0,800" not in tabela

    def test_previsao_fica_em_secao_propria(self, client, db, escola_com_duas_leituras):
        """
        O defeito que motivou a separacao: previsao e historico na mesma tabela,
        na mesma coluna "Indice", em ordem nao cronologica.
        """
        html = self._html(client, escola_com_duas_leituras)
        assert "<h2>Previsão</h2>" in html
        assert "Para 2025" in html

    def test_previsao_e_apresentada_como_probabilidade(self, client, db, escola_com_duas_leituras):
        """
        O indice de regras e uma soma ponderada; o score do modelo e uma
        probabilidade. Exibir os dois como "Indice" sugeria que a escola tinha
        piorado de um numero para o outro.
        """
        html = self._html(client, escola_com_duas_leituras)
        assert "80%" in html
        assert "probabilidade estimada" in html

    def test_previsao_avisa_que_nao_e_comparavel(self, client, db, escola_com_duas_leituras):
        html = self._html(client, escola_com_duas_leituras)
        assert "Não é comparável ao índice da tabela acima" in html

    def test_previsao_diz_de_onde_veio(self, client, db, escola_com_duas_leituras):
        """O ano dos indicadores que geraram a previsao precisa estar visivel."""
        html = self._html(client, escola_com_duas_leituras)
        assert "a partir dos indicadores de 2024" in html

    def test_escola_sem_previsao_nao_quebra(self, client, db, escolas):
        from painel.models import IndiceRisco

        escola = escolas[0]
        IndiceRisco.objects.create(
            escola=escola, ano=2024, versao="regras-v1", score=0.5, classe="medio"
        )
        html = self._html(client, escola)
        assert "não recebeu previsão" in html


class TestExplicabilidadeNaPagina:
    """
    A pagina da escola mostra POR QUE o indice e a previsao deram o que deram.

    O risco que estes testes cobrem nao e visual: e a explicacao deixar de
    corresponder ao calculo. Uma explicacao plausivel e errada e pior que
    nenhuma, porque induz decisao com falsa confianca.
    """

    @pytest.fixture
    def escola_explicada(self, escolas):
        from painel.models import IndiceRisco

        escola = escolas[2]
        IndiceRisco.objects.update_or_create(
            escola=escola, ano=2024, versao="regras-v1",
            defaults={
                "score": 0.8, "classe": "alto",
                "detalhes": {
                    "metodo": "soma_ponderada",
                    "parcelas": [
                        {"componente": "taxa_abandono", "valor": 25.0,
                         "normalizado": 1.0, "peso": 0.40, "peso_efetivo": 0.40,
                         "contribuicao": 0.40, "invertido": False},
                        {"componente": "contexto_socioeconomico", "valor": 1.5,
                         "normalizado": 0.8, "peso": 0.15, "peso_efetivo": 0.15,
                         "contribuicao": 0.12, "invertido": True},
                    ],
                },
            },
        )
        IndiceRisco.objects.update_or_create(
            escola=escola, ano=2024, versao="modelo-v1",
            defaults={
                "score": 0.43, "classe": "alto",
                "detalhes": {
                    "metodo": "contribuicoes",
                    "modelo": "Floresta aleatória",
                    "base": 0.50,
                    "contribuicoes": [
                        {"atributo": "taxa_abandono", "valor": 0.0,
                         "contribuicao": -0.11},
                        {"atributo": "distorcao_idade_serie", "valor": 24.0,
                         "contribuicao": 0.05},
                    ],
                },
            },
        )
        return escola

    def _html(self, client, escola):
        resposta = client.get(f"/escola/{escola.pk}/")
        assert resposta.status_code == 200
        return re.sub(r"\s+", " ", resposta.content.decode())

    def test_mostra_as_parcelas_do_indice(self, client, db, escola_explicada):
        html = self._html(client, escola_explicada)
        assert "Como este índice foi calculado" in html
        assert "Taxa de abandono" in html
        assert "Contexto socioeconômico do município" in html

    def test_marca_o_componente_invertido(self, client, db, escola_explicada):
        """
        Sem a marca, um município mais rico com posição baixa parece erro de
        cálculo para quem lê a tabela.
        """
        html = self._html(client, escola_explicada)
        assert "(invertido)" in html

    def test_explica_a_previsao_por_atributo(self, client, db, escola_explicada):
        html = self._html(client, escola_explicada)
        assert "Por que esta previsão" in html
        assert "reduz o risco previsto" in html
        assert "aumenta o risco previsto" in html

    def test_mostra_o_ponto_de_partida_do_modelo(self, client, db, escola_explicada):
        """
        Sem a base, a explicação se contradiz: o maior fator pode REDUZIR o
        risco e a escola ainda sair como risco alto.
        """
        html = self._html(client, escola_explicada)
        assert "O modelo parte de" in html
        assert "50%" in html

    def test_avisa_que_a_classe_vem_de_tercis(self, client, db, escola_explicada):
        """43% caindo em "risco alto" precisa de explicação, ou parece defeito."""
        html = self._html(client, escola_explicada)
        assert "não vem de um limiar fixo de probabilidade" in html

    def test_sentido_nao_depende_so_da_cor(self, client, db, escola_explicada):
        """
        Criterio 1.4.1: a barra colorida e redundante. "aumenta" e "reduz"
        aparecem escritos, junto da porcentagem.
        """
        html = self._html(client, escola_explicada)
        import re as _re
        assert _re.search(r"Responde por \d+% do que moveu", html)


class TestOrdemDoPainel:
    """
    A pagina responde a duas perguntas, nesta ordem: ONDE agir e QUEM.

    Antes a sequencia era introducao, filtros, matriz, resumo, dois graficos e
    so entao o ranking, somando 4.200 px: quem precisava agir rolava quatro
    telas ate a lista de escolas. Estes testes travam a ordem.
    """

    def _html(self, client):
        resposta = client.get("/")
        assert resposta.status_code == 200
        return resposta.content.decode()

    def test_matriz_vem_antes_do_ranking(self, client, db, escolas):
        html = self._html(client)
        assert html.index("titulo-matriz") < html.index("titulo-ranking")

    def test_ranking_vem_antes_do_contexto(self, client, db, escolas):
        """Resumo e grafico sao contexto: nao podem empurrar o ranking."""
        html = self._html(client)
        assert html.index("titulo-ranking") < html.index('class="panorama"')

    def test_contexto_comeca_recolhido(self, client, db, escolas):
        html = self._html(client)
        bloco = html[html.index('<details class="panorama">') :][:200]
        assert "open" not in bloco

    def test_grafico_de_barras_por_classe_foi_removido(self, client, db, escolas):
        """
        A classificacao e por tercis dentro de (UF, ano), entao os tres grupos
        tem o mesmo tamanho por construcao e o grafico nao informava nada.
        Removido, nao escondido: o codigo morto tambem saiu do JavaScript.
        """
        html = self._html(client)
        assert "g-classes" not in html
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(
            encoding="utf-8"
        )
        assert "desenharClasses" not in js
        assert "graficoClasses" not in js

    def test_grafico_dentro_do_recolhido_e_redesenhado(self):
        """
        Chart.js dimensiona o canvas pelo container. Dentro de um <details>
        fechado o container tem tamanho zero, e o grafico sairia vazio e assim
        ficaria depois de aberto.
        """
        js = (RAIZ / "painel" / "static" / "painel" / "painel.js").read_text(
            encoding="utf-8"
        )
        assert 'addEventListener("toggle"' in js


class TestIdentidadeVisual:
    """
    A marca tem os mesmos deveres do resto da interface: cor vinda da paleta
    validada, nome legivel por leitor de tela, icone servido de verdade.
    """

    MARCA = RAIZ / "painel" / "static" / "painel" / "marca.svg"
    ICONE = RAIZ / "painel" / "static" / "painel" / "favicon.png"

    def test_arquivos_da_marca_existem(self):
        assert self.MARCA.exists(), "marca.svg ausente"
        assert self.ICONE.exists(), "favicon.png ausente"

    def test_cor_da_marca_vem_da_paleta(self):
        """
        O SVG tem hexadecimal literal, porque arquivo de icone nao enxerga as
        variaveis do CSS. Se divergir da paleta, a marca passa a usar uma cor
        que ninguem validou.
        """
        svg = self.MARCA.read_text(encoding="utf-8").upper()
        usadas = set(re.findall(r"#[0-9A-F]{6}\b", svg))
        fora = usadas - cores.todos_os_hex()
        assert not fora, f"Cores no marca.svg fora da paleta: {sorted(fora)}"

    def test_azul_da_marca_contrasta_com_o_branco_do_simbolo(self):
        """
        O traco e branco sobre o quadrado azul. E elemento grafico: minimo 3:1
        pelo criterio 1.4.11.
        """
        razao = cores.contraste(cores.LINK, cores.BRANCO)
        assert razao >= cores.CONTRASTE_MINIMO_GRAFICO

    def test_pagina_declara_o_icone(self, client, db):
        html = client.get("/").content.decode()
        assert 'rel="icon"' in html
        assert "marca.svg" in html
        assert "favicon.png" in html

    def test_simbolo_nao_e_anunciado_duas_vezes(self, client, db):
        """
        O SVG embutido fica com aria-hidden: o nome ao lado ja identifica o
        produto, e anunciar os dois seria repeticao no leitor de tela.
        """
        html = re.sub(r"\s+", " ", client.get("/").content.decode())
        i = html.index('class="marca-simbolo"')
        assert 'aria-hidden="true"' in html[i : i + 200]

    def test_nome_continua_em_texto(self, client, db):
        """
        A marca e texto com um simbolo ao lado, nunca uma imagem do nome: assim
        ela e selecionavel, aumenta com o zoom e e lida por leitor de tela.
        """
        html = re.sub(r"\s+", " ", client.get("/").content.decode())
        assert "<span>Educa</span><strong>Alerta</strong>" in html
