"""Testes da API REST propria e das paginas do painel."""

import pytest
from rest_framework.test import APIClient

from painel import risco
from painel.models import IndiceRisco


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
