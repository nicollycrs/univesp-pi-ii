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
        "ufs": sorted(Escola.objects.values_list("uf", flat=True).distinct()),
        "redes": Escola.Rede.choices,
        "anos": sorted(
            IndicadorAnual.objects.values_list("ano", flat=True).distinct(), reverse=True
        ),
        "ano_padrao": faixa["maior"],
        "versao_indice": risco.VERSAO,
        "tarjas": cores.TARJAS,
        # A paleta vai para o JavaScript em JSON, de modo que grafico e CSS usem
        # exatamente as mesmas cores validadas em painel/cores.py.
        "paleta_json": mark_safe(
            json.dumps({"grafico": cores.GRAFICO, "tarjas": cores.TARJAS})
        ),
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
            "riscos": [
                {"obj": r, "rotulo": risco.rotulo(r.classe)}
                for r in escola.riscos.order_by("ano")
            ],
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
        }
    )
