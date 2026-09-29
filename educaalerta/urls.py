"""Rotas do projeto EducaAlerta."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("painel.urls")),
    path("api/", include("painel.api_urls")),
    path("admin/", admin.site.urls),
]
