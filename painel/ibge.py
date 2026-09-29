"""
Cliente da API de localidades do IBGE.

Atende ao requisito de consumo de API externa do enunciado do PI.
Endpoint: https://servicodados.ibge.gov.br/api/v1/localidades
Publico, gratuito e sem autenticacao.

Politica de uso: a resposta e gravada na tabela Municipio e reaproveitada. A API
nao e chamada a cada requisicao do painel, so quando o cache esta vazio ou
quando a sincronizacao e pedida explicitamente. Falha de rede nunca derruba a
pagina: o painel continua funcionando com o que ja esta no banco.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE = "https://servicodados.ibge.gov.br/api/v1/localidades"


class ErroIBGE(RuntimeError):
    """Falha ao consultar a API do IBGE."""


def _uf_e_regiao(municipio):
    """
    Extrai sigla da UF e nome da regiao do JSON do IBGE.

    O caminho canonico passa por microrregiao > mesorregiao > UF, mas em alguns
    municipios microrregiao vem nula. Nesses casos cai para regiao-imediata >
    regiao-intermediaria > UF, que carrega a mesma informacao.
    """
    caminhos = (
        ("microrregiao", "mesorregiao"),
        ("regiao-imediata", "regiao-intermediaria"),
    )
    for externo, interno in caminhos:
        no = (municipio.get(externo) or {}).get(interno) or {}
        uf = no.get("UF") or {}
        if uf.get("sigla"):
            return uf["sigla"], (uf.get("regiao") or {}).get("nome", "")
    return "", ""


def buscar_municipios(uf=None, timeout=None):
    """
    Consulta a API e devolve a lista de municipios ja normalizada.

    Com `uf` busca so aquela unidade federativa, o que e bem mais rapido que
    baixar os mais de cinco mil municipios do pais.
    """
    url = f"{BASE}/estados/{uf}/municipios" if uf else f"{BASE}/municipios"
    timeout = timeout or getattr(settings, "IBGE_TIMEOUT", 8)

    try:
        resposta = requests.get(url, timeout=timeout, headers={"Accept": "application/json"})
        resposta.raise_for_status()
        dados = resposta.json()
    except requests.RequestException as exc:
        raise ErroIBGE(f"Falha ao consultar a API do IBGE em {url}: {exc}") from exc
    except ValueError as exc:
        raise ErroIBGE(f"A API do IBGE devolveu conteudo que nao e JSON: {exc}") from exc

    normalizados = []
    for m in dados:
        sigla, regiao = _uf_e_regiao(m)
        normalizados.append(
            {
                "codigo_ibge": str(m["id"]),
                "nome": m["nome"],
                "uf": sigla,
                "regiao": regiao,
            }
        )
    return normalizados


def sincronizar_municipios(uf=None):
    """
    Grava os municipios da API no banco e devolve quantos foram criados e
    atualizados. Idempotente: rodar duas vezes nao duplica registro.
    """
    from painel.models import Municipio

    registros = buscar_municipios(uf=uf)

    ja_existiam = set(
        Municipio.objects.filter(
            codigo_ibge__in=[r["codigo_ibge"] for r in registros]
        ).values_list("codigo_ibge", flat=True)
    )

    # Upsert em lote. Com update_or_create por municipio seriam mais de 11 mil
    # consultas para os 5.571 municipios do pais: em SQLite local passa, mas
    # contra o Neon, com latencia de rede em cada ida, levaria varios minutos.
    Municipio.objects.bulk_create(
        [
            Municipio(
                codigo_ibge=r["codigo_ibge"],
                nome=r["nome"],
                uf=r["uf"],
                regiao=r["regiao"],
            )
            for r in registros
        ],
        batch_size=1000,
        update_conflicts=True,
        update_fields=["nome", "uf", "regiao"],
        unique_fields=["codigo_ibge"],
    )

    criados = sum(1 for r in registros if r["codigo_ibge"] not in ja_existiam)
    atualizados = len(registros) - criados

    logger.info("IBGE sincronizado: %s criados, %s atualizados", criados, atualizados)
    return criados, atualizados


def municipios_em_cache(uf=None):
    """Le do banco, sem tocar na rede. E o que o painel usa."""
    from painel.models import Municipio

    qs = Municipio.objects.all()
    if uf:
        qs = qs.filter(uf=uf.upper())
    return qs
