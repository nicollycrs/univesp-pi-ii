"""
Testes dos comandos de gestao.

O ponto critico e a idempotencia: carregar duas vezes nao pode duplicar registro.
Sem isso, uma recarga durante o deploy inflaria os numeros do painel.
"""

import csv

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from painel.models import Escola, IndicadorAnual, IndiceRisco

LINHAS = [
    {
        "co_entidade": "35000001", "nome": "Escola Alfa", "uf": "SP",
        "codigo_municipio": "3550308", "rede": "estadual", "localizacao": "urbana",
        "ano": "2024", "taxa_aprovacao": "85.0", "taxa_reprovacao": "10.0",
        "taxa_abandono": "5.0", "distorcao_idade_serie": "15.0", "inse": "55.0",
        "origem": "INEP",
    },
    {
        "co_entidade": "35000002", "nome": "Escola Beta", "uf": "SP",
        "codigo_municipio": "3550308", "rede": "estadual", "localizacao": "rural",
        "ano": "2024", "taxa_aprovacao": "70.0", "taxa_reprovacao": "18.0",
        "taxa_abandono": "12.0", "distorcao_idade_serie": "35.0", "inse": "38.0",
        "origem": "INEP",
    },
]


@pytest.fixture
def csv_indicadores(tmp_path):
    caminho = tmp_path / "indicadores.csv"
    with caminho.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(LINHAS[0]))
        escritor.writeheader()
        escritor.writerows(LINHAS)
    return caminho


class TestCarregarDados:
    def test_carrega_escolas_e_indicadores(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        assert Escola.objects.count() == 2
        assert IndicadorAnual.objects.count() == 2
        escola = Escola.objects.get(pk=35000001)
        assert escola.nome == "Escola Alfa"
        assert escola.municipio_id == "3550308"

    def test_e_idempotente(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        call_command("carregar_dados", str(csv_indicadores))
        assert Escola.objects.count() == 2
        assert IndicadorAnual.objects.count() == 2

    def test_arquivo_inexistente_da_erro_com_orientacao(self, db):
        with pytest.raises(CommandError, match="gerar_amostra"):
            call_command("carregar_dados", "nao/existe.csv")

    def test_municipio_fora_do_cache_nao_impede_a_carga(self, db, csv_indicadores):
        """Sem o IBGE sincronizado a escola entra sem municipio, e nao falha."""
        call_command("carregar_dados", str(csv_indicadores))
        assert Escola.objects.count() == 2
        assert Escola.objects.filter(municipio__isnull=True).count() == 2

    def test_marca_origem_de_amostra(self, db, tmp_path):
        linha = dict(LINHAS[0], origem="AMOSTRA")
        caminho = tmp_path / "amostra.csv"
        with caminho.open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(linha))
            escritor.writeheader()
            escritor.writerow(linha)
        call_command("carregar_dados", str(caminho))
        assert IndicadorAnual.objects.filter(origem="AMOSTRA").count() == 1

    def test_limpar_apaga_antes_de_carregar(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        call_command("carregar_dados", str(csv_indicadores), limpar=True)
        assert IndicadorAnual.objects.count() == 2


class TestCalcularRisco:
    def test_gera_indices(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        call_command("calcular_risco")
        assert IndiceRisco.objects.count() == 2

    def test_e_idempotente(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        call_command("calcular_risco")
        call_command("calcular_risco")
        assert IndiceRisco.objects.count() == 2

    def test_escola_pior_recebe_score_maior(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        call_command("calcular_risco")
        alfa = IndiceRisco.objects.get(escola_id=35000001)
        beta = IndiceRisco.objects.get(escola_id=35000002)
        assert beta.score > alfa.score

    def test_sem_indicadores_avisa_e_nao_quebra(self, db, capsys):
        call_command("calcular_risco")
        assert "carregar_dados" in capsys.readouterr().out

    def test_filtra_por_ano(self, db, municipio, csv_indicadores):
        call_command("carregar_dados", str(csv_indicadores))
        call_command("calcular_risco", ano=2023)
        assert IndiceRisco.objects.count() == 0


class TestGerarAmostra:
    def test_gera_csv_marcado_como_amostra(self, db, tmp_path):
        saida = tmp_path / "AMOSTRA_DESENVOLVIMENTO.csv"
        call_command("gerar_amostra", escolas=10, saida=str(saida))
        assert saida.exists()
        with saida.open(encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        assert len(linhas) == 20  # 10 escolas x 2 anos
        assert all(l["origem"] == "AMOSTRA" for l in linhas)

    def test_pipeline_completo_da_amostra(self, db, tmp_path):
        """Gerar, carregar e calcular risco: o caminho de desenvolvimento inteiro."""
        saida = tmp_path / "amostra.csv"
        call_command("gerar_amostra", escolas=30, saida=str(saida))
        call_command("carregar_dados", str(saida))
        call_command("calcular_risco")
        assert Escola.objects.count() == 30
        assert IndicadorAnual.objects.count() == 60
        assert IndiceRisco.objects.count() == 60
        # Com 30 escolas e dois anos os tres niveis precisam aparecer.
        assert set(IndiceRisco.objects.values_list("classe", flat=True)) == {
            "alto", "medio", "baixo"
        }
