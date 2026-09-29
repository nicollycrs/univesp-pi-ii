"""
Calcula o indice de risco para os indicadores carregados e grava em IndiceRisco.

Idempotente pela restricao unica de (escola, ano, versao): recalcular sobrescreve
o valor daquela versao, em vez de acumular duplicatas.

A gravacao e em lote pelo mesmo motivo do carregar_dados: com 40 mil escolas, um
upsert por linha significa 40 mil idas ao banco, o que levava quase um minuto em
SQLite local e seria pior ainda contra o Neon.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from painel import risco
from painel.models import IndicadorAnual, IndiceRisco


class Command(BaseCommand):
    help = "Calcula o indice de risco escolar a partir dos indicadores no banco."

    def add_arguments(self, parser):
        parser.add_argument("--ano", type=int, help="Calcula so este ano.")
        parser.add_argument("--uf", help="Calcula so esta unidade federativa.")

    def handle(self, *args, **opcoes):
        qs = IndicadorAnual.objects.select_related("escola")
        if opcoes.get("ano"):
            qs = qs.filter(ano=opcoes["ano"])
        if opcoes.get("uf"):
            qs = qs.filter(escola__uf=opcoes["uf"].upper())

        registros = [
            {
                "co_entidade": i.escola_id,
                "uf": i.escola.uf,
                "ano": i.ano,
                "taxa_abandono": i.taxa_abandono,
                "taxa_reprovacao": i.taxa_reprovacao,
                "distorcao_idade_serie": i.distorcao_idade_serie,
                "inse": i.inse,
            }
            for i in qs
        ]

        if not registros:
            self.stdout.write(
                self.style.WARNING(
                    "Nenhum indicador encontrado. Rode antes: python manage.py carregar_dados"
                )
            )
            return

        calculados = risco.calcular(registros)
        sem_score = sum(1 for r in calculados if r["score"] is None)

        objetos = [
            IndiceRisco(
                escola_id=r["co_entidade"],
                ano=r["ano"],
                versao=r["versao"],
                score=r["score"],
                classe=r["classe"],
            )
            for r in calculados
            if r["score"] is not None
        ]

        with transaction.atomic():
            IndiceRisco.objects.bulk_create(
                objetos,
                batch_size=2000,
                update_conflicts=True,
                update_fields=["score", "classe"],
                unique_fields=["escola", "ano", "versao"],
            )
        gravados = len(objetos)

        distribuicao = {
            c: IndiceRisco.objects.filter(classe=c, versao=risco.VERSAO).count()
            for c in (risco.CLASSE_ALTO, risco.CLASSE_MEDIO, risco.CLASSE_BAIXO)
        }

        self.stdout.write(
            self.style.SUCCESS(
                f"Indice {risco.VERSAO} calculado\n"
                f"  {gravados} gravados, {sem_score} sem indicador suficiente\n"
                f"  risco alto: {distribuicao[risco.CLASSE_ALTO]}\n"
                f"  risco medio: {distribuicao[risco.CLASSE_MEDIO]}\n"
                f"  risco baixo: {distribuicao[risco.CLASSE_BAIXO]}"
            )
        )
