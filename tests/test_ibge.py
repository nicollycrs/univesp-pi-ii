"""
Testes do consumo da API do IBGE.

Nao chamam a rede: a resposta e simulada. O teste que importa e o do formato,
porque alguns municipios vem com `microrregiao` nula, e um parser que so use o
caminho canonico perderia a UF desses casos em silencio.
"""

import pytest
import requests

from painel import ibge
from painel.models import Municipio

# Formato real, conferido na API em 23/09/2026.
RESPOSTA_CANONICA = [
    {
        "id": 1400027,
        "nome": "Amajari",
        "microrregiao": {
            "id": 14001,
            "nome": "Boa Vista",
            "mesorregiao": {
                "id": 1401,
                "nome": "Norte de Roraima",
                "UF": {
                    "id": 14, "sigla": "RR", "nome": "Roraima",
                    "regiao": {"id": 1, "sigla": "N", "nome": "Norte"},
                },
            },
        },
    }
]

# Caso com microrregiao nula: a UF precisa vir por regiao-imediata.
RESPOSTA_SEM_MICRORREGIAO = [
    {
        "id": 3550308,
        "nome": "São Paulo",
        "microrregiao": None,
        "regiao-imediata": {
            "id": 355003,
            "nome": "São Paulo",
            "regiao-intermediaria": {
                "id": 3506,
                "nome": "São Paulo",
                "UF": {
                    "id": 35, "sigla": "SP", "nome": "São Paulo",
                    "regiao": {"id": 3, "sigla": "SE", "nome": "Sudeste"},
                },
            },
        },
    }
]


class RespostaFalsa:
    def __init__(self, dados, status=200):
        self._dados = dados
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._dados


class TestExtracaoDeUf:
    def test_caminho_canonico(self):
        assert ibge._uf_e_regiao(RESPOSTA_CANONICA[0]) == ("RR", "Norte")

    def test_caminho_alternativo_quando_microrregiao_e_nula(self):
        assert ibge._uf_e_regiao(RESPOSTA_SEM_MICRORREGIAO[0]) == ("SP", "Sudeste")

    def test_sem_nenhum_caminho_devolve_vazio(self):
        assert ibge._uf_e_regiao({"id": 1, "nome": "X"}) == ("", "")


class TestBuscar:
    def test_normaliza_a_resposta(self, monkeypatch):
        monkeypatch.setattr(
            requests, "get", lambda *a, **k: RespostaFalsa(RESPOSTA_CANONICA)
        )
        dados = ibge.buscar_municipios(uf="RR")
        assert dados == [
            {"codigo_ibge": "1400027", "nome": "Amajari", "uf": "RR", "regiao": "Norte"}
        ]

    def test_falha_de_rede_virou_erro_ibge(self, monkeypatch):
        def explode(*a, **k):
            raise requests.ConnectionError("sem rede")

        monkeypatch.setattr(requests, "get", explode)
        with pytest.raises(ibge.ErroIBGE, match="Falha ao consultar"):
            ibge.buscar_municipios(uf="RR")

    def test_resposta_que_nao_e_json_virou_erro_ibge(self, monkeypatch):
        class NaoJson(RespostaFalsa):
            def json(self):
                raise ValueError("nao e json")

        monkeypatch.setattr(requests, "get", lambda *a, **k: NaoJson(None))
        with pytest.raises(ibge.ErroIBGE, match="nao e JSON"):
            ibge.buscar_municipios(uf="RR")

    def test_status_de_erro_virou_erro_ibge(self, monkeypatch):
        monkeypatch.setattr(requests, "get", lambda *a, **k: RespostaFalsa([], 503))
        with pytest.raises(ibge.ErroIBGE):
            ibge.buscar_municipios(uf="RR")


class TestSincronizacao:
    def test_grava_no_banco(self, db, monkeypatch):
        monkeypatch.setattr(
            requests, "get", lambda *a, **k: RespostaFalsa(RESPOSTA_CANONICA)
        )
        criados, atualizados = ibge.sincronizar_municipios(uf="RR")
        assert (criados, atualizados) == (1, 0)
        assert Municipio.objects.get(codigo_ibge="1400027").uf == "RR"

    def test_e_idempotente(self, db, monkeypatch):
        """Rodar duas vezes nao pode duplicar municipio."""
        monkeypatch.setattr(
            requests, "get", lambda *a, **k: RespostaFalsa(RESPOSTA_CANONICA)
        )
        ibge.sincronizar_municipios(uf="RR")
        criados, atualizados = ibge.sincronizar_municipios(uf="RR")
        assert (criados, atualizados) == (0, 1)
        assert Municipio.objects.count() == 1

    def test_cache_le_do_banco_sem_rede(self, db, monkeypatch):
        Municipio.objects.create(codigo_ibge="3550308", nome="São Paulo", uf="SP")

        def nao_deveria_chamar(*a, **k):
            raise AssertionError("o cache nao pode chamar a rede")

        monkeypatch.setattr(requests, "get", nao_deveria_chamar)
        assert ibge.municipios_em_cache(uf="sp").count() == 1
