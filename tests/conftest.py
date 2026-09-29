"""Fixtures compartilhadas pelos testes."""

import pytest

from painel.models import Escola, IndicadorAnual, Municipio


@pytest.fixture
def municipio(db):
    return Municipio.objects.create(
        codigo_ibge="3550308", nome="São Paulo", uf="SP", regiao="Sudeste"
    )


@pytest.fixture
def escolas(db, municipio):
    """
    Tres escolas em SP com indicadores deliberadamente escalonados.

    A escola 3 tem o pior quadro em todos os componentes e o INSE mais baixo,
    logo precisa sair como risco alto. A escola 1 e o oposto. Isso torna os
    testes do indice independentes dos pesos exatos.
    """
    dados = [
        (1001, "Escola Boa", 5.0, 3.0, 8.0, 70.0),
        (1002, "Escola Media", 12.0, 10.0, 25.0, 50.0),
        (1003, "Escola Critica", 25.0, 20.0, 55.0, 30.0),
    ]
    criadas = []
    for codigo, nome, abandono, reprovacao, distorcao, inse in dados:
        escola = Escola.objects.create(
            co_entidade=codigo,
            nome=nome,
            uf="SP",
            municipio=municipio,
            rede=Escola.Rede.ESTADUAL,
            localizacao=Escola.Localizacao.URBANA,
        )
        IndicadorAnual.objects.create(
            escola=escola,
            ano=2024,
            taxa_abandono=abandono,
            taxa_reprovacao=reprovacao,
            distorcao_idade_serie=distorcao,
            inse=inse,
            taxa_aprovacao=100 - abandono - reprovacao,
        )
        criadas.append(escola)
    return criadas


@pytest.fixture
def api_client_db(db):
    """Cliente da API com banco de testes, sem dados pre-carregados."""
    from rest_framework.test import APIClient

    return APIClient()
