"""
Testes do modelo preditivo.

O que mais importa aqui nao e a metrica do modelo treinado, que depende dos
dados reais, e sim a **construcao do rotulo**. O alvo deste projeto foi inventado
pelos autores a partir dos indicadores do ano seguinte, e um erro silencioso
nessa construcao produziria um modelo que parece funcionar e nao responde a
pergunta pretendida. Por isso a maior parte destes testes verifica o rotulo.
"""

import numpy as np
import pandas as pd
import pytest

from etl import modelo


def _linha(codigo, ano, uf, abandono, reprovacao=10.0, distorcao=20.0,
           localizacao="urbana", contexto=2.0):
    return {
        "co_entidade": codigo,
        "ano": ano,
        "uf": uf,
        "taxa_abandono": abandono,
        "taxa_reprovacao": reprovacao,
        "distorcao_idade_serie": distorcao,
        # Contexto socioeconomico do municipio, em salarios minimos.
        "contexto_socioeconomico": contexto,
        "localizacao": localizacao,
    }


class TestConstrucaoDoRotulo:
    """
    O alvo e: a escola estara no quartil superior de abandono da SUA UF no ano
    seguinte?
    """

    @pytest.fixture
    def duas_ufs(self):
        """
        SP com abandono baixo, AC com abandono alto, nos dois anos.

        O ponto do caso: a pior escola de SP tem abandono (8%) MENOR que a melhor
        escola do AC (20%). Num corte nacional, nenhuma escola de SP seria
        positiva. No corte por UF, a pior de cada estado precisa ser positiva.
        """
        linhas = []
        for ano in (2023, 2024):
            for i, abandono in enumerate([1.0, 2.0, 3.0, 8.0]):
                linhas.append(_linha(3500000 + i, ano, "SP", abandono))
            for i, abandono in enumerate([20.0, 22.0, 24.0, 40.0]):
                linhas.append(_linha(1200000 + i, ano, "AC", abandono))
        return pd.DataFrame(linhas)

    def test_corte_e_calculado_dentro_da_uf(self, duas_ufs):
        base = modelo.montar_base(duas_ufs, 2023, 2024)

        positivas = set(base[base["alvo"] == 1]["co_entidade"])
        # A pior de SP (8%) entra, apesar de ter abandono menor que toda escola
        # do AC. A melhor do AC (20%) fica fora, apesar de ter abandono maior que
        # toda escola de SP.
        assert 3500003 in positivas
        assert 1200000 not in positivas

    def test_cada_uf_tem_positivas(self, duas_ufs):
        base = modelo.montar_base(duas_ufs, 2023, 2024)
        por_uf = base.groupby("uf")["alvo"].sum()
        assert por_uf["SP"] > 0
        assert por_uf["AC"] > 0

    def test_atributos_vem_do_ano_base_e_rotulo_do_ano_seguinte(self):
        """
        Teste direto da separacao temporal. A escola melhora de 2023 para 2024:
        o atributo tem de registrar o valor ruim de 2023, e o rotulo, a situacao
        boa de 2024.
        """
        df = pd.DataFrame([
            _linha(1, 2023, "SP", 30.0),
            _linha(1, 2024, "SP", 1.0),
            _linha(2, 2023, "SP", 1.0),
            _linha(2, 2024, "SP", 30.0),
            _linha(3, 2023, "SP", 2.0),
            _linha(3, 2024, "SP", 2.0),
            _linha(4, 2023, "SP", 3.0),
            _linha(4, 2024, "SP", 3.0),
        ])
        base = modelo.montar_base(df, 2023, 2024).set_index("co_entidade")

        assert base.loc[1, "taxa_abandono"] == 30.0  # atributo de 2023
        assert base.loc[1, "alvo"] == 0  # melhorou em 2024
        assert base.loc[2, "taxa_abandono"] == 1.0
        assert base.loc[2, "alvo"] == 1  # piorou em 2024

    def test_escola_presente_em_apenas_um_ano_sai_da_base(self):
        df = pd.DataFrame([
            _linha(1, 2023, "SP", 5.0),
            _linha(2, 2023, "SP", 6.0),
            _linha(3, 2023, "SP", 7.0),
            _linha(1, 2024, "SP", 5.0),
            _linha(2, 2024, "SP", 6.0),
            # a escola 3 nao tem 2024: nao ha o que prever
        ])
        base = modelo.montar_base(df, 2023, 2024)
        assert set(base["co_entidade"]) == {1, 2}

    def test_linha_sem_atributo_sai_da_base(self):
        df = pd.DataFrame([
            _linha(1, 2023, "SP", 5.0),
            _linha(2, 2023, "SP", np.nan),
            _linha(1, 2024, "SP", 5.0),
            _linha(2, 2024, "SP", 9.0),
        ])
        base = modelo.montar_base(df, 2023, 2024)
        assert set(base["co_entidade"]) == {1}

    def test_localizacao_vira_indicador_binario(self):
        df = pd.DataFrame([
            _linha(1, 2023, "SP", 5.0, localizacao="rural"),
            _linha(2, 2023, "SP", 6.0, localizacao="urbana"),
            _linha(1, 2024, "SP", 5.0, localizacao="rural"),
            _linha(2, 2024, "SP", 6.0, localizacao="urbana"),
        ])
        base = modelo.montar_base(df, 2023, 2024).set_index("co_entidade")
        assert base.loc[1, "rural"] == 1
        assert base.loc[2, "rural"] == 0

    def test_proporcao_de_positivas_fica_perto_do_quartil(self):
        """
        Como o corte e o quantil 0,75, cerca de um quarto das escolas deve sair
        positiva. Muito acima ou muito abaixo disso indica corte mal aplicado.
        """
        gerador = np.random.default_rng(7)
        linhas = []
        for i in range(400):
            base_abandono = float(gerador.uniform(0, 30))
            for ano in (2023, 2024):
                linhas.append(_linha(i, ano, "SP", base_abandono))
        base = modelo.montar_base(pd.DataFrame(linhas), 2023, 2024)
        proporcao = base["alvo"].mean()
        assert 0.20 <= proporcao <= 0.30


