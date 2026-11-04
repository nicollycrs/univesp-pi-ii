"""
Testes da matriz de decisao.

A matriz cruza o indice atual com a previsao do modelo. O risco de erro aqui nao
e visual: e uma escola cair no quadrante errado e receber a recomendacao errada.
Por isso os testes montam escolas com classes conhecidas nas duas versoes e
conferem em que grupo cada uma aterrissa.
"""

import pytest
from rest_framework.test import APIClient

from painel import matriz
from painel.models import Escola, IndicadorAnual, IndiceRisco, Municipio


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def cenario(db):
    """
    Uma escola para cada quadrante, mais duas situacoes de borda.

    As classes sao gravadas direto, e nao calculadas: o que esta sob teste e o
    cruzamento, nao o calculo do indice nem o treino do modelo, que tem testes
    proprios.
    """
    municipio = Municipio.objects.create(
        codigo_ibge="3550308", nome="São Paulo", uf="SP", regiao="Sudeste"
    )

    casos = [
        # (codigo, classe atual, classe prevista, grupo esperado)
        (1, "alto", "alto", "crise"),
        (2, "baixo", "alto", "deterioracao"),
        (3, "medio", "alto", "deterioracao"),  # medio tambem e "nao alto"
        (4, "alto", "baixo", "recuperacao"),
        (5, "baixo", "baixo", "estavel"),
        (6, "medio", "medio", "estavel"),
        (7, "alto", None, None),  # sem previsao
        (8, "baixo", None, None),
    ]

    for codigo, atual, prevista, _ in casos:
        escola = Escola.objects.create(
            co_entidade=codigo, nome=f"Escola {codigo}", uf="SP",
            municipio=municipio, rede=Escola.Rede.ESTADUAL,
            localizacao=Escola.Localizacao.URBANA,
        )
        IndicadorAnual.objects.create(
            escola=escola, ano=2024, taxa_abandono=5.0, taxa_reprovacao=5.0,
            taxa_aprovacao=90.0, distorcao_idade_serie=20.0,
        )
        IndiceRisco.objects.create(
            escola=escola, ano=2024, versao=matriz.VERSAO_ATUAL,
            score=0.5, classe=atual,
        )
        if prevista:
            IndiceRisco.objects.create(
                escola=escola, ano=2024, versao=matriz.VERSAO_PREVISTA,
                # score crescente com o codigo, para testar a ordenacao
                score=0.1 * codigo, classe=prevista,
            )
    return casos


class TestRegraDeAgrupamento:
    """A funcao `grupo_de` e o unico lugar que decide o quadrante."""

    @pytest.mark.parametrize(
        "atual,prevista,esperado",
        [
            ("alto", "alto", "crise"),
            ("baixo", "alto", "deterioracao"),
            ("medio", "alto", "deterioracao"),
            ("alto", "baixo", "recuperacao"),
            ("alto", "medio", "recuperacao"),
            ("baixo", "baixo", "estavel"),
            ("medio", "medio", "estavel"),
            ("baixo", "medio", "estavel"),
        ],
    )
    def test_cada_par_cai_no_grupo_certo(self, atual, prevista, esperado):
        assert matriz.grupo_de(atual, prevista) == esperado

    def test_risco_medio_conta_como_situacao_aceitavel(self):
        """
        A binarizacao e alto contra os demais, entao medio cai do lado
        "aceitavel". E uma escolha com consequencia, e esta fixada em teste para
        que ninguem a mude sem perceber.
        """
        assert matriz.e_alto("medio") is False
        assert matriz.e_alto("alto") is True

    def test_sem_previsao_nao_tem_grupo(self):
        assert matriz.grupo_de("alto", None) is None
        assert matriz.grupo_de(None, "alto") is None

    def test_todo_grupo_tem_combinacao_unica(self):
        """Nenhuma escola pode caber em dois quadrantes."""
        combinacoes = {(g["atual"], g["previsto"]) for g in matriz.GRUPOS.values()}
        assert len(combinacoes) == len(matriz.GRUPOS) == 4

    def test_os_quatro_quadrantes_estao_cobertos(self):
        for atual in ("alto", "baixo"):
            for previsto in ("alto", "baixo"):
                assert matriz.grupo_de(atual, previsto) is not None

    def test_cada_grupo_ocupa_uma_celula_distinta_da_grade(self):
        posicoes = {(g["linha"], g["coluna"]) for g in matriz.GRUPOS.values()}
        assert len(posicoes) == 4

    def test_urgencias_sao_distintas_e_completas(self):
        assert sorted(g["urgencia"] for g in matriz.GRUPOS.values()) == [1, 2, 3, 4]

    def test_deterioracao_e_a_prioridade_um(self):
        """
        É o grupo que nenhuma das duas leituras isoladas revela, e a razao de a
        matriz existir. Se deixar de ser prioridade 1, foi decisao e nao
        descuido.
        """
        assert matriz.por_urgencia()[0] == "deterioracao"

    def test_todo_grupo_tem_texto_para_o_usuario(self):
        for chave, grupo in matriz.GRUPOS.items():
            for campo in ("rotulo", "condicao", "explicacao", "acao"):
                assert grupo[campo].strip(), f"{chave} sem {campo}"


