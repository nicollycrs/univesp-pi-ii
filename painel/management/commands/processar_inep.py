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
from etl.transformar import CANONICAS, mapa_distorcao, mapa_etapa, transformar

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
            self.stdout.write(f"  {len(cru)} linhas lidas da planilha de rendimento")

            mapa = dict(mapa_etapa(etapa))

            # A distorcao idade-serie vem de outra planilha do INEP, com a mesma
            # estrutura mas codigos de coluna proprios. Quando o arquivo existe,
            # e unida ao rendimento pelo codigo da escola; quando nao existe, o
            # indice simplesmente redistribui o peso desse componente.
            caminho_tdi = rendimento.caminho_distorcao(ano)
            if caminho_tdi.exists():
                mapa_tdi = mapa_distorcao(etapa)
                cru_tdi = rendimento.ler(caminho_tdi, etapa=etapa, mapa=mapa_tdi)
                coluna = next(
                    c for c in cru_tdi.columns
                    if c not in ("CO_ENTIDADE", "NO_ENTIDADE", "SG_UF", "CO_MUNICIPIO",
                                 "NO_DEPENDENCIA", "NO_CATEGORIA", "NU_ANO_CENSO")
                )
                antes = len(cru)
                cru = cru.merge(
                    cru_tdi[["CO_ENTIDADE", coluna]], on="CO_ENTIDADE", how="left"
                )
                mapa.update(mapa_tdi)
                self.stdout.write(
                    f"  {len(cru_tdi)} linhas de distorcao idade-serie unidas "
                    f"({antes} linhas de rendimento preservadas)"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  distorcao idade-serie nao encontrada em {caminho_tdi}; "
                        "o indice vai redistribuir o peso desse componente"
                    )
                )

            limpo, rel = transformar(cru, ano=ano, mapa=mapa, redes=redes)
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
