# Operação local

Este roteiro é apenas para desenvolvimento. Use valores próprios no `.env`; os exemplos abaixo
não são credenciais válidas.

## 1. Pré-requisitos

- Docker e Docker Compose;
- Python 3.12;
- Node.js compatível com o projeto;
- uma chave OpenAI para testar IA;
- opcionalmente, Evolution API e bot do Telegram.

## 2. Configuração

Na raiz do projeto:

```bash
cp backend/.env.example backend/.env
```

Troque todos os placeholders. Gere segredos locais, por exemplo:

```bash
openssl rand -hex 32
```

Campos essenciais:

```dotenv
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@localhost:5432/BANCO
JWT_SECRET=SEGREDO_COM_PELO_MENOS_32_CARACTERES
OPENAI_API_KEY=SUA_CHAVE
PLATFORM_BOOTSTRAP_TOKEN=OUTRO_SEGREDO_FORTE
```

O `.env` não deve ser versionado.

## 3. Instalação

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cd ..
```

Frontend:

```bash
cd frontend
npm install
cd ..
```

## 4. Subir a aplicação

Terminal 1, banco:

```bash
docker compose --env-file backend/.env up -d postgres
docker compose --env-file backend/.env ps
```

Terminal 2, backend:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 3, painel da imobiliária:

```bash
cd frontend
npm run dev
```

Terminal 4, administração da plataforma:

```bash
cd frontend
npm run dev:platform
```

Acessos:

- painel da imobiliária: `http://localhost:5173`;
- administração da plataforma: `http://localhost:5174`;
- saúde da API: `http://localhost:8000/health`;
- OpenAPI: `http://localhost:8000/docs`.

Para parar o banco sem apagar os dados:

```bash
docker compose --env-file backend/.env stop postgres
```

Evite `docker compose down -v`: `-v` remove o volume do banco.

## 5. Criar acessos

### Administrador da plataforma

O bootstrap funciona uma única vez. Com o backend ativo:

```bash
curl -X POST 'http://127.0.0.1:8000/platform/auth/bootstrap' \
  -H 'Content-Type: application/json' \
  -H 'X-Platform-Bootstrap-Token: SEU_TOKEN_DE_BOOTSTRAP' \
  -d '{
    "name": "Administrador da plataforma",
    "email": "admin-plataforma@seu-dominio.test",
    "password": "ESCOLHA_UMA_SENHA_FORTE"
  }'
```

Depois, entre em `http://localhost:5174`. A chamada é recusada quando já existe um usuário da
plataforma.

### Tenant de teste

Crie a imobiliária pelo painel da plataforma. Defina um slug, e-mail e senha próprios. Entre
em `http://localhost:5173` com:

- slug escolhido;
- e-mail do administrador criado;
- senha escolhida.

Não registre esses valores neste documento ou em commits.

## 6. OpenAI e resposta automática

Configuração mínima:

```dotenv
OPENAI_API_KEY=SUA_CHAVE
OPENAI_CHAT_MODEL=MODELO_DE_CHAT_CONFIGURADO
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
OPENAI_IMAGE_MODEL=gpt-image-1
PROPERTY_MEDIA_ROOT=storage/property-images
PROPERTY_IMAGE_MAX_BYTES=10485760
PROPERTY_IMAGE_MAX_FILES=12
AI_AUTO_REPLY_ENABLED=true
AI_AUTO_SEND_TO_CHANNEL=false
```

Com `AI_AUTO_SEND_TO_CHANNEL=false`, a resposta pode ser gerada e persistida sem ser enviada
ao WhatsApp. Isso é útil no teste de webhook simulado.

A mesma chave pode autorizar chat, embeddings e edição de imagens, conforme os modelos
habilitados na conta. Sem opções de otimização, as imagens são apenas validadas e armazenadas
localmente. Com opções selecionadas, o backend usa `OPENAI_IMAGE_MODEL`; uma falha interrompe o
cadastro e aparece na interface. `PROPERTY_MEDIA_ROOT` é apenas para desenvolvimento: produção
deve usar storage de objetos e acesso protegido.

