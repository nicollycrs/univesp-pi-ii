from django.contrib import admin

from painel.models import Escola, IndicadorAnual, IndiceRisco, Municipio


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ("codigo_ibge", "nome", "uf", "regiao")
    list_filter = ("uf", "regiao")
    search_fields = ("nome", "codigo_ibge")


@admin.register(Escola)
class EscolaAdmin(admin.ModelAdmin):
    list_display = ("co_entidade", "nome", "uf", "rede", "localizacao")
    list_filter = ("uf", "rede", "localizacao")
    search_fields = ("nome", "co_entidade")
    autocomplete_fields = ("municipio",)


@admin.register(IndicadorAnual)
class IndicadorAnualAdmin(admin.ModelAdmin):
    list_display = (
        "escola",
        "ano",
        "taxa_abandono",
        "taxa_reprovacao",
        "distorcao_idade_serie",
        "inse",
        "origem",
    )
    list_filter = ("ano", "origem", "escola__uf")
    search_fields = ("escola__nome",)


@admin.register(IndiceRisco)
class IndiceRiscoAdmin(admin.ModelAdmin):
    list_display = ("escola", "ano", "score", "classe", "versao")
    list_filter = ("ano", "classe", "versao", "escola__uf")
    search_fields = ("escola__nome",)
