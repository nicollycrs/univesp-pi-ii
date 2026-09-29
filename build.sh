#!/usr/bin/env bash
# Script de build executado pelo Render a cada deploy.
# Registrar como executavel antes do primeiro push:
#   git update-index --chmod=+x build.sh

set -o errexit  # aborta o deploy se qualquer etapa falhar

pip install -r requirements.txt

# Reune os arquivos estaticos para o WhiteNoise servir
python manage.py collectstatic --no-input

# Aplica as migracoes no banco do Neon
python manage.py migrate --no-input
