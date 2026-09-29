"""
Catalogo das fontes de dados do projeto.

As URLs do INEP mudam entre edicoes. Por isso este arquivo guarda o ponto de
partida da busca, e nao um link definitivo, e o comando `verificar_fontes`
confere o que ainda responde. Quando uma fonte muda, registrar aqui e em
docs/FONTES_DE_DADOS.md com a nova URL, a data de acesso e o ano de referencia.

Regra do projeto: se um arquivo nao for encontrado, registrar a falha. Nunca
substituir dado oficial por dado gerado, em silencio.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fonte:
    chave: str
    nome: str
    descricao: str
    portal: str
    observacao: str = ""


FONTES = (
    Fonte(
        chave="taxas_rendimento",
        nome="Taxas de Rendimento Escolar por escola",
        descricao="Aprovacao, reprovacao e abandono, por escola e etapa de ensino.",
        portal="https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais",
    ),
    Fonte(
        chave="distorcao",
        nome="Taxa de Distorcao Idade-Serie por escola",
        descricao="Percentual de estudantes com dois anos ou mais de defasagem.",
        portal="https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais",
    ),
    Fonte(
        chave="inse",
        nome="Indicador de Nivel Socioeconomico (INSE) por escola",
        descricao="Nivel socioeconomico medio dos estudantes da escola.",
        portal="https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/indicadores-educacionais",
        observacao="Valor maior significa nivel socioeconomico mais alto. No indice de risco entra invertido.",
    ),
    Fonte(
        chave="censo_escolar",
        nome="Microdados do Censo Escolar",
        descricao="Usado apenas para atributos cadastrais: rede, localizacao e municipio.",
        portal="https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar",
        observacao="Arquivo de varios GB. Nunca carregar bruto no banco em nuvem.",
    ),
    Fonte(
        chave="ibge_localidades",
        nome="API de Localidades do IBGE",
        descricao="Municipios, unidades federativas e regioes.",
        portal="https://servicodados.ibge.gov.br/api/v1/localidades/municipios",
        observacao="Publica, gratuita e sem autenticacao. Consumida em painel/ibge.py.",
    ),
)


def por_chave(chave: str) -> Fonte:
    for f in FONTES:
        if f.chave == chave:
            return f
    raise KeyError(f"Fonte desconhecida: {chave!r}")
