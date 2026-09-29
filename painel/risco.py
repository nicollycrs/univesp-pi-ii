"""
Indice de risco escolar, versao baseada em regras.

Fundamentacao. Bowers, Sprott e Taff (2013) mostram que indicadores simples e
diretamente observaveis pela escola, como frequencia, historico de reprovacao e
defasagem idade-serie, tem desempenho preditivo comparavel ao de modelos
estatisticos complexos. Soares et al. (2015) tratam o abandono como combinacao
de fatores intraescolares e extraescolares, e nao de causa unica: por isso o
indice combina indicadores de trajetoria com um indicador de contexto (INSE).

Os pesos abaixo sao uma escolha do grupo, informada pela literatura, e devem ser
declarados como tal no relatorio. Nao sao valor consagrado na area.

Nota de implementacao: este modulo usa apenas a biblioteca padrao, sem pandas.
O processo web roda em instancia de 512 MB de RAM no plano gratuito do Render, e
importar pandas ali custaria memoria demais. pandas fica restrito ao pacote etl,
que roda na maquina local.
"""

from __future__ import annotations

from collections import defaultdict

VERSAO = "regras-v1"

PESOS = {
    "taxa_abandono": 0.40,
    "taxa_reprovacao": 0.25,
    "distorcao_idade_serie": 0.20,
    "inse_invertido": 0.15,
}

# Componentes em que valor maior significa risco maior.
COMPONENTES_DIRETOS = ("taxa_abandono", "taxa_reprovacao", "distorcao_idade_serie")
# O INSE e invertido: nivel socioeconomico menor significa risco maior.
COMPONENTE_INVERTIDO = "inse"

CLASSE_BAIXO, CLASSE_MEDIO, CLASSE_ALTO = "baixo", "medio", "alto"


def _minmax(valor, minimo, maximo):
    """Normaliza para o intervalo de 0 a 1. Grupo sem variacao devolve 0,5."""
    if valor is None:
        return None
    if maximo is None or minimo is None or maximo == minimo:
        return 0.5
    return (valor - minimo) / (maximo - minimo)


def _limites(registros, campo):
    valores = [r[campo] for r in registros if r.get(campo) is not None]
    if not valores:
        return None, None
    return min(valores), max(valores)


def _score_de_um(registro, limites):
    """
    Soma ponderada dos componentes disponiveis.

    Quando um componente esta ausente, o peso dele e redistribuido entre os
    demais em proporcao. Assim uma escola sem INSE ainda recebe score, em vez de
    ser descartada, e o resultado continua na escala de 0 a 1.
    """
    parcelas = []

    for campo in COMPONENTES_DIRETOS:
        minimo, maximo = limites[campo]
        norm = _minmax(registro.get(campo), minimo, maximo)
        if norm is not None:
            parcelas.append((PESOS[campo], norm))

    minimo, maximo = limites[COMPONENTE_INVERTIDO]
    norm_inse = _minmax(registro.get(COMPONENTE_INVERTIDO), minimo, maximo)
    if norm_inse is not None:
        parcelas.append((PESOS["inse_invertido"], 1.0 - norm_inse))

    if not parcelas:
        return None

    peso_total = sum(p for p, _ in parcelas)
    return sum(p * v for p, v in parcelas) / peso_total


def _classificar_por_tercis(scores):
    """
    Devolve os dois pontos de corte por tercis.

    Com menos de tres escolas no grupo os tercis nao fazem sentido, e a funcao
    devolve limiares fixos de 1/3 e 2/3.
    """
    if len(scores) < 3:
        return 1 / 3, 2 / 3
    ordenados = sorted(scores)
    n = len(ordenados)
    return ordenados[n // 3], ordenados[(2 * n) // 3]


def classe_de(score, corte_baixo, corte_medio):
    if score < corte_baixo:
        return CLASSE_BAIXO
    if score < corte_medio:
        return CLASSE_MEDIO
    return CLASSE_ALTO


def calcular(registros):
    """
    Calcula o indice de risco para uma lista de registros.

    Cada registro e um dicionario com, no minimo, as chaves `uf`, `ano` e os
    campos de indicador. A normalizacao e a classificacao ocorrem dentro de cada
    grupo (uf, ano): comparar escola de UF diferente ou de ano diferente na mesma
    escala distorceria o resultado.

    Devolve uma nova lista de dicionarios com `score`, `classe` e `versao`
    acrescentados. Registros sem nenhum indicador disponivel sao devolvidos com
    `score` igual a None e sem classe.
    """
    grupos = defaultdict(list)
    for r in registros:
        grupos[(r.get("uf"), r.get("ano"))].append(r)

    saida = []
    for _chave, grupo in grupos.items():
        limites = {
            campo: _limites(grupo, campo)
            for campo in (*COMPONENTES_DIRETOS, COMPONENTE_INVERTIDO)
        }

        com_score = []
        for r in grupo:
            score = _score_de_um(r, limites)
            com_score.append((r, score))

        scores_validos = [s for _, s in com_score if s is not None]
        corte_baixo, corte_medio = _classificar_por_tercis(scores_validos)

        for r, score in com_score:
            novo = dict(r)
            novo["score"] = score
            novo["classe"] = (
                None if score is None else classe_de(score, corte_baixo, corte_medio)
            )
            novo["versao"] = VERSAO
            saida.append(novo)

    return saida


ROTULOS = {
    CLASSE_ALTO: "Risco alto",
    CLASSE_MEDIO: "Risco médio",
    CLASSE_BAIXO: "Risco baixo",
}


def rotulo(classe):
    """
    Texto que acompanha a cor no painel.

    Existe para atender ao criterio 1.4.1 da WCAG 2.1 (Uso da Cor, nivel A):
    a informacao de risco nunca pode ser transmitida somente por cor.
    """
    return ROTULOS.get(classe, "Sem dados")