@pytest.fixture
def base_sintetica():
    """
    Base em que o abandono realmente prediz o alvo, com ruido.

    Serve para verificar que o treino roda de ponta a ponta e aprende algo. Nao
    serve para avaliar desempenho: isso e o que docs/AVALIACAO_DO_MODELO.md faz
    com os dados reais.
    """
    gerador = np.random.default_rng(11)
    n = 600
    abandono = gerador.uniform(0, 30, n)
    ruido = gerador.normal(0, 4, n)
    return pd.DataFrame({
        "co_entidade": range(n),
        "ano": 2023,
        "uf": "SP",
        "taxa_abandono": abandono,
        "taxa_reprovacao": gerador.uniform(0, 25, n),
        "distorcao_idade_serie": abandono * 1.5 + gerador.normal(0, 5, n),
        "contexto_socioeconomico": gerador.uniform(1.0, 5.0, n),
        "rural": gerador.integers(0, 2, n),
        "alvo": ((abandono + ruido) > 20).astype(int),
    })


class TestTreino:
    def test_treina_e_devolve_avaliacao_dos_dois_candidatos(self, base_sintetica):
        _, melhor, avaliacoes = modelo.treinar(base_sintetica)

        assert len(avaliacoes) == 2
        assert {a.nome for a in avaliacoes} == set(modelo.PREFERENCIA)
        assert melhor in avaliacoes

    def test_aprende_o_sinal_que_existe_na_base(self, base_sintetica):
        """
        Com um sinal forte plantado, a AUC tem de ficar bem acima de 0,5, que e o
        desempenho de um palpite aleatorio.
        """
        _, melhor, _ = modelo.treinar(base_sintetica)
        assert melhor.auc > 0.8

    def test_abandono_e_o_atributo_de_maior_peso(self, base_sintetica):
        """
        Na base sintetica o abandono e, por construcao, o que gera o rotulo.
        Vale tanto para coeficiente quanto para importancia: nos dois casos ele
        tem de ser o maior em valor absoluto.
        """
        _, melhor, _ = modelo.treinar(base_sintetica)
        maior = max(melhor.importancias, key=lambda k: abs(melhor.importancias[k]))
        assert maior == "taxa_abandono"

    def test_declara_se_e_coeficiente_ou_importancia(self, base_sintetica):
        """
        Coeficiente tem sinal e diz a direcao do efeito; importancia de floresta
        e sempre positiva e nao diz direcao. O relatorio precisa saber qual das
        duas esta apresentando, ou induz a leitura errada.
        """
        _, melhor, _ = modelo.treinar(base_sintetica)
        assert melhor.tipo_importancia in ("coeficiente", "importancia")
        if melhor.tipo_importancia == "importancia":
            assert all(v >= 0 for v in melhor.importancias.values())

    def test_divisao_e_reprodutivel(self, base_sintetica):
        """
        Mesma base, mesma semente, mesmo resultado. Sem isso, os numeros do
        relatorio mudariam a cada execucao e nao poderiam ser citados.
        """
        _, a, _ = modelo.treinar(base_sintetica)
        _, b, _ = modelo.treinar(base_sintetica)
        assert a.sensibilidade == b.sensibilidade
        assert a.auc == b.auc


