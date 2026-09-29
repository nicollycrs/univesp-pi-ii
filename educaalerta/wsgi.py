"""Ponto de entrada WSGI, usado pelo gunicorn em producao."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "educaalerta.settings")

application = get_wsgi_application()