## 7. Testar WhatsApp sem número real

O webhook exige uma entrada do tenant em `EVOLUTION_TENANT_CONFIGS`, inclusive no teste local:

```dotenv
EVOLUTION_TENANT_CONFIGS={"SLUG":{"base_url":"https://evolution.exemplo","instance":"instancia","api_key":"CHAVE","webhook_secret":"SEGREDO"}}
AI_AUTO_REPLY_ENABLED=true
AI_AUTO_SEND_TO_CHANNEL=false
```

Simule a Evolution, substituindo os placeholders:

```bash
curl -X POST 'http://127.0.0.1:8000/webhooks/whatsapp/SLUG' \
  -H 'Content-Type: application/json' \
  -H 'X-ImobIA-Webhook-Secret: SEGREDO' \
  -d '{
    "event": "MESSAGES_UPSERT",
    "data": {
      "key": {
        "id": "ID_UNICO_DA_MENSAGEM",
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": false
      },
      "pushName": "Cliente Teste",
      "message": {
        "conversation": "Procuro um apartamento para comprar em São Paulo"
      }
    }
  }'
```

A resposta esperada contém `status: "processed"`. Se a IA estiver configurada, também poderá
conter `ai_response`. Use outro `data.key.id` a cada mensagem; IDs repetidos são ignorados.

Para conexão real pelo fluxo gerenciado:

```dotenv
EVOLUTION_BASE_URL=https://SUA_EVOLUTION
EVOLUTION_API_KEY=SUA_CHAVE_GLOBAL
EVOLUTION_VERSION=VERSAO_COMPATIVEL
BACKEND_PUBLIC_URL=https://SUA_API_PUBLICA
```

Conecte o canal pelo QR Code em `Configurações > Canais`.

## 8. Testar Telegram

1. Crie um bot com `@BotFather`.
2. Gere um segredo de webhook.
3. Exponha o backend por uma URL HTTPS, por exemplo com um túnel de desenvolvimento.
4. Configure:

```dotenv
BACKEND_PUBLIC_URL=https://SUA_URL_PUBLICA
TELEGRAM_AUTO_REPLY_ENABLED=true
TELEGRAM_TENANT_CONFIGS={"SLUG":{"bot_token":"TOKEN_DO_BOT","webhook_secret":"SEGREDO","bot_username":"USUARIO_DO_BOT"}}
```

Reinicie o backend e, no painel da imobiliária, use
`Configurações > Canais > Telegram > Configurar webhook`.

O endpoint registrado é:

```text
https://SUA_URL_PUBLICA/webhooks/telegram/SLUG
```

O Telegram envia o segredo em `X-Telegram-Bot-Api-Secret-Token`. O MVP aceita somente
conversas privadas.

## 9. Validação

Backend:

```bash
cd backend
source .venv/bin/activate
pytest
```

Os testes de integração exigem `TEST_DATABASE_URL` apontando para banco PostgreSQL
descartável.

Frontend:

```bash
cd frontend
npm run build
npm run build:platform
```

## 10. Diagnóstico rápido

- banco não sobe: confira as variáveis `POSTGRES_*` e se a porta está livre;
- backend não inicia: execute migrations e confira `DATABASE_URL` e `JWT_SECRET`;
- IA não responde: confira a chave, `AI_AUTO_REPLY_ENABLED` e o modo da conversa;
- resposta não chega ao WhatsApp: confira `AI_AUTO_SEND_TO_CHANNEL`, a instância e a URL
  pública;
- Telegram não recebe: confira a URL HTTPS, segredo, token e status do webhook;
- imagens não salvam: confira formato/tamanho, permissão em `PROPERTY_MEDIA_ROOT`, chave e
  `OPENAI_IMAGE_MODEL`;
- painel da plataforma abriu o painel comum: use `npm run dev:platform` e a porta `5174`.
