# Deploy do EducaAlerta

Passo a passo verificado em 28/09/2026. Custo total: **R$ 0**, sem cartão de crédito.

**A ordem importa.** O Neon vem antes do Render, porque o Render pede a
connection string do banco durante a criação do serviço.

Tempo estimado: 30 a 40 minutos, quase tudo esperando build.

---

## Passo 1. Publicar o código no GitHub

Hoje o repositório remoto tem apenas 3 arquivos. Sem o código lá, o Render não
tem o que publicar.

```bash
cd Desktop/univesp/univesp-pi-ii

# O Render executa ./build.sh. Sem o bit de execução, o build falha com
# "permission denied". No Windows o Git não guarda esse bit sozinho.
git add .
git update-index --chmod=+x build.sh

git commit -m "Implementa o EducaAlerta: ETL do INEP, API REST, painel acessivel e testes"
git push
```

O `git push` vai abrir o navegador para você entrar no GitHub, se ainda não
estiver autenticada.

**Confira antes de seguir:** abra o repositório no navegador e veja se a aba
Actions mostra o CI rodando. Ele executa `check`, confere migrations, roda os 140
testes e valida o `collectstatic`. Se o CI ficar verde, o build no Render também
vai passar.

---

## Passo 2. Criar o banco no Neon

1. Entrar em https://neon.com e criar conta com o login do GitHub.
2. **Create project**, preenchendo:

| Campo | Valor | Por quê |
|---|---|---|
| Project name | `educaalerta` | |
| Region | **AWS US East 1 (N. Virginia)** | Precisa ser a mesma região do Render, que está como `virginia` no `render.yaml`. Aplicação e banco em costas opostas dos EUA somariam cerca de 60 ms por consulta. Virginia também é a região dos EUA mais próxima do Brasil |
| Services | só **Postgres database** | Object storage, Functions, AI gateway e Neon Auth não são usados e consomem cota |
| Database name | `neondb` | O padrão basta |
| Postgres version | **17** | O Django 5.2 declara suporte a PostgreSQL 14 ou superior, sem limite máximo, então a 18 deve funcionar. Mas a 17 tem muito mais rodagem com o Django 5.2, e não há ganho algum em usar a mais nova aqui. Trocar de versão depois exigiria recriar o banco |

3. Na tela do projeto, achar **Connection string** e copiar. O formato é:

```
postgresql://usuario:senha@ep-algo-123456.us-east-1.aws.neon.tech/neondb?sslmode=require
```

Guarde essa string. Ela é segredo: **nunca** entra no repositório.

> Por que Neon e não o PostgreSQL do Render: o banco gratuito do Render **expira
> 30 dias depois de criado**. O PI vai até novembro, então ele morreria no meio do
> semestre. O plano gratuito do Neon não expira e desperta sozinho depois de
> hibernar.

---

## Passo 3. Publicar a aplicação no Render

1. Entrar em https://render.com e criar conta com o login do GitHub.
2. **New** → **Blueprint**.
3. Selecionar o repositório `univesp-pi-ii`. O Render lê o `render.yaml` e já
   configura o serviço: plano free, build `./build.sh`, start
   `gunicorn educaalerta.wsgi:application`, health check em `/saude/`.
4. O Render vai **pedir o valor de `DATABASE_URL`**, porque no `render.yaml` ela
   está marcada como `sync: false`. Cole a connection string do Neon.
   A `DJANGO_SECRET_KEY` é gerada automaticamente, você não precisa criar nenhuma.
5. **Apply**. O primeiro build leva de 3 a 5 minutos.

Se o build falhar, a mensagem no log diz o motivo. Os dois erros mais comuns:

| Erro no log | Causa | Correção |
|---|---|---|
| `permission denied: ./build.sh` | Faltou o bit de execução | Rodar `git update-index --chmod=+x build.sh`, commitar e dar push |
| `DATABASE_URL nao definida com DEBUG desligado` | A variável não foi cadastrada | Adicionar em Environment e clicar em Manual Deploy |

Essa segunda mensagem é proposital. Sem ela, o Django cairia para SQLite no disco
efêmero do contêiner: a aplicação subiria, pareceria funcionar, e perderia todos
os dados a cada deploy.

---

## Passo 4. Carregar os dados no Neon

O banco está vazio: o `build.sh` só criou as tabelas. Rode a carga **da sua
máquina**, apontando para o Neon. É mais rápido que o terminal do Render e você vê
o que está acontecendo.

No Git Bash, dentro da pasta do projeto:

```bash
export DATABASE_URL="cole-aqui-a-connection-string-do-neon"

.venv/Scripts/python.exe manage.py sincronizar_ibge
.venv/Scripts/python.exe manage.py carregar_dados dados_processados/indicadores.csv
.venv/Scripts/python.exe manage.py calcular_risco
```

Tempos medidos localmente: 2s, 8s e 6s. Contra o Neon deve levar um pouco mais,
por causa da rede, mas fica na casa de segundos, não de minutos. As três operações
são idempotentes: rodar de novo não duplica nada.

O `indicadores.csv` já está no repositório, com os 40.377 registros reais do INEP,
então você não precisa baixar nem reprocessar as planilhas.

Ao terminar, **feche o terminal ou rode `unset DATABASE_URL`**. Com ela exportada,
qualquer comando que você rodar vai contra o banco de produção. Os testes são a
exceção: eles ignoram essa variável de propósito e sempre usam SQLite, justamente
para não haver risco de a suíte apagar dados reais.

---

## Passo 5. Conferir

Trocar `educaalerta` pelo nome real do serviço na URL:

| Endereço | O que esperar |
|---|---|
| `https://educaalerta.onrender.com/saude/` | `{"status": "ok", "escolas": 20406, "indicadores": 40377, "riscos": 40377, ...}` |
| `https://educaalerta.onrender.com/` | O painel com o ranking preenchido |
| `https://educaalerta.onrender.com/sobre/` | A página de metodologia |
| `https://educaalerta.onrender.com/api/` | A API navegável |

Se `/saude/` devolver zeros, o Passo 4 não chegou ao banco certo.

**O primeiro acesso leva de 30 a 60 segundos.** O plano gratuito hiberna após 15
minutos sem uso. Isso é esperado e está avisado no README.

---

## Passo 6. Guardar as evidências para o Relatório Parcial

Três capturas de tela que valem mais que parágrafos:

1. **O painel funcionando**, com a URL visível na barra de endereços. Evidência de
   nuvem e de script web.
2. **A aba Events do Render**, mostrando os deploys disparados pelos seus commits.
   Essa amarra nuvem e controle de versão numa evidência só.
3. **A aba Actions do GitHub** com o CI verde. Evidência de testes.

E anote a URL pública no relatório e no `README.md`, no campo que hoje está como
*a publicar*.

---

## Depois do deploy

- **Manter o serviço acordado na semana da entrega**: cadastrar a URL no
  UptimeRobot, gratuito, com ping a cada 10 minutos. O mês tem no máximo 744 horas
  e a cota do Render é de 750, então um serviço sempre ativo cabe, sem margem.
- **Antes de gravar o vídeo**: abrir a aplicação um minuto antes, para ela já estar
  acordada e a demonstração fluir.
- **Se o Render mudar de regra**: `nuvem/PLANO_B.md` tem as alternativas. Vale
  ativar o GitHub Student Pack agora, que dá crédito Azure sem cartão e leva
  alguns dias para aprovar.
