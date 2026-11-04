"""Testes da API REST propria e das paginas do painel."""

import pytest
from rest_framework.test import APIClient

from painel import risco
from painel.api import EIXOS_DISPERSAO
from painel.models import IndicadorAnual, IndiceRisco


def matriz_de_eixos():
    """Eixos validos do grafico de dispersao, lidos da propria API."""
    return set(EIXOS_DISPERSAO)


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def com_riscos(db, escolas):
    """Riscos calculados de verdade, pelo modulo de risco, e nao valores fixos."""
    from painel.models import IndicadorAnual

    registros = [
        {
            "co_entidade": i.escola_id,
            "uf": i.escola.uf,
            "ano": i.ano,
            "taxa_abandono": i.taxa_abandono,
            "taxa_reprovacao": i.taxa_reprovacao,
            "distorcao_idade_serie": i.distorcao_idade_serie,
            "inse": i.inse,
        }
        for i in IndicadorAnual.objects.select_related("escola")
    ]
    for r in risco.calcular(registros):
        if r["score"] is not None:
            IndiceRisco.objects.create(
                escola_id=r["co_entidade"], ano=r["ano"],
                score=r["score"], classe=r["classe"], versao=r["versao"],
            )
    return IndiceRisco.objects.all()


class TestEscolas:
    def test_lista_responde(self, api, escolas):
        resposta = api.get("/api/escolas/")
        assert resposta.status_code == 200
        assert resposta.json()["count"] == 3

    def test_filtra_por_uf(self, api, escolas):
        assert api.get("/api/escolas/?uf=SP").json()["count"] == 3
        assert api.get("/api/escolas/?uf=BA").json()["count"] == 0

    def test_filtra_por_rede(self, api, escolas):
        assert api.get("/api/escolas/?rede=estadual").json()["count"] == 3
        assert api.get("/api/escolas/?rede=privada").json()["count"] == 0

    def test_busca_por_nome(self, api, escolas):
        dados = api.get("/api/escolas/?search=Critica").json()
        assert dados["count"] == 1
        assert "Critica" in dados["results"][0]["nome"]

    def test_detalhe_traz_serie_historica(self, api, escolas):
        dados = api.get(f"/api/escolas/{escolas[0].pk}/").json()
        assert dados["co_entidade"] == escolas[0].pk
        assert len(dados["indicadores"]) == 1
        assert dados["indicadores"][0]["ano"] == 2024

    def test_detalhe_inexistente_da_404(self, api, db):
        assert api.get("/api/escolas/99999999/").status_code == 404


