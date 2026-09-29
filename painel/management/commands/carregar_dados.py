"""
Carrega indicadores de um CSV canonico para o banco.

Idempotente: rodar duas vezes nao duplica registro. A garantia vem de duas
coisas: a restricao unica de (escola, ano) no banco e o uso de upsert em lote.

Por que em lote. A primeira versao usava update_or_create por linha, o que para
40 mil registros significa cerca de 80 mil idas e voltas ao banco. Em SQLite
local isso ja passava de dois minutos; contra o Neon, com latencia de rede em
cada consulta, estouraria o tempo do deploy. bulk_create com update_conflicts
resolve o mesmo problema em poucas instrucoes.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from painel.models import Escola, IndicadorAnual, IndiceRisco, Municipio

NUMERICAS = (
    "taxa_aprovacao",
    "taxa_reprovacao",
    "taxa_abandono",
    "distorcao_idade_serie",
    "inse",
)

LOTE = 2000


def _numero(valor):
    if valor is None:
        return None
    valor = str(valor).strip()
    if valor in ("", "None", "nan", "NA", "<NA>", "nat"):
        return None
    try:
        return float(valor)
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Carrega indicadores escolares de um CSV canonico para o banco."

    def add_arguments(self, parser):
        parser.add_argument(
            "caminho",
            nargs="?",
            default="dados_processados/indicadores.csv",
            help="Caminho do CSV canonico.",
        )
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Apaga indicadores e indices de risco antes de carregar.",
        )

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["caminho"])
        if not caminho.exists():
            raise CommandError(
                f"Arquivo nao encontrado: {caminho}\n"
                "Gere os dados reais com: python manage.py processar_inep --ano 2023 --ano 2024\n"
                "Ou uma amostra de desenvolvimento com: python manage.py gerar_amostra"
            )

        with caminho.open(encoding="utf-8", newline="") as arquivo:
            linhas = list(csv.DictReader(arquivo))
        if not linhas:
            raise CommandError("O CSV esta vazio.")

        self.stdout.write(f"Lendo {len(linhas)} linhas de {caminho}...")

        if opcoes["limpar"]:
            # Apagar tambem os indices: um IndiceRisco calculado sobre dados que
            # nao existem mais e resultado orfao, e apareceria no painel como se
            # fosse valido.
            riscos = IndiceRisco.objects.all().delete()[0]
            indicadores = IndicadorAnual.objects.all().delete()[0]
            self.stdout.write(
                f"Apagados: {indicadores} indicadores e {riscos} indices de risco"
            )

        municipios = set(Municipio.objects.values_list("codigo_ibge", flat=True))
        sem_municipio = 0

        # Uma escola pode aparecer em varios anos; o dicionario deduplica.
        escolas: dict[int, Escola] = {}
        indicadores: list[IndicadorAnual] = []
        descartadas = 0

        for linha in linhas:
            try:
                codigo = int(float(linha["co_entidade"]))
                ano = int(float(linha["ano"]))
            except (KeyError, TypeError, ValueError):
                descartadas += 1
                continue

            codigo_municipio = (linha.get("codigo_municipio") or "").strip()
            municipio_id = codigo_municipio if codigo_municipio in municipios else None
            if codigo_municipio and municipio_id is None:
                sem_municipio += 1

            escolas[codigo] = Escola(
                co_entidade=codigo,
                nome=(linha.get("nome") or "Sem nome").strip()[:200],
                uf=(linha.get("uf") or "").strip().upper()[:2],
                rede=(linha.get("rede") or "").strip() or Escola.Rede.ESTADUAL,
                localizacao=(linha.get("localizacao") or "").strip(),
                municipio_id=municipio_id,
            )

            origem = (linha.get("origem") or IndicadorAnual.Origem.INEP).strip().upper()
            if origem not in IndicadorAnual.Origem.values:
                origem = IndicadorAnual.Origem.INEP

            indicadores.append(
                IndicadorAnual(
                    escola_id=codigo,
                    ano=ano,
                    origem=origem,
                    **{c: _numero(linha.get(c)) for c in NUMERICAS},
                )
            )

        with transaction.atomic():
            Escola.objects.bulk_create(
                list(escolas.values()),
                batch_size=LOTE,
                update_conflicts=True,
                update_fields=["nome", "uf", "rede", "localizacao", "municipio"],
                unique_fields=["co_entidade"],
            )
            IndicadorAnual.objects.bulk_create(
                indicadores,
                batch_size=LOTE,
                update_conflicts=True,
                update_fields=[*NUMERICAS, "origem"],
                unique_fields=["escola", "ano"],
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Carga concluida\n"
                f"  escolas no arquivo: {len(escolas)}\n"
                f"  indicadores no arquivo: {len(indicadores)}\n"
                f"  escolas no banco: {Escola.objects.count()}\n"
                f"  indicadores no banco: {IndicadorAnual.objects.count()}"
            )
        )
        if descartadas:
            self.stdout.write(
                self.style.WARNING(f"  {descartadas} linhas sem codigo ou ano validos")
            )
        if sem_municipio:
            self.stdout.write(
                self.style.WARNING(
                    f"  {sem_municipio} linhas com municipio fora do cache do IBGE. "
                    "Rode: python manage.py sincronizar_ibge"
                )
            )
        if IndicadorAnual.objects.filter(origem=IndicadorAnual.Origem.AMOSTRA).exists():
            self.stdout.write(
                self.style.WARNING(
                    "  A base contem dados de AMOSTRA de desenvolvimento. "
                    "Nao use estes numeros como resultado."
                )
            )
        self.stdout.write("Proximo passo: python manage.py calcular_risco")
