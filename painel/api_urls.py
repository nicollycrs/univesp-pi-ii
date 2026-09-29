"""Rotas da API REST."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from painel import api

router = DefaultRouter()
router.register("escolas", api.EscolaViewSet, basename="escola")
router.register("municipios", api.MunicipioViewSet, basename="municipio")
router.register("risco", api.IndiceRiscoViewSet, basename="risco")

urlpatterns = [
    path("indicadores/resumo/", api.resumo, name="api-resumo"),
    path("indicadores/dispersao/", api.dispersao, name="api-dispersao"),
    path("", include(router.urls)),
]
