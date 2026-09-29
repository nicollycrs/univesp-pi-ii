# Relatório do ETL

Gerado por `manage.py processar_inep`. Este arquivo é a prestação de
contas sobre o que a limpeza descartou e por quê.

- Etapa de ensino: **MED**
- Recorte de rede: **estadual**
- Linhas no CSV final: **40377**
- Escolas distintas: **20406**

## 2023

```
Linhas lidas: 128370
Linhas validas: 20147
Descartes:
  fora do recorte de rede ('estadual',): 100336
  sem nenhum indicador disponivel: 7887
Ausentes por coluna:
  distorcao_idade_serie: 20147
  inse: 20147
```

## 2024

```
Linhas lidas: 128096
Linhas validas: 20230
Descartes:
  fora do recorte de rede ('estadual',): 100264
  sem nenhum indicador disponivel: 7602
Ausentes por coluna:
  distorcao_idade_serie: 20230
  inse: 20230
```
