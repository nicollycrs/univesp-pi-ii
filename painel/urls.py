"""Rotas das paginas do painel."""

from django.urls import path

from painel import views

urlpatterns = [
    path("", views.painel, name="painel"),
    path("escola/<int:co_entidade>/", views.escola_detalhe, name="escola-detalhe"),
    path("sobre/", views.sobre, name="sobre"),
    path("saude/", views.saude, name="saude"),
]
