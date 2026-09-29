"""
Testes da transformacao do ETL.

O caso central e o do "arquivo sujo conhecido": uma planilha com os defeitos que
os arquivos do INEP realmente tem (virgula decimal, marcador de ausente, nome de
coluna com acento, duplicata, taxa impossivel) entra e sai limpa.
"""

import pandas as pd
import pytest

from etl import transformar as t


def test_normalizar_nome_remove_acento_e_pontuacao():
    assert t.normalizar_nome("Distorção Idade-Série") == "distorcaoidadeserie"
    assert t.normalizar_nome("CO_ENTIDADE") == "coentidade"
    assert t.normalizar_nome("Taxa de Aprovação (%)") == "taxadeaprovacao"


def test_renomear_colunas_reporta_ignoradas():
    df = pd.DataFrame(columns=["CO_ENTIDADE", "SG_UF", "COLUNA_QUE_NAO_EXISTE"])
    renomeado, ignoradas = t.renomear_colunas(df)
    assert "co_entidade" in renomeado.columns
    assert "uf" in renomeado.columns
    assert ignoradas == ["COLUNA_QUE_NAO_EXISTE"]


def test_coluna_obrigatoria_ausente_falha_com_mensagem_util():
    df = pd.DataFrame({"Escola": ["A"], "Abandono": ["1,0"]})
    with pytest.raises(ValueError, match="Colunas obrigatorias ausentes"):
        t.transformar(df, ano=2024)


@pytest.fixture
def planilha_suja():
    """Planilha com os defeitos tipicos dos arquivos do INEP."""
    return pd.DataFrame(
        {
            "CO_ENTIDADE": ["35000001", "35000002", "35000002", "", "35000005"],
            "NO_ENTIDADE": ["  Escola A  ", "Escola B", "Escola B", "Escola C", "Escola E"],
            "SG_UF": ["sp", "SP", "SP", "SP", "XX"],
            "Dependência Administrativa": ["Estadual", "Municipal", "Municipal", "Estadual", "Estadual"],
            "Localização": ["Urbana", "Rural", "Rural", "Urbana", "Urbana"],
            "Taxa de Aprovação": ["85,5", "90,0", "90,0", "80,0", "88,0"],
            "Taxa de Reprovação": ["10,5", "7,0", "7,0", "15,0", "8,0"],
            "Taxa de Abandono": ["4,0", "--", "--", "5,0", "4,0"],
            "Distorção Idade-Série": ["15,2", "180,0", "180,0", "20,0", "12,0"],
            "INSE": ["50,25", "ND", "ND", "45,00", "51,0"],
        }
    )


class TestTransformacaoCompleta:
    def test_limpa_e_descarta_o_que_deve(self, planilha_suja):
        limpo, rel = t.transformar(planilha_suja, ano=2024)

        assert rel.linhas_lidas == 5
        # Sobram A e B: a duplicata de B, a linha sem codigo e a de UF invalida saem.
        assert rel.linhas_validas == 2
        assert set(limpo["co_entidade"]) == {35000001, 35000002}

    def test_virgula_decimal_convertida(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2024)
        linha = limpo[limpo["co_entidade"] == 35000001].iloc[0]
        assert linha["taxa_aprovacao"] == pytest.approx(85.5)
        assert linha["inse"] == pytest.approx(50.25)

    def test_marcadores_de_ausente_viram_nulo(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2024)
        linha = limpo[limpo["co_entidade"] == 35000002].iloc[0]
        assert pd.isna(linha["taxa_abandono"])  # era '--'
        assert pd.isna(linha["inse"])  # era 'ND'

    def test_taxa_impossivel_e_anulada_nao_propagada(self, planilha_suja):
        """
        Distorcao de 180% nao existe. Anular em vez de manter evita que a media
        do painel fique errada sem ninguem perceber.
        """
        limpo, rel = t.transformar(planilha_suja, ano=2024)
        linha = limpo[limpo["co_entidade"] == 35000002].iloc[0]
        assert pd.isna(linha["distorcao_idade_serie"])
        assert any("fora do intervalo" in m for m in rel.descartes)

    def test_nome_com_espaco_extra_e_limpo(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2024)
        linha = limpo[limpo["co_entidade"] == 35000001].iloc[0]
        assert linha["nome"] == "Escola A"

    def test_uf_normalizada_para_maiusculas(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2024)
        assert set(limpo["uf"]) == {"SP"}

    def test_rede_e_localizacao_mapeadas(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2024)
        assert set(limpo["rede"]) <= {"estadual", "municipal", "federal", "privada"}
        assert set(limpo["localizacao"]) <= {"urbana", "rural"}

    def test_ano_gravado_em_toda_linha(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2023)
        assert set(limpo["ano"]) == {2023}

    def test_todas_as_colunas_canonicas_presentes(self, planilha_suja):
        limpo, _ = t.transformar(planilha_suja, ano=2024)
        for coluna in t.CANONICAS:
            assert coluna in limpo.columns

    def test_recorte_por_rede(self, planilha_suja):
        limpo, rel = t.transformar(planilha_suja, ano=2024, redes=("estadual",))
        assert set(limpo["rede"]) == {"estadual"}
        assert any("fora do recorte" in m for m in rel.descartes)

    def test_relatorio_tem_resumo_legivel(self, planilha_suja):
        _limpo, rel = t.transformar(planilha_suja, ano=2024)
        resumo = rel.resumo()
        assert "Linhas lidas: 5" in resumo
        assert "Descartes:" in resumo


