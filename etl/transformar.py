"""
Transformacao dos arquivos do INEP para o formato canonico do EducaAlerta.

Decisao de projeto: a transformacao e guiada por um mapa de colunas explicito, e
nao por nomes fixos no codigo. Os arquivos do INEP mudam de cabecalho entre
edicoes, e descobrir isso com o projeto ja em producao custa caro. Com o mapa
externo, adaptar a uma nova edicao e editar um dicionario.

Toda linha descartada e contada e justificada no relatorio devolvido, que vira a
secao de qualidade dos dados do relatorio academico.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import pandas as pd

# Nomes canonicos usados no resto do projeto.
CANONICAS = (
    "co_entidade",
    "nome",
    "uf",
    "codigo_municipio",
    "rede",
    "localizacao",
    "taxa_aprovacao",
    "taxa_reprovacao",
    "taxa_abandono",
    "distorcao_idade_serie",
    "inse",
)

OBRIGATORIAS = ("co_entidade", "uf")

# As 26 unidades federativas mais o Distrito Federal. Conferir contra esta lista,
# e nao apenas contra "duas letras maiusculas", e o que pega lixo como 'XX'.
UFS_VALIDAS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

# Variacoes conhecidas de cabecalho nos arquivos do INEP, em forma normalizada
# (sem acento, minusculas, so letras e numeros). Acrescentar aqui ao encontrar
# uma edicao com nome diferente.
MAPA_PADRAO = {
    "coentidade": "co_entidade",
    "codigodaescola": "co_entidade",
    "codescola": "co_entidade",
    "noentidade": "nome",
    "nomedaescola": "nome",
    "escola": "nome",
    "sguf": "uf",
    "uf": "uf",
    "siglauf": "uf",
    "comunicipio": "codigo_municipio",
    "codigodomunicipio": "codigo_municipio",
    "dependenciaadministrativa": "rede",
    "rede": "rede",
    "localizacao": "localizacao",
    "aprovacao": "taxa_aprovacao",
    "taxadeaprovacao": "taxa_aprovacao",
    "reprovacao": "taxa_reprovacao",
    "taxadereprovacao": "taxa_reprovacao",
    "abandono": "taxa_abandono",
    "taxadeabandono": "taxa_abandono",
    "distorcaoidadeserie": "distorcao_idade_serie",
    "taxadedistorcaoidadeserie": "distorcao_idade_serie",
    "inse": "inse",
    "indicadordenivelsocioeconomico": "inse",
    "nivelsocioeconomico": "inse",
}

# Colunas de identificacao das planilhas de indicadores do INEP.
# Conferidas em tx_rend_escolas_2023.xlsx, linha 9 do cabecalho, em 23/09/2026.
MAPA_PADRAO.update(
    {
        "nuanocenso": "ano_censo",
        "nocategoria": "localizacao",
        "nodependencia": "rede",
        "noregiao": "regiao",
        "nomunicipio": "nome_municipio",
    }
)


def mapa_etapa(etapa: str = "MED") -> dict:
    """
    Mapa das colunas de indicador para uma etapa de ensino.

    Nas planilhas de rendimento do INEP o prefixo numerico identifica o
    indicador e o sufixo identifica a etapa: 1 e aprovacao, 2 e reprovacao e 3 e
    abandono; MED e ensino medio e FUN e ensino fundamental. Assim, 3_CAT_MED e
    a taxa de abandono no ensino medio.

    Existe uma coluna por serie tambem (1_CAT_MED_01 e seguintes). Aqui interessa
    so o total da etapa.
    """
    e = etapa.strip().lower()
    return {
        f"1cat{e}": "taxa_aprovacao",
        f"2cat{e}": "taxa_reprovacao",
        f"3cat{e}": "taxa_abandono",
    }


MAPA_REDE = {
    "estadual": "estadual",
    "2": "estadual",
    "municipal": "municipal",
    "3": "municipal",
    "federal": "federal",
    "1": "federal",
    "privada": "privada",
    "particular": "privada",
    "4": "privada",
}

MAPA_LOCALIZACAO = {"urbana": "urbana", "1": "urbana", "rural": "rural", "2": "rural"}


@dataclass
class Relatorio:
    """Contagens da transformacao, para o relatorio de qualidade dos dados."""

    linhas_lidas: int = 0
    linhas_validas: int = 0
    descartes: dict[str, int] = field(default_factory=dict)
    ausentes_por_coluna: dict[str, int] = field(default_factory=dict)
    colunas_nao_reconhecidas: list[str] = field(default_factory=list)

    def descartar(self, motivo: str, quantidade: int) -> None:
        if quantidade:
            self.descartes[motivo] = self.descartes.get(motivo, 0) + int(quantidade)

    def resumo(self) -> str:
        linhas = [
            f"Linhas lidas: {self.linhas_lidas}",
            f"Linhas validas: {self.linhas_validas}",
        ]
        if self.descartes:
            linhas.append("Descartes:")
            linhas += [f"  {m}: {n}" for m, n in sorted(self.descartes.items())]
        if self.ausentes_por_coluna:
            linhas.append("Ausentes por coluna:")
            linhas += [
                f"  {c}: {n}" for c, n in sorted(self.ausentes_por_coluna.items()) if n
            ]
        if self.colunas_nao_reconhecidas:
            linhas.append(
                "Colunas ignoradas: " + ", ".join(self.colunas_nao_reconhecidas)
            )
        return "\n".join(linhas)


def normalizar_nome(nome: str) -> str:
    """Reduz um cabecalho a letras e numeros minusculos, sem acento."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(nome)) if not unicodedata.combining(c)
    )
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def renomear_colunas(df: pd.DataFrame, mapa: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Aplica o mapa de colunas. Devolve o dataframe e as colunas ignoradas."""
    mapa = {**MAPA_PADRAO, **(mapa or {})}
    novos, ignoradas = {}, []
    for coluna in df.columns:
        chave = normalizar_nome(coluna)
        if chave in mapa:
            novos[coluna] = mapa[chave]
        else:
            ignoradas.append(str(coluna))
    return df.rename(columns=novos), ignoradas


def _para_numero(serie: pd.Series) -> pd.Series:
    """
    Converte para numero detectando o separador decimal, e trata os marcadores
    de ausente do INEP.

    Por que detectar em vez de assumir: os arquivos do INEP nao sao uniformes.
    As planilhas de taxas de rendimento usam ponto como separador decimal
    ("79.8"), enquanto outras publicacoes usam o formato brasileiro
    ("1.234,56"). Remover o ponto sem verificar transformaria 79.8 em 798, e o
    erro passaria despercebido porque 798 e um numero valido.

    Regra aplicada:
      tem virgula e ponto  -> ponto e milhar, virgula e decimal
      so virgula           -> virgula e decimal
      so ponto             -> ponto ja e decimal, nao mexer
    """
    texto = (
        serie.astype("string")
        .str.strip()
        .str.replace("%", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    texto = texto.replace(
        {"--": None, "-": None, "ND": None, "nd": None, "": None, "...": None}
    )

    tem_virgula = texto.str.contains(",", regex=False, na=False)
    tem_ponto = texto.str.contains(".", regex=False, na=False)

    formato_br = tem_virgula & tem_ponto
    texto = texto.mask(
        formato_br,
        texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
    )

    so_virgula = tem_virgula & ~tem_ponto
    texto = texto.mask(so_virgula, texto.str.replace(",", ".", regex=False))

    return pd.to_numeric(texto, errors="coerce")


def transformar(
    df: pd.DataFrame,
    ano: int,
    mapa: dict | None = None,
    redes: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, Relatorio]:
    """
    Normaliza um dataframe cru do INEP para o formato canonico.

    `redes` filtra o recorte, por exemplo ("estadual",) para a rede estadual.
    Devolve o dataframe limpo e o relatorio de qualidade.
    """
    rel = Relatorio(linhas_lidas=len(df))

    df, ignoradas = renomear_colunas(df, mapa)
    rel.colunas_nao_reconhecidas = ignoradas

    faltando = [c for c in OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(
            "Colunas obrigatorias ausentes apos o mapeamento: "
            + ", ".join(faltando)
            + ". Ajuste o mapa de colunas em etl/transformar.py."
        )

    # Mantem so as canonicas presentes e cria as ausentes como vazias.
    for coluna in CANONICAS:
        if coluna not in df.columns:
            df[coluna] = pd.NA
    df = df[list(CANONICAS)].copy()

    # Chave da escola precisa ser inteiro.
    df["co_entidade"] = pd.to_numeric(df["co_entidade"], errors="coerce")
    sem_chave = df["co_entidade"].isna().sum()
    rel.descartar("sem codigo de escola valido", sem_chave)
    df = df[df["co_entidade"].notna()]
    df["co_entidade"] = df["co_entidade"].astype("int64")

    df["uf"] = df["uf"].astype("string").str.strip().str.upper()
    uf_ok = df["uf"].isin(UFS_VALIDAS)
    rel.descartar("UF fora da lista oficial", int((~uf_ok).sum()))
    df = df[uf_ok]

    df["nome"] = df["nome"].astype("string").str.strip()
    df["codigo_municipio"] = (
        pd.to_numeric(df["codigo_municipio"], errors="coerce").astype("Int64").astype("string")
    )

    for coluna, mapa_valores in (("rede", MAPA_REDE), ("localizacao", MAPA_LOCALIZACAO)):
        df[coluna] = (
            df[coluna]
            .astype("string")
            .str.strip()
            .str.lower()
            .map(lambda v: mapa_valores.get(normalizar_nome(v)) if pd.notna(v) else None)
            .astype("string")
        )

    numericas = (
        "taxa_aprovacao",
        "taxa_reprovacao",
        "taxa_abandono",
        "distorcao_idade_serie",
        "inse",
    )
    for coluna in numericas:
        df[coluna] = _para_numero(df[coluna])

    # Taxas fora de 0 a 100 nao existem: viram ausentes em vez de contaminar medias.
    for coluna in ("taxa_aprovacao", "taxa_reprovacao", "taxa_abandono", "distorcao_idade_serie"):
        fora = ((df[coluna] < 0) | (df[coluna] > 100)).sum()
        rel.descartar(f"{coluna} fora do intervalo de 0 a 100 (valor anulado)", fora)
        df.loc[(df[coluna] < 0) | (df[coluna] > 100), coluna] = pd.NA

    if redes:
        antes = len(df)
        df = df[df["rede"].isin(redes)]
        rel.descartar(f"fora do recorte de rede {redes}", antes - len(df))

    # Uma escola por ano. Duplicata fica com o primeiro registro.
    duplicadas = df["co_entidade"].duplicated().sum()
    rel.descartar("codigo de escola duplicado", duplicadas)
    df = df[~df["co_entidade"].duplicated()]

    # Sem nenhum indicador a linha nao serve para calcular risco.
    sem_indicador = df[list(numericas)].isna().all(axis=1).sum()
    rel.descartar("sem nenhum indicador disponivel", sem_indicador)
    df = df[~df[list(numericas)].isna().all(axis=1)]

    df["ano"] = int(ano)

    rel.linhas_validas = len(df)
    rel.ausentes_por_coluna = {c: int(df[c].isna().sum()) for c in CANONICAS}

    return df.reset_index(drop=True), rel
