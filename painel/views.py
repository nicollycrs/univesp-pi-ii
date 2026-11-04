"""Paginas do painel."""

import json

from django.db.models import Max, Min
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe

from painel import cores, risco
from painel.models import Escola, IndicadorAnual, IndiceRisco


def _contexto_base():
    """Opcoes de filtro e metadados compartilhados pelas paginas."""
    faixa = IndicadorAnual.objects.aggregate(menor=Min("ano"), maior=Max("ano"))
    return {
        # order_by() vazio e obrigatorio antes de distinct().
        #
        # Os modelos declaram ordenacao padrao no Meta (Escola por uf e nome,
        # IndicadorAnual por ano e nome da escola). O Django inclui os campos de
        # ordenacao no SELECT, entao distinct() passava a operar sobre o par
        # (uf, nome) em vez de so uf: o seletor de UF vinha com uma opcao por
        # escola, 19.776 no lugar de 27, e o de ano com 38.925 no lugar de 2.
        # A pagina chegou a 2,9 MB por causa disso.
        "ufs": sorted(
            Escola.objects.order_by().values_list("uf", flat=True).distinct()
        ),
        "redes": Escola.Rede.choices,
        "anos": sorted(
            IndicadorAnual.objects.order_by().values_list("ano", flat=True).distinct(),
            reverse=True,
        ),
        "ano_padrao": faixa["maior"],
        "versao_indice": risco.VERSAO,
        # Agora existe mais de uma versao do indice: a baseada em regras e a
        # preditiva. O painel deixa escolher, e explica a diferenca, porque sao
        # perguntas distintas: uma descreve o presente, a outra antecipa o ano
        # seguinte.
        # Ordem deliberada: o indice descritivo primeiro, porque e a leitura
        # mais direta e deve ser o padrao; a previsao vem depois, como opcao.
        "versoes": [
            {"valor": v, "rotulo": risco.ROTULO_VERSAO.get(v, v)}
            for v in sorted(
                IndiceRisco.objects.order_by()
                .values_list("versao", flat=True)
                .distinct(),
                key=lambda v: risco.ORDEM_VERSAO.get(v, 99),
            )
        ],
        "tarjas": cores.TARJAS,
        # A paleta vai para o JavaScript em JSON, de modo que grafico e CSS usem
        # exatamente as mesmas cores validadas em painel/cores.py.
        "paleta_json": mark_safe(
            json.dumps({"grafico": cores.GRAFICO, "tarjas": cores.TARJAS})
        ),
        "descricoes_versao": mark_safe(json.dumps(risco.DESCRICAO_VERSAO)),
        # Aviso honesto: se a base contem amostra de desenvolvimento, a pagina diz
        # isso em destaque, para que numero de amostra nunca passe por resultado.
        "contem_amostra": IndicadorAnual.objects.filter(
            origem=IndicadorAnual.Origem.AMOSTRA
        ).exists(),
        "sem_dados": not IndicadorAnual.objects.exists(),
    }


def painel(request):
    """Pagina principal: filtros, ranking de risco e dois graficos."""
    return render(request, "painel/painel.html", _contexto_base())


def _historico_da_escola(escola):
    """
    Indice observado por ano, em ordem cronologica, com a variacao anual.

    So a versao baseada em regras entra aqui: e a unica que descreve um ano que
    de fato aconteceu.
    """
    linhas = list(escola.riscos.filter(versao=risco.VERSAO).order_by("ano"))
    historico, anterior = [], None
    for linha in linhas:
        variacao = None if anterior is None else round(linha.score - anterior, 3)
        historico.append(
            {
                "obj": linha,
                "rotulo": risco.rotulo(linha.classe),
                "variacao": variacao,
                # A seta nunca vai sozinha: o sinal e o numero acompanham, por
                # causa do criterio 1.4.1 Uso da Cor.
                "sentido": (
                    None if variacao is None
                    else "subiu" if variacao > 0.0005
                    else "caiu" if variacao < -0.0005
                    else "igual"
                ),
            }
        )
        anterior = linha.score
    return historico


# Nome legivel dos atributos do modelo, para a explicacao da previsao.
ROTULO_ATRIBUTO = {
    "taxa_abandono": "Taxa de abandono",
    "taxa_reprovacao": "Taxa de reprovação",
    "distorcao_idade_serie": "Distorção idade-série",
    "contexto_socioeconomico": "Contexto socioeconômico do município",
    "rural": "Localização rural",
}

UNIDADE_ATRIBUTO = {
    "taxa_abandono": "%",
    "taxa_reprovacao": "%",
    "distorcao_idade_serie": "%",
    "contexto_socioeconomico": "salários mínimos",
    "rural": "",
}


def _descrever_valor(atributo, valor):
    """Valor do atributo em linguagem corrente, com a unidade certa."""
    if atributo == "rural":
        return "a escola é rural" if valor >= 0.5 else "a escola é urbana"
    unidade = UNIDADE_ATRIBUTO.get(atributo, "")
    numero = f"{valor:.1f}".replace(".", ",")
    if unidade == "%":
        return f"em {numero}%"
    return f"em {numero} {unidade}".strip()