def test_linha_sem_nenhum_indicador_e_descartada():
    df = pd.DataFrame(
        {
            "CO_ENTIDADE": ["35000009"],
            "SG_UF": ["SP"],
            "Taxa de Aprovação": ["--"],
            "Taxa de Reprovação": ["--"],
            "Taxa de Abandono": ["--"],
            "Distorção Idade-Série": ["--"],
            "INSE": ["--"],
        }
    )
    limpo, rel = t.transformar(df, ano=2024)
    assert len(limpo) == 0
    assert any("sem nenhum indicador" in m for m in rel.descartes)

class TestDeteccaoDeSeparadorDecimal:
    """
    Regressao de um erro real encontrado em 23/09/2026.

    A primeira versao removia todo ponto, assumindo separador de milhar. As
    planilhas de taxas de rendimento do INEP usam ponto como separador decimal,
    e "79.8" virava 798. O numero resultante era valido, entao nada falhava: as
    taxas do painel ficariam dez vezes maiores sem aviso nenhum.
    """

    def _converter(self, valores):
        return t._para_numero(pd.Series(valores, dtype="object"))

    def test_ponto_como_decimal_preservado(self):
        """Formato das planilhas de rendimento do INEP."""
        saida = self._converter(["79.8", "0.3", "100", "1.7"])
        assert list(saida) == pytest.approx([79.8, 0.3, 100.0, 1.7])

    def test_virgula_como_decimal_convertida(self):
        saida = self._converter(["79,8", "0,3", "100"])
        assert list(saida) == pytest.approx([79.8, 0.3, 100.0])

    def test_formato_brasileiro_com_milhar_e_decimal(self):
        saida = self._converter(["1.234,56", "12.000,00"])
        assert list(saida) == pytest.approx([1234.56, 12000.0])

    def test_marcadores_de_ausente(self):
        saida = self._converter(["--", "-", "ND", "nd", "", "...", None])
        assert saida.isna().all()

    def test_percentual_com_simbolo(self):
        assert self._converter(["79.8%"]).iloc[0] == pytest.approx(79.8)

    def test_texto_invalido_vira_ausente(self):
        assert self._converter(["abc"]).isna().all()


def test_soma_das_tres_taxas_fica_proxima_de_cem():
    """
    Validacao de sanidade sobre dados reais do INEP: aprovacao, reprovacao e
    abandono sao partes de um todo e somam 100 por escola. Se a conversao
    numerica quebrar, esta soma deixa de fechar, e e o sinal mais barato de que
    algo saiu errado no ETL.
    """
    df = pd.DataFrame(
        {
            "CO_ENTIDADE": ["11024682", "11024968"],
            "SG_UF": ["RO", "RO"],
            "NO_DEPENDENCIA": ["Estadual", "Estadual"],
            "1_CAT_MED": ["98", "97.5"],
            "2_CAT_MED": ["1.7", "2.5"],
            "3_CAT_MED": ["0.3", "0"],
        }
    )
    limpo, _ = t.transformar(df, ano=2023, mapa=t.mapa_etapa("MED"))
    soma = limpo["taxa_aprovacao"] + limpo["taxa_reprovacao"] + limpo["taxa_abandono"]
    assert soma.tolist() == pytest.approx([100.0, 100.0])


class TestMapaDeEtapa:
    def test_ensino_medio(self):
        m = t.mapa_etapa("MED")
        assert m["3catmed"] == "taxa_abandono"
        assert m["1catmed"] == "taxa_aprovacao"

    def test_ensino_fundamental(self):
        assert t.mapa_etapa("FUN")["3catfun"] == "taxa_abandono"

    def test_codigo_real_do_inep_e_reconhecido(self):
        """3_CAT_MED normalizado precisa cair no mapa da etapa."""
        assert t.normalizar_nome("3_CAT_MED") in t.mapa_etapa("MED")
