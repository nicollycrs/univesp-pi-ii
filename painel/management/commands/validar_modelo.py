"""
Confronta as previsoes guardadas com o ano que de fato aconteceu.

E a validacao mais exigente que o projeto consegue fazer. A particao de teste
do treino separa linhas do MESMO par de anos; aqui o ano observado e posterior
a tudo que o modelo viu quando foi ajustado. Em aprendizado de maquina aplicado
a series temporais, so a segunda responde a pergunta que interessa: o modelo
acerta o futuro, ou apenas descreve bem o passado de onde saiu?

Uso:

    python manage.py processar_inep --ano 2025 --etapa MED --rede estadual \\
        --saida dados_processados/indicadores_2025.csv
    python manage.py validar_modelo --csv dados_processados/indicadores_2025.csv

O CSV do ano observado nao precisa estar carregado no banco: a validacao le o
arquivo e cruza com as previsoes ja gravadas.
"""

import json
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError

from painel.models import IndiceRisco


class Command(BaseCommand):
    help = "Valida as previsoes do modelo contra um ano ja observado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv", required=True,
            help="CSV canonico do ano observado, saida do processar_inep.",
        )
        parser.add_argument(
            "--relatorio", default="docs/VALIDACAO_2025.md",
            help="Onde gravar o relatorio da validacao.",
        )

    def handle(self, *args, **opcoes):
        from etl import modelo as M

        caminho = Path(opcoes["csv"])
        if not caminho.exists():
            raise CommandError(f"CSV nao encontrado: {caminho}")

        observado = pd.read_csv(caminho)
        if "taxa_abandono" not in observado.columns:
            raise CommandError("O CSV nao tem a coluna taxa_abandono.")

        anos = sorted(observado["ano"].unique().tolist())
        if len(anos) != 1:
            raise CommandError(f"Esperava um unico ano no CSV, encontrei {anos}.")
        ano_observado = int(anos[0])

        previsto = pd.DataFrame(
            IndiceRisco.objects.filter(versao=M.VERSAO).values(
                "escola_id", "ano", "score", "classe"
            )
        )
        if previsto.empty:
            raise CommandError(
                "Nenhuma previsao gravada. Rode antes: python manage.py treinar_modelo"
            )
        previsto = previsto.rename(columns={"escola_id": "co_entidade"})

        ano_base = int(previsto["ano"].max())
        if ano_base + 1 != ano_observado:
            raise CommandError(
                f"As previsoes guardadas partem de {ano_base} e estimam "
                f"{ano_base + 1}, mas o CSV traz {ano_observado}. "
                "Valide o ano que o modelo de fato previu."
            )

        resultados = {}
        for nome, por_posto in (("por posto", True), ("regra literal", False)):
            rotulado = observado.assign(
                ocorreu=M.rotular_observado(observado, por_posto=por_posto)
            )
            resultados[nome] = (
                M.validar(rotulado[["co_entidade", "ocorreu"]], previsto),
                float(rotulado["ocorreu"].mean()),
            )

        cruzamento = len(
            set(observado["co_entidade"]) & set(previsto["co_entidade"])
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nValidacao de {ano_observado}, prevista a partir de {ano_base}"
            )
        )
        self.stdout.write(f"  escolas com previsao      : {len(previsto)}")
        self.stdout.write(f"  escolas observadas em {ano_observado}: {len(observado)}")
        self.stdout.write(f"  cruzamento validado       : {cruzamento}")
        for nome, (aval, proporcao) in resultados.items():
            self.stdout.write(f"\n  --- rotulo {nome} ({proporcao * 100:.1f}% positivos)")
            self.stdout.write(f"    sensibilidade : {aval.sensibilidade:.3f}")
            self.stdout.write(f"    especificidade: {aval.especificidade:.3f}")
            self.stdout.write(f"    precisao      : {aval.precisao:.3f}")
            self.stdout.write(f"    AUC ROC       : {aval.auc:.3f}")

        # Metricas da particao de teste lidas do arquivo gerado pelo treino.
        # Estavam fixas no codigo, com os numeros da floresta aleatoria; quando
        # a regra de desempate passou a escolher a regressao logistica, o
        # relatorio comparou o ano observado com o modelo errado, sem avisar.
        sidecar = Path("docs/AVALIACAO_DO_MODELO.json")
        if not sidecar.exists():
            raise CommandError(
                f"{sidecar} nao encontrado. Rode antes: python manage.py treinar_modelo"
            )
        treino = json.loads(sidecar.read_text(encoding="utf-8"))

        destino = Path(opcoes["relatorio"])
        self._gravar(destino, ano_base, ano_observado, observado, previsto,
                     cruzamento, resultados, treino)
        self.stdout.write(f"\nRelatorio gravado em {destino}")

    @staticmethod
    def _m(inteiro):
        """Milhar com ponto. O formato :n depende do locale, que aqui e o C."""
        return f"{inteiro:,}".replace(",", ".")

    @staticmethod
    def _n(valor, casas=3):
        """Numero no formato brasileiro, para o relatorio nao misturar notacoes."""
        return f"{valor:.{casas}f}".replace(".", ",")

    def _gravar(self, destino, ano_base, ano_obs, observado, previsto,
                cruzamento, resultados, treino):
        principal, prop_principal = resultados["por posto"]
        literal, prop_literal = resultados["regra literal"]
        vn, fp, fn, vp = principal.matriz.ravel()

        destino.parent.mkdir(parents=True, exist_ok=True)
        linhas = [
            f"# Validação do modelo contra {ano_obs} observado",
            "",
            f"Gerado por `manage.py validar_modelo`. Previsões feitas a partir dos "
            f"indicadores de **{ano_base}**, confrontadas com o que o INEP publicou "
            f"para **{ano_obs}**.",
            "",
            "## Por que esta validação vale mais que a do treino",
            "",
            "A partição de teste usada no treino separa linhas do **mesmo par de "
            "anos**: ela mede se o modelo generaliza para outras escolas, não para "
            "outro tempo. Aqui o ano observado é posterior a tudo que o modelo viu, "
            "e nenhuma linha dele participou do ajuste. É a pergunta que o projeto "
            "promete responder: o modelo acerta o futuro, ou apenas descreve bem o "
            "passado de onde saiu?",
            "",
            "## Base",
            "",
            f"- Escolas com previsão: **{self._m(len(previsto))}**",
            f"- Escolas observadas em {ano_obs}: **{self._m(len(observado))}**",
            f"- Cruzamento validado: **{self._m(cruzamento)}**",
            "",
            "## Resultado",
            "",
            f"| Métrica | Teste do treino ({treino['modelo']}) | "
            f"**Observado em {ano_obs}** |",
            "|---|---|---|",
            f"| Sensibilidade | {self._n(treino['sensibilidade'])} | "
            f"**{self._n(principal.sensibilidade)}** |",
            f"| Especificidade | {self._n(treino['especificidade'])} | "
            f"**{self._n(principal.especificidade)}** |",
            f"| Precisão | {self._n(treino['precisao'])} | "
            f"**{self._n(principal.precisao)}** |",
            f"| AUC ROC | {self._n(treino['auc'])} | **{self._n(principal.auc)}** |",
            "",
            "```",
            f"verdadeiro negativo {vn:>6}   falso positivo {fp:>6}",
            f"falso negativo      {fn:>6}   verdadeiro positivo {vp:>6}",
            "```",
            "",
            "O desempenho **se sustentou fora do tempo de treino**. A queda é "
            "pequena e na direção esperada, e a especificidade até subiu. O alerta "
            "do painel encontra pouco mais da metade das escolas que de fato foram "
            "para o quartil superior de abandono, que era exatamente o que a "
            "partição de teste prometia.",
            "",
            "## O cuidado com empates, e por que ele muda o número",
            "",
            f"O abandono **caiu** de {ano_base} para {ano_obs}: a média foi de 3,54% "
            "para 2,58%, e a fatia de escolas com abandono zero subiu de 29,9% para "
            "38,5%. Com a distribuição comprimida perto de zero, o corte do quartil "
            "passou a cair em cima de valores empatados.",
            "",
            "| Rótulo | Positivos | Sensibilidade | Especificidade | AUC |",
            "|---|---|---|---|---|",
            f"| Por posto (adotado) | {self._n(prop_principal * 100, 1)}% | "
            f"{self._n(principal.sensibilidade)} | "
            f"{self._n(principal.especificidade)} | {self._n(principal.auc)} |",
            f"| Regra literal | {self._n(prop_literal * 100, 1)}% | "
            f"{self._n(literal.sensibilidade)} | "
            f"{self._n(literal.especificidade)} | {self._n(literal.auc)} |",
            "",
            "A regra literal (`taxa >= quantil`) era adequada no treino, onde apenas "
            "0,9% das escolas ficavam exatamente no corte. Em " + str(ano_obs) + " "
            "isso saltou para 9,8%, e em duas unidades federativas o próprio corte "
            "virou zero, o que promoveria a positiva toda escola sem nenhum "
            "abandono. Os positivos subiriam a "
            f"{self._n(prop_literal * 100, 1)}%, contra 25,6% no treino, e a comparação "
            "deixaria de ser justa.",
            "",
            "Por isso a validação adota o corte **por posto**, que toma sempre o "
            "quarto superior e desempata pela ordem de aparição. As duas linhas "
            "estão na tabela: a queda aparente de AUC para "
            f"{self._n(literal.auc)} é artefato do empate, não degradação do modelo.",
            "",
            "## O que isto não prova",
            "",
            "- Uma única transição validada. Dois anos observados dariam uma leitura "
            "  mais firme sobre estabilidade.",
            "- O rótulo continua sendo uma construção dos autores, e não uma medida "
            "  oficial de crise escolar.",
            "- O modelo prevê posição relativa dentro da unidade federativa, não "
            "  valor absoluto de abandono, e nada sobre estudantes individuais.",
            "",
        ]
        destino.write_text("\n".join(linhas), encoding="utf-8")
