"""
Confere se os portais das fontes de dados ainda respondem.

Nao baixa arquivo: so verifica se o endereco de partida esta de pe, para que a
equipe descubra cedo que uma fonte mudou de lugar, e nao na vespera da entrega.
"""

import requests
from django.core.management.base import BaseCommand

from etl.fontes import FONTES


class Command(BaseCommand):
    help = "Verifica a disponibilidade dos portais das fontes de dados."

    def handle(self, *args, **opcoes):
        problemas = 0
        for fonte in FONTES:
            try:
                resposta = requests.head(
                    fonte.portal, timeout=15, allow_redirects=True,
                    headers={"User-Agent": "EducaAlerta/1.0 (PI-2 Univesp)"},
                )
                codigo = resposta.status_code
                if codigo >= 400:
                    resposta = requests.get(fonte.portal, timeout=20, stream=True)
                    codigo = resposta.status_code
                situacao = "ok" if codigo < 400 else f"ATENCAO ({codigo})"
                problemas += codigo >= 400
            except requests.RequestException as exc:
                situacao = f"FALHOU ({type(exc).__name__})"
                problemas += 1
            self.stdout.write(f"  [{situacao}] {fonte.chave}: {fonte.portal}")

        if problemas:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{problemas} fonte(s) com problema. Registre em docs/FONTES_DE_DADOS.md "
                    "a nova URL ou a indisponibilidade. Nao substitua dado oficial por dado gerado."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nTodas as fontes responderam."))
