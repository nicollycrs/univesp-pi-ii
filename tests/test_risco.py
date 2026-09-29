"""
Testes do indice de risco.

Cobrem o que pode dar errado em silencio e estragar o resultado do projeto: a
inversao do INSE, a normalizacao por grupo, o tratamento de ausentes e a garantia
de que o rotulo textual sempre acompanha a classe.
"""

import pytest

from painel import risco


def _registro(**kwargs):
    base = {
        "uf": "SP",
        "ano": 2024,
        "taxa_abandono": 10.0,
        "taxa_reprovacao": 10.0,
        "distorcao_idade_serie": 20.0,
        "inse": 50.0,
    }
    base.update(kwargs)
    return base


class TestOrdenacao:
    def test_escola_pior_em_tudo_tem_score_maior(self):
        registros = [
            _registro(co_entidade=1, taxa_abandono=2, taxa_reprovacao=2,
                      distorcao_idade_serie=5, inse=80),
            _registro(co_entidade=2, taxa_abandono=30, taxa_reprovacao=25,
                      distorcao_idade_serie=60, inse=25),
        ]
        saida = {r["co_entidade"]: r for r in risco.calcular(registros)}
        assert saida[2]["score"] > saida[1]["score"]

    def test_score_fica_entre_zero_e_um(self):
        registros = [
            _registro(co_entidade=i, taxa_abandono=i * 3, inse=80 - i * 5)
            for i in range(1, 11)
        ]
        for r in risco.calcular(registros):
            assert 0.0 <= r["score"] <= 1.0


class TestInseInvertido:
    def test_inse_menor_eleva_o_risco(self):
        """
        O INSE e o unico componente invertido. Se a inversao quebrar, escolas de
        contexto socioeconomico alto passariam a aparecer como as mais criticas,
        e o painel inteiro perderia sentido.
        """
        registros = [
            _registro(co_entidade=1, inse=20),  # nivel baixo, risco maior
            _registro(co_entidade=2, inse=80),  # nivel alto, risco menor
        ]
        saida = {r["co_entidade"]: r for r in risco.calcular(registros)}
        assert saida[1]["score"] > saida[2]["score"]


class TestNormalizacaoPorGrupo:
    def test_ufs_diferentes_sao_normalizadas_separadamente(self):
        """
        Escolas identicas em UFs diferentes recebem o mesmo score, porque cada
        grupo e normalizado no proprio intervalo. Comparar UFs na mesma escala
        distorceria o ranking.
        """
        registros = [
            _registro(co_entidade=1, uf="SP", taxa_abandono=10),
            _registro(co_entidade=2, uf="SP", taxa_abandono=20),
            _registro(co_entidade=3, uf="BA", taxa_abandono=10),
            _registro(co_entidade=4, uf="BA", taxa_abandono=20),
        ]
        saida = {r["co_entidade"]: r for r in risco.calcular(registros)}
        assert saida[1]["score"] == pytest.approx(saida[3]["score"])
        assert saida[2]["score"] == pytest.approx(saida[4]["score"])

    def test_anos_diferentes_sao_grupos_diferentes(self):
        registros = [
            _registro(co_entidade=1, ano=2023, taxa_abandono=10),
            _registro(co_entidade=1, ano=2024, taxa_abandono=10),
        ]
        saida = risco.calcular(registros)
        assert len({(r["ano"]) for r in saida}) == 2


class TestAusentes:
    def test_componente_ausente_redistribui_peso_e_mantem_escala(self):
        registros = [
            _registro(co_entidade=1, inse=None),
            _registro(co_entidade=2, inse=None, taxa_abandono=30),
        ]
        saida = {r["co_entidade"]: r for r in risco.calcular(registros)}
        for r in saida.values():
            assert r["score"] is not None
            assert 0.0 <= r["score"] <= 1.0

    def test_sem_nenhum_indicador_devolve_score_nulo(self):
        registros = [
            _registro(
                co_entidade=1,
                taxa_abandono=None,
                taxa_reprovacao=None,
                distorcao_idade_serie=None,
                inse=None,
            )
        ]
        saida = risco.calcular(registros)
        assert saida[0]["score"] is None
        assert saida[0]["classe"] is None

    def test_grupo_sem_variacao_nao_divide_por_zero(self):
        registros = [_registro(co_entidade=i) for i in range(1, 4)]
        for r in risco.calcular(registros):
            assert r["score"] is not None


class TestClassificacao:
    def test_tres_niveis_aparecem_em_grupo_disperso(self):
        registros = [
            _registro(co_entidade=i, taxa_abandono=i, distorcao_idade_serie=i * 2,
                      inse=80 - i * 2)
            for i in range(1, 31)
        ]
        classes = {r["classe"] for r in risco.calcular(registros)}
        assert classes == {risco.CLASSE_BAIXO, risco.CLASSE_MEDIO, risco.CLASSE_ALTO}

    def test_versao_registrada_em_todo_resultado(self):
        saida = risco.calcular([_registro(co_entidade=1)])
        assert saida[0]["versao"] == risco.VERSAO


class TestRotuloTextual:
    @pytest.mark.parametrize(
        "classe,esperado",
        [
            (risco.CLASSE_ALTO, "Risco alto"),
            (risco.CLASSE_MEDIO, "Risco médio"),
            (risco.CLASSE_BAIXO, "Risco baixo"),
        ],
    )
    def test_toda_classe_tem_rotulo(self, classe, esperado):
        """
        Criterio 1.4.1 da WCAG 2.1: a informacao de risco nao pode depender de
        cor. Sem rotulo textual para alguma classe, a interface violaria isso.
        """
        assert risco.rotulo(classe) == esperado

    def test_classe_desconhecida_nao_quebra(self):
        assert risco.rotulo(None) == "Sem dados"


class TestPesos:
    def test_pesos_somam_um(self):
        assert sum(risco.PESOS.values()) == pytest.approx(1.0)

    def test_abandono_tem_o_maior_peso(self):
        """O abandono e o fenomeno que o sistema quer antecipar."""
        assert risco.PESOS["taxa_abandono"] == max(risco.PESOS.values())
