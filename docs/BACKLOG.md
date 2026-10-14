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
| B-004 | Backup fora do servidor | Melhoria | Equipe | Alta | Aprovado (antes da abertura pública) |
| B-005 | Kanban de leads | Ideia | Equipe | A definir | Novo |
| B-006 | Revisão de segurança da infraestrutura | Correção | Equipe | Alta | Em andamento |
| B-007 | Diferenciar os planos por recurso, não só pela franquia | Ideia | Equipe | A definir | Novo |
| B-008 | Planos para corretor autônomo | Ideia | Equipe | Alta | Implementado (beta) |
| B-009 | Imposto real na precificação | Correção | Equipe | Alta | Novo |
| B-010 | Testar o agente em conversas fora do escopo | Correção | Equipe | Alta | Aprovado |
| B-011 | Endereço com CEP no cadastro e estudo de exclusividade territorial | Melhoria | Equipe | A definir | Novo |
| B-012 | Ajuda sem cobrir ações da tela | Melhoria | Equipe | Média | Em validação |
| B-013 | Evitar repetir busca vazia na carteira | Correção | Equipe | Alta | Em validação |
| B-014 | Transferir à equipe quando o agente prometer fazê-lo | Correção | Equipe | Alta | Em validação |
| B-015 | Registrar quartos no campo da demanda | Correção | Equipe | Média | Em validação |
| B-016 | Busca externa sem progresso visível | Correção | Equipe | Alta | Em validação |

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
- **Prioridade:** Alta · **Status:** Aprovado (antes da abertura pública)
- **Descrição:** hoje o backup diário guarda, no mesmo disco do servidor, 14 cópias completas do
  banco e de todas as mídias. Isso ocupa muito espaço e se perde junto se o servidor falhar.
  Proposta:
  - enviar os backups para um armazenamento externo (Cloudflare R2 ou Backblaze B2);
  - copiar só as mídias novas a cada dia;
  - manter o dump diário do banco, que é pequeno.
- **Depois:** guardar as fotos dos imóveis no mesmo armazenamento. O sistema já suporta isso
  (`PROPERTY_STORAGE_BACKEND=s3`).
- **Quando:** antes da abertura pública do MVP; não bloqueia os beta testers convidados.
- **Decisão (11/10/2026):** o backup diário local já roda em contêiner separado no mesmo VPS.
  Um healthcheck passou a verificar se há dump recente legível e ficou saudável em produção.
  Uma rotina de sincronização para um destino externo foi preparada, mas nenhum destino está
  ativo. A conta de armazenamento inicialmente considerada foi retirada do escopo. Falta escolher
  um destino fora do VPS e fazer uma restauração de teste.
- **Andamento (11/10/2026):** a rotina aceita um endpoint S3 compatível, permitindo usar R2 ou B2
  em uma conta independente. O destino ainda depende da conta e das credenciais do provedor.
- **Decisão (11/10/2026):** usar o backup diário local durante o beta fechado e adiar a ativação
  da cópia externa para antes da abertura pública do MVP. Na retomada, configurar o destino e
  validar uma restauração completa.

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
- **Decisão (11/10/2026):** revisão iniciada após o deploy da oferta beta. Portas públicas de
  bancos de apoio foram fechadas, credenciais expostas foram trocadas, o webhook de cobrança foi
  atualizado e os painéis ganharam cabeçalhos de proteção, validados em produção. As recomendações
  operacionais restantes estão no documento interno de estado atual.

### B-007 · Diferenciar os planos por recurso, não só pela franquia

- **Tipo:** Ideia · **Origem:** Equipe · **Registrado em:** 07/10/2026
- **Prioridade:** A definir · **Status:** Novo
- **Descrição:** hoje os quatro planos têm os mesmos recursos e só mudam o tamanho das
  franquias. A ideia é diferenciar também pelo que cada plano inclui. Por exemplo:
  - **Essencial:** focado no atendimento com IA, com uma franquia de atendimentos maior que a de
    hoje (100) e sem buscas nos portais nem otimização de fotos;
  - **Profissional em diante:** buscas de imóveis e otimização de fotos incluídas, com franquias
    que crescem a cada plano.
- **Por quê:** o recurso que mais pesa na decisão de compra é o atendimento com IA. Deixar buscas e
  fotos a partir do Profissional dá um motivo claro para o upgrade, além do volume.
