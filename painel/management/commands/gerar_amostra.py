"""
Gera o CSV de amostra para desenvolvimento.

ATENCAO: os dados NAO SAO REAIS. Servem para desenvolver e testar a aplicacao
enquanto os arquivos oficiais do INEP nao estao mapeados. Toda linha sai marcada
com origem AMOSTRA, e o painel exibe aviso enquanto houver amostra na base.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

NOME_PADRAO = "dados_processados/AMOSTRA_DESENVOLVIMENTO.csv"


class Command(BaseCommand):
    help = "Gera um CSV de amostra (dados NAO reais) para desenvolvimento."

    def add_arguments(self, parser):
        parser.add_argument("--escolas", type=int, default=400)
        parser.add_argument("--saida", default=NOME_PADRAO)

    def handle(self, *args, **opcoes):
        from etl.amostra import gerar

        df = gerar(n_escolas=opcoes["escolas"])
        saida = Path(opcoes["saida"])
        saida.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(saida, index=False, encoding="utf-8")

        self.stdout.write(
            self.style.WARNING(
                f"AMOSTRA gerada em {saida} com {len(df)} linhas.\n"
                "Estes dados NAO SAO REAIS e nao podem ser citados como resultado."
            )
        )
        self.stdout.write(f"Carregue com: python manage.py carregar_dados {saida}")
