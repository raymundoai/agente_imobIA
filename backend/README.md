# ImobIA API

## Desenvolvimento

1. Copie `.env.example` para `.env` e substitua todos os placeholders.
2. Inicie o PostgreSQL: `docker compose --env-file backend/.env up -d postgres`.
3. Em `backend/`, instale: `python -m pip install -e '.[dev]'`.
4. Aplique o schema: `alembic upgrade head`.
5. Execute: `uvicorn app.main:app --reload`.

O cadastro inicial é feito por `POST /tenants`, que cria tenant e primeiro usuário
administrador na mesma transação. Login exige `tenant_slug`, `email` e `password`.

## Evolution API

Para o fluxo gerenciado pelo ImobIA, configure a URL e a chave global da
Evolution somente no backend:

```dotenv
EVOLUTION_BASE_URL=https://evolution.exemplo
EVOLUTION_API_KEY=...
EVOLUTION_VERSION=2.3.1
BACKEND_PUBLIC_URL=
```

No desenvolvimento local, `BACKEND_PUBLIC_URL` pode ficar vazio. A geração do QR
Code funciona, mas o recebimento de mensagens por webhook só funciona quando o
backend tem URL pública acessível pela Evolution.

Rotas autenticadas usadas pelo frontend:

```http
POST /integrations/evolution/whatsapp/connect
GET  /integrations/evolution/whatsapp/status
```

O ImobIA cria/reutiliza uma instância com o padrão
`imobia-{slug-da-empresa}-whatsapp` e grava no `settings` público apenas
metadados não sensíveis, como status e nome da instância.

O fluxo legado por tenant também é suportado por ambiente, em um mapa JSON:

```dotenv
EVOLUTION_TENANT_CONFIGS={"slug-do-tenant":{"base_url":"https://evolution.exemplo","instance":"nome-instancia","api_key":"...","webhook_secret":"..."}}
```

Configure na Evolution o evento `MESSAGES_UPSERT` apontando para:

```text
https://api.exemplo/webhooks/whatsapp/slug-do-tenant?token=WEBHOOK_SECRET
```

O envio humano usa `POST /message/sendText/{instance}` através de
`MessageChannelPort`. Repetições do mesmo `external_message_id` são ignoradas em
transação e não duplicam `UsageRecord`.

## OpenAI + Knowledge Base

Configure a chave só por variável de ambiente:

```dotenv
OPENAI_API_KEY=...
OPENAI_CHAT_MODEL=gpt-5.5
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

A Fase 3 adiciona `KnowledgeDocument`, `KnowledgeChunk` com pgvector e
`AiAuditLog`. O upload MVP usa JSON com `content_base64`:

```http
POST /knowledge/documents
```

O pipeline passa pela porta `KnowledgeJobQueuePort` e pelo adapter in-process do
MVP; pode ser trocado por Redis/RQ sem alterar os casos de uso. Toda busca RAG é
executada com filtro obrigatório `tenant_id`.

Para testar respostas automáticas localmente sem enviar à Evolution, use
`AI_AUTO_REPLY_ENABLED=true` e `AI_AUTO_SEND_TO_CHANNEL=false`. O roteiro completo está em
`../docs/teste-local-agente-leads.md`.

## HubSpot + SDR

As credenciais do HubSpot são configuradas somente por ambiente, em mapa JSON por
tenant:

```dotenv
HUBSPOT_TENANT_CONFIGS={"slug-do-tenant":{"base_url":"https://api.hubapi.com","access_token":"...","pipeline_id":"...","stage_ids":{"qualified":"..."},"owner_map":{"default":"...","handoff":"..."}}}
HUBSPOT_API_VERSION=2026-03
```

O agente IA chama a ferramenta `create_or_update_lead`; o caso de uso depende de
`LeadQualificationPort`, que persiste `LeadDemand` por `tenant_id` e sincroniza
contato, deal, nota e tarefa via `CrmPort`. Nenhum caso de uso chama HubSpot
diretamente.

## Integrações MVP

O setup assistido de Kenlo, Tecimob, Jetimob e Órulo usa rotas autenticadas para
registrar status por empresa sem expor credenciais no frontend:

```http
GET  /integrations/setup
POST /integrations/setup
```

Checklist operacional e dados necessários por fornecedor:
`docs/integracoes-mvp.md`.

### Tecimob

A integração Tecimob usa a API oficial em `https://api.tecimob.com.br/v1` com
autenticação Bearer. Configure por tenant:

```dotenv
TECIMOB_TENANT_CONFIGS={"demo":{"base_url":"https://api.tecimob.com.br/v1","access_token":"CHAVE_API"}}
```

Rotas de apoio:

```http
GET  /integrations/tecimob/status
POST /integrations/tecimob/test
```

## Atendimento interno / Manutenção

A Fase 5 adiciona `MaintenanceTicket` com rotas:

```http
GET   /maintenance/tickets
GET   /maintenance/tickets/{id}
PATCH /maintenance/tickets/{id}
POST  /maintenance/tickets
```

O agente IA usa a ferramenta `create_maintenance_ticket` via
`MaintenanceTicketingPort`. Guardrails hardcoded fazem handoff antes de chamar o
modelo para temas financeiros, jurídicos, rescisão ou alteração/cancelamento de
contrato.

## Captação

A Fase 6 adiciona demandas, imóveis captados e missões para extensão:

```http
POST  /leads/demands
GET   /leads/demands
GET   /leads/demands/{id}
PATCH /leads/demands/{id}

GET   /properties?demand_id=
GET   /capture/missions/{demand_id}
POST  /capture/properties
```

`POST /capture/properties` normaliza campos, detecta duplicatas por
`source_url` ou hash de campos-chave, e vincula o imóvel à demanda no escopo do
`tenant_id`.

## Testes

Testes unitários não dependem de serviços externos. Testes de integração exigem
`TEST_DATABASE_URL` apontando para um banco PostgreSQL descartável e aplicam as
migrations Alembic antes de executar.

```bash
pytest
```

## WebApp MVP

A Fase 7 adiciona o painel React/Vite em `frontend/`. Para rodar localmente:

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

O Vite usa proxy `/api` para `http://127.0.0.1:8000`. Em produção, configure
`VITE_API_BASE_URL` por variável de ambiente.
