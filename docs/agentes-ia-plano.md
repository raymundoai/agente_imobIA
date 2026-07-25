# Plano de Acao - Agentes IA

Objetivo: transformar os agentes IA de uma configuracao visual em um recurso
operacional real, com comportamento por tipo de conversa, regras proprias,
ferramentas especificas e auditoria.

## 1. Modelo De Agentes

- Definir oficialmente os agentes do MVP:
  - `leads`: novos leads e primeiros contatos.
  - `service`: inquilinos, proprietarios e clientes ativos.
- Padronizar campos de configuracao:
  - nome;
  - status;
  - publico;
  - objetivo;
  - canais;
  - regras de handoff;
  - limites de autonomia;
  - mensagem de transferencia;
  - ferramentas habilitadas;
  - escopo da base de conhecimento.
- Manter configuracao em `tenant.settings.agents` no MVP.
- Planejar migracao futura para tabela propria se precisarmos de versionamento e
  historico.

## 2. Estado Da IA Por Conversa

- Adicionar controle real por conversa:
  - agente vinculado;
  - IA ligada/desligada;
  - modo atual: `ai`, `team`, `handoff`;
  - motivo do handoff;
  - data da ultima alteracao;
  - usuario que assumiu, quando aplicavel.
- Expor endpoints para:
  - alterar agente da conversa;
  - ligar/desligar IA;
  - assumir conversa pela equipe;
  - devolver conversa para IA.
- Fazer o toggle do chat persistir no backend, nao so no estado local do
  frontend.

## 3. Selecao Automatica Do Agente

- Criar regra inicial:
  - lead/novo cliente -> `Agente de Leads`;
  - proprietario -> `Agente de Atendimento`;
  - inquilino -> `Agente de Atendimento`;
  - indefinido -> `Agente de Leads`.
- Usar tags/tipo do contato quando existirem.
- Permitir alteracao manual no chat.
- Registrar a decisao para auditoria.

## 4. Prompt Por Agente

- Refatorar o prompt generico atual.
- Criar montagem de system prompt por agente:
  - identidade do agente;
  - objetivo;
  - publico;
  - restricoes;
  - regras de transferencia;
  - ferramentas disponiveis;
  - contexto da empresa;
  - contexto da conversa;
  - trechos da base de conhecimento.
- Garantir que o `Agente de Leads` nao responda como suporte interno.
- Garantir que o `Agente de Atendimento` nao tente vender/captar lead sem
  contexto.

## 5. Ferramentas Do Agente De Leads

- Habilitar ferramentas especificas:
  - cadastrar/atualizar lead;
  - cadastrar demanda;
  - buscar imoveis proprios;
  - sugerir imoveis compativeis;
  - compartilhar imovel;
  - solicitar handoff para corretor;
  - iniciar busca/captacao quando nao houver imovel compativel.
- Definir criterios minimos para lead qualificado:
  - finalidade;
  - cidade/bairro;
  - tipo de imovel;
  - faixa de valor;
  - quartos/vagas;
  - urgencia;
  - nome e telefone.

## 6. Ferramentas Do Agente De Atendimento

- Habilitar ferramentas especificas:
  - criar chamado;
  - consultar chamado;
  - registrar observacao no contato;
  - classificar solicitacao;
  - solicitar handoff;
  - criar tarefa interna.
- Definir assuntos que sempre exigem equipe:
  - juridico;
  - rescisao;
  - negociacao de divida;
  - alteracao contratual;
  - reclamacoes graves;
  - manutencao critica.

## 7. Base De Conhecimento Por Escopo

- Adicionar metadados aos documentos:
  - `leads`;
  - `service`;
  - `maintenance`;
  - `owners`;
  - `tenants`;
  - `general`.
- Ajustar busca RAG para filtrar por escopo do agente.
- Manter fallback para documentos gerais.
- Atualizar tela de Conhecimento depois, se necessario.

## 8. Webhook E Resposta Automatica

- Definir quando a IA responde automaticamente:
  - conversa com IA ativa;
  - agente ativo;
  - canal conectado;
  - sem handoff aberto;
  - mensagem inbound valida;
  - dentro da janela permitida do canal.
- Se IA desligada ou handoff ativo:
  - apenas registrar mensagem;
  - nao responder automaticamente.
- No MVP local, deixar pronto no backend mesmo que o canal oficial ainda esteja
  pendente.

## 9. Auditoria E Metricas

- Registrar por resposta:
  - agente usado;
  - ferramentas chamadas;
  - chunks consultados;
  - motivo de handoff;
  - tokens;
  - custo estimado;
  - status: respondeu, sugeriu, falhou, bloqueou.
- Exibir depois em Uso:
  - respostas por agente;
  - handoffs por agente;
  - leads qualificados;
  - chamados criados;
  - custo por agente.

## 10. Ajustes No Frontend

- No chat:
  - toggle persistente de IA;
  - indicacao do agente ativo;
  - opcao de trocar agente manualmente;
  - badge `IA`/`Equipe` baseado no backend;
  - mostrar estado de handoff.
- Em Configuracoes > Agentes:
  - reorganizar por abas:
    - Comportamento;
    - Autonomia;
    - Ferramentas;
    - Transferencia;
    - Base usada.
- Evitar campos tecnicos demais para o usuario final.

## 11. Testes

- Testes unitarios:
  - selecao automatica de agente;
  - montagem de prompt por agente;
  - bloqueio por guardrails;
  - ferramentas permitidas por agente.
- Testes de integracao:
  - mensagem inbound com IA ativa gera resposta;
  - IA desligada nao responde;
  - handoff impede resposta automatica;
  - lead cria demanda;
  - atendimento cria chamado.
- Testes frontend:
  - toggle persiste;
  - troca de agente reflete no chat;
  - badges mudam corretamente.

## Ordem Recomendada

1. Persistir estado da IA por conversa.
2. Separar selecao real de agente no backend.
3. Montar prompt por agente.
4. Persistir toggle e agente no chat.
5. Aplicar ferramentas especificas por agente.
6. Adicionar auditoria por agente.
7. Refinar tela de Configuracoes > Agentes.