- **Pontos a levantar antes de aprovar:**
  - o novo tamanho da franquia de atendimentos do Essencial, e se o preço muda;
  - o custo e a margem no simulador de precificação. A margem do atendimento já é alta (90% ou
    mais em conversas típicas), então dá espaço para uma franquia maior;
  - se o Essencial pode comprar pacotes avulsos de buscas e fotos ou se precisa fazer upgrade;
  - o que acontece com os beta testers que já assinaram o Essencial;
  - os ajustes no sistema: o plano sem um recurso esconde a função ou mostra um convite para o
    upgrade.
- **Decisão:** —

### B-008 · Planos para corretor autônomo

- **Tipo:** Ideia · **Origem:** Equipe (reunião de 07/10/2026) · **Registrado em:** 07/10/2026
- **Prioridade:** Alta · **Status:** Implementado (beta); preço definitivo em análise
- **Descrição:** o Essencial (R$ 369) é acessível para uma imobiliária, mas caro para um corretor
  autônomo. Criar uma oferta própria para corretores; os preços anteriores abaixo são hipóteses
  históricas e a condição beta vigente está na decisão de 11/10/2026.
- **No sistema:** o cadastro inicial pergunta o tipo de conta e o guarda como categoria
  comercial. A oferta beta exige corretor e liberação pelo admin; a elegibilidade é validada
  também no servidor. Os planos existentes de imobiliárias continuam registrados para as
  contas anteriores, mas ficam ocultos nas novas contratações.
- **Pontos a levantar antes de aprovar:**
  - os volumes de cada franquia: quantos atendimentos e buscas um corretor faz por mês. Validar
    com os beta testers e com a pesquisa quantitativa (com apoio de Creci e Secovi), que deve
    incluir essas faixas de preço;
  - as margens no simulador, já com o imposto real (B-009);
  - a relação com o B-007, que diferencia os planos por recurso.
- **Discussão de 08/10/2026 (hipóteses, sem decisão):** estudar preços mensais redondos a partir
  de R$ 60, com opções até R$ 190. Para o corretor autônomo, considerar 30 buscas padrão no
  plano de entrada e comparar duas formas de oferecer IA: cobrança de R$ 2,50 por atendimento
  desde o primeiro uso ou uma pequena franquia incluída, seguida de uso adicional nesse preço.
  Avaliar otimização de imagens a R$ 3,50 por foto, pacotes adicionais de buscas e limite de dois
  usuários; o segundo acesso poderia ser um adicional mensal de baixo valor. Examinar o preço
  por unidade de operação para imobiliárias com várias lojas ou franquias, mantendo por ora os
  quatro planos de imobiliárias como estão. Medir o custo operacional da busca padrão e separar
  sua futura versão com IA na precificação. Validar também a percepção dos preços redondos com
  corretores.
- **Discussão de 08/10/2026 (continuação, proposta em análise):** priorizar mensalidade baixa e
  cobrança proporcional ao uso para reduzir o custo fixo nos meses fracos do corretor. Cenário
  de entrada: R$ 60/mês, 50 buscas padrão incluídas, nenhum atendimento de IA incluído e
  R$ 2,50 por atendimento realizado. Segundo degrau: R$ 89,90/mês, 100 buscas padrão
  incluídas, nenhum atendimento de IA incluído e comparar R$ 2,10 com R$ 2,00 por
  atendimento. Estudar uma única cobrança mensal com assinatura e consumo consolidado, sem
  transação por atendimento; definir limite de gasto, detalhamento da fatura e tratamento de
  inadimplência. Os valores e a forma de cobrança seguem sem aprovação final.
- **Discussão de 08/10/2026 (simulação seguinte, sem decisão):** testar R$ 2,80 por atendimento
  no plano de R$ 60, preservando as 50 buscas incluídas. Comparar esse desenho com uma linha
  única de baixo custo fixo e desconto automático por volume de atendimentos, sem obrigar o
  corretor a trocar de assinatura nos meses de maior movimento. Conferir o preço de mercado
  por conversa com cuidado, pois a definição de atendimento e os recursos variam entre
  fornecedores.
- **Discussão de 08/10/2026 (nova hipótese, sem decisão):** linha única para corretor com
  R$ 60 fixos, 50 buscas padrão incluídas e IA cobrada por atendimento em faixas de volume:
  R$ 3,20 até o 30º, R$ 2,80 do 31º ao 90º e R$ 2,15 acima do 150º. Em 08/10, a proposta
  de R$ 2,50 do 91º ao 150º foi aceita para continuar a análise. A aplicação progressiva ou
  retroativa do desconto ainda precisa ser definida. Comparar o total em alto volume com o
  plano Essencial para imobiliárias.
