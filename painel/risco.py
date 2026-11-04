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
    "contexto_socioeconomico_invertido": 0.15,
}

# Componentes em que valor maior significa risco maior.
COMPONENTES_DIRETOS = ("taxa_abandono", "taxa_reprovacao", "distorcao_idade_serie")

# Componente socioeconomico, invertido: contexto mais pobre significa risco maior.
#
# A fonte pretendida era o INSE do INEP, por escola. Ele nao e publicado de
# forma cruzavel: esta nos microdados do Saeb 2023, na coluna
# NIVEL_SOCIO_ECONOMICO, mas com os codigos de escola mascarados por LGPD
# ("Mascaras dos Codigos de Escola (sao codigos ficticios)", dicionario oficial),
# o que impede a juncao pelo codigo do Censo.
#
# A vaga passou a ser ocupada pelo salario medio mensal dos trabalhadores
# formais do MUNICIPIO, do IBGE. A troca muda a natureza do componente e isso e
# declarado em todo lugar onde ele aparece:
#
#   - granularidade cai de escola para municipio: escolas do mesmo municipio
#     recebem o mesmo valor, e o componente nao as diferencia entre si;
#   - mede o territorio, nao as familias dos estudantes daquela escola;
#   - cobre so o trabalho formal, entao subestima a informalidade.
#
# O que ele preserva: e dado publico, oficial, cruzavel e varia dentro de cada
# UF, que e a condicao para contribuir com o indice, ja que a normalizacao
# acontece dentro do grupo (uf, ano).
COMPONENTE_INVERTIDO = "contexto_socioeconomico"

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


# Nome legivel de cada componente, para a explicacao na pagina da escola.
ROTULO_COMPONENTE = {
    "taxa_abandono": "Taxa de abandono",
    "taxa_reprovacao": "Taxa de reprovação",
    "distorcao_idade_serie": "Distorção idade-série",
    "contexto_socioeconomico": "Contexto socioeconômico do município",
}

UNIDADE_COMPONENTE = {
    "taxa_abandono": "%",
    "taxa_reprovacao": "%",
    "distorcao_idade_serie": "%",
    "contexto_socioeconomico": "salários mínimos",
}


def _score_de_um(registro, limites):
    """
    Soma ponderada dos componentes disponiveis, e a conta aberta.

    Devolve (score, parcelas), onde cada parcela registra como aquele componente
    contribuiu. A conta aberta existe para a pagina da escola poder mostrar POR
    QUE o indice deu o que deu, em vez de pedir confianca em um numero.

    Quando um componente esta ausente, o peso dele e redistribuido entre os
    demais em proporcao. Assim uma escola sem um indicador ainda recebe score,
    em vez de ser descartada, e o resultado continua na escala de 0 a 1.
    """
    parcelas = []

    for campo in COMPONENTES_DIRETOS:
        minimo, maximo = limites[campo]
        norm = _minmax(registro.get(campo), minimo, maximo)
        if norm is not None:
            parcelas.append(
                {
                    "componente": campo,
                    "valor": registro.get(campo),
                    "normalizado": norm,
                    "peso": PESOS[campo],
                    "invertido": False,
                }
            )

    minimo, maximo = limites[COMPONENTE_INVERTIDO]
    norm_contexto = _minmax(registro.get(COMPONENTE_INVERTIDO), minimo, maximo)
    if norm_contexto is not None:
        parcelas.append(
            {
                "componente": COMPONENTE_INVERTIDO,
                "valor": registro.get(COMPONENTE_INVERTIDO),
                # Invertido: contexto mais rico significa risco menor, entao o
                # que entra na soma e o complemento do valor normalizado.
                "normalizado": 1.0 - norm_contexto,
                "peso": PESOS["contexto_socioeconomico_invertido"],
                "invertido": True,
            }
        )

    if not parcelas:
        return None, []

    # Peso efetivo: quando falta componente, o peso dele se redistribui entre os
    # presentes. Guardar o efetivo, e nao o nominal, e o que faz as parcelas
    # somarem exatamente o score.
    peso_total = sum(p["peso"] for p in parcelas)
    for p in parcelas:
        p["peso_efetivo"] = p["peso"] / peso_total
        p["contribuicao"] = p["peso_efetivo"] * p["normalizado"]

    score = sum(p["contribuicao"] for p in parcelas)
    return score, parcelas


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
            score, parcelas = _score_de_um(r, limites)
            com_score.append((r, score, parcelas))

        scores_validos = [s for _, s, _ in com_score if s is not None]
        corte_baixo, corte_medio = _classificar_por_tercis(scores_validos)

        for r, score, parcelas in com_score:
            novo = dict(r)
            novo["score"] = score
            novo["classe"] = (
                None if score is None else classe_de(score, corte_baixo, corte_medio)
            )
            novo["versao"] = VERSAO
            # A conta aberta acompanha o resultado, para a pagina da escola.
            novo["detalhes"] = (
                None if score is None
                else {"metodo": "soma_ponderada", "parcelas": parcelas}
            )
            saida.append(novo)

    return saida


# Nome legivel de cada versao do indice, para o seletor do painel.
ROTULO_VERSAO = {
    "regras-v1": "Índice atual (baseado em regras)",
    "modelo-v1": "Previsão para o ano seguinte (modelo preditivo)",
}

# Ordem de apresentacao no seletor. O indice de regras vem primeiro por ser a
# leitura padrao: descreve a situacao do ano consultado.
ORDEM_VERSAO = {"regras-v1": 0, "modelo-v1": 1}

DESCRICAO_VERSAO = {
    "regras-v1": (
        "Combina os indicadores do próprio ano em uma soma ponderada. "
        "Descreve a situação atual da escola."
    ),
    "modelo-v1": (
        "Modelo treinado para estimar, a partir dos indicadores do ano "
        "selecionado, se a escola estará no quartil superior de abandono da sua "
        "UF no ano seguinte. Antecipa, em vez de descrever."
    ),
}

# Em uma linha de IndiceRisco, `ano` significa coisas diferentes conforme a
# versao, e isso precisa ficar explicito onde a linha e exibida:
#
#   regras-v1  o ano DESCRITO. A escola estava assim naquele ano.
#   modelo-v1  o ano de REFERENCIA dos indicadores que geraram a previsao.
#              O ano previsto e esse mais um.
#
# Sem essa distincao a pagina da escola mostrava "2024" em duas linhas com
# valores diferentes, e um leitor razoavel concluiria que uma delas esta errada.
ANO_PREVISTO_SOMA = {"regras-v1": 0, "modelo-v1": 1}


def descrever_leitura(versao, ano):
    """Rotulo de uma linha do indice, com o ano a que ela de fato se refere."""
    if versao == "modelo-v1":
        return f"Previsão para {ano + 1} (a partir de {ano})"
    return ROTULO_VERSAO.get(versao, versao)


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
