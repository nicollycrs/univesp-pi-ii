"""
Processa as planilhas de Taxas de Rendimento Escolar do INEP e gera o CSV canonico.

Roda na maquina local, nunca na nuvem: le arquivos de 39 MB e consolida cerca de
128 mil escolas por ano. Para a nuvem sobe apenas o CSV agregado que sai daqui.

Uso:
    python manage.py processar_inep --ano 2023 --ano 2024 --etapa MED --rede estadual

Antes de rodar, baixar e descompactar em dados_brutos/:
    https://download.inep.gov.br/informacoes_estatisticas/indicadores_educacionais/{ano}/tx_rend_escolas_{ano}.zip
"""

from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from etl import rendimento
from etl.transformar import CANONICAS, mapa_etapa, transformar

SAIDA_PADRAO = "dados_processados/indicadores.csv"


class Command(BaseCommand):
    help = "Le as planilhas do INEP em dados_brutos/ e gera o CSV canonico."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ano", type=int, action="append", dest="anos", required=True,
            help="Ano a processar. Pode repetir.",
        )
        parser.add_argument(
            "--etapa", default="MED",
            help="Etapa de ensino: MED para ensino medio, FUN para fundamental.",
        )
        parser.add_argument(
            "--rede", action="append", dest="redes",
            help="Filtra a rede: estadual, municipal, federal ou privada. Pode repetir.",
        )
        parser.add_argument("--saida", default=SAIDA_PADRAO)
        parser.add_argument(
            "--relatorio", default="docs/RELATORIO_ETL.md",
            help="Onde gravar o relatorio de qualidade dos dados.",
        )

    def handle(self, *args, **opcoes):
        etapa = opcoes["etapa"].upper()
        redes = tuple(opcoes["redes"]) if opcoes.get("redes") else None
        partes, relatorios = [], []

        for ano in opcoes["anos"]:
            caminho = rendimento.caminho_padrao(ano)
            if not caminho.exists():
                raise CommandError(
                    f"Planilha nao encontrada: {caminho}\n"
                    f"Baixe e descompacte em dados_brutos/:\n"
                    f"  https://download.inep.gov.br/informacoes_estatisticas/"
                    f"indicadores_educacionais/{ano}/tx_rend_escolas_{ano}.zip"
                )

            self.stdout.write(f"Lendo {caminho.name} (etapa {etapa})...")
            cru = rendimento.ler(caminho, etapa=etapa)
            self.stdout.write(f"  {len(cru)} linhas lidas da planilha")

            limpo, rel = transformar(
                cru, ano=ano, mapa=mapa_etapa(etapa), redes=redes
            )
            self.stdout.write(f"  {len(limpo)} linhas validas apos a limpeza")
            partes.append(limpo)
            relatorios.append((ano, rel))

        consolidado = pd.concat(partes, ignore_index=True)
        consolidado["origem"] = "INEP"

        colunas = [*CANONICAS, "ano", "origem"]
        consolidado = consolidado[[c for c in colunas if c in consolidado.columns]]

        saida = Path(opcoes["saida"])
        saida.parent.mkdir(parents=True, exist_ok=True)
        consolidado.to_csv(saida, index=False, encoding="utf-8")

        self._gravar_relatorio(
            Path(opcoes["relatorio"]), relatorios, consolidado, etapa, redes
        )

        soma = (
            consolidado["taxa_aprovacao"]
            + consolidado["taxa_reprovacao"]
            + consolidado["taxa_abandono"]
        ).dropna()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCSV canonico gravado em {saida}\n"
                f"  linhas: {len(consolidado)}\n"
                f"  escolas distintas: {consolidado['co_entidade'].nunique()}\n"
                f"  anos: {sorted(consolidado['ano'].unique().tolist())}\n"
                f"  UFs: {consolidado['uf'].nunique()}"
            )
        )
        # Validacao de sanidade: as tres taxas sao partes de um todo e somam 100.
        # Se esta media fugir de 100, a conversao numerica quebrou.
        self.stdout.write(
            f"  soma media das tres taxas: {soma.mean():.2f} (esperado 100,00)"
        )
        if abs(soma.mean() - 100) > 1:
            self.stdout.write(
                self.style.ERROR(
                    "  ATENCAO: a soma fugiu de 100. Revise a conversao numerica "
                    "em etl/transformar.py antes de usar estes dados."
                )
            )
        self.stdout.write(f"\nProximo passo: python manage.py carregar_dados {saida}")

    def _gravar_relatorio(self, caminho, relatorios, consolidado, etapa, redes):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        linhas = [
            "# Relatório do ETL",
            "",
            "Gerado por `manage.py processar_inep`. Este arquivo é a prestação de",
            "contas sobre o que a limpeza descartou e por quê.",
            "",
            f"- Etapa de ensino: **{etapa}**",
            f"- Recorte de rede: **{', '.join(redes) if redes else 'todas'}**",
            f"- Linhas no CSV final: **{len(consolidado)}**",
            f"- Escolas distintas: **{consolidado['co_entidade'].nunique()}**",
            "",
        ]
        for ano, rel in relatorios:
            linhas += [f"## {ano}", "", "```", rel.resumo(), "```", ""]
        caminho.write_text("\n".join(linhas), encoding="utf-8")
        self.stdout.write(f"Relatorio de qualidade em {caminho}")