class TestRisco:
    def test_ranking_ordena_do_maior_para_o_menor(self, api, com_riscos):
        scores = [r["score"] for r in api.get("/api/risco/").json()["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_escola_critica_aparece_primeiro(self, api, com_riscos, escolas):
        primeiro = api.get("/api/risco/").json()["results"][0]
        assert primeiro["escola_nome"] == "Escola Critica"

    def test_cada_item_traz_rotulo_textual(self, api, com_riscos):
        for item in api.get("/api/risco/").json()["results"]:
            assert item["rotulo"] in ("Risco alto", "Risco médio", "Risco baixo")

    def test_filtra_por_classe(self, api, com_riscos):
        dados = api.get("/api/risco/?classe=alto").json()
        assert all(i["classe"] == "alto" for i in dados["results"])

    def test_filtra_por_uf_da_escola(self, api, com_riscos):
        assert api.get("/api/risco/?escola__uf=SP").json()["count"] == 3
        assert api.get("/api/risco/?escola__uf=BA").json()["count"] == 0


class TestResumo:
    def test_responde_com_agregados(self, api, com_riscos):
        dados = api.get("/api/indicadores/resumo/").json()
        assert dados["agregados"]["escolas"] == 3
        assert dados["agregados"]["abandono_medio"] == pytest.approx(14.0, abs=0.01)

    def test_traz_distribuicao_por_classe_com_rotulo(self, api, com_riscos):
        dados = api.get("/api/indicadores/resumo/").json()
        classes = {i["classe"] for i in dados["risco_por_classe"]}
        assert classes == {"alto", "medio", "baixo"}
        for item in dados["risco_por_classe"]:
            assert item["rotulo"].startswith("Risco ")

    def test_sinaliza_ausencia_de_amostra(self, api, com_riscos):
        assert api.get("/api/indicadores/resumo/").json()["contem_dados_de_amostra"] is False

    def test_sinaliza_presenca_de_amostra(self, api, escolas):
        from painel.models import IndicadorAnual

        IndicadorAnual.objects.update(origem=IndicadorAnual.Origem.AMOSTRA)
        assert api.get("/api/indicadores/resumo/").json()["contem_dados_de_amostra"] is True

    def test_filtro_por_uf_sem_dados_nao_quebra(self, api, com_riscos):
        dados = api.get("/api/indicadores/resumo/?uf=RR").json()
        assert dados["agregados"]["escolas"] == 0

    def test_informa_versao_do_indice(self, api, com_riscos):
        assert api.get("/api/indicadores/resumo/").json()["versao_indice"] == risco.VERSAO


class TestDispersao:
    def test_devolve_pares_de_inse_e_abandono(self, api, escolas):
        dados = api.get("/api/indicadores/dispersao/").json()
        assert dados["total"] == 3
        for ponto in dados["pontos"]:
            assert ponto["inse"] is not None
            assert ponto["taxa_abandono"] is not None

    def test_respeita_o_limite(self, api, escolas):
        assert api.get("/api/indicadores/dispersao/?limite=2").json()["total"] == 2

    def test_eixo_padrao_e_o_contexto_socioeconomico(self, api, escolas):
        """
        Contexto socioeconomico e a relacao que a literatura aponta, logo tem a
        preferencia. Vem do municipio, porque o INSE por escola do INEP nao e
        publicado de forma cruzavel.
        """
        dados = api.get("/api/indicadores/dispersao/").json()
        assert dados["eixo"] == "contexto"
        assert dados["pontos"][0]["x"] == dados["pontos"][0]["contexto_socioeconomico"]

    def test_sem_contexto_cai_para_a_distorcao_idade_serie(self, api, escolas, municipio):
        """
        Sem essa troca automatica o grafico ficaria vazio sempre que faltasse o
        indicador preferido, que foi o que aconteceu enquanto so havia o INSE.
        """
        municipio.salario_medio = None
        municipio.save(update_fields=["salario_medio"])
        dados = api.get("/api/indicadores/dispersao/").json()

        assert dados["eixo"] == "distorcao"
        assert dados["total"] == 3
        for ponto in dados["pontos"]:
            assert ponto["x"] == ponto["distorcao_idade_serie"]

    def test_rotulo_do_eixo_acompanha_o_indicador(self, api, escolas):
        """
        O painel escreve titulo e cabecalho a partir deste rotulo. Se ele nao
        vier, a pagina descreveria um grafico diferente do que esta na tela.
        """
        dados = api.get("/api/indicadores/dispersao/").json()
        assert "Salário médio" in dados["rotulo_eixo"]
        assert dados["unidade_eixo"] == "salários mínimos"

        api.get("/api/indicadores/dispersao/?eixo=distorcao")
        dados = api.get("/api/indicadores/dispersao/?eixo=distorcao").json()
        assert "Distorção" in dados["rotulo_eixo"]
        # A unidade vem separada: o titulo da secao nao a usa, o eixo sim.
        assert "%" not in dados["rotulo_eixo"]
        assert dados["unidade_eixo"] == "%"

    def test_eixo_pode_ser_pedido_explicitamente(self, api, escolas):
        dados = api.get("/api/indicadores/dispersao/?eixo=distorcao").json()
        assert dados["eixo"] == "distorcao"
        assert dados["pontos"][0]["x"] == dados["pontos"][0]["distorcao_idade_serie"]

    def test_eixo_invalido_cai_no_automatico(self, api, escolas):
        dados = api.get("/api/indicadores/dispersao/?eixo=inventado").json()
        assert dados["eixo"] in matriz_de_eixos()

    def test_lista_os_eixos_com_dados(self, api, escolas, municipio):
        assert {e["valor"] for e in api.get(
            "/api/indicadores/dispersao/"
        ).json()["eixos_disponiveis"]} == {"contexto", "distorcao", "inse"}

        municipio.salario_medio = None
        municipio.save(update_fields=["salario_medio"])
        IndicadorAnual.objects.update(inse=None)
        assert [e["valor"] for e in api.get(
            "/api/indicadores/dispersao/"
        ).json()["eixos_disponiveis"]] == ["distorcao"]

    def test_sem_nenhum_indicador_devolve_vazio_sem_quebrar(self, api, escolas, municipio):
        municipio.salario_medio = None
        municipio.save(update_fields=["salario_medio"])
        IndicadorAnual.objects.update(inse=None, distorcao_idade_serie=None)
        dados = api.get("/api/indicadores/dispersao/").json()
        assert dados["total"] == 0
        assert dados["pontos"] == []
        assert dados["eixos_disponiveis"] == []


class TestMunicipios:
    def test_lista_do_cache(self, api, municipio):
        dados = api.get("/api/municipios/").json()
        assert dados["count"] == 1
        assert dados["results"][0]["nome"] == "São Paulo"


class TestPaginas:
    def test_painel_responde(self, client, escolas):
        resposta = client.get("/")
        assert resposta.status_code == 200
        assert "EducaAlerta" in resposta.content.decode()

    def test_painel_sem_dados_orienta_o_proximo_passo(self, client, db):
        conteudo = client.get("/").content.decode()
        assert "Nenhum dado carregado" in conteudo
        assert "carregar_dados" in conteudo

    def test_painel_avisa_quando_ha_amostra(self, client, escolas):
        from painel.models import IndicadorAnual

        IndicadorAnual.objects.update(origem=IndicadorAnual.Origem.AMOSTRA)
        conteudo = client.get("/").content.decode()
        assert "dados de amostra" in conteudo

    def test_metodologia_declara_os_pesos(self, client, db):
        conteudo = client.get("/sobre/").content.decode()
        assert "0,40" in conteudo
        assert "Bowers" in conteudo
        assert "Soares" in conteudo

    def test_metodologia_declara_os_limites(self, client, db):
        conteudo = client.get("/sobre/").content.decode()
        assert "escolha do grupo" in conteudo

    def test_saude_responde_json(self, client, escolas):
        dados = client.get("/saude/").json()
        assert dados["status"] == "ok"
        assert dados["escolas"] == 3
        assert dados["versao_indice"] == risco.VERSAO

    def test_detalhe_da_escola(self, client, escolas):
        resposta = client.get(f"/escola/{escolas[0].pk}/")
        assert resposta.status_code == 200
        assert escolas[0].nome in resposta.content.decode()


class TestOpcoesDosFiltros:
    """
    Regressao de um defeito encontrado em 19/10/2026, visivel em producao.

    Os modelos declaram ordenacao padrao no Meta. O Django inclui os campos de
    ordenacao no SELECT quando ha distinct(), de modo que
    `Escola.objects.values_list("uf").distinct()` passava a aplicar DISTINCT
    sobre o par (uf, nome): o seletor de UF recebia uma opcao por escola, 19.776
    em vez de 27, e o de ano 38.925 em vez de 2. A pagina chegou a 2,9 MB.

    A correcao e chamar order_by() sem argumentos antes de distinct().
    """

    def test_uf_sem_repeticao(self, client, db, escolas):
        contexto = client.get("/").context
        assert contexto["ufs"] == sorted(set(contexto["ufs"]))
        assert len(contexto["ufs"]) == 1  # a fixture cria tres escolas, todas em SP

    def test_ano_sem_repeticao(self, client, db, escolas):
        contexto = client.get("/").context
        assert contexto["anos"] == sorted(set(contexto["anos"]), reverse=True)
        assert len(contexto["anos"]) == 1  # a fixture usa apenas 2024

    def test_varias_escolas_na_mesma_uf_geram_uma_opcao(self, client, db, municipio):
        """O caso que produzia a repeticao: muitas escolas, poucas UFs."""
        from painel.models import Escola, IndicadorAnual

        for i in range(12):
            e = Escola.objects.create(
                co_entidade=9000 + i, nome=f"Escola {i}", uf="BA",
                municipio=municipio, rede=Escola.Rede.ESTADUAL,
            )
            IndicadorAnual.objects.create(escola=e, ano=2023, taxa_abandono=5.0)

        contexto = client.get("/").context
        assert contexto["ufs"].count("BA") == 1
        assert contexto["anos"].count(2023) == 1

    def test_pagina_nao_fica_gigante(self, client, db, municipio):
        """
        Guarda de tamanho. Com a repeticao, a pagina crescia linearmente com o
        numero de escolas; sem ela, o tamanho independe da base.
        """
        from painel.models import Escola, IndicadorAnual

        for i in range(60):
            e = Escola.objects.create(
                co_entidade=8000 + i, nome=f"Escola {i}", uf="MG",
                municipio=municipio, rede=Escola.Rede.ESTADUAL,
            )
            IndicadorAnual.objects.create(escola=e, ano=2024, taxa_abandono=5.0)

        html = client.get("/").content.decode()
        assert html.count("<option") < 20, (
            f"{html.count('<option')} opcoes para 60 escolas em 1 UF e 1 ano. "
            "Provavel regressao do distinct() com ordenacao padrao."
        )


class TestVersoesDoIndice:
    """
    O painel oferece duas leituras do risco. A ordem em que aparecem e
    deliberada: o indice descritivo primeiro, porque e a leitura mais direta e e
    o padrao; a previsao depois, como opcao. Ordem alfabetica inverteria as duas.
    """

    @pytest.fixture
    def duas_versoes(self, escolas):
        from painel.models import IndicadorAnual

        for indicador in IndicadorAnual.objects.all():
            for versao, score in (("modelo-v1", 0.9), ("regras-v1", 0.5)):
                IndiceRisco.objects.create(
                    escola=indicador.escola, ano=indicador.ano, versao=versao,
                    score=score, classe="alto",
                )
        return escolas

    def test_resumo_lista_as_versoes_na_ordem_do_painel(self, api, duas_versoes):
        dados = api.get("/api/indicadores/resumo/").json()
        assert dados["versoes_disponiveis"] == ["regras-v1", "modelo-v1"]

    def test_ranking_filtra_por_versao(self, api, duas_versoes):
        dados = api.get("/api/risco/?versao=modelo-v1").json()
        assert dados["count"] == 3
        for item in dados["results"]:
            assert item["versao"] == "modelo-v1"

    def test_cada_versao_tem_rotulo_legivel(self):
        """
        Sem rotulo, o seletor mostraria "modelo-v1" para o usuario final, que nao
        tem como saber o que isso significa.
        """
        for versao in ("regras-v1", "modelo-v1"):
            rotulo = risco.ROTULO_VERSAO[versao]
            assert rotulo != versao
            assert versao not in rotulo
            assert risco.DESCRICAO_VERSAO[versao]
