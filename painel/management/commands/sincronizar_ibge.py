"""
Sincroniza municipios a partir da API de localidades do IBGE.

Este e o consumo de API externa exigido pelo enunciado do PI. A resposta e
gravada na tabela Municipio e reaproveitada pelo painel; a API nao e chamada a
cada requisicao.
"""

from django.core.management.base import BaseCommand, CommandError

from painel.ibge import ErroIBGE, sincronizar_municipios


class Command(BaseCommand):
    help = "Baixa municipios da API do IBGE e grava no banco (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--uf",
            action="append",
            dest="ufs",
            help="Sincroniza apenas esta UF. Pode repetir. Sem o parametro, baixa o pais todo.",
        )

    def handle(self, *args, **opcoes):
        ufs = opcoes.get("ufs") or [None]
        total_criados = total_atualizados = 0

        for uf in ufs:
            alvo = uf.upper() if uf else "todo o pais"
            self.stdout.write(f"Consultando a API do IBGE para {alvo}...")
            try:
                criados, atualizados = sincronizar_municipios(uf=uf.upper() if uf else None)
            except ErroIBGE as exc:
                raise CommandError(str(exc)) from exc
            total_criados += criados
            total_atualizados += atualizados
            self.stdout.write(f"  {criados} criados, {atualizados} atualizados")

        self.stdout.write(
            self.style.SUCCESS(
                f"IBGE sincronizado: {total_criados} criados, {total_atualizados} atualizados"
            )
        )