def _explicar_previsao(detalhes):
    """
    Converte a decomposicao guardada em algo exibivel.

    A contribuicao bruta esta na unidade interna do modelo, que varia conforme
    ele seja floresta ou regressao. O que a pagina mostra e a participacao
    RELATIVA de cada atributo no total movido, que se le do mesmo jeito nos dois
    casos: "este indicador responde por tanto do que empurrou a previsao".
    """
    if not detalhes or detalhes.get("metodo") != "contribuicoes":
        return None

    itens = detalhes.get("contribuicoes") or []
    if not itens:
        return None

    total = sum(abs(i["contribuicao"]) for i in itens) or 1.0
    # O ponto de partida do modelo precisa aparecer, ou a explicacao parece se
    # contradizer: o maior fator pode REDUZIR o risco e a escola ainda sair
    # como risco alto, porque a base ja era alta e a classe vem de tercis
    # dentro da UF, nao de um limiar fixo de probabilidade.
    base = detalhes.get("base")
    explicadas = []
    for i in itens:
        contrib = i["contribuicao"]
        explicadas.append(
            {
                "rotulo": ROTULO_ATRIBUTO.get(i["atributo"], i["atributo"]),
                # Frase pronta em vez de numero cru: "rural" e binario, e
                # exibi-lo como "1,0" ao lado de uma unidade vazia produzia
                # "Localizacao rural, em 1,0 ,", que nao quer dizer nada.
                "valor_descrito": _descrever_valor(i["atributo"], i["valor"]),
                "sentido": "aumenta" if contrib > 0 else "reduz",
                "participacao": round(100 * abs(contrib) / total),
            }
        )
    return {
        "modelo": detalhes.get("modelo", ""),
        "base_porcentagem": None if base is None else round(base * 100),
        "itens": explicadas,
    }


def _explicar_indice(detalhes):
    """Parcelas do indice de regras, prontas para a tabela da pagina."""
    if not detalhes or detalhes.get("metodo") != "soma_ponderada":
        return None

    parcelas = detalhes.get("parcelas") or []
    if not parcelas:
        return None

    return [
        {
            "rotulo": risco.ROTULO_COMPONENTE.get(p["componente"], p["componente"]),
            "unidade": risco.UNIDADE_COMPONENTE.get(p["componente"], ""),
            "valor": p["valor"],
            "invertido": p.get("invertido", False),
            # Posicao da escola dentro do grupo (UF, ano), de 0 a 100.
            "posicao": round(100 * p["normalizado"]),
            "peso": round(100 * p["peso_efetivo"]),
            "contribuicao": p["contribuicao"],
            "participacao": round(
                100 * p["contribuicao"] / sum(q["contribuicao"] for q in parcelas)
            ) if sum(q["contribuicao"] for q in parcelas) else 0,
        }
        for p in parcelas
    ]


def _previsao_da_escola(escola):
    """
    Ultima previsao do modelo para a escola, ja com o ano previsto resolvido.

    A linha guarda o ano dos INDICADORES que a geraram; o ano previsto e esse
    mais um. Resolver isso aqui evita que o template faca aritmetica de ano.
    """
    linha = escola.riscos.filter(versao=modelo_versao()).order_by("-ano").first()
    if linha is None:
        return None
    return {
        "obj": linha,
        "rotulo": risco.rotulo(linha.classe),
        "ano_base": linha.ano,
        "ano_previsto": linha.ano + 1,
        "porcentagem": round(linha.score * 100),
        "explicacao": _explicar_previsao(linha.detalhes),
    }


def modelo_versao():
    """Versao do indice produzida pelo modelo preditivo."""
    return "modelo-v1"


def escola_detalhe(request, co_entidade):
    """Serie historica de uma escola."""
    escola = get_object_or_404(
        Escola.objects.select_related("municipio"), pk=co_entidade
    )
    contexto = _contexto_base()
    contexto.update(
        {
            "escola": escola,
            "indicadores": escola.indicadores.order_by("ano"),
            # Historico e previsao sao separados de proposito.
            #
            # Ficavam na mesma tabela, ordenados por (ano, versao), o que
            # produzia a sequencia 2023, previsao para 2025, 2024: fora de
            # ordem cronologica e com o mesmo ano aparecendo duas vezes.
            #
            # Pior que a ordem: os dois numeros caiam na mesma coluna "Indice",
            # convidando a uma comparacao que nao existe. O indice de regras e
            # uma soma ponderada normalizada de 0 a 1; o score do modelo e uma
            # PROBABILIDADE. Sao grandezas diferentes, e junta-las numa coluna
            # so sugeria que a escola "piorou de 0,824 para 0,849".
            "historico": _historico_da_escola(escola),
            "previsao": _previsao_da_escola(escola),
            # Conta aberta do indice do ano mais recente.
            "explicacao_indice": _explicar_indice(
                getattr(
                    escola.riscos.filter(versao=risco.VERSAO).order_by("-ano").first(),
                    "detalhes",
                    None,
                )
            ),
        }
    )
    return render(request, "painel/escola.html", contexto)


def sobre(request):
    """Metodologia, fontes e limites do indice. Exigencia de transparencia."""
    contexto = _contexto_base()
    contexto.update({"pesos": risco.PESOS})
    return render(request, "painel/sobre.html", contexto)


def saude(request):
    """
    Verificacao de saude da aplicacao, em JSON.

    Usada para monitoramento de disponibilidade e para confirmar, sem abrir o
    painel, se o banco responde e quantos registros existem.
    """
    return JsonResponse(
        {
            "status": "ok",
            "escolas": Escola.objects.count(),
            "indicadores": IndicadorAnual.objects.count(),
            "riscos": IndiceRisco.objects.count(),
            "versao_indice": risco.VERSAO,
            # A lista de versoes fica de fora de proposito: esta rota e o health
            # check do provedor de hospedagem e precisa continuar barata. Quem
            # precisa das versoes consulta /api/indicadores/resumo/.
        }
    )
