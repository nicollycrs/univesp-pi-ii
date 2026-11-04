"""
API REST propria do EducaAlerta, em Django REST Framework.

Atende ao requisito de uso de API do enunciado na direcao "API produzida". O
consumo de API externa esta em painel/ibge.py.

O painel em JavaScript consome estes mesmos endpoints, e nao dados embutidos no
HTML: e isso que torna a API parte do produto e nao um anexo.
"""

from django.db.models import Avg, Count, Max, Min, OuterRef, Subquery
from rest_framework import filters, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from painel import matriz, risco
from painel.models import Escola, IndicadorAnual, IndiceRisco, Municipio
from painel.serializers import (
    EscolaDetalheSerializer,
    EscolaSerializer,
    IndiceRiscoSerializer,
    MunicipioSerializer,
)


class MunicipioViewSet(viewsets.ReadOnlyModelViewSet):
    """Municipios, preenchidos a partir da API do IBGE."""

    queryset = Municipio.objects.all()
    serializer_class = MunicipioSerializer
    filterset_fields = ["uf", "regiao"]
    filter_backends = [
        *viewsets.ReadOnlyModelViewSet.filter_backends,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["nome"]
    ordering_fields = ["nome", "uf"]


class EscolaViewSet(viewsets.ReadOnlyModelViewSet):
    """Escolas. O detalhe traz a serie historica de indicadores e os riscos."""

    queryset = Escola.objects.select_related("municipio").all()
    filterset_fields = ["uf", "rede", "municipio", "localizacao"]
    filter_backends = [
        *viewsets.ReadOnlyModelViewSet.filter_backends,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["nome"]
    ordering_fields = ["nome", "uf"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EscolaDetalheSerializer
        return EscolaSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            return qs.prefetch_related("indicadores", "riscos")
        return qs


class IndiceRiscoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Ranking de risco. Ordenado do maior para o menor score por padrao, que e a
    leitura util para quem precisa priorizar atencao.
    """

    queryset = IndiceRisco.objects.select_related("escola", "escola__municipio").all()
    serializer_class = IndiceRiscoSerializer
    filterset_fields = ["ano", "classe", "versao", "escola__uf", "escola__rede"]
    filter_backends = [
        *viewsets.ReadOnlyModelViewSet.filter_backends,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    # Busca por nome da escola: o painel tem 20 mil escolas, e procurar uma
    # especifica paginando era inviavel.
    search_fields = ["escola__nome"]
    ordering_fields = ["score", "ano", "score_previsto"]
    ordering = ["-score"]

    def get_queryset(self):
        """
        Filtro extra por grupo da matriz de decisao.

        `?grupo=deterioracao` devolve apenas as escolas daquele quadrante. Como
        o grupo depende das DUAS versoes do indice, e nao de um campo da linha,
        ele nao cabe no `filterset_fields` e e resolvido aqui.
        """
        qs = super().get_queryset()
        grupo = self.request.query_params.get("grupo")
        if grupo not in matriz.GRUPOS:
            return qs

        regra = matriz.GRUPOS[grupo]
        # A linha base e sempre a do indice atual: e ela que o ranking exibe.
        # A previsao entra por subconsulta na mesma escola e ano, o que permite
        # tanto filtrar pelo quadrante quanto ordenar pelo risco previsto.
        qs = qs.filter(versao=matriz.VERSAO_ATUAL).annotate(
            classe_prevista=Subquery(_classe_prevista()),
            score_previsto=Subquery(_classe_prevista(campo="score")),
        )
        qs = (
            qs.filter(classe=matriz.CLASSE_DE_CORTE)
            if regra["atual"]
            else qs.exclude(classe=matriz.CLASSE_DE_CORTE)
        )
        qs = (
            qs.filter(classe_prevista=matriz.CLASSE_DE_CORTE)
            if regra["previsto"]
            else qs.filter(classe_prevista__isnull=False).exclude(
                classe_prevista=matriz.CLASSE_DE_CORTE
            )
        )
        return qs


def _classe_prevista(campo: str = "classe"):
    """Subconsulta com a previsao do modelo para a mesma escola e ano."""
    return IndiceRisco.objects.filter(
        escola=OuterRef("escola"),
        ano=OuterRef("ano"),
        versao=matriz.VERSAO_PREVISTA,
    ).values(campo)[:1]


@api_view(["GET"])
def matriz_decisao(request):
    """
    Contagem de escolas em cada quadrante da matriz de decisao.

    Cruza a classe do indice atual com a classe prevista pelo modelo, para o
    mesmo ano. Aceita `ano`, `uf` e `rede`.

    Quando nao existe previsao para o ano pedido, a resposta vem com os grupos
    zerados e `previsao_disponivel` falso, em vez de erro: o painel precisa
    continuar funcionando com o ano em que so ha o indice atual.
    """
    ano = request.query_params.get("ano")
    uf = request.query_params.get("uf")
    rede = request.query_params.get("rede")

    base = IndiceRisco.objects.filter(versao=matriz.VERSAO_ATUAL)
    if ano:
        base = base.filter(ano=ano)
    if uf:
        base = base.filter(escola__uf=uf.upper())
    if rede:
        base = base.filter(escola__rede=rede)

    # Uma consulta agrupada resolve a matriz inteira. Trazer as 20 mil linhas
    # para a memoria do processo web custaria RAM que a instancia nao tem.
    pares = (
        base.order_by()
        .annotate(classe_prevista=Subquery(_classe_prevista()))
        .values("classe", "classe_prevista")
        .annotate(escolas=Count("*"))
    )

    contagem = {chave: 0 for chave in matriz.GRUPOS}
    sem_previsao = 0
    for linha in pares:
        grupo = matriz.grupo_de(linha["classe"], linha["classe_prevista"])
        if grupo is None:
            sem_previsao += linha["escolas"]
        else:
            contagem[grupo] += linha["escolas"]

    total_com_previsao = sum(contagem.values())
    grupos = []
    for chave in matriz.por_posicao():
        descricao = matriz.descrever(chave)
        escolas = contagem[chave]
        descricao["escolas"] = escolas
        descricao["proporcao"] = (
            round(100 * escolas / total_com_previsao, 1) if total_com_previsao else None
        )
        grupos.append(descricao)

    return Response(
        {
            "filtros": {"ano": ano, "uf": uf, "rede": rede},
            "previsao_disponivel": total_com_previsao > 0,
            "versao_atual": matriz.VERSAO_ATUAL,
            "versao_prevista": matriz.VERSAO_PREVISTA,
            "classe_de_corte": matriz.CLASSE_DE_CORTE,
            "eixo_linha": matriz.EIXO_LINHA,
            "eixo_coluna": matriz.EIXO_COLUNA,
            "escolas_com_previsao": total_com_previsao,
            "sem_previsao": {"escolas": sem_previsao, **matriz.SEM_PREVISAO},
            "grupos": grupos,
        }
    )


@api_view(["GET"])
def resumo(request):
    """
    Agregados para os cartoes e graficos do painel.

    Aceita os parametros de consulta `uf` e `ano`.
    """
    indicadores = IndicadorAnual.objects.all()
    uf = request.query_params.get("uf")
    ano = request.query_params.get("ano")
    if uf:
        indicadores = indicadores.filter(escola__uf=uf.upper())
    if ano:
        indicadores = indicadores.filter(ano=ano)

    agregados = indicadores.aggregate(
        escolas=Count("escola", distinct=True),
        abandono_medio=Avg("taxa_abandono"),
        reprovacao_media=Avg("taxa_reprovacao"),
        distorcao_media=Avg("distorcao_idade_serie"),
        inse_medio=Avg("inse"),
        ano_min=Min("ano"),
        ano_max=Max("ano"),
    )

    riscos = IndiceRisco.objects.all()
    if uf:
        riscos = riscos.filter(escola__uf=uf.upper())
    if ano:
        riscos = riscos.filter(ano=ano)
    versao = request.query_params.get("versao")
    if versao:
        riscos = riscos.filter(versao=versao)

    por_classe = {c: 0 for c in (risco.CLASSE_ALTO, risco.CLASSE_MEDIO, risco.CLASSE_BAIXO)}
    for linha in riscos.values("classe").annotate(n=Count("id")):
        por_classe[linha["classe"]] = linha["n"]

    # Sinaliza se ha dado de amostra de desenvolvimento na base. O painel usa
    # isso para exibir aviso e nao apresentar numero de amostra como resultado.
    tem_amostra = IndicadorAnual.objects.filter(
        origem=IndicadorAnual.Origem.AMOSTRA
    ).exists()

    return Response(
        {
            "filtros": {"uf": uf.upper() if uf else None, "ano": int(ano) if ano else None},
            "agregados": {
                k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in agregados.items()
            },
            "risco_por_classe": [
                {"classe": c, "rotulo": risco.rotulo(c), "escolas": n}
                for c, n in por_classe.items()
            ],
            "contem_dados_de_amostra": tem_amostra,
            "versao_indice": versao or risco.VERSAO,
            # Mesma ordem do seletor do painel: o indice descritivo primeiro,
            # a previsao depois. Ordem alfabetica inverteria os dois.
            "versoes_disponiveis": sorted(
                IndiceRisco.objects.order_by().values_list("versao", flat=True).distinct(),
                key=lambda v: risco.ORDEM_VERSAO.get(v, 99),
            ),
        }
    )


# Eixos disponiveis para o grafico de dispersao.
#
# A unidade vem separada do rotulo porque os dois sao usados em lugares
# diferentes: o titulo da secao le "Distorcao idade-serie e taxa de abandono",
# sem a unidade, enquanto o eixo do grafico precisa dela.
EIXOS_DISPERSAO = {
    "contexto": (
        "escola__municipio__salario_medio",
        "Salário médio do município",
        "salários mínimos",
    ),
    "distorcao": ("distorcao_idade_serie", "Distorção idade-série", "%"),
    "inse": ("inse", "Nível socioeconômico (INSE)", ""),
}

# Ordem de preferencia do eixo no modo automatico.
#
# O contexto socioeconomico vem primeiro porque e a relacao que a literatura
# aponta: contexto mais pobre associado a abandono mais alto. A distorcao
# idade-serie vem depois, com respaldo proprio na literatura de fluxo escolar.
# O INSE fica por ultimo, pronto para assumir caso o INEP volte a publica-lo
# por escola de forma cruzavel.
PREFERENCIA_DISPERSAO = ("contexto", "distorcao", "inse")


def _valor_do_eixo(indicador, campo):
    """Le o valor do eixo, que pode estar na escola, no municipio ou na linha."""
    objeto = indicador
    for parte in campo.split("__"):
        if objeto is None:
            return None
        objeto = getattr(objeto, parte, None)
    return objeto


@api_view(["GET"])
def dispersao(request):
    """
    Pares de um indicador socioeducacional e a taxa de abandono.

    O eixo horizontal e escolhido pelo parametro `eixo`, que aceita `inse`,
    `distorcao` ou `auto`. Em `auto`, vale o primeiro da ordem de preferencia que
    tiver dados na selecao atual.
    """
    uf = request.query_params.get("uf")
    ano = request.query_params.get("ano")

    def filtrar(campo):
        qs = (
            IndicadorAnual.objects.select_related("escola", "escola__municipio")
            .exclude(**{f"{campo}__isnull": True})
            .exclude(taxa_abandono__isnull=True)
        )
        if uf:
            qs = qs.filter(escola__uf=uf.upper())
        if ano:
            qs = qs.filter(ano=ano)
        return qs

    pedido = (request.query_params.get("eixo") or "auto").lower()
    if pedido in EIXOS_DISPERSAO:
        candidatos = (pedido,)
    else:
        candidatos = PREFERENCIA_DISPERSAO

    eixo = candidatos[-1]
    qs = filtrar(EIXOS_DISPERSAO[eixo][0])
    for nome in candidatos:
        tentativa = filtrar(EIXOS_DISPERSAO[nome][0])
        if tentativa.exists():
            eixo, qs = nome, tentativa
            break

    campo, rotulo, unidade = EIXOS_DISPERSAO[eixo]
    limite = min(int(request.query_params.get("limite", 1500)), 5000)
    dados = [
        {
            "co_entidade": i.escola_id,
            "escola_nome": i.escola.nome,
            # `x` e o valor do eixo escolhido; os dois campos nomeados seguem no
            # payload para que a resposta se explique sozinha.
            "x": _valor_do_eixo(i, campo),
            "inse": i.inse,
            "distorcao_idade_serie": i.distorcao_idade_serie,
            "contexto_socioeconomico": (
                i.escola.municipio.salario_medio if i.escola.municipio_id else None
            ),
            "taxa_abandono": i.taxa_abandono,
        }
        for i in qs[:limite]
    ]
    return Response(
        {
            "total": len(dados),
            "eixo": eixo,
            "rotulo_eixo": rotulo,
            "unidade_eixo": unidade,
            "eixos_disponiveis": [
                {"valor": nome, "rotulo": EIXOS_DISPERSAO[nome][1]}
                for nome in PREFERENCIA_DISPERSAO
                if filtrar(EIXOS_DISPERSAO[nome][0]).exists()
            ],
            "pontos": dados,
        }
    )