class TestEscolhaDoModelo:
    """
    A escolha privilegia sensibilidade, e desempata pelo modelo interpretavel.
    Sem a regra de desempate, uma diferenca de milesimos, que e ruido amostral,
    decidiria a favor do modelo mais opaco.
    """

    def _avaliacao(self, nome, sensibilidade, auc=0.7):
        return modelo.Avaliacao(
            nome=nome,
            sensibilidade=sensibilidade,
            especificidade=0.7,
            precisao=0.4,
            auc=auc,
            matriz=np.array([[10, 5], [5, 10]]),
        )

    def test_sensibilidade_claramente_maior_vence(self):
        floresta = self._avaliacao("Floresta aleatória", 0.80)
        logistica = self._avaliacao("Regressão logística", 0.50)
        assert modelo.escolher([logistica, floresta]).nome == "Floresta aleatória"

    def test_empate_tecnico_fica_com_o_interpretavel(self):
        """O caso que motivou a regra: diferenca de 0,005 na sensibilidade."""
        floresta = self._avaliacao("Floresta aleatória", 0.566, auc=0.95)
        logistica = self._avaliacao("Regressão logística", 0.561, auc=0.50)
        escolhido = modelo.escolher([logistica, floresta])
        assert escolhido.nome == "Regressão logística"

    def test_dentro_da_tolerancia_ainda_e_empate(self):
        floresta = self._avaliacao("Floresta aleatória", 0.60)
        logistica = self._avaliacao(
            "Regressão logística", 0.60 - modelo.TOLERANCIA_SENSIBILIDADE * 0.9
        )
        assert modelo.escolher([logistica, floresta]).nome == "Regressão logística"

    def test_fora_da_tolerancia_nao_e_empate(self):
        floresta = self._avaliacao("Floresta aleatória", 0.60)
        logistica = self._avaliacao(
            "Regressão logística", 0.60 - modelo.TOLERANCIA_SENSIBILIDADE * 1.5
        )
        assert modelo.escolher([logistica, floresta]).nome == "Floresta aleatória"


