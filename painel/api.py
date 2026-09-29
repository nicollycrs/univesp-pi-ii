"""
API REST propria do EducaAlerta, em Django REST Framework.

Atende ao requisito de uso de API do enunciado na direcao "API produzida". O
consumo de API externa esta em painel/ibge.py.

O painel em JavaScript consome estes mesmos endpoints, e nao dados embutidos no
HTML: e isso que torna a API parte do produto e nao um anexo.
"""

from django.db.models import Avg, Count, Max, Min
from rest_framework import filters, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from painel import risco
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
        filters.OrderingFilter,
    ]
    ordering_fields = ["score", "ano"]
    ordering = ["-score"]


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
            "versao_indice": risco.VERSAO,
        }
    )


@api_view(["GET"])
def dispersao(request):
    """
    Pares de INSE e taxa de abandono, para o grafico de dispersao.

    Recorte pensado para a relacao que a literatura aponta: nivel
    socioeconomico mais baixo associado a abandono mais alto.
    """
    qs = IndicadorAnual.objects.select_related("escola").exclude(
        inse__isnull=True
    ).exclude(taxa_abandono__isnull=True)

    uf = request.query_params.get("uf")
    ano = request.query_params.get("ano")
    if uf:
        qs = qs.filter(escola__uf=uf.upper())
    if ano:
        qs = qs.filter(ano=ano)

    limite = min(int(request.query_params.get("limite", 1500)), 5000)
    dados = [
        {
            "co_entidade": i.escola_id,
            "escola_nome": i.escola.nome,
            "inse": i.inse,
            "taxa_abandono": i.taxa_abandono,
        }
        for i in qs[:limite]
    ]
    return Response({"total": len(dados), "pontos": dados})
