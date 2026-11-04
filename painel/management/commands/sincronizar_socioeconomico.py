"""
Preenche o contexto socioeconomico dos municipios a partir da API do IBGE.

Ocupa a vaga que seria do INSE do INEP no indice de risco. O INSE por escola nao
e publicado de forma cruzavel: esta nos microdados do Saeb 2023, mas com os
codigos de escola mascarados por LGPD. A justificativa completa da substituicao
esta em docs/FONTES_DE_DADOS.md.

Rodar depois de sincronizar_ibge e antes de calcular_risco:

    python manage.py sincronizar_ibge
    python manage.py sincronizar_socioeconomico
    python manage.py calcular_risco
"""

from django.core.management.base import BaseCommand, CommandError

from painel import ibge
from painel.models import Municipio


class Command(BaseCommand):
    help = "Busca o salario medio municipal no IBGE e grava nos municipios."

    def add_arguments(self, parser):
        parser.add_argument("--uf", help="Sincroniza so esta unidade federativa.")

    def handle(self, *args, **opcoes):
        uf = opcoes.get("uf")
        if not Municipio.objects.exists():
            raise CommandError(
                "Nenhum municipio no banco. Rode antes: python manage.py sincronizar_ibge"
            )

        self.stdout.write("Consultando o IBGE (pode levar um minuto)...")
        try:
            preenchidos, sem_dado = ibge.sincronizar_salario_medio(uf=uf)
        except ibge.ErroIBGE as erro:
            raise CommandError(str(erro)) from erro

        # order_by() vazio antes de distinct(): o Meta do Municipio ordena por
        # uf e nome, e sem isso o distinct passa a operar sobre a tupla
        # (uf, nome, ano) e devolve um ano por municipio. Mesmo defeito que ja
        # inchou o seletor de UF do painel para 19.776 opcoes.
        anos = sorted(
            Municipio.objects.exclude(salario_medio_ano__isnull=True)
            .order_by()
            .values_list("salario_medio_ano", flat=True)
            .distinct()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Contexto socioeconomico sincronizado\n"
                f"  {preenchidos} municipios preenchidos\n"
                f"  {sem_dado} sem dado publicado\n"
                f"  anos de referencia: {anos}"
            )
        )
        self.stdout.write("\nProximo passo: python manage.py calcular_risco")
