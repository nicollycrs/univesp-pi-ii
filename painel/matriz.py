"""
Matriz de decisao: cruzamento entre a situacao atual e a previsao.

POR QUE ESTA MATRIZ EXISTE

O painel produz duas leituras de risco. O indice baseado em regras descreve a
situacao da escola no ano observado; o modelo preditivo estima a situacao do ano
seguinte. Apresentadas uma de cada vez, as duas produzem dois rankings, e um
ranking diz onde o problema e maior, mas nao diz o que fazer.

Cruzadas, elas separam quatro situacoes que pedem respostas diferentes. A mais
importante e a que nenhuma das duas leituras isoladas revela: a escola que vai
bem hoje e que o modelo aponta como provavel caso de risco no ano seguinte. Ela
nao aparece no topo do ranking atual, porque hoje esta bem, e e exatamente a
escola em que a identificacao precoce tem mais valor.

O QUE SIGNIFICA O ANO NA MATRIZ

A matriz cruza, para um mesmo ano de referencia N, duas linhas de indice:

    regras-v1   a situacao OBSERVADA em N
    modelo-v1   a previsao para N+1, calculada a partir dos indicadores de N

Ou seja, selecionado o ano 2024, a matriz le "situacao em 2024 contra previsao
para 2025". As duas linhas compartilham a chave de ano justamente para que esse
cruzamento seja direto.

COMO A BINARIZACAO E FEITA

Cada leitura classifica a escola em tres niveis por tercis. Para a matriz, os
tres viram dois: **risco alto** contra **os demais**. E uma escolha do grupo, e
tem uma razao pratica: quatro grupos de acao sao acionaveis, nove nao sao. O
corte no nivel alto e o mesmo que o painel ja usa para destacar prioridade.

Consequencia a declarar: uma escola de risco medio aparece aqui como "situacao
aceitavel", o que nao significa situacao boa. A leitura em tres niveis continua
disponivel no ranking e na pagina da escola.
"""

from __future__ import annotations

VERSAO_ATUAL = "regras-v1"
VERSAO_PREVISTA = "modelo-v1"

CLASSE_DE_CORTE = "alto"


def e_alto(classe: str | None) -> bool | None:
    """Binariza a classe em risco alto contra os demais. None quando nao ha dado."""
    if classe is None:
        return None
    return classe == CLASSE_DE_CORTE


# Os quatro grupos.
#
# `atual` e `previsto` sao as condicoes que definem o grupo, em forma binaria.
# `linha` e `coluna` posicionam o grupo na grade 2x2 da pagina: as linhas sao a
# situacao atual, as colunas a previsao. `urgencia` ordena por prioridade de
# acao, e aparece escrita no cartao, de modo que a posicao na grade nunca seja o
# unico portador dessa informacao.
GRUPOS = {
    "deterioracao": {
        "rotulo": "Deterioração",
        "atual": False,
        "previsto": True,
        "condicao": "Situação aceitável hoje, previsão de risco alto",
        "explicacao": (
            "A escola não está entre as de maior risco hoje, mas os indicadores "
            "apontam para o quartil superior de abandono no ano seguinte."
        ),
        "acao": (
            "Agir agora. É neste grupo que a identificação precoce tem mais "
            "valor, porque a escola ainda não entrou em crise."
        ),
        "urgencia": 1,
        "linha": 0,
        "coluna": 1,
        "tarja": "medio",
    },
    "crise": {
        "rotulo": "Crise persistente",
        "atual": True,
        "previsto": True,
        "condicao": "Risco alto hoje e previsão de risco alto",
        "explicacao": (
            "A escola já está entre as de maior risco e nada nos indicadores "
            "sugere reversão no ano seguinte."
        ),
        "acao": (
            "Intervenção estrutural. O quadro se repete, e medidas pontuais já "
            "tiveram a chance de alterá-lo."
        ),
        "urgencia": 2,
        "linha": 1,
        "coluna": 1,
        "tarja": "alto",
    },
    "recuperacao": {
        "rotulo": "Recuperação",
        "atual": True,
        "previsto": False,
        "condicao": "Risco alto hoje, previsão de melhora",
        "explicacao": (
            "A escola está entre as de maior risco hoje, mas os indicadores "
            "apontam para fora do quartil superior no ano seguinte."
        ),
        "acao": (
            "Manter o que está em curso e confirmar a melhora quando o próximo "
            "dado do INEP for publicado."
        ),
        "urgencia": 3,
        "linha": 1,
        "coluna": 0,
        "tarja": "baixo",
    },
    "estavel": {
        "rotulo": "Estável",
        "atual": False,
        "previsto": False,
        "condicao": "Situação aceitável hoje e previsão de continuidade",
        "explicacao": (
            "A escola não está entre as de maior risco hoje nem é apontada para "
            "o quartil superior no ano seguinte."
        ),
        "acao": "Acompanhamento de rotina.",
        "urgencia": 4,
        "linha": 0,
        "coluna": 0,
        "tarja": "neutro",
    },
}

# Rotulos dos eixos da grade.
EIXO_LINHA = ("Situação aceitável hoje", "Risco alto hoje")
EIXO_COLUNA = (
    "Previsão para o ano seguinte: risco baixo ou médio",
    "Previsão para o ano seguinte: risco alto",
)

# Grupo usado quando a escola tem indice atual mas nao tem previsao. Acontece
# com a escola que aparece em apenas um dos dois anos: sem o par, nao ha
# transicao a aprender nem a prever. Vai declarado, e nao silenciosamente
# somado a algum dos quatro grupos.
SEM_PREVISAO = {
    "rotulo": "Sem previsão",
    "explicacao": (
        "A escola não aparece nos dois anos necessários para o modelo, então "
        "não recebeu previsão. O índice atual dela continua disponível no "
        "ranking."
    ),
}


def grupo_de(classe_atual: str | None, classe_prevista: str | None) -> str | None:
    """
    Devolve a chave do grupo para um par de classes, ou None sem previsao.

    Esta funcao e o unico lugar que decide a que grupo uma escola pertence. A
    API e os testes chamam ela, em vez de repetir a regra.
    """
    atual, previsto = e_alto(classe_atual), e_alto(classe_prevista)
    if atual is None or previsto is None:
        return None
    for chave, grupo in GRUPOS.items():
        if grupo["atual"] is atual and grupo["previsto"] is previsto:
            return chave
    return None


def por_urgencia() -> list[str]:
    """Chaves dos grupos, da acao mais urgente para a menos urgente."""
    return sorted(GRUPOS, key=lambda c: GRUPOS[c]["urgencia"])


def por_posicao() -> list[str]:
    """Chaves dos grupos na ordem em que ocupam a grade 2x2, linha a linha."""
    return sorted(GRUPOS, key=lambda c: (GRUPOS[c]["linha"], GRUPOS[c]["coluna"]))


def descrever(chave: str) -> dict:
    """Grupo em forma serializavel, com a chave incluida."""
    return {"grupo": chave, **GRUPOS[chave]}
