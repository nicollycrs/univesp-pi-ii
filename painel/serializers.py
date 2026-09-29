"""Serializadores da API REST do EducaAlerta."""

from rest_framework import serializers

from painel import risco
from painel.models import Escola, IndicadorAnual, IndiceRisco, Municipio


class MunicipioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Municipio
        fields = ["codigo_ibge", "nome", "uf", "regiao"]


class IndicadorAnualSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicadorAnual
        fields = [
            "ano",
            "taxa_aprovacao",
            "taxa_reprovacao",
            "taxa_abandono",
            "distorcao_idade_serie",
            "inse",
            "origem",
        ]


class EscolaSerializer(serializers.ModelSerializer):
    municipio_nome = serializers.CharField(source="municipio.nome", default=None, read_only=True)
    rede_display = serializers.CharField(source="get_rede_display", read_only=True)

    class Meta:
        model = Escola
        fields = [
            "co_entidade",
            "nome",
            "uf",
            "municipio",
            "municipio_nome",
            "rede",
            "rede_display",
            "localizacao",
        ]


class EscolaDetalheSerializer(EscolaSerializer):
    """Escola com a serie historica de indicadores e os riscos calculados."""

    indicadores = IndicadorAnualSerializer(many=True, read_only=True)
    riscos = serializers.SerializerMethodField()

    class Meta(EscolaSerializer.Meta):
        fields = EscolaSerializer.Meta.fields + ["indicadores", "riscos"]

    def get_riscos(self, obj):
        return [
            {
                "ano": r.ano,
                "score": round(r.score, 4),
                "classe": r.classe,
                "rotulo": risco.rotulo(r.classe),
                "versao": r.versao,
            }
            for r in obj.riscos.all()
        ]


class IndiceRiscoSerializer(serializers.ModelSerializer):
    """
    Item do ranking de risco.

    `rotulo` existe de proposito: o consumidor da API recebe o texto do risco, e
    nao apenas o codigo da classe, de modo que a interface nunca precise
    depender de cor para comunicar o nivel (WCAG 2.1, criterio 1.4.1).
    """

    co_entidade = serializers.IntegerField(source="escola.co_entidade", read_only=True)
    escola_nome = serializers.CharField(source="escola.nome", read_only=True)
    uf = serializers.CharField(source="escola.uf", read_only=True)
    municipio_nome = serializers.CharField(
        source="escola.municipio.nome", default=None, read_only=True
    )
    rede = serializers.CharField(source="escola.rede", read_only=True)
    rotulo = serializers.SerializerMethodField()

    class Meta:
        model = IndiceRisco
        fields = [
            "co_entidade",
            "escola_nome",
            "uf",
            "municipio_nome",
            "rede",
            "ano",
            "score",
            "classe",
            "rotulo",
            "versao",
        ]

    def get_rotulo(self, obj):
        return risco.rotulo(obj.classe)