class TestMetricas:
    def test_f1_combina_precisao_e_sensibilidade(self):
        a = modelo.Avaliacao(
            nome="teste", sensibilidade=0.5, especificidade=0.8, precisao=0.5,
            auc=0.7, matriz=np.array([[1, 1], [1, 1]]),
        )
        assert a.f1 == pytest.approx(0.5)

    def test_f1_nao_divide_por_zero(self):
        """
        Um modelo que nao aponta ninguem tem precisao e sensibilidade zero. O F1
        precisa devolver zero, nao estourar.
        """
        a = modelo.Avaliacao(
            nome="inutil", sensibilidade=0.0, especificidade=1.0, precisao=0.0,
            auc=0.5, matriz=np.array([[10, 0], [10, 0]]),
        )
        assert a.f1 == 0.0

    def test_resumo_mostra_a_matriz_de_confusao(self):
        a = modelo.Avaliacao(
            nome="teste", sensibilidade=0.6, especificidade=0.7, precisao=0.4,
            auc=0.7, matriz=np.array([[70, 30], [40, 60]]),
        )
        texto = a.resumo()
        assert "verdadeiro negativo" in texto
        assert "70" in texto and "60" in texto


class TestPrevisaoEClassificacao:
    def test_prever_devolve_probabilidade_por_escola(self, base_sintetica):
        treinado, _, _ = modelo.treinar(base_sintetica)
        saida = modelo.prever(treinado, base_sintetica)

        assert len(saida) == len(base_sintetica)
        assert list(saida.columns) == ["co_entidade", "uf", "ano", "score"]
        assert saida["score"].between(0, 1).all()

    def test_classificar_usa_tercis_dentro_da_uf(self, db):
        """
        A classificacao reparte cada UF em tres grupos de tamanho parecido, o
        mesmo criterio do indice baseado em regras. Assim a leitura do painel nao
        muda ao trocar a versao.
        """
        saida = pd.DataFrame({
            "co_entidade": range(90),
            "uf": ["SP"] * 45 + ["AC"] * 45,
            "ano": 2024,
            "score": list(np.linspace(0.0, 0.3, 45)) + list(np.linspace(0.6, 0.9, 45)),
        })
        classificado = modelo.classificar(saida)

        for uf in ("SP", "AC"):
            contagem = classificado[classificado["uf"] == uf]["classe"].value_counts()
            # Cada UF recebe os tres niveis, em grupos de tamanho proximo, mesmo
            # com faixas de score completamente diferentes entre as duas.
            assert set(contagem.index) == {"alto", "medio", "baixo"}
            assert contagem.min() >= 10

    def test_classificar_nao_quebra_com_uf_de_poucas_escolas(self, db):
        saida = pd.DataFrame({
            "co_entidade": [1, 2],
            "uf": ["SP", "SP"],
            "ano": 2024,
            "score": [0.1, 0.9],
        })
        classificado = modelo.classificar(saida)
        assert classificado["classe"].notna().all()


