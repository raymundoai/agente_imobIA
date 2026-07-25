# Relatorio de Validacao do Sistema

Data da revisao: 2026-07-07

## Escopo

Revisao da estrutura atual do projeto, com foco nas regras de negocio abaixo:

- Backend com banco de imoveis.
- Backend com banco de clientes/leads.
- System prompt padrao populado por variaveis configuradas no front.
- Acesso dos agentes IA aos cadastros de imoveis via MCP.
- Acesso dos agentes IA aos cadastros de clientes/leads via MCP.
- Integridade das funcoes predefinidas no frontend em relacao ao sistema.

## Resultado Das Validacoes

Validacoes executadas:

```bash
cd backend && pytest
```

Resultado: 16 passed, 13 skipped.

```bash
cd frontend && npm run build
```

Resultado: build concluido com sucesso.

## Regras De Negocio

| Regra | Status | Avaliacao |
| --- | --- | --- |
| 2.1 DB de imoveis | Parcial | Existe tabela `properties`, vinculo com demandas e listagem por tenant em `backend/app/modules/properties`. Porem o cadastro manual de "imoveis proprios" no frontend grava apenas em `localStorage`, nao no backend. |
| 2.2 DB de clientes/leads | Parcial | Existe `lead_demands` para demandas/leads em `backend/app/modules/leads`. Nao existe tabela/API real de `contacts` ou clientes ativos; a tela de Contatos e mockada. |
| 2.3 System prompt com variaveis do front | Parcial | O agente injeta `tenant.settings` inteiro no prompt. O front salva `profile` e `agents` em `tenant.settings`. Porem o prompt ainda e generico, sem montagem por agente, sem status/escopo/ferramentas por agente. |
| 2.4 IA acessa imoveis via MCP | Nao implementado | Nao ha dependencia MCP, servidor MCP ou cliente MCP. As tools do agente nao incluem busca/listagem de imoveis. |
| 2.5 IA acessa clientes/leads via MCP | Nao implementado | O agente consegue criar/atualizar lead por function calling, mas nao ha MCP nem ferramenta para consultar/listar cadastros de clientes/leads. |

## Evidencias Tecnicas

### Backend

- A aplicacao e um monolito modular FastAPI com SQLAlchemy/Alembic.
- Rotas principais registradas em `backend/app/main.py`.
- DB de imoveis:
  - Model: `backend/app/modules/properties/adapters/models.py`
  - API: `backend/app/modules/properties/api.py`
  - Repositorio: `backend/app/modules/properties/adapters/repositories.py`
  - Captura: `backend/app/modules/capture/api.py`
- DB de leads/demandas:
  - Model: `backend/app/modules/leads/adapters/models.py`
  - API: `backend/app/modules/leads/api.py`
  - Repositorio: `backend/app/modules/leads/adapters/repositories.py`
- Agente IA:
  - Use case: `backend/app/modules/ai/application/use_cases.py`
  - Provider OpenAI: `backend/app/modules/ai/adapters/openai_adapter.py`
  - Auditoria: `ai_audit_logs`
- O system prompt e montado em `_system_prompt(settings, chunks)`, com:
  - instrucao generica do ImobIA;
  - `tenant.settings` serializado;
  - trechos RAG recuperados.
- Tools atuais do agente:
  - `search_knowledge_base`
  - `request_human_handoff`
  - `record_usage`
  - `create_or_update_lead`
  - `create_maintenance_ticket`
- Nao ha tools para:
  - buscar imoveis proprios;
  - sugerir imoveis compativeis;
  - consultar lead por telefone;
  - consultar/listar clientes;
  - consultar contatos ativos;
  - expor recursos via MCP.

### MCP

Nao foram encontrados:

- pacote/dependencia MCP em `backend/pyproject.toml`;
- modulo `mcp`;
- servidor MCP;
- cliente MCP;
- contratos de tools MCP;
- limites/regras MCP por agente;
- testes de MCP.

Conclusao: MCP ainda nao esta implementado.

### Frontend

O frontend e React/Vite.

Telas principais roteadas:

- Dashboard
- Conversas
- Contatos
- Imoveis
- Configuracoes

`CapturePage` existe, mas o item "Buscador" esta desabilitado na sidebar.

Paginas existentes mas nao roteadas diretamente no app principal:

- `LeadsPage`
- `MaintenancePage`
- `KnowledgePage`
- `UsagePage`

Algumas dessas funcionalidades aparecem duplicadas ou parcialmente expostas dentro de Configuracoes.

## Integridade Das Funcoes Do Front

### Imoveis

Problema: cadastro manual nao persiste no backend.

Detalhes:

- `PropertiesPage` carrega `/properties`, mas tambem mistura dados de `localStorage`.
- Ao cadastrar imovel manualmente, cria um objeto local com `tenant_id: "local"`.
- O salvamento usa `addLocalProperty`, que grava em `window.localStorage`.
- Importacao de carteira apenas exibe mensagem de processamento futuro.
- Otimizacao de imagens com IA e apenas metadado local, sem backend.

Impacto:

- Os imoveis manuais nao entram no banco.
- O agente nao consegue acessar esses imoveis pelo backend.
- Dashboard e APIs nao contam esses imoveis.
- Dados ficam presos ao navegador.

### Contatos / Clientes

Problema: tela totalmente mockada.

Detalhes:

- `ContactsPage` usa array hardcoded.
- Busca, filtros e detalhe funcionam apenas em memoria.
- Botao "Novo contato" nao abre fluxo real.
- Botao "Salvar alteracoes" nao chama API.
- Nao existe modulo backend `contacts`.

Impacto:

