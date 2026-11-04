"""
Treina o modelo preditivo de risco, avalia e grava as previsoes no banco.

Roda na maquina local, nunca na nuvem: importa scikit-learn, que e pesado para
a instancia de 512 MB do plano gratuito. O processo web apenas le do banco as
previsoes ja calculadas, marcadas com a versao `modelo-v1`.

Uso:
    python manage.py treinar_modelo --ano-atributos 2023 --ano-alvo 2024
"""

import json
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from painel.models import IndicadorAnual, IndiceRisco


class Command(BaseCommand):
    help = "Treina o modelo preditivo de abandono, avalia e grava as previsoes."

    def add_arguments(self, parser):
        parser.add_argument("--ano-atributos", type=int, default=2023,
                            help="Ano de onde vem os atributos.")
        parser.add_argument("--ano-alvo", type=int, default=2024,
                            help="Ano de onde vem o rotulo a prever.")
        parser.add_argument("--relatorio", default="docs/AVALIACAO_DO_MODELO.md")
        parser.add_argument("--nao-gravar", action="store_true",
                            help="Treina e avalia, mas nao grava as previsoes.")

    def handle(self, *args, **opcoes):
        from etl import modelo as M

        ano_atr, ano_alvo = opcoes["ano_atributos"], opcoes["ano_alvo"]

        registros = list(
            # order_by por chave UNICA, e nao a ordenacao padrao do model.
            #
            # O Meta ordena por (-ano, escola__nome), e 1.190 escolas dividem
            # nome com outra: "EE DE ENSINO MEDIO" aparece 18 vezes. Empate na
            # chave de ordenacao e resolvido de forma diferente por cada banco,
            # entao a ordem das linhas mudava entre o SQLite local e o
            # PostgreSQL de producao. Como train_test_split sorteia a partir da
            # ordem recebida, o mesmo codigo com a mesma semente treinava
            # modelos ligeiramente diferentes, e as metricas do relatorio nao
            # fechavam entre os dois ambientes.
            IndicadorAnual.objects.select_related("escola")
            .order_by("escola_id", "ano")
            .values(
                "escola_id", "ano", "taxa_abandono", "taxa_reprovacao",
                "escola__municipio__salario_medio",
                "distorcao_idade_serie", "inse", "escola__uf", "escola__localizacao",
            )
        )
        if not registros:
            raise CommandError(
                "Nenhum indicador no banco. Rode antes: python manage.py carregar_dados"
            )

        df = pd.DataFrame(registros).rename(columns={
            "escola_id": "co_entidade",
            "escola__uf": "uf",
            "escola__localizacao": "localizacao",
            "escola__municipio__salario_medio": "contexto_socioeconomico",
        })

        anos = sorted(df["ano"].unique())
        if ano_atr not in anos or ano_alvo not in anos:
            raise CommandError(
                f"A base tem os anos {anos}. Para treinar sao necessarios "
                f"{ano_atr} (atributos) e {ano_alvo} (alvo)."
            )

        self.stdout.write(f"Montando a base: atributos de {ano_atr}, alvo em {ano_alvo}...")
        base = M.montar_base(df, ano_atr, ano_alvo)
        positivos = int(base["alvo"].sum())
        self.stdout.write(
            f"  {len(base)} escolas com os dois anos completos\n"
            f"  {positivos} no quartil superior de abandono em {ano_alvo} "
            f"({positivos / len(base) * 100:.1f}%)"
        )
        if len(base) < 100:
            raise CommandError("Base pequena demais para treinar com confianca.")

        self.stdout.write("\nTreinando e comparando modelos...")
        melhor, aval_melhor, avaliacoes = M.treinar(base)

        for a in avaliacoes:
            self.stdout.write("\n" + a.resumo())
        self.stdout.write(
            self.style.SUCCESS(f"\nModelo escolhido: {aval_melhor.nome}")
        )

        caminho = Path(opcoes["relatorio"])
        self._gravar_relatorio(caminho, base, avaliacoes, aval_melhor, ano_atr, ano_alvo)
        self.stdout.write(f"Avaliacao registrada em {caminho}")

        # Metricas em formato legivel por maquina. O validar_modelo compara o
        # ano observado com a particao de teste, e antes trazia esses numeros
        # fixos no codigo: quando o modelo escolhido mudou, a comparacao passou
        # a confrontar o modelo errado, em silencio.
        sidecar = caminho.with_suffix(".json")
        sidecar.write_text(
            json.dumps(
                {
                    "modelo": aval_melhor.nome,
                    "ano_atributos": ano_atr,
                    "ano_alvo": ano_alvo,
                    "sensibilidade": round(aval_melhor.sensibilidade, 4),
                    "especificidade": round(aval_melhor.especificidade, 4),
                    "precisao": round(aval_melhor.precisao, 4),
                    "auc": round(aval_melhor.auc, 4),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.stdout.write(f"Metricas em {sidecar}")

        if opcoes["nao_gravar"]:
            self.stdout.write(self.style.WARNING("Previsoes nao gravadas (--nao-gravar)."))
            return

        # A previsao NAO e feita sobre a base de treino, e sim sobre os
        # atributos do ano mais recente disponivel, para estimar o ano seguinte.
        # O modelo aprendeu a transicao de ano_atr para ano_alvo; aplicado aos
        # indicadores de ano_alvo, ele estima ano_alvo + 1, que e o ano em que
        # ainda da para agir.
        #
        # A linha gravada leva `ano = ano_alvo`: e o ano de REFERENCIA dos
        # indicadores que geraram a previsao. O ano previsto e esse mais um.
        # Guardar assim mantem o cruzamento da matriz de decisao direto, porque
        # o indice atual do mesmo ano fica na mesma chave.
        quadro = M.montar_previsao(df, ano_alvo)
        if quadro.empty:
            raise CommandError(
                f"Nenhuma escola com atributos completos em {ano_alvo} para prever "
                f"{ano_alvo + 1}."
            )
        self.stdout.write("")
        self.stdout.write(
            "Prevendo " + str(ano_alvo + 1) + " a partir dos "
            "indicadores de " + str(ano_alvo) + ": "
            + str(len(quadro)) + " escolas"
        )
        previsoes = M.classificar(M.prever(melhor, quadro))

        # Decomposicao exata de cada previsao, para a pagina da escola explicar
        # qual indicador puxou o numero para cima ou para baixo. Roda aqui, na
        # maquina local, e nao no processo web: a floresta tem 300 arvores e o
        # percurso por arvore sairia caro a cada visita.
        self.stdout.write("Explicando cada previsao...")
        explicacoes = {
            e["co_entidade"]: {
                "metodo": "contribuicoes",
                "modelo": aval_melhor.nome,
                "base": e["base"],
                "contribuicoes": e["contribuicoes"],
            }
            for e in M.explicar(melhor, quadro, maximo=4)
        }

        objetos = [
            IndiceRisco(
                escola_id=int(linha.co_entidade),
                ano=ano_alvo,
                versao=M.VERSAO,
                score=float(linha.score),
                classe=linha.classe,
                detalhes=explicacoes.get(int(linha.co_entidade)),
            )
            for linha in previsoes.itertuples()
        ]
        with transaction.atomic():
            # Substituicao completa, e nao acumulo.
            #
            # O conjunto de escolas previstas muda entre execucoes: quando o
            # modelo passou a prever a partir de um unico ano, 56 escolas da
            # rodada anterior deixaram de ser previstas e ficaram no banco com
            # o score antigo, de uma versao que previa outro ano. O upsert nao
            # as removia, porque so toca nas linhas que recebe.
            #
            # As previsoes de uma versao sao um retrato, nao um historico: cada
            # treino as refaz por inteiro.
            apagadas, _ = IndiceRisco.objects.filter(versao=M.VERSAO).delete()
            if apagadas:
                self.stdout.write(f"  {apagadas} previsoes anteriores substituidas")

            IndiceRisco.objects.bulk_create(
                objetos, batch_size=2000, update_conflicts=True,
                update_fields=["score", "classe", "detalhes"],
                unique_fields=["escola", "ano", "versao"],
            )

        distrib = {
            c: IndiceRisco.objects.filter(versao=M.VERSAO, classe=c).count()
            for c in ("alto", "medio", "baixo")
        }
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{len(objetos)} previsoes gravadas como versao {M.VERSAO}\n"
                f"  risco alto: {distrib['alto']}\n"
                f"  risco medio: {distrib['medio']}\n"
                f"  risco baixo: {distrib['baixo']}"
            )
        )

    @staticmethod
    def _explicar_escolha(melhor, avaliacoes):
        """
        Diz o que de fato decidiu a escolha.

        O texto era fixo em "o criterio foi a maior sensibilidade", o que fica
        falso quando quem decide e a regra de desempate: os dois modelos ficam
        dentro da tolerancia e vence o interpretavel, que pode ter a
        sensibilidade MENOR. Afirmar um criterio errado em relatorio e pior do
        que nao explicar.
        """
        from etl import modelo as M

        maior = max(a.sensibilidade for a in avaliacoes)
        if melhor.sensibilidade >= maior:
            return (
                "O critério foi a maior sensibilidade. Encontrar a escola que vai "
                "piorar importa mais do que evitar o alarme falso: o custo de olhar "
                "uma escola que estava bem é baixo; o de não olhar uma que piorou, "
                "alto."
            )
        vencedor = max(avaliacoes, key=lambda a: a.sensibilidade)
        return (
            f"A sensibilidade mais alta foi a de {vencedor.nome} "
            f"({vencedor.sensibilidade:.3f} contra {melhor.sensibilidade:.3f}), mas a "
            f"diferença de {maior - melhor.sensibilidade:.3f} cabe dentro da "
            f"tolerância de {M.TOLERANCIA_SENSIBILIDADE:.2f} adotada pelo projeto. "
            "Em uma única divisão entre treino e teste, diferença dessa ordem é "
            "ruído amostral, não desempenho. Havendo empate técnico, vence o modelo "
            "interpretável, cujos coeficientes podem ser lidos e defendidos."
        )

    def _gravar_relatorio(self, caminho, base, avaliacoes, melhor, ano_atr, ano_alvo):
        from etl import modelo as M

        caminho.parent.mkdir(parents=True, exist_ok=True)
        positivos = int(base["alvo"].sum())
        linhas = [
            "# Avaliação do modelo preditivo",
            "",
            f"Gerado por `manage.py treinar_modelo`. Versão `{M.VERSAO}`.",
            "",
            "## Desenho do problema",
            "",
            f"- **Atributos:** indicadores da escola em **{ano_atr}**",
            f"- **Alvo:** a escola está no quartil superior de abandono da sua UF em **{ano_alvo}**",
            f"- **Escolas com os dois anos completos:** {len(base)}",
            f"- **Casos positivos:** {positivos} ({positivos / len(base) * 100:.1f}%)",
            f"- **Atributos usados:** {', '.join(M.ATRIBUTOS)}",
            f"- **Divisão treino e teste:** 75% e 25%, estratificada, semente {M.SEMENTE}",
            "",
            "O quartil é calculado **dentro de cada unidade federativa**. Comparar",
            "escolas de estados diferentes na mesma escala mediria sobretudo a diferença",
            "entre os estados, e não o risco relativo da escola no contexto em que opera.",
            "",
            "## Por que não acurácia",
            "",
            "Bowers, Sprott e Taff (2013) mostram que indicadores de evasão devem ser",
            "avaliados por precisão, sensibilidade e especificidade. Em base desbalanceada,",
            "a acurácia engana: classificar todas as escolas como sem risco acertaria cerca",
            f"de {100 - positivos / len(base) * 100:.0f}% dos casos e não encontraria nenhuma escola em risco.",
            "",
            "## Resultados",
            "",
            "| Modelo | Sensibilidade | Especificidade | Precisão | F1 | AUC ROC |",
            "|---|---|---|---|---|---|",
        ]
        for a in avaliacoes:
            linhas.append(
                f"| {a.nome} | {a.sensibilidade:.3f} | {a.especificidade:.3f} | "
                f"{a.precisao:.3f} | {a.f1:.3f} | {a.auc:.3f} |"
            )
        linhas += [
            "",
            f"**Modelo escolhido: {melhor.nome}.**",
            "",
            self._explicar_escolha(melhor, avaliacoes),
            "",
            "### Matriz de confusão do modelo escolhido",
            "",
            "```",
            melhor.resumo(),
            "```",
            "",
        ]
        if melhor.importancias:
            if melhor.tipo_importancia == "coeficiente":
                cabecalho, explicacao = "Coeficiente", (
                    "Coeficientes da regressão logística, sobre atributos "
                    "padronizados. O **sinal** diz a direção do efeito e a "
                    "magnitude diz a força."
                )
            else:
                cabecalho, explicacao = "Importância", (
                    "Importância de atributo da floresta aleatória. É sempre "
                    "positiva e mede o quanto o atributo foi usado para separar "
                    "os casos, **não** a direção do efeito. Não se lê como "
                    "coeficiente de regressão."
                )
            linhas += ["### Contribuição de cada atributo", "", explicacao, "",
                       f"| Atributo | {cabecalho} |", "|---|---|"]
            for k, v in sorted(melhor.importancias.items(), key=lambda x: -abs(x[1])):
                valor = f"{v:+.4f}" if melhor.tipo_importancia == "coeficiente" else f"{v:.4f}"
                linhas.append(f"| {k} | {valor} |")
            linhas.append("")
        linhas += [
            "## Limites declarados",
            "",
            "- A base dispõe de **apenas uma transição entre anos**, de "
            f"{ano_atr} para {ano_alvo}. Não é possível validar o modelo em outro par de",
            "  anos, o que seria o teste mais honesto de generalização.",
            "- O rótulo é uma **construção dos autores**, não uma medida oficial de crise",
            "  escolar. Mudar o quantil ou o recorte geográfico muda o problema.",
            "- O modelo prevê **posição relativa dentro da UF**, não valor absoluto de",
            "  abandono, e não deve ser lido como previsão do que acontecerá com estudantes",
            "  individuais.",
            "",
        ]
        caminho.write_text("\n".join(linhas), encoding="utf-8")
