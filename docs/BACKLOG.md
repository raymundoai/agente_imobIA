# Backlog do ImmobIA

Feedback dos beta testers, sugestões de melhoria e correções, num lugar só, com a decisão
tomada para cada um.

O feedback chega pelo botão **Enviar feedback** do painel e cai na aba **Feedback** do admin. Quando
um item for analisado, ele é registrado aqui, e a aba do admin é atualizada (em andamento ou
resolvido).

> **Este repositório é público.** Não registre nome, telefone, e-mail ou dados de clientes dos
> beta testers. Identifique a origem pelo nome da conta (ex.: "conta Imobiliária X") ou só por
> "beta tester".

## Como registrar

Cada item tem um código sequencial (`B-001`, `B-002`…), que nunca é reaproveitado.

| Campo | Valores |
|---|---|
| Tipo | Melhoria · Correção · Ideia · Dúvida recorrente |
| Origem | Equipe · Beta tester · Cliente |
| Prioridade | Alta · Média · Baixa · A definir |
| Status | Novo · Em análise · Aprovado · Em andamento · Implementado · Descartado |

**Fluxo:** Novo → Em análise → Aprovado → Em andamento → Implementado. Um item pode ser
descartado a partir de qualquer etapa. Ao implementar ou descartar, registre a data e o motivo ou
o commit em **Decisão**.

## Resumo

| Código | Título | Tipo | Origem | Prioridade | Status |
|---|---|---|---|---|---|
| B-001 | Volume de mensagens por horário no painel | Melhoria | Equipe | A definir | Novo |
| B-002 | Emissão de certidões pela API da InfoSimples | Melhoria | Equipe | A definir | Em análise |
| B-003 | Recuperação de senha por e-mail | Melhoria | Equipe | Média | Aprovado |
| B-004 | Backup fora do servidor | Melhoria | Equipe | Alta | Aprovado |
| B-005 | Kanban de leads | Ideia | Equipe | A definir | Novo |
| B-006 | Revisão de segurança da infraestrutura | Correção | Equipe | Alta | Em andamento |

## Itens

### B-001 · Volume de mensagens por horário no painel

- **Tipo:** Melhoria · **Origem:** Equipe · **Registrado em:** 06/10/2026
- **Prioridade:** A definir · **Status:** Novo
- **Descrição:** mostrar na Visão geral do painel da imobiliária o volume de mensagens por horário
  do dia, ao lado do gráfico semanal que já existe. Juntos, os dois mostram os dias e os horários
  de maior interação, por exemplo num mapa de calor (dia da semana × hora).
- **Por quê:** ajuda a imobiliária a decidir quando ter gente de plantão e mostra o valor do
  atendimento da IA fora do horário comercial.
- **Decisão:** —

### B-002 · Emissão de certidões pela API da InfoSimples

- **Tipo:** Melhoria · **Origem:** Equipe · **Registrado em:** 06/10/2026
- **Prioridade:** A definir · **Status:** Em análise
- **Descrição:** emitir as certidões pertinentes à negociação (pessoas e imóvel) pela API da
  InfoSimples, a partir do MCP de certidões já desenvolvido internamente na Eugen.IA. Os detalhes
  desse projeto serão passados pela equipe na hora de implementar.
- **Em aberto:** entender, pelo fluxo de trabalho mapeado com os beta testers, em que momento a
  emissão faz mais sentido e como deixá-la simples. Por exemplo: na captação do imóvel, na
  proposta ou na preparação da documentação para o fechamento.
- **Pontos a levantar antes de aprovar:**
  - quais certidões entram, e se variam por estado;
  - o custo por consulta na InfoSimples e como cobrar (franquia do plano ou pacote avulso);
  - onde os documentos ficam guardados e por quanto tempo, conforme a LGPD.
- **Decisão:** —

### B-003 · Recuperação de senha por e-mail

- **Tipo:** Melhoria · **Origem:** Equipe · **Registrado em:** 06/10/2026
- **Prioridade:** Média · **Status:** Aprovado (V2)
- **Descrição:** o link "Esqueci minha senha" do login passa a enviar um e-mail com um link
  temporário para criar uma senha nova.
- **Hoje:** o link mostra uma orientação: quem é da equipe pede ao administrador da conta
  (Configurações → Equipe), e o administrador fala com o suporte, que gera um link de nova senha
  pelo admin.
- **Depende de:** um serviço de envio de e-mail (domínio próprio com SPF/DKIM configurados).
- **Decisão:** aprovado para a V2.

### B-004 · Backup fora do servidor

- **Tipo:** Melhoria · **Origem:** Equipe · **Registrado em:** 06/10/2026
- **Prioridade:** Alta · **Status:** Aprovado
- **Descrição:** hoje o backup diário guarda, no mesmo disco do servidor, 14 cópias completas do
  banco e de todas as mídias. Isso ocupa muito espaço e se perde junto se o servidor falhar.
  Proposta:
  - enviar os backups para um armazenamento externo (Cloudflare R2 ou Backblaze B2);
  - copiar só as mídias novas a cada dia;
  - manter o dump diário do banco, que é pequeno.
- **Depois:** guardar as fotos dos imóveis no mesmo armazenamento. O sistema já suporta isso
  (`PROPERTY_STORAGE_BACKEND=s3`).
- **Quando:** antes dos primeiros 20 a 30 clientes.
- **Decisão:** —

### B-005 · Kanban de leads

- **Tipo:** Ideia · **Origem:** Equipe · **Registrado em:** 06/10/2026
- **Prioridade:** A definir · **Status:** Novo
- **Descrição:** um quadro com as etapas do lead (novo, em atendimento, visita, proposta,
  fechado), alimentado pelas demandas que o agente de IA coleta. Referência: o DeskcommCRM, a
  analisar à parte.
- **Decisão:** avaliar na V2, junto com o feedback dos beta testers sobre o acompanhamento de leads.

### B-006 · Revisão de segurança da infraestrutura

- **Tipo:** Correção · **Origem:** Equipe · **Registrado em:** 06/10/2026
- **Prioridade:** Alta · **Status:** Em andamento
- **Descrição:** juntar num documento interno, fora deste repositório público, as recomendações
  de segurança do servidor e dos serviços que rodam junto com o ImmobIA, e somar com a lista que
  a equipe já tem. A execução das correções é feita pela equipe.
- **Decisão:** —