- Nao ha cadastro real de clientes ativos, inquilinos ou proprietarios.
- Nao ha fonte backend para a IA consultar clientes.
- A regra 2.2 so e atendida para leads/demandas, nao para clientes completos.

### Conversas

Problema: tela principal mistura API com demo/local state.

Detalhes:

- Se `/conversations` retorna vazio ou falha, a tela usa `demoConversations`.
- Mensagens enviadas pela tela principal sao adicionadas via `appendMessage`, sem API.
- `Assumir`, toggle IA, anexos e compartilhamento de imovel nao persistem.
- `ConversationDetailPage` tem integracao real com `PATCH /mode` e `POST /messages`, mas ela nao e usada no fluxo principal.

Impacto:

- O operador pode acreditar que alterou estado real, mas parte do fluxo fica apenas no browser.
- Toggle IA/agente nao controla o backend.
- Handoff real nao acontece pela tela principal.

### Agentes

Status: parcialmente conectado.

Detalhes:

- `AgentsSettingsPanel` salva configuracao em `tenant.settings.agents`.
- Campos configurados:
  - nome;
  - status;
  - publico;
  - objetivo;
  - canais;
  - base usada;
  - regras de handoff;
  - restricoes;
  - mensagem de transferencia.

Lacunas:

- Backend nao escolhe agente real por conversa.
- Prompt nao e montado por agente.
- Status `inactive` nao impede uso do agente.
- Ferramentas nao sao filtradas por agente.
- Nao ha auditoria por agente.

### Empresa / Configuracao Do Negocio

Status: parcialmente conectado.

Detalhes:

- `TenantSettingsPanel` salva `profile` em `tenant.settings`.
- O agente injeta `tenant.settings` no prompt.

Lacunas:

- Nao ha schema validado para `settings`.
- Backend injeta o JSON bruto, sem normalizacao orientada para prompt.
- Nao ha separacao clara entre configuracao publica, regras de negocio e configuracao operacional.

### Canais

Status: parcialmente conectado.

Detalhes:

- WhatsApp Evolution tem rotas reais de conectar/status.
- Configuracao de canais salva em `tenant.settings.channels`.
- Instagram e UI futura.

Lacunas:

- Mapeamento canal -> agente nao e usado pelo backend.
- Recebimento via webhook grava mensagem e publica `MessageReceived`, mas nao dispara IA automaticamente.

### Integracoes

Status: setup assistido.

Detalhes:

- Backend tem setup de Kenlo, Tecimob, Jetimob e Orulo.
- Tecimob tem adapter com portas para imoveis, contatos e leads.

Lacunas:

- Nao ha sincronizacao real para popular `properties`/`contacts`.
- Credenciais ficam por variavel de ambiente no MVP.
- Integracao com platform adapter nao esta ligada ao agente nem ao MCP.

### Base De Conhecimento

Status: funcional para RAG.

Detalhes:

- Upload, listagem, remocao e busca por tenant existem.
- Busca RAG filtra por `tenant_id`.
- Chunks usados sao registrados em auditoria.

Lacunas:

- Nao ha escopo por agente/documento.
- A busca nao diferencia `leads`, `service`, `maintenance`, `owners`, `tenants`, `general`.

## Principais Riscos

1. O sistema aparenta ter cadastro de imoveis proprios, mas esses dados nao estao no backend.
2. O sistema aparenta ter cadastro de contatos/clientes, mas a tela e mockada.
3. Agentes configurados no front nao controlam efetivamente prompt, ferramentas ou comportamento no backend.
4. MCP nao existe, entao as regras 2.4 e 2.5 nao sao atendidas.
5. Webhook nao dispara resposta automatica da IA; exige chamada manual a `/ai/conversations/{id}/respond`.
6. Chat principal pode divergir do estado real, pois varias acoes sao apenas locais.

## Recomendacao De Proximos Passos

1. Criar modulo backend real de `contacts`/clientes:
   - tabela `contacts`;
   - tipo: lead, cliente ativo, inquilino, proprietario;
   - telefone/email/tags/notas;
   - endpoints CRUD e busca por telefone.
2. Persistir cadastro manual de imoveis no backend:
   - `POST /properties` para imoveis proprios;
   - diferenciar `source=manual` e `via_extension=false`;
   - upload/armazenamento real de imagens ou metadados.
3. Implementar selecao real de agente:
   - `current_agent` ou campo equivalente na conversa;
   - selecao por canal, tipo de contato e contexto;
   - persistencia do toggle IA/handoff.
4. Refatorar montagem do system prompt:
   - usar `tenant.settings.profile`;
   - usar `tenant.settings.agents[agent_key]`;
   - montar identidade, objetivo, publico, restricoes, handoff, ferramentas permitidas e contexto RAG.
5. Implementar MCP:
   - servidor MCP interno ou adapter MCP;
   - tools para `search_properties`, `get_property`, `search_leads`, `get_lead`, `search_contacts`;
   - limites por tenant/agente;
   - logs/auditoria de chamadas.
6. Conectar webhook ao agente:
   - subscriber para `MessageReceived`;
   - respeitar `conversation.mode`;
   - nao responder em handoff/humano;
   - registrar auditoria e uso.
7. Remover ou sinalizar flows mockados no frontend:
   - substituir `ContactsPage` por API real;
   - remover fallback demo em producao;
   - conectar chat principal ao backend.

## Conclusao

A base backend de imoveis, leads, knowledge, conversas, manutencao, usuarios e auditoria esta bem encaminhada e com isolamento por tenant. O sistema ainda nao atende completamente as regras solicitadas porque faltam MCP, cadastro real de contatos/clientes, persistencia real de imoveis manuais, prompt por agente e integracao efetiva entre configuracoes do front e runtime dos agentes.
