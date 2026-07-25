# Integracoes MVP

Este documento define o preparo inicial do ImobIA para integrar com Kenlo,
Tecimob, Jetimob e Orulo.

## Estrategia

As credenciais nao devem ser salvas pelo frontend. No MVP, a tela de
Configuracoes > Integracoes registra apenas o status do setup da empresa:

- `not_configured`
- `awaiting_credentials`
- `testing`
- `connected`
- `error`

Credenciais reais devem entrar por endpoint seguro no backend, com criptografia
em repouso, ou por variaveis/secret manager no setup inicial do cliente.

## Rotas Preparadas

```http
GET  /integrations/setup
POST /integrations/setup
```

O `POST /integrations/setup` aceita:

```json
{
  "provider": "kenlo",
  "notes": "Setup solicitado para cliente X"
}
```

Providers aceitos no MVP:

- `kenlo`
- `tecimob`
- `jetimob`
- `orulo`

## Dados Minimos Por Fornecedor

### Kenlo

Solicitar ao Kenlo:

- acesso ao programa de parceiros/integradores;
- documentacao da API REST;
- ambiente sandbox, se disponivel;
- base URL de sandbox/producao;
- credenciais por cliente ou credenciais de parceiro;
- escopos para imoveis, contatos, leads e atividades;
- limites de requisicao;
- webhooks disponiveis;
- regras para sincronizacao incremental.

Pergunta objetiva para suporte/parcerias:

> Precisamos integrar o ImobIA ao Kenlo para sincronizar imoveis, contatos,
> leads e atividades. Podem liberar documentacao da API REST, sandbox,
> credenciais de teste e orientacoes de webhook?

### Tecimob

Solicitar ao Tecimob:

- ativacao do recurso de API no painel da imobiliaria;
- token/chave API gerado em `Configuracoes > Integrações API`;
- permissoes liberadas para a chave;
- confirmacao de que o plano da imobiliaria libera API;
- base URL de producao: `https://api.tecimob.com.br/v1`;
- documentacao Swagger: `https://swagger.tecimob.com.br/`;
- limites de uso;
- webhooks, se existirem, ou recomendacao de frequencia para sincronizacao.

Autenticacao identificada no Swagger:

```http
Authorization: Bearer TECIMOB_API_KEY
```

Endpoints mapeados inicialmente:

```http
GET  /api/properties
GET  /api/properties/{id}
GET  /api/people
POST /api/people
GET  /api/people/{id}
PUT  /api/people/{id}
GET  /api/users
POST /api/leads/store-person
POST /api/leads/relate-person
GET  /api/notes
POST /api/notes
GET  /api/people/groups
```

Configuracao por ambiente no ImobIA:

```dotenv
TECIMOB_TENANT_CONFIGS={"demo":{"base_url":"https://api.tecimob.com.br/v1","access_token":"CHAVE_GERADA_NO_TECIMOB"}}
```

Pergunta objetiva:

> O cliente deseja conectar o Tecimob ao ImobIA. O plano atual libera API?
> Precisamos ativar a integracao via API, gerar uma chave com permissoes para
> imoveis, clientes/pessoas, leads, usuarios e anotacoes, e confirmar limites de
> uso e webhooks.

### Jetimob

Solicitar ao Jetimob:

- confirmacao de que o plano libera chaves de API;
- chaves/token de API;
- base URL;
- documentacao de imoveis ativos;
- endpoints para leads e contatos;
- regra de sincronizacao recomendada;
- limites de consulta;
- webhooks, se existirem.

Pergunta objetiva:

> Precisamos integrar o ImobIA ao Jetimob para consultar imoveis ativos e
> sincronizar leads/contatos. O plano do cliente libera chaves de API? Podem
> enviar documentacao, base URL e credenciais de teste/producao?

### Orulo

Solicitar a Orulo:

- `client_id`;
- `client_secret`;
- tipo de autenticacao liberado;
- escopos da API v2;
- autorizacao para uso como CRM/parceiro;
- base URL;
- endpoints de catalogo, empreendimento, unidade, imagens e detalhes;
- limites de requisicao;
- processo de homologacao.

Pergunta objetiva:

> Precisamos conectar o ImobIA a API da Orulo para consultar catalogo,
> empreendimentos, unidades, imagens e detalhes dos imoveis. Podem liberar
> client_id, client_secret, escopos autorizados e documentacao de homologacao?

## Mapeamento Inicial De Dados

### Imoveis

- ID externo
- titulo
- tipo
- finalidade
- valor
- condominio/IPTU, se disponivel
- cidade
- bairro
- endereco, conforme permissao
- quartos
- vagas
- area
- descricao
- fotos
- status
- URL publica

### Contatos

- ID externo
- nome
- telefone
- email
- tipo: lead, proprietario, inquilino, cliente ativo
- tags
- origem
- responsavel

### Leads/Demandas

- ID externo
- contato
- interesse
- finalidade
- cidade/bairro
- faixa de valor
- quartos/vagas/area
- observacoes
- etapa/funil

### Atividades

- tipo
- data
- contato relacionado
- imovel relacionado
- descricao
- responsavel
- status

## Proximo Passo Tecnico

Quando as credenciais/documentacoes forem obtidas, criar adapters especificos:

- `KenloAdapter`
- `TecimobAdapter`
- `JetimobAdapter`
- `OruloAdapter`

Todos devem implementar portas internas comuns para reduzir dependencia do
frontend e evitar logica especifica de fornecedor fora do modulo de integracoes.
