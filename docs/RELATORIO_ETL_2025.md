# Relatório do ETL

Gerado por `manage.py processar_inep`. Este arquivo é a prestação de
contas sobre o que a limpeza descartou e por quê.

- Etapa de ensino: **MED**
- Recorte de rede: **estadual**
- Linhas no CSV final: **20594**
- Escolas distintas: **20594**

## 2025

```
Linhas lidas: 126684
Linhas validas: 20594
Descartes:
  fora do recorte de rede ('estadual',): 98561
  sem nenhum indicador disponivel: 7529
Ausentes por coluna:
  distorcao_idade_serie: 177
  inse: 20594
  taxa_abandono: 4
  taxa_aprovacao: 4
  taxa_reprovacao: 4
```
