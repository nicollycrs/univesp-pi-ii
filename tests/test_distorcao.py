"""
Testes da leitura e da juncao da planilha de distorcao idade-serie.

A distorcao vem de um arquivo separado do INEP (TDI), com a mesma estrutura das
taxas de rendimento mas outra convencao de nome de coluna. Os testes constroem
planilhas sinteticas com essa estrutura, em vez de depender dos 35 MB do arquivo
real, e cobrem o que pode dar errado na juncao:

  - ler a coluna certa, MED_CAT_0 e nao MED_01_CAT_0;
  - preservar toda escola do rendimento, inclusive as sem distorcao;
  - nao duplicar linha na juncao.
"""

import openpyxl
import pandas as pd
import pytest

from etl import rendimento
from etl.transformar import mapa_distorcao, mapa_etapa, transformar

CABECALHO_IDENTIFICACAO = [
    "NU_ANO_CENSO", "SG_UF", "CO_MUNICIPIO", "CO_ENTIDADE", "NO_ENTIDADE",
    "NO_DEPENDENCIA", "NO_CATEGORIA",
]


def _planilha(caminho, codigos_indicador, linhas):
    """
    Escreve uma planilha com a estrutura real do INEP.

    Oito linhas de titulo e cabecalho mesclado, codigos legiveis por maquina na
    linha 9, dados a partir da linha 10.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = rendimento.ABA
    for _ in range(rendimento.LINHA_CODIGOS - 1):
        ws.append(["Título decorativo do INEP"])
    ws.append(CABECALHO_IDENTIFICACAO + list(codigos_indicador))
    for linha in linhas:
        ws.append(linha)
    wb.save(caminho)
    wb.close()
    return caminho


@pytest.fixture
def tdi(tmp_path):
    """
    Planilha de distorcao com tres escolas.

    MED_01_CAT_0 existe de proposito: e a distorcao da primeira serie do ensino
    medio, e o leitor nao pode confundi-la com o total da etapa.
    """
    return _planilha(
        tmp_path / "TDI.xlsx",
        ["MED_CAT_0", "MED_01_CAT_0"],
        [
            [2023, "SP", 3550308, 35000001, "Escola Alfa", "Estadual", "Urbana", 15.2, 40.0],
            [2023, "SP", 3550308, 35000002, "Escola Beta", "Estadual", "Rural", 30.5, 50.0],
            [2023, "SP", 3550308, 35000003, "Escola Gama", "Estadual", "Urbana", "--", "--"],
        ],
    )


@pytest.fixture
def rend(tmp_path):
    """Planilha de rendimento com quatro escolas: a quarta nao existe no TDI."""
    return _planilha(
        tmp_path / "REND.xlsx",
        ["1_CAT_MED", "2_CAT_MED", "3_CAT_MED"],
        [
            [2023, "SP", 3550308, 35000001, "Escola Alfa", "Estadual", "Urbana", 85.5, 10.5, 4.0],
            [2023, "SP", 3550308, 35000002, "Escola Beta", "Estadual", "Rural", 70.0, 18.0, 12.0],
            [2023, "SP", 3550308, 35000003, "Escola Gama", "Estadual", "Urbana", 90.0, 8.0, 2.0],
            [2023, "SP", 3550308, 35000004, "Escola Delta", "Estadual", "Urbana", 80.0, 15.0, 5.0],
        ],
    )


class TestLeituraDaPlanilhaDeDistorcao:
    def test_le_o_total_da_etapa_e_nao_a_serie(self, tdi):
        lido = rendimento.ler(tdi, etapa="MED", mapa=mapa_distorcao("MED"))

        assert "MED_CAT_0" in lido.columns
        # MED_01_CAT_0 e a primeira serie: nao esta no mapa, logo nao e lida.
        assert "MED_01_CAT_0" not in lido.columns

    def test_le_todas_as_escolas(self, tdi):
        lido = rendimento.ler(tdi, etapa="MED", mapa=mapa_distorcao("MED"))
        assert len(lido) == 3

    def test_falha_alto_quando_a_coluna_nao_existe(self, tmp_path):
        """
        Se o INEP mudar o codigo da coluna, o leitor precisa falhar com mensagem
        clara, e nao devolver a distorcao vazia em silencio.
        """
        caminho = _planilha(
            tmp_path / "SEM_COLUNA.xlsx",
            ["OUTRO_CODIGO"],
            [[2023, "SP", 3550308, 35000001, "Escola Alfa", "Estadual", "Urbana", 1.0]],
        )
        with pytest.raises(rendimento.FormatoInesperado, match="colunas esperadas"):
            rendimento.ler(caminho, etapa="MED", mapa=mapa_distorcao("MED"))


class TestJuncaoComORendimento:
    @pytest.fixture
    def unido(self, rend, tdi):
        """Reproduz a juncao que o comando processar_inep faz."""
        cru = rendimento.ler(rend, etapa="MED")
        cru_tdi = rendimento.ler(tdi, etapa="MED", mapa=mapa_distorcao("MED"))
        return cru.merge(
            cru_tdi[["CO_ENTIDADE", "MED_CAT_0"]], on="CO_ENTIDADE", how="left"
        )

    def test_nao_duplica_linha(self, unido):
        """
        O erro classico de juncao. Com duplicata no lado direito, uma escola
        apareceria duas vezes e os agregados do painel ficariam errados.
        """
        assert len(unido) == 4
        assert unido["CO_ENTIDADE"].is_unique

    def test_preserva_escola_sem_distorcao(self, unido):
        """
        A juncao e pela esquerda de proposito: escola sem distorcao continua na
        base, e o indice redistribui o peso do componente ausente, em vez de a
        escola desaparecer do painel.
        """
        delta = unido[unido["CO_ENTIDADE"] == 35000004]
        assert len(delta) == 1
        assert pd.isna(delta["MED_CAT_0"].iloc[0])

    def test_valor_vai_para_a_escola_certa(self, unido):
        por_escola = unido.set_index("CO_ENTIDADE")["MED_CAT_0"]
        assert por_escola[35000001] == 15.2
        assert por_escola[35000002] == 30.5

    def test_transformacao_gera_a_coluna_canonica(self, unido):
        mapa = {**mapa_etapa("MED"), **mapa_distorcao("MED")}
        limpo, _ = transformar(unido, ano=2023, mapa=mapa)

        assert "distorcao_idade_serie" in limpo.columns
        # A transformacao converte o codigo da escola para inteiro.
        por_escola = limpo.set_index("co_entidade")["distorcao_idade_serie"]
        assert por_escola[35000001] == pytest.approx(15.2)
        # A escola Gama tinha "--" na planilha: marcador de ausente, nao zero.
        assert pd.isna(por_escola[35000003])
        assert pd.isna(por_escola[35000004])

    def test_juncao_nao_corrompe_as_taxas_de_rendimento(self, unido):
        """
        As tres taxas somam 100 por escola. Conferir isso depois da juncao
        garante que a coluna nova nao embaralhou as existentes.
        """
        mapa = {**mapa_etapa("MED"), **mapa_distorcao("MED")}
        limpo, _ = transformar(unido, ano=2023, mapa=mapa)
        soma = (
            limpo["taxa_aprovacao"] + limpo["taxa_reprovacao"] + limpo["taxa_abandono"]
        )
        assert soma.tolist() == pytest.approx([100.0] * 4)


class TestCaminhoDoArquivo:
    def test_padrao_de_nome_da_distorcao(self):
        """
        O padrao difere do rendimento: maiusculas, e o ano antes da palavra
        ESCOLAS. Custou tempo descobrir, entao fica fixado em teste.
        """
        caminho = rendimento.caminho_distorcao(2023, raiz="dados_brutos")
        assert caminho.parts[-3:] == ("TDI_2023", "TDI_2023_ESCOLAS", "TDI_ESCOLAS_2023.xlsx")

    def test_padrao_de_nome_do_rendimento_continua_diferente(self):
        caminho = rendimento.caminho_padrao(2023, raiz="dados_brutos")
        assert caminho.name == "tx_rend_escolas_2023.xlsx"
