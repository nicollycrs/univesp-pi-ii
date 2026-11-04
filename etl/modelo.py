"""
Modelo preditivo de risco de abandono escolar.

DESENHO DO PROBLEMA

Nao existe, nos dados publicos, um rotulo dizendo "esta escola vai entrar em
crise". Foi preciso construir um, e a construcao escolhida e esta:

    atributos da escola no ano t  ->  a escola estara no quartil superior de
                                      abandono da sua UF no ano t+1?

Ou seja, o modelo responde a uma pergunta sobre o futuro usando apenas o que se
sabe no presente, que e exatamente o que o projeto promete: identificacao
precoce. Um indice calculado sobre o ano corrente descreve; um modelo treinado
sobre a transicao entre anos antecipa.

POR QUE O QUARTIL DENTRO DA UF, E NAO NACIONAL

Porque comparar uma escola do Acre com uma de Santa Catarina na mesma escala
mede sobretudo a diferenca entre os estados, e nao o risco relativo da escola no
contexto em que ela opera. O recorte por UF torna a tarefa mais dificil e mais
util: o modelo precisa achar, dentro de cada estado, quais escolas vao piorar.

POR QUE SENSIBILIDADE E ESPECIFICIDADE, E NAO ACURACIA

Bowers, Sprott e Taff (2013) mostram que indicadores de evasao devem ser
avaliados por precisao, sensibilidade e especificidade. Em base desbalanceada,
a acuracia engana: um modelo que classificasse todas as escolas como "sem risco"
acertaria 75% dos casos e seria inutil, porque nao encontraria nenhuma escola em
risco. Sensibilidade mede justamente quantas das escolas que de fato pioraram o
modelo conseguiu apontar.

Este modulo roda na maquina local, junto do ETL. O processo web nao importa
scikit-learn: apenas le do banco as previsoes ja calculadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

VERSAO = "modelo-v1"
SEMENTE = 42

# Diferenca de sensibilidade abaixo da qual dois modelos sao considerados
# equivalentes. Em uma unica divisao treino/teste, variacoes dessa ordem sao
# ruido amostral, nao desempenho.
TOLERANCIA_SENSIBILIDADE = 0.02

# Ordem de preferencia quando os modelos empatam: o interpretavel primeiro.
# Os coeficientes de uma regressao logistica podem ser lidos e defendidos em
# banca; a importancia de atributo de uma floresta diz menos sobre direcao e
# magnitude do efeito.
PREFERENCIA = ["Regressão logística", "Floresta aleatória"]
QUANTIL_ALVO = 0.75  # quartil superior de abandono

ATRIBUTOS = [
    "taxa_abandono",
    "taxa_reprovacao",
    "distorcao_idade_serie",
    "contexto_socioeconomico",
    "rural",
]


@dataclass
class Avaliacao:
    """Metricas de um modelo no conjunto de teste."""

    nome: str
    sensibilidade: float
    especificidade: float
    precisao: float
    auc: float
    matriz: np.ndarray
    importancias: dict[str, float] = field(default_factory=dict)
    # "coeficiente" ou "importancia". Os dois nao se leem da mesma forma: o
    # coeficiente da regressao tem SINAL, e diz a direcao do efeito; a
    # importancia da floresta e sempre positiva, e diz so o quanto o atributo
    # foi usado para separar os casos. Apresentar um como o outro seria um erro
    # de interpretacao no relatorio.
    tipo_importancia: str = ""

    @property
    def f1(self) -> float:
        if self.precisao + self.sensibilidade == 0:
            return 0.0
        return 2 * self.precisao * self.sensibilidade / (self.precisao + self.sensibilidade)

    def resumo(self) -> str:
        vn, fp, fn, vp = self.matriz.ravel()
        return (
            f"{self.nome}\n"
            f"  sensibilidade (recall):  {self.sensibilidade:.3f}\n"
            f"  especificidade:          {self.especificidade:.3f}\n"
            f"  precisao:                {self.precisao:.3f}\n"
            f"  F1:                      {self.f1:.3f}\n"
            f"  AUC ROC:                 {self.auc:.3f}\n"
            f"  matriz de confusao:\n"
            f"    verdadeiro negativo {vn:>6}   falso positivo {fp:>6}\n"
            f"    falso negativo      {fn:>6}   verdadeiro positivo {vp:>6}"
        )


def montar_base(df: pd.DataFrame, ano_atributos: int, ano_alvo: int) -> pd.DataFrame:
    """
    Constroi a base supervisionada a partir dos indicadores de dois anos.

    Espera um dataframe com uma linha por escola e ano, contendo ao menos
    co_entidade, ano, uf e os indicadores. Devolve uma linha por escola, com os
    atributos do ano t e o rotulo construido sobre o ano t+1.
    """
    atual = df[df["ano"] == ano_atributos].copy()
    futuro = df[df["ano"] == ano_alvo][["co_entidade", "taxa_abandono", "uf"]].copy()
    futuro = futuro.rename(columns={"taxa_abandono": "abandono_futuro"})

    base = atual.merge(futuro[["co_entidade", "abandono_futuro"]], on="co_entidade")

    # O corte do quartil e calculado dentro de cada UF, no ano futuro.
    cortes = (
        df[df["ano"] == ano_alvo]
        .groupby("uf")["taxa_abandono"]
        .quantile(QUANTIL_ALVO)
        .rename("corte_uf")
    )
    base = base.merge(cortes, left_on="uf", right_index=True, how="left")
    base["alvo"] = (base["abandono_futuro"] >= base["corte_uf"]).astype(int)

    base["rural"] = (base["localizacao"].astype(str) == "rural").astype(int)

    # O contexto socioeconomico e do municipio, entao escolas do mesmo municipio
    # compartilham o valor. Entra assim mesmo: o modelo aprende o efeito do
    # territorio, que a literatura do projeto trata como fator extraescolar.
    if "contexto_socioeconomico" not in base.columns:
        base["contexto_socioeconomico"] = float("nan")

    # Sem atributo nao ha o que aprender; sem rotulo nao ha o que prever.
    base = base.dropna(subset=ATRIBUTOS + ["alvo"])
    return base.reset_index(drop=True)


def _avaliar(nome, modelo, X_teste, y_teste, nomes_atributos) -> Avaliacao:
    previsto = modelo.predict(X_teste)
    prob = modelo.predict_proba(X_teste)[:, 1]
    matriz = confusion_matrix(y_teste, previsto)
    vn, fp, fn, vp = matriz.ravel()

    importancias, tipo = {}, ""
    final = modelo[-1] if isinstance(modelo, Pipeline) else modelo
    if hasattr(final, "coef_"):
        importancias = dict(zip(nomes_atributos, final.coef_[0].round(4)))
        tipo = "coeficiente"
    elif hasattr(final, "feature_importances_"):
        importancias = dict(zip(nomes_atributos, final.feature_importances_.round(4)))
        tipo = "importancia"

    return Avaliacao(
        nome=nome,
        sensibilidade=recall_score(y_teste, previsto, zero_division=0),
        especificidade=vn / (vn + fp) if (vn + fp) else 0.0,
        precisao=precision_score(y_teste, previsto, zero_division=0),
        auc=roc_auc_score(y_teste, prob),
        matriz=matriz,
        importancias={k: float(v) for k, v in importancias.items()},
        tipo_importancia=tipo,
    )


def treinar(base: pd.DataFrame, teste: float = 0.25):
    """
    Treina e compara dois modelos, devolvendo o melhor e as avaliacoes.

    Sao dois de proposito: a regressao logistica e interpretavel, e seus
    coeficientes podem ser lidos e defendidos; a floresta aleatoria captura
    relacoes nao lineares. Se a diferenca de desempenho for pequena, a escolha
    recai sobre a interpretavel, coerente com Bowers, Sprott e Taff (2013).

    `class_weight="balanced"` compensa o desbalanceamento: sem isso, ambos
    tenderiam a classificar quase tudo como sem risco.
    """
    X = base[ATRIBUTOS].to_numpy(dtype=float)
    y = base["alvo"].to_numpy(dtype=int)

    X_treino, X_teste, y_treino, y_teste = train_test_split(
        X, y, test_size=teste, random_state=SEMENTE, stratify=y
    )

    candidatos = {
        "Regressão logística": Pipeline([
            ("escala", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=1000, class_weight="balanced", random_state=SEMENTE
            )),
        ]),
        "Floresta aleatória": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=20, class_weight="balanced",
            random_state=SEMENTE, n_jobs=-1,
        ),
    }

    avaliacoes, modelos = [], {}
    for nome, modelo in candidatos.items():
        modelo.fit(X_treino, y_treino)
        avaliacoes.append(_avaliar(nome, modelo, X_teste, y_teste, ATRIBUTOS))
        modelos[nome] = modelo

    melhor = escolher(avaliacoes)
    return modelos[melhor.nome], melhor, avaliacoes


def escolher(avaliacoes: list[Avaliacao]) -> Avaliacao:
    """
    Escolhe o modelo entre os avaliados, em duas etapas.

    Primeiro a sensibilidade, que e o que o projeto precisa: encontrar a escola
    que vai piorar importa mais que evitar o alarme falso, porque o custo de
    olhar uma escola que estava bem e baixo, e o de nao olhar uma que piorou,
    alto.

    Depois, entre os modelos praticamente empatados, o mais interpretavel. Sem
    essa segunda etapa, uma diferenca de milesimos, que e ruido de uma unica
    divisao treino/teste, decidiria a favor do modelo mais opaco.
    """
    melhor_sens = max(a.sensibilidade for a in avaliacoes)
    empatados = [
        a for a in avaliacoes
        if melhor_sens - a.sensibilidade <= TOLERANCIA_SENSIBILIDADE
    ]
    ordem = {nome: i for i, nome in enumerate(PREFERENCIA)}
    return min(empatados, key=lambda a: ordem.get(a.nome, 99))


def montar_previsao(df: pd.DataFrame, ano_base: int) -> pd.DataFrame:
    """
    Monta o quadro de atributos de UM ano, para gerar a previsao do ano seguinte.

    Diferente de `montar_base`, nao constroi rotulo: nao existe rotulo para um
    ano que ainda nao aconteceu. E essa a diferenca entre treinar e prever.

    Por que isto existe. Antes, as previsoes gravadas no painel vinham de
    `prever(modelo, base)`, com a MESMA base usada no treino. Isso tinha dois
    defeitos: o ano previsto ja havia acontecido, entao nao era previsao, e as
    escolas eram as mesmas sobre as quais o modelo foi ajustado, o que torna o
    score otimista. Aplicar o modelo aos atributos do ano mais recente corrige
    os dois: o alvo passa a ser um ano sem dado publicado, e as linhas de
    entrada nao sao as linhas de treino.
    """
    quadro = df[df["ano"] == ano_base].copy()
    quadro["rural"] = (quadro["localizacao"].astype(str) == "rural").astype(int)
    if "contexto_socioeconomico" not in quadro.columns:
        quadro["contexto_socioeconomico"] = float("nan")
    quadro = quadro.dropna(subset=ATRIBUTOS)
    return quadro.reset_index(drop=True)


def prever(modelo, base: pd.DataFrame) -> pd.DataFrame:
    """Probabilidade de a escola entrar no quartil superior de abandono."""
    X = base[ATRIBUTOS].to_numpy(dtype=float)
    saida = base[["co_entidade", "uf", "ano"]].copy()
    saida["score"] = modelo.predict_proba(X)[:, 1]
    return saida


def classificar(saida: pd.DataFrame) -> pd.DataFrame:
    """
    Converte a probabilidade em tres niveis, por tercis dentro de cada UF.

    Mantem a mesma leitura do indice baseado em regras, de modo que o painel e a
    interpretacao do usuario nao mudem ao trocar a versao.
    """
    from painel import risco

    saida = saida.copy()
    saida["classe"] = None
    for uf, grupo in saida.groupby("uf"):
        scores = sorted(grupo["score"])
        n = len(scores)
        if n < 3:
            corte_baixo, corte_medio = 1 / 3, 2 / 3
        else:
            corte_baixo, corte_medio = scores[n // 3], scores[(2 * n) // 3]
        saida.loc[grupo.index, "classe"] = [
            risco.classe_de(s, corte_baixo, corte_medio) for s in grupo["score"]
        ]
    return saida


# ------------------------------------------------------------- explicabilidade
#
# Por que esta parte existe. Um painel que diz "43% de risco" e nao diz de onde
# veio o numero pede confianca cega. Para uma gestora decidir se age, ela precisa
# saber qual indicador puxou a previsao para cima.
#
# A decomposicao abaixo e EXATA, nao aproximada: para os dois modelos, a soma
# das contribuicoes mais a base reproduz a previsao. Isso e testado.
#
# Nao usa biblioteca externa de propósito. `shap` resolveria, mas e uma
# dependencia pesada para uma instancia de 512 MB, e o calculo cabe em poucas
# linhas para os dois modelos que o projeto usa.


def _contribuicoes_arvore(arvore, x, indice_classe=1):
    """
    Contribuicao de cada atributo em UMA arvore, pelo metodo de Saabas.

    Percorre o caminho da raiz ate a folha. Em cada no, a mudanca na proporcao
    da classe positiva entre o no e o filho escolhido e creditada ao atributo
    que fez a divisao. Somando tudo, a base da raiz mais as contribuicoes da
    exatamente o valor da folha.
    """
    t = arvore.tree_
    contrib = np.zeros(x.shape[0])

    def proporcao(no):
        valores = t.value[no][0]
        total = valores.sum()
        return valores[indice_classe] / total if total else 0.0

    no, base = 0, proporcao(0)
    while t.children_left[no] != -1:
        atributo = t.feature[no]
        filho = (
            t.children_left[no]
            if x[atributo] <= t.threshold[no]
            else t.children_right[no]
        )
        contrib[atributo] += proporcao(filho) - proporcao(no)
        no = filho
    return base, contrib


def contribuicoes(modelo, x: np.ndarray) -> tuple[float, dict[str, float]]:
    """
    Decompoe UMA previsao nas contribuicoes de cada atributo.

    Devolve (base, {atributo: contribuicao}), com a garantia de que
    base + soma(contribuicoes) reproduz a previsao do modelo:

      - floresta aleatoria: a probabilidade da classe positiva;
      - regressao logistica: o log-odds, antes da funcao logistica.

    A unidade difere entre os dois, e por isso o que a interface mostra e a
    contribuicao RELATIVA de cada atributo, nao o valor absoluto.
    """
    final = modelo[-1] if isinstance(modelo, Pipeline) else modelo

    if isinstance(final, RandomForestClassifier):
        bases, somas = [], np.zeros(len(ATRIBUTOS))
        for arvore in final.estimators_:
            base, contrib = _contribuicoes_arvore(arvore, x)
            bases.append(base)
            somas += contrib
        n = len(final.estimators_)
        return float(np.mean(bases)), dict(zip(ATRIBUTOS, (somas / n).tolist()))

    if hasattr(final, "coef_"):
        # Com Pipeline, o x chega cru e precisa passar pela mesma padronizacao
        # usada no treino, senao a contribuicao sai em escala errada.
        if isinstance(modelo, Pipeline):
            x_usado = modelo[:-1].transform(x.reshape(1, -1))[0]
        else:
            x_usado = x
        contrib = final.coef_[0] * x_usado
        return float(final.intercept_[0]), dict(zip(ATRIBUTOS, contrib.tolist()))

    raise TypeError(f"Modelo sem decomposicao implementada: {type(final).__name__}")


def _contribuicoes_floresta_lote(floresta, X: np.ndarray, indice_classe=1):
    """
    Mesma decomposicao de `_contribuicoes_arvore`, para TODAS as linhas de uma vez.

    A versao linha a linha percorria 300 arvores por escola em laco Python: com
    20 mil escolas isso passava de dez minutos e tornava o comando impraticavel.
    Aqui o percurso vem de `decision_path`, que e codigo compilado e devolve de
    uma vez os nos visitados por cada amostra, e as diferencas entre nos viram
    operacao de vetor.

    O resultado e identico ao da versao simples, e ha teste comparando os dois.
    """
    n_amostras = X.shape[0]
    contrib = np.zeros((n_amostras, len(ATRIBUTOS)))
    bases = np.zeros(len(floresta.estimators_))

    for k, arvore in enumerate(floresta.estimators_):
        t = arvore.tree_
        valores = t.value[:, 0, :]
        totais = valores.sum(axis=1)
        prop = np.divide(
            valores[:, indice_classe], totais,
            out=np.zeros(len(totais)), where=totais > 0,
        )
        bases[k] = prop[0]

        caminhos = arvore.decision_path(X).tocsr()
        indptr, indices = caminhos.indptr, caminhos.indices

        # Monta, para a floresta inteira, os pares (amostra, atributo) e o
        # salto de proporcao de cada passo, e acumula tudo em uma chamada.
        linhas, colunas, saltos = [], [], []
        for i in range(n_amostras):
            nos = indices[indptr[i] : indptr[i + 1]]
            if len(nos) < 2:
                continue
            pais = nos[:-1]
            linhas.append(np.full(len(pais), i))
            colunas.append(t.feature[pais])
            saltos.append(prop[nos[1:]] - prop[pais])

        if linhas:
            np.add.at(
                contrib,
                (np.concatenate(linhas), np.concatenate(colunas)),
                np.concatenate(saltos),
            )

    return float(bases.mean()), contrib / len(floresta.estimators_)


def explicar(modelo, base: pd.DataFrame, maximo: int | None = None) -> list[dict]:
    """
    Explica cada linha da base, em forma serializavel para o banco.

    `maximo` limita quantos atributos entram na explicacao, do mais influente
    para o menos: a pagina da escola nao precisa dos cinco para ser util.
    """
    X = base[ATRIBUTOS].to_numpy(dtype=float)
    final = modelo[-1] if isinstance(modelo, Pipeline) else modelo

    if isinstance(final, RandomForestClassifier):
        base_valor, matriz_contrib = _contribuicoes_floresta_lote(final, X)
        bases = [base_valor] * len(X)
    else:
        bases, linhas = [], []
        for i in range(len(X)):
            b, c = contribuicoes(modelo, X[i])
            bases.append(b)
            linhas.append([c[nome] for nome in ATRIBUTOS])
        matriz_contrib = np.array(linhas)

    valores = base[ATRIBUTOS].to_numpy(dtype=float)
    codigos = base["co_entidade"].tolist()

    saida = []
    for i, codigo in enumerate(codigos):
        itens = sorted(
            zip(ATRIBUTOS, matriz_contrib[i], valores[i]),
            key=lambda item: -abs(item[1]),
        )
        if maximo:
            itens = itens[:maximo]
        saida.append(
            {
                "co_entidade": int(codigo),
                "base": float(bases[i]),
                "contribuicoes": [
                    {
                        "atributo": nome,
                        "valor": float(valor),
                        "contribuicao": float(contrib),
                    }
                    for nome, contrib, valor in itens
                ],
            }
        )
    return saida
