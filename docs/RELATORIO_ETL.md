# Relatório do ETL

Gerado por `manage.py processar_inep`. Este arquivo é a prestação de
contas sobre o que a limpeza descartou e por quê.

- Etapa de ensino: **MED**
- Recorte de rede: **estadual**
- Linhas no CSV final: **40384**
- Escolas distintas: **20408**

## 2023

```
Linhas lidas: 128370
Linhas validas: 20152
Descartes:
  fora do recorte de rede ('estadual',): 100336
  sem nenhum indicador disponivel: 7882
Ausentes por coluna:
  distorcao_idade_serie: 139
  inse: 20152
  taxa_abandono: 5
  taxa_aprovacao: 5
  taxa_reprovacao: 5
```

## 2024

```
Linhas lidas: 128096
Linhas validas: 20232
Descartes:
  fora do recorte de rede ('estadual',): 100264
  sem nenhum indicador disponivel: 7600
Ausentes por coluna:
  distorcao_idade_serie: 157
  inse: 20232
  taxa_abandono: 2
  taxa_aprovacao: 2
  taxa_reprovacao: 2
```
