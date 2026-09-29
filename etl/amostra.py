"""
Gerador de amostra para desenvolvimento.

ATENCAO. Os dados produzidos aqui NAO SAO REAIS. Existem para que a aplicacao
possa ser desenvolvida, testada e demonstrada enquanto os arquivos oficiais do
INEP estao sendo baixados e mapeados.

Salvaguardas contra confundir amostra com dado oficial:
  1. toda linha sai com a coluna `origem` igual a AMOSTRA;
  2. o nome do arquivo gerado diz AMOSTRA_DESENVOLVIMENTO;
  3. o painel exibe aviso em destaque enquanto houver linha de amostra na base;
  4. o endpoint /api/indicadores/resumo/ devolve `contem_dados_de_amostra`.

Nenhum numero vindo daqui pode aparecer no relatorio como resultado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MARCA_ORIGEM = "AMOSTRA"

UFS = ("SP", "MG", "BA", "PA", "RS")


def gerar(n_escolas: int = 400, anos: tuple[int, ...] = (2023, 2024), semente: int = 42) -> pd.DataFrame:
    """
    Gera indicadores sinteticos plausiveis.

    A correlacao negativa entre INSE e abandono e imposta de proposito, para que
    o grafico de dispersao mostre a relacao que a literatura descreve e a
    interface possa ser avaliada com forma realista. Isso e conveniencia de
    desenvolvimento, nao evidencia de nada.
    """
    rng = np.random.default_rng(semente)
    linhas = []

    codigos = rng.choice(np.arange(11_000_000, 99_000_000), size=n_escolas, replace=False)
    ufs = rng.choice(UFS, size=n_escolas)
    redes = rng.choice(("estadual", "municipal"), size=n_escolas, p=(0.7, 0.3))
    locais = rng.choice(("urbana", "rural"), size=n_escolas, p=(0.8, 0.2))
    inse_base = rng.normal(50, 8, size=n_escolas).clip(20, 80)

    for i in range(n_escolas):
        for ano in anos:
            inse = float(np.clip(inse_base[i] + rng.normal(0, 1.5), 20, 80))
            # Abandono cai conforme o INSE sobe, com ruido.
            abandono = float(np.clip((80 - inse) * 0.18 + rng.normal(0, 1.8), 0, 35))
            reprovacao = float(np.clip((75 - inse) * 0.22 + rng.normal(0, 3.0), 0, 40))
            aprovacao = float(np.clip(100 - abandono - reprovacao, 0, 100))
            distorcao = float(np.clip(abandono * 1.6 + rng.normal(0, 4), 0, 70))

            linhas.append(
                {
                    "co_entidade": int(codigos[i]),
                    "nome": f"Escola de Amostra {i + 1:04d}",
                    "uf": ufs[i],
                    "codigo_municipio": None,
                    "rede": redes[i],
                    "localizacao": locais[i],
                    "ano": ano,
                    "taxa_aprovacao": round(aprovacao, 1),
                    "taxa_reprovacao": round(reprovacao, 1),
                    "taxa_abandono": round(abandono, 1),
                    "distorcao_idade_serie": round(distorcao, 1),
                    "inse": round(inse, 2),
                    "origem": MARCA_ORIGEM,
                }
            )

    return pd.DataFrame(linhas)