- **Discussão de 08/10/2026 (preço beta em análise):** avaliar a mensalidade de R$ 60 e as
  faixas variáveis de IA como condição dos beta testers, com preço público fixo maior para a
  linha de corretores. Testar R$ 90 como referência pública, mantendo a mesma tarifa por
  atendimento para ambos os grupos. Definir duração, elegibilidade e comunicação da condição
  beta a partir da conversão e do uso observados, antes de publicar esses valores. Ao desenhar
  a oferta, evitar que o mesmo corretor tenha acesso simultâneo ao Essencial beta atual de
  imobiliárias (R$ 49 com 100 atendimentos incluídos), que seria mais vantajoso que a nova
  linha beta para corretores.
- **Discussão de 08/10/2026 (alternativa beta em análise):** simular R$ 60 de mensalidade para
  corretores beta e R$ 3,00 por atendimento de IA desde o primeiro uso, sem desconto por
  volume. Avaliar receita e contribuição para um grupo de 20 contas pagantes em meses de
  diferentes volumes, incluindo as buscas, a cobrança e o servidor. Não confundir margem
  direta positiva com resultado final, que depende também do suporte e da aquisição.
- **Decisão parcial em 08/10/2026:** preparar para corretores beta o plano de R$ 59,90/mês,
  com 50 buscas padrão por ciclo, acesso ao compartilhamento de imóveis e atendimento de IA a
  R$ 2,90 por conversa cobrável desde a primeira. Otimização de imagem: R$ 2,50 por foto avulsa
  ou pacote de 15 por R$ 30,00. O preço público definitivo para corretores permanece em análise;
  os planos das imobiliárias continuam como estão. Definir antes da implementação a regra de
  início/fim da conversa cobrável, a cobrança consolidada do consumo, o uso após as 50 buscas,
  a validade do pacote, os limites de usuários e a elegibilidade dos beta testers. Evitar que a
  conta de corretor receba também a oferta beta Essencial de imobiliárias.
- **Decisão em 11/10/2026:** aprovada para implementação a oferta beta de corretor por
  **R$ 59,90/mês**, com **20 buscas padrão por ciclo**, compartilhamento de imóveis,
  **R$ 2,90 por conversa cobrável de IA** desde a primeira e otimização de imagem a
  **R$ 2,50 avulsa** ou **15 por R$ 30,00**. Esta decisão substitui as 50 buscas da proposta de
  08/10. O preço definitivo depois do beta continua em análise. Na fase inicial, apresentar
  somente a oferta beta aos corretores convidados; estudar ocultar os planos de imobiliária na
  contratação de novas contas, sem apagar os planos existentes nem mudar assinaturas ativas.
  Restringir também a contratação no servidor, pois ocultar cartões na interface não impede
  pedidos diretos. Antes do lançamento, definir o tratamento da 21ª busca, a validade do pacote,
  o limite de usuários e a cobrança mensal do consumo variável.
- **Implementação publicada em 11/10/2026 (`f2db16a`):** a 21ª busca bloqueia até o
  próximo ciclo; o pacote de 15 fotos vale 90 dias e é consumido antes das fotos avulsas; o
  plano permite dois usuários durante o beta. Uma fatura mensal reúne a nova mensalidade e as
  conversas/fotos avulsas ainda não faturadas. O pagamento da fatura libera o ciclo seguinte.
  O usuário paga a fatura por PIX ou cartão na página do Asaas. O preço após o beta permanece
  em análise.

### B-009 · Imposto real na precificação

- **Tipo:** Correção · **Origem:** Equipe (reunião de 07/10/2026) · **Registrado em:** 07/10/2026
- **Prioridade:** Alta · **Status:** Novo
- **Descrição:** a planilha financeira e o painel de precificação usam 6% de imposto (Simples
  Nacional, primeira faixa). Na reunião, a estimativa como PJ foi de 18,5%. A diferença muda
  todas as margens.
- **Próximo passo:** confirmar o regime e a alíquota com a contabilidade e atualizar a planilha, o
  simulador e, se preciso, os preços de referência por unidade.
- **Decisão:** —

### B-010 · Testar o agente em conversas fora do escopo

- **Tipo:** Correção · **Origem:** Equipe (reunião de 07/10/2026) · **Registrado em:** 07/10/2026
- **Prioridade:** Alta · **Status:** Aprovado
- **Descrição:** o agente já tem instrução para recusar assuntos fora do atendimento imobiliário.
  É preciso testar no beta se ela se sustenta quando o lead insiste em puxar outros assuntos,
  como usar a IA de companhia ou desabafar. Isso protege o cliente (custo e imagem) e evita
  atendimentos que chegam ao teto de 50 respostas.