class TestEndpointDaMatriz:
    def test_conta_cada_quadrante(self, api, cenario):
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        contagem = {g["grupo"]: g["escolas"] for g in dados["grupos"]}

        assert contagem["crise"] == 1
        assert contagem["deterioracao"] == 2
        assert contagem["recuperacao"] == 1
        assert contagem["estavel"] == 2

    def test_escolas_sem_previsao_ficam_fora_dos_grupos(self, api, cenario):
        """
        Duas escolas nao tem previsao. Somar elas a qualquer quadrante seria
        inventar dado; a resposta as declara em separado.
        """
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        assert dados["sem_previsao"]["escolas"] == 2
        assert dados["escolas_com_previsao"] == 6
        assert sum(g["escolas"] for g in dados["grupos"]) == 6

    def test_proporcoes_somam_cem(self, api, cenario):
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        assert sum(g["proporcao"] for g in dados["grupos"]) == pytest.approx(100.0, abs=0.2)

    def test_grupos_vem_na_ordem_da_grade(self, api, cenario):
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        posicoes = [(g["linha"], g["coluna"]) for g in dados["grupos"]]
        assert posicoes == sorted(posicoes)

    def test_ano_sem_previsao_responde_sem_quebrar(self, api, cenario):
        """
        O ano mais antigo da base tem indice mas nao tem previsao. A resposta
        precisa dizer isso, para o painel esconder a secao em vez de mostrar
        quatro zeros, que pareceriam ausencia de escolas.
        """
        IndiceRisco.objects.filter(versao=matriz.VERSAO_PREVISTA).delete()
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()

        assert dados["previsao_disponivel"] is False
        assert dados["escolas_com_previsao"] == 0
        assert all(g["escolas"] == 0 for g in dados["grupos"])
        assert all(g["proporcao"] is None for g in dados["grupos"])

    def test_filtra_por_uf(self, api, cenario):
        assert api.get("/api/indicadores/matriz/?ano=2024&uf=SP").json()[
            "escolas_com_previsao"
        ] == 6
        assert api.get("/api/indicadores/matriz/?ano=2024&uf=RR").json()[
            "escolas_com_previsao"
        ] == 0

    def test_traz_os_rotulos_dos_eixos(self, api, cenario):
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        assert len(dados["eixo_linha"]) == 2
        assert len(dados["eixo_coluna"]) == 2

    def test_declara_as_versoes_que_cruzou(self, api, cenario):
        """
        Sem isso, o consumidor da API nao tem como saber quais duas leituras
        produziram a matriz.
        """
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        assert dados["versao_atual"] == matriz.VERSAO_ATUAL
        assert dados["versao_prevista"] == matriz.VERSAO_PREVISTA
        assert dados["classe_de_corte"] == "alto"