class TestExplicabilidade:
    """
    A decomposicao precisa ser EXATA, nao uma aproximacao plausivel.

    Se base + soma(contribuicoes) nao reproduz a previsao, a explicacao mostrada
    na pagina da escola e uma historia bonita que nao corresponde ao que o
    modelo fez. Esse e o unico teste que importa de verdade aqui.
    """

    def test_floresta_soma_exatamente_a_probabilidade(self, base_sintetica):
        from sklearn.ensemble import RandomForestClassifier

        X = base_sintetica[modelo.ATRIBUTOS].to_numpy(dtype=float)
        y = base_sintetica["alvo"].to_numpy(dtype=int)
        floresta = RandomForestClassifier(
            n_estimators=25, min_samples_leaf=20, random_state=modelo.SEMENTE
        ).fit(X, y)

        for i in range(12):
            base, contrib = modelo.contribuicoes(floresta, X[i])
            previsto = floresta.predict_proba(X[i].reshape(1, -1))[0, 1]
            assert base + sum(contrib.values()) == pytest.approx(previsto, abs=1e-9)

    def test_logistica_soma_exatamente_o_log_odds(self, base_sintetica):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        X = base_sintetica[modelo.ATRIBUTOS].to_numpy(dtype=float)
        y = base_sintetica["alvo"].to_numpy(dtype=int)
        tubo = Pipeline([
            ("escala", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=modelo.SEMENTE)),
        ]).fit(X, y)

        for i in range(12):
            base, contrib = modelo.contribuicoes(tubo, X[i])
            esperado = tubo.decision_function(X[i].reshape(1, -1))[0]
            assert base + sum(contrib.values()) == pytest.approx(esperado, abs=1e-9)

    def test_explica_todas_as_linhas(self, base_sintetica):
        treinado, _, _ = modelo.treinar(base_sintetica)
        explicacoes = modelo.explicar(treinado, base_sintetica.head(20))

        assert len(explicacoes) == 20
        for e in explicacoes:
            assert e["contribuicoes"]
            for c in e["contribuicoes"]:
                assert c["atributo"] in modelo.ATRIBUTOS

    def test_base_explicada_e_sempre_uma_probabilidade(self, base_sintetica):
        """
        Regressao: a pagina da escola anuncia a base como "a probabilidade
        media antes de olhar para esta escola". Na logistica ela sai de
        `contribuicoes` em log-odds, e o intercepto negativo chegava a tela
        como "o modelo parte de -9%". Probabilidade nao e negativa.
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        tubo = Pipeline([
            ("escala", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=modelo.SEMENTE)),
        ]).fit(
            base_sintetica[modelo.ATRIBUTOS].to_numpy(dtype=float),
            base_sintetica["alvo"].to_numpy(dtype=int),
        )

        for treinado in (tubo, modelo.treinar(base_sintetica)[0]):
            for e in modelo.explicar(treinado, base_sintetica.head(10)):
                assert 0.0 <= e["base"] <= 1.0, e["base"]

    def test_limita_aos_atributos_mais_influentes(self, base_sintetica):
        treinado, _, _ = modelo.treinar(base_sintetica)
        explicacoes = modelo.explicar(treinado, base_sintetica.head(5), maximo=3)

        for e in explicacoes:
            assert len(e["contribuicoes"]) == 3
            # Ordenadas pelo peso absoluto, da maior para a menor.
            pesos = [abs(c["contribuicao"]) for c in e["contribuicoes"]]
            assert pesos == sorted(pesos, reverse=True)

    def test_abandono_alto_empurra_a_previsao_para_cima(self, base_sintetica):
        """
        Checagem de sentido: na base sintetica o abandono gera o rotulo, entao
        para uma escola de abandono alto ele tem de contribuir positivamente.
        """
        treinado, _, _ = modelo.treinar(base_sintetica)
        pior = base_sintetica.nlargest(1, "taxa_abandono")
        explicacao = modelo.explicar(treinado, pior)[0]
        por_atributo = {c["atributo"]: c["contribuicao"] for c in explicacao["contribuicoes"]}
        assert por_atributo["taxa_abandono"] > 0

    def test_versao_em_lote_bate_com_a_linha_a_linha(self, base_sintetica):
        """
        A versao vetorizada existe so por desempenho. Se ela divergir da simples,
        a explicacao da pagina deixa de corresponder ao modelo, em silencio.
        """
        from sklearn.ensemble import RandomForestClassifier

        X = base_sintetica[modelo.ATRIBUTOS].to_numpy(dtype=float)
        y = base_sintetica["alvo"].to_numpy(dtype=int)
        floresta = RandomForestClassifier(
            n_estimators=20, min_samples_leaf=15, random_state=modelo.SEMENTE
        ).fit(X, y)

        base_lote, matriz = modelo._contribuicoes_floresta_lote(floresta, X[:30])
        for i in range(30):
            base_um, contrib_um = modelo.contribuicoes(floresta, X[i])
            assert base_lote == pytest.approx(base_um, abs=1e-9)
            for j, nome in enumerate(modelo.ATRIBUTOS):
                assert matriz[i][j] == pytest.approx(contrib_um[nome], abs=1e-9)


class TestValidacaoProspectiva:
    """
    Validacao contra um ano ja observado.

    O risco coberto aqui nao e o modelo ir mal: e a MEDICAO estar errada. Um
    rotulo construido de forma diferente da usada no treino produz numeros que
    parecem desempenho e sao artefato.
    """

    @pytest.fixture
    def observado(self):
        """
        Ano observado com empate deliberado no corte.

        Metade das escolas de SP tem abandono zero, que e o caso real de 2025:
        a distribuicao comprimiu perto de zero e o quartil caiu sobre um valor
        repetido.
        """
        return pd.DataFrame({
            "co_entidade": range(1, 21),
            "uf": ["SP"] * 20,
            "taxa_abandono": [0.0] * 10 + [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        })

    def test_por_posto_mantem_um_quarto(self, observado):
        rotulo = modelo.rotular_observado(observado, por_posto=True)
        assert rotulo.sum() == 5  # 25% de 20

    def test_regra_literal_infla_quando_o_corte_cai_em_empate(self):
        """
        O defeito que a opcao por posto evita. Com a distribuicao comprimida, o
        quartil cai sobre um valor repetido e a regra literal leva junto todas
        as escolas empatadas nele.
        """
        df = pd.DataFrame({
            "co_entidade": range(1, 21),
            "uf": ["SP"] * 20,
            "taxa_abandono": [2.0] * 16 + [5.0, 6.0, 7.0, 8.0],
        })
        literal = modelo.rotular_observado(df, por_posto=False)
        posto = modelo.rotular_observado(df, por_posto=True)
        assert posto.sum() == 5
        assert literal.sum() > posto.sum()

    def test_corte_zero_promoveria_todo_mundo(self):
        """
        O caso extremo que apareceu em duas UFs de 2025: com o corte em zero, a
        regra literal marca como em risco toda escola sem nenhum abandono.
        """
        df = pd.DataFrame({
            "co_entidade": range(1, 11),
            "uf": ["AC"] * 10,
            "taxa_abandono": [0.0] * 8 + [5.0, 9.0],
        })
        assert modelo.rotular_observado(df, por_posto=False).sum() == 10
        assert modelo.rotular_observado(df, por_posto=True).sum() < 10

    def test_rotulo_e_por_uf(self):
        """
        Cada UF tem o proprio corte, como no treino. Sem isso a validacao
        mediria a diferenca entre estados.
        """
        df = pd.DataFrame({
            "co_entidade": range(1, 9),
            "uf": ["SP"] * 4 + ["AC"] * 4,
            "taxa_abandono": [1.0, 2.0, 3.0, 4.0, 20.0, 30.0, 40.0, 50.0],
        })
        rotulo = modelo.rotular_observado(df, por_posto=True)
        # A pior de SP entra, apesar de ter abandono menor que toda escola do AC.
        assert rotulo.iloc[3] == 1
        assert rotulo.iloc[4] == 0

    def test_validar_calcula_as_metricas(self):
        observado = pd.DataFrame({
            "co_entidade": [1, 2, 3, 4],
            "ocorreu": [1, 1, 0, 0],
        })
        previsto = pd.DataFrame({
            "co_entidade": [1, 2, 3, 4],
            "score": [0.9, 0.3, 0.8, 0.1],
            "classe": ["alto", "baixo", "alto", "baixo"],
        })
        aval = modelo.validar(observado, previsto)
        assert aval.sensibilidade == pytest.approx(0.5)
        assert aval.especificidade == pytest.approx(0.5)

    def test_validar_exige_escolas_em_comum(self):
        observado = pd.DataFrame({"co_entidade": [1], "ocorreu": [1]})
        previsto = pd.DataFrame(
            {"co_entidade": [99], "score": [0.5], "classe": ["alto"]}
        )
        with pytest.raises(ValueError, match="Nenhuma escola em comum"):
            modelo.validar(observado, previsto)