- **Como:** um roteiro de conversas que tentam desviar o assunto, rodado na conta interna de
  testes. Se a instrução falhar, reforçar o prompt ou encerrar a conversa e passar para a equipe
  depois de algumas tentativas.
- **Decisão:** —

### B-011 · Endereço com CEP no cadastro e estudo de exclusividade territorial

- **Tipo:** Melhoria · **Origem:** Equipe · **Registrado em:** 08/10/2026
- **Prioridade:** A definir · **Status:** Novo
- **Descrição:** incluir endereço com CEP no cadastro da conta, com número, complemento quando
  houver, bairro, cidade e UF. Distinguir endereço cadastral do local ou área onde o corretor
  atende. Guardar a informação de forma estruturada para permitir no futuro estudar uma oferta
  de exclusividade por raio de atuação.
- **Antes de oferecer exclusividade:** definir ponto de referência e raio, como tratar áreas
  sobrepostas, mudança de endereço e contas já existentes, além das condições comerciais.
  Cadastrar o endereço não concede exclusividade automaticamente.
- **Decisão:** —

### B-012 · Ajuda sem cobrir ações da tela

- **Tipo:** Melhoria · **Origem:** Equipe · **Registrado em:** 13/10/2026
- **Prioridade:** Média · **Status:** Em validação
- **Descrição:** a casinha de ajuda pode cobrir o botão de enviar. Permitir fechá-la e acessá-la
  pelo botão Dúvidas na barra lateral.
- **Andamento:** botão Dúvidas e recolhimento da ajuda implementados; falta teste visual em produção.
- **Decisão (14/10/2026):** manter a ajuda acessível na barra lateral quando for recolhida.

### B-013 · Evitar repetir busca vazia na carteira

- **Tipo:** Correção · **Origem:** Equipe · **Registrado em:** 13/10/2026
- **Prioridade:** Alta · **Status:** Em validação
- **Descrição:** quando a carteira não contém imóvel para os critérios do lead, o agente repete
  a busca e o aviso em respostas seguintes. Guardar esse resultado no contexto da conversa e
  consultar novamente apenas se os critérios mudarem ou após um prazo.
- **Andamento:** memória de 24 horas implementada; falta validar em conversa real.
- **Decisão (14/10/2026):** guardar o resultado da busca vazia por 24 horas, ligado aos critérios.

### B-014 · Transferir à equipe quando o agente prometer fazê-lo

- **Tipo:** Correção · **Origem:** Equipe · **Registrado em:** 13/10/2026
- **Prioridade:** Alta · **Status:** Em validação
- **Descrição:** o agente disse que acionaria o corretor, mas a conversa permaneceu com a IA.
  A promessa de transferência deve colocar o atendimento no modo humano.
- **Andamento:** troca para atendimento humano implementada; falta validar em conversa real.
- **Decisão (14/10/2026):** a promessa de acionar a equipe deve transferir a conversa.

### B-015 · Registrar quartos no campo da demanda

- **Tipo:** Correção · **Origem:** Equipe · **Registrado em:** 13/10/2026
- **Prioridade:** Média · **Status:** Em validação
- **Descrição:** a quantidade de quartos informada pelo lead foi parar nas observações da
  demanda, em vez do campo usado pela busca.
- **Andamento:** extração dos quartos implementada; falta validar em conversa real. A demanda
  já criada precisa de correção manual no painel.
- **Decisão (14/10/2026):** guardar quartos no campo estruturado usado pela busca.

### B-016 · Busca externa sem progresso visível

- **Tipo:** Correção · **Origem:** Equipe · **Registrado em:** 13/10/2026
- **Prioridade:** Alta · **Status:** Em validação
- **Descrição:** uma busca iniciada a partir da demanda permaneceu em execução sem avançar.
  Identificar a causa na execução real e garantir estado final ou aviso claro ao usuário.
- **Andamento (14/10/2026):** o print de 13/10 mostra 0/10 portais consultados e todos na fila
  cerca de 45 minutos após iniciar. Prints dos logs mostram que o worker falha ao reivindicar
  a busca porque o modelo de usuário não foi carregado no processo. Correção e teste em
  processo isolado implementados; o reteste real ainda falta. O aviso de demora e o
  encerramento de tarefas abandonadas também foram implementados.
- **Decisão (14/10/2026):** carregar os modelos exigidos pelo worker antes de pegar a busca;
  mostrar demora ao usuário e encerrar tarefas cujo processamento foi abandonado.

