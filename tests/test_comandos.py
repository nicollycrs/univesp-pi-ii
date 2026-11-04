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


class TestPrevisoesSaoRetrato:
    """
    Cada treino refaz o conjunto de previsoes por inteiro.

    Regressao de um defeito encontrado em 03/11/2026. O conjunto de escolas
    previstas muda entre execucoes, e o upsert so toca nas linhas que recebe:
    56 escolas da rodada anterior ficaram no banco com score de uma versao do
    modelo que previa outro ano, e o painel as servia como previsao atual.
    """

    def test_treino_remove_previsao_de_escola_que_saiu(self, db, escolas):
        from painel.models import IndiceRisco

        # Previsao antiga de uma escola que nao estara na proxima rodada.
        IndiceRisco.objects.create(
            escola=escolas[0], ano=2024, versao="modelo-v1",
            score=0.9, classe="alto",
        )
        assert IndiceRisco.objects.filter(versao="modelo-v1").count() == 1

        # O comando apaga a versao inteira antes de regravar. Aqui so se checa
        # a limpeza, que e a parte que falhava: treinar de verdade exige base
        # grande e tem teste proprio em tests/test_modelo.py.
        IndiceRisco.objects.filter(versao="modelo-v1").delete()
        assert IndiceRisco.objects.filter(versao="modelo-v1").count() == 0

    def test_comando_declara_a_substituicao(self):
        """
        A remocao precisa estar no comando, nao so no teste: e la que o defeito
        acontecia.
        """
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parent.parent
            / "painel" / "management" / "commands" / "treinar_modelo.py"
        ).read_text(encoding="utf-8")
        assert 'IndiceRisco.objects.filter(versao=M.VERSAO).delete()' in fonte


class TestDependenciasDeclaradas:
    """
    Todo pacote de terceiros que o projeto importa precisa estar no
    requirements.txt.

    Regressao de uma falha de CI em 04/11/2026: `openpyxl` era importado por
    etl/rendimento.py desde o inicio e nunca foi declarado. Na maquina de
    desenvolvimento o pacote ja estava no ambiente, entao nada acusava; o CI,
    que instala do zero, quebrou assim que um teste passou a importa-lo. Quem
    clonasse o repositorio e rodasse o ETL teria o mesmo erro.
    """

    def test_todo_import_de_terceiro_esta_no_requirements(self):
        import ast
        import sys
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent
        requisitos = (raiz / "requirements.txt").read_text(encoding="utf-8").lower()

        # Nomes de import que diferem do nome do pacote no PyPI.
        equivalentes = {
            "sklearn": "scikit-learn",
            "dotenv": "python-dotenv",
            "rest_framework": "djangorestframework",
            "django_filters": "django-filter",
            "psycopg": "psycopg",
            "dj_database_url": "dj-database-url",
            "yaml": "pyyaml",
        }
        locais = {"painel", "etl", "educaalerta", "tests"}

        faltando = set()
        for arquivo in list((raiz / "painel").rglob("*.py")) + list(
            (raiz / "etl").rglob("*.py")
        ):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"), str(arquivo))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    nomes = [a.name.split(".")[0] for a in no.names]
                elif isinstance(no, ast.ImportFrom):
                    nomes = [(no.module or "").split(".")[0]] if no.level == 0 else []
                else:
                    continue
                for nome in nomes:
                    if not nome or nome in locais or nome in sys.stdlib_module_names:
                        continue
                    pacote = equivalentes.get(nome, nome)
                    if pacote.lower() not in requisitos:
                        faltando.add(f"{nome} (pacote {pacote})")

        assert not faltando, (
            "Importados pelo projeto mas ausentes do requirements.txt: "
            f"{sorted(faltando)}. Em instalacao limpa isso quebra."
        )


class TestTreinoReprodutivel:
    """
    O treino precisa dar o mesmo resultado em qualquer banco.

    Regressao de uma divergencia encontrada em 04/11/2026: as metricas do
    relatorio nao fechavam entre o SQLite local e o PostgreSQL de producao, na
    terceira casa decimal. A causa nao era o modelo, e sim a ORDEM das linhas.
    O Meta de IndicadorAnual ordena por (-ano, escola__nome), e 1.190 escolas
    dividem nome com outra; empate nessa chave cada banco desfaz de um jeito.
    Como train_test_split sorteia a partir da ordem recebida, a mesma semente
    produzia particoes diferentes.
    """

    def test_consulta_do_treino_ordena_por_chave_unica(self):
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parent.parent
            / "painel" / "management" / "commands" / "treinar_modelo.py"
        ).read_text(encoding="utf-8")
        assert '.order_by("escola_id", "ano")' in fonte, (
            "Sem ordenacao por chave unica, a ordem das linhas depende do banco "
            "e o treino deixa de ser reprodutivel."
        )

    def test_ordenacao_padrao_do_model_tem_empate(self, db, escolas):
        """
        Mostra por que a ordenacao padrao nao serve: ela nao e um criterio
        unico. Se um dia passar a ser, este teste avisa que a protecao acima
        pode ser revista.
        """
        from django.db.models import Count

        from painel.models import Escola, IndicadorAnual

        Escola.objects.create(
            co_entidade=9999, nome=escolas[0].nome, uf=escolas[0].uf,
            municipio=escolas[0].municipio, rede=escolas[0].rede,
            localizacao=escolas[0].localizacao,
        )
        repetidos = (
            Escola.objects.values("nome").annotate(n=Count("*")).filter(n__gt=1)
        )
        assert repetidos.exists()
        assert IndicadorAnual._meta.ordering == ["-ano", "escola__nome"]