class TestFiltroPorGrupoNoRanking:
    def test_cada_grupo_devolve_as_suas_escolas(self, api, cenario):
        esperado = {"crise": 1, "deterioracao": 2, "recuperacao": 1, "estavel": 2}
        for grupo, quantidade in esperado.items():
            dados = api.get(f"/api/risco/?ano=2024&grupo={grupo}").json()
            assert dados["count"] == quantidade, grupo

    def test_contagem_bate_com_a_da_matriz(self, api, cenario):
        """
        Os dois caminhos sao consultas diferentes. Se divergirem, o cartao
        promete um numero de escolas e a lista entrega outro.
        """
        dados = api.get("/api/indicadores/matriz/?ano=2024").json()
        for g in dados["grupos"]:
            lista = api.get(f"/api/risco/?ano=2024&grupo={g['grupo']}").json()
            assert lista["count"] == g["escolas"], g["grupo"]

    def test_escola_sem_previsao_nao_entra_em_grupo_nenhum(self, api, cenario):
        encontradas = set()
        for grupo in matriz.GRUPOS:
            dados = api.get(f"/api/risco/?ano=2024&grupo={grupo}").json()
            encontradas |= {r["co_entidade"] for r in dados["results"]}
        # As escolas 7 e 8 nao tem previsao.
        assert 7 not in encontradas
        assert 8 not in encontradas

    def test_resposta_traz_a_previsao_de_cada_linha(self, api, cenario):
        dados = api.get("/api/risco/?ano=2024&grupo=deterioracao").json()
        for r in dados["results"]:
            assert r["classe_prevista"] == "alto"
            assert r["score_previsto"] is not None
            # O rotulo em texto evita que a interface dependa de cor (1.4.1).
            assert r["rotulo_previsto"] == "Risco alto"

    def test_sem_grupo_a_previsao_vem_nula_e_nao_ausente(self, api, cenario):
        """
        O formato da resposta nao pode mudar conforme o filtro, senao o
        consumidor precisa testar a existencia de cada campo.
        """
        primeiro = api.get("/api/risco/?ano=2024").json()["results"][0]
        assert "score_previsto" in primeiro
        assert primeiro["score_previsto"] is None
        assert primeiro["rotulo_previsto"] is None

    def test_pode_ordenar_pelo_risco_previsto(self, api, cenario):
        """
        Em deterioracao a ordem util e a da previsao: por definicao essas
        escolas nao estao mal hoje, entao ordenar pelo indice atual nao
        prioriza nada.
        """
        dados = api.get(
            "/api/risco/?ano=2024&grupo=deterioracao&ordering=-score_previsto"
        ).json()
        scores = [r["score_previsto"] for r in dados["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_grupo_invalido_e_ignorado_sem_erro(self, api, cenario):
        completo = api.get("/api/risco/?ano=2024").json()["count"]
        assert api.get("/api/risco/?ano=2024&grupo=inventado").json()["count"] == completo

    def test_grupo_combina_com_os_demais_filtros(self, api, cenario):
        assert api.get("/api/risco/?ano=2024&grupo=estavel&escola__uf=SP").json()["count"] == 2
        assert api.get("/api/risco/?ano=2024&grupo=estavel&escola__uf=RR").json()["count"] == 0

    def test_ranking_por_grupo_usa_a_linha_do_indice_atual(self, api, cenario):
        """
        Cada escola tem duas linhas de indice. O ranking precisa devolver uma so,
        a do indice atual, ou a escola apareceria duplicada na lista.
        """
        dados = api.get("/api/risco/?ano=2024&grupo=crise").json()
        assert dados["count"] == 1
        assert dados["results"][0]["versao"] == matriz.VERSAO_ATUAL
