"""
Configuracao do projeto EducaAlerta.

Principio: nada de segredo escrito no codigo. Tudo que muda entre a maquina
local e a nuvem vem de variavel de ambiente.

Banco: com DATABASE_URL definida usa PostgreSQL (Neon em producao); sem ela,
cai para SQLite, o que permite rodar os testes sem infraestrutura.
"""

import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Le o .env apenas na maquina local; no Render as variaveis vem do painel.
if (BASE_DIR / ".env").exists():
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")


# ----------------------------------------------------------------- SEGURANCA
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

# Deteta execucao de teste. Usado para afrouxar exigencias que so fazem sentido
# em producao, como o manifesto de arquivos estaticos.
TESTANDO = (
    "pytest" in sys.modules
    or bool(os.environ.get("PYTEST_VERSION"))
    or "test" in sys.argv
)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or TESTANDO:
        SECRET_KEY = "django-insecure-chave-apenas-para-desenvolvimento-local"
    else:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY nao definida. Em producao ela e obrigatoria."
        )

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]
if DEBUG:
    ALLOWED_HOSTS += ["127.0.0.1", "localhost", "testserver"]

# O Render publica o dominio da aplicacao nesta variavel automaticamente.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS = [f"https://{RENDER_EXTERNAL_HOSTNAME}"]

if not DEBUG and not TESTANDO:
    # O Render encerra o TLS no proxy. Sem esta linha o Django nao percebe que a
    # requisicao chegou por HTTPS e entra em laco de redirecionamento.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # HSTS: obriga o navegador a usar HTTPS nas visitas seguintes. Um ano e o
    # valor recomendado. Comeca modesto de proposito, porque HSTS e dificil de
    # reverter: uma vez enviado, o navegador guarda a regra pelo prazo indicado.
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", 3600))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

# Avisos silenciados de proposito, com justificativa:
#   security.W005 (HSTS includeSubdomains) e security.W021 (HSTS preload)
# A aplicacao roda em subdominio de onrender.com, que o projeto nao controla.
# Aplicar HSTS a subdominios de terceiros ou pedir inclusao na lista de preload
# do navegador seria incorreto. Revisar se um dia houver dominio proprio.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]


# ---------------------------------------------------------------- APLICACOES
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "painel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise entra logo apos o SecurityMiddleware: e ele que serve CSS e JS
    # em producao, dispensando servidor de arquivos separado.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "educaalerta.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "educaalerta.wsgi.application"


# --------------------------------------------------------------------- BANCO
DATABASE_URL = os.environ.get("DATABASE_URL")

if TESTANDO:
    # Teste sempre em SQLite, mesmo com DATABASE_URL definida no ambiente.
    # Isso e uma salvaguarda: sem ela, quem tivesse a connection string do Neon
    # exportada rodaria a suite contra o banco de producao, e pytest-django cria
    # e destroi o banco de teste. O risco de perder dados reais nao vale a
    # semelhanca com producao.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db_teste.sqlite3",
        }
    }
elif DATABASE_URL:
    # Erro comum: colar so o host em vez da string de conexao inteira. Sem esta
    # verificacao, o dj_database_url falha com "No support for ''", que nao diz
    # a ninguem o que fazer. A mensagem abaixo diz.
    if "://" not in DATABASE_URL:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "DATABASE_URL nao e uma string de conexao valida: falta o esquema. "
            f"O valor definido tem {len(DATABASE_URL)} caracteres e nao contem '://'. "
            "Um erro comum e colar apenas o host. O valor precisa ser a string "
            "inteira, no formato "
            "postgresql://usuario:senha@host.neon.tech/neondb?sslmode=require"
        )

    # conn_max_age mantem a conexao aberta por 10 min. Importante porque o computo
    # do Neon hiberna, e reabrir conexao a cada requisicao custa caro.
    _config = dj_database_url.parse(
        DATABASE_URL, conn_max_age=600, conn_health_checks=True
    )
    # SSL obrigatorio, mas so em Postgres: uma URL sqlite:// nao entende sslmode,
    # e o CI usa justamente uma dessas para validar a configuracao sem subir banco.
    if "postgresql" in _config.get("ENGINE", ""):
        _config.setdefault("OPTIONS", {})["sslmode"] = os.environ.get(
            "DJANGO_DB_SSLMODE", "require"
        )
    DATABASES = {"default": _config}
elif DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    # Falha alto de proposito. Em producao sem DATABASE_URL o Django cairia para
    # SQLite no disco efemero do container: a aplicacao subiria, pareceria
    # funcionar, e perderia todos os dados a cada deploy. Um erro de
    # configuracao visivel e muito melhor que essa perda silenciosa.
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "DATABASE_URL nao definida com DEBUG desligado. Em producao o banco e "
        "obrigatorio: cadastre a connection string do Neon na variavel "
        "DATABASE_URL do Render. Sem isso os dados seriam perdidos a cada deploy."
    )

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ------------------------------------------------------------------ REST API
REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}


# ------------------------------------------------------- ARQUIVOS ESTATICOS
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Em producao comprime e versiona os estaticos com hash no nome, o que
        # permite cache longo no navegador. Em desenvolvimento e em teste usa o
        # backend simples, porque o manifesto so existe depois do collectstatic.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if (DEBUG or TESTANDO)
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}


# ---------------------------------------------------------------- LOCALIZACAO
# LANGUAGE_CODE tambem importa para acessibilidade: o Django usa este valor no
# atributo lang do <html>, que e o que faz o leitor de tela pronunciar a pagina
# em portugues. Criterio 3.1.1 da WCAG 2.1, nivel A.
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------- CONFIG DO PROJETO
# Tempo de cache da consulta a API do IBGE, em segundos (24 h por padrao).
IBGE_CACHE_SEGUNDOS = int(os.environ.get("IBGE_CACHE_SEGUNDOS", 86400))
IBGE_TIMEOUT = float(os.environ.get("IBGE_TIMEOUT", 8))
