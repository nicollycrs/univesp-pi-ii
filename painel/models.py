"""
Modelo de dados do EducaAlerta.

Granularidade: escola e ano. Nenhum dado pessoal de estudante trafega ou e
armazenado, so indicadores agregados por escola, todos publicos.
"""

from django.db import models


class Municipio(models.Model):
    """Municipio, com codigo do IBGE. Preenchido pela API do IBGE."""

    codigo_ibge = models.CharField("código IBGE", max_length=7, primary_key=True)
    nome = models.CharField(max_length=120)
    uf = models.CharField("UF", max_length=2, db_index=True)
    regiao = models.CharField("região", max_length=20, blank=True)

    class Meta:
        verbose_name = "município"
        verbose_name_plural = "municípios"
        ordering = ["uf", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.uf})"


class Escola(models.Model):
    """Escola de educacao basica, identificada pelo codigo do INEP."""

    class Rede(models.TextChoices):
        ESTADUAL = "estadual", "Estadual"
        MUNICIPAL = "municipal", "Municipal"
        FEDERAL = "federal", "Federal"
        PRIVADA = "privada", "Privada"

    class Localizacao(models.TextChoices):
        URBANA = "urbana", "Urbana"
        RURAL = "rural", "Rural"

    co_entidade = models.BigIntegerField("código INEP", primary_key=True)
    nome = models.CharField(max_length=200)
    municipio = models.ForeignKey(
        Municipio, on_delete=models.PROTECT, related_name="escolas",
        null=True, blank=True, verbose_name="município",
    )
    uf = models.CharField("UF", max_length=2, db_index=True)
    rede = models.CharField(max_length=12, choices=Rede.choices, db_index=True)
    localizacao = models.CharField(
        "localização", max_length=8, choices=Localizacao.choices, blank=True
    )

    class Meta:
        verbose_name = "escola"
        verbose_name_plural = "escolas"
        ordering = ["uf", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.co_entidade})"


class IndicadorAnual(models.Model):
    """
    Indicadores publicos da escola em um ano.

    As taxas sao percentuais de 0 a 100. O INSE e o indicador de nivel
    socioeconomico do INEP, em que valor maior significa nivel mais alto.
    """

    class Origem(models.TextChoices):
        INEP = "INEP", "Dados oficiais do INEP"
        AMOSTRA = "AMOSTRA", "Amostra de desenvolvimento (não usar em resultado)"

    escola = models.ForeignKey(
        Escola, on_delete=models.CASCADE, related_name="indicadores"
    )
    ano = models.PositiveSmallIntegerField(db_index=True)

    taxa_aprovacao = models.FloatField("taxa de aprovação", null=True, blank=True)
    taxa_reprovacao = models.FloatField("taxa de reprovação", null=True, blank=True)
    taxa_abandono = models.FloatField("taxa de abandono", null=True, blank=True)
    distorcao_idade_serie = models.FloatField(
        "distorção idade-série", null=True, blank=True
    )
    inse = models.FloatField("INSE", null=True, blank=True)

    origem = models.CharField(
        max_length=8, choices=Origem.choices, default=Origem.INEP, db_index=True
    )
    carregado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "indicador anual"
        verbose_name_plural = "indicadores anuais"
        constraints = [
            models.UniqueConstraint(
                fields=["escola", "ano"], name="indicador_unico_por_escola_e_ano"
            )
        ]
        ordering = ["-ano", "escola__nome"]

    def __str__(self):
        return f"{self.escola.nome} / {self.ano}"


class IndiceRisco(models.Model):
    """
    Indice de risco calculado para a escola em um ano.

    O score vai de 0 a 1. A classe e derivada do score por tercis dentro da UF.
    `versao` registra qual formula ou modelo produziu o valor, para que
    resultados de versoes diferentes nunca sejam comparados por engano.
    """

    class Classe(models.TextChoices):
        BAIXO = "baixo", "Risco baixo"
        MEDIO = "medio", "Risco médio"
        ALTO = "alto", "Risco alto"

    escola = models.ForeignKey(Escola, on_delete=models.CASCADE, related_name="riscos")
    ano = models.PositiveSmallIntegerField(db_index=True)
    score = models.FloatField()
    classe = models.CharField(max_length=6, choices=Classe.choices, db_index=True)
    versao = models.CharField(max_length=40, db_index=True)
    calculado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "índice de risco"
        verbose_name_plural = "índices de risco"
        constraints = [
            models.UniqueConstraint(
                fields=["escola", "ano", "versao"],
                name="risco_unico_por_escola_ano_versao",
            )
        ]
        ordering = ["-score"]

    def __str__(self):
        return f"{self.escola.nome} / {self.ano}: {self.get_classe_display()}"
