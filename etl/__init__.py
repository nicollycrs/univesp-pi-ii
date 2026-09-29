"""
Pacote de ETL do EducaAlerta.

Roda na maquina local, nunca no processo web. O motivo e a restricao de 0,5 GB
do banco no plano gratuito do Neon: os microdados brutos do INEP tem varios GB e
nao cabem na nuvem. A limpeza e a agregacao por escola acontecem aqui, e para a
nuvem sobe apenas a tabela agregada.

pandas fica restrito a este pacote. O processo web roda em instancia de 512 MB
de RAM, e importar pandas ali custaria memoria demais.
"""
