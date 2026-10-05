/**
 * What the assistant says on each screen, the guided tours and the help centre articles.
 * Tours point at CSS selectors; a step whose element is not on screen is skipped.
 */

export type HelpContext =
  | "dashboard"
  | "conversations"
  | "contacts"
  | "properties"
  | "propertySearch"
  | "settings:company"
  | "settings:channels"
  | "settings:integrations"
  | "settings:agents"
  | "settings:users"
  | "settings:network"
  | "settings:billing"
  | "settings:history";

export type TourStep = { target: string; title: string; text: string };

export type ScreenHelp = {
  /** Said once, the first time the person opens this screen. */
  tip: string;
  tour: TourStep[];
  articles: string[];
};

export type Article = {
  id: string;
  title: string;
  summary: string;
  body: Array<{ heading?: string; text?: string; steps?: string[] }>;
  link?: { label: string; href: string };
};

export const SCREENS: Record<HelpContext, ScreenHelp> = {
  dashboard: {
    tip: "Oi! Eu sou a casinha da ImmobIA. Aqui na Visão geral você acompanha os leads e as conversas. Se aparecer um aviso, ele já tem um botão que leva até a solução.",
    tour: [
      { target: ".first-steps", title: "Primeiros passos", text: "Siga esta lista para deixar o agente pronto para atender. Cada item leva direto à tela certa." },
      { target: ".metric-grid", title: "Números da operação", text: "Contatos, pedidos de imóvel, carteira e conversas iniciadas. No card de contatos dá para filtrar por tipo." },
      { target: ".timeline-header", title: "Conversas por dia", text: "Veja o movimento dos últimos 7, 30 ou 90 dias. Passe o mouse sobre as barras para ver cada dia." },
      { target: ".sidebar-user", title: "Seu menu", text: "Configurações, tema claro ou escuro, notificações e sair ficam aqui." },
    ],
    articles: ["primeiros-passos", "conectar-whatsapp", "como-o-agente-atende"],
  },
  conversations: {
    tip: "Aqui chegam as mensagens do WhatsApp. O agente responde sozinho, e você pode assumir qualquer conversa quando quiser.",
    tour: [
      { target: ".inbox-list", title: "Caixa de entrada", text: "Todas as conversas, das mais recentes para as mais antigas. Use a busca para achar um contato." },
      { target: ".chat-panel-header", title: "Quem está atendendo", text: "A chave de IA mostra se o agente está respondendo. Clique em Assumir para a conversa ficar com você." },
      { target: ".chat-composer", title: "Responder", text: "Escreva aqui quando a conversa estiver com você. Dá para mandar áudio e anexos." },
    ],
    articles: ["como-o-agente-atende", "assumir-conversa"],
  },
  contacts: {
    tip: "Todo lead que conversa com o agente vira um contato aqui, com o interesse já preenchido.",
    tour: [
      { target: ".contacts-toolbar", title: "Filtrar por tipo", text: "Leads, proprietários, inquilinos e clientes. Crie um contato manualmente pelo botão ao lado." },
      { target: ".contacts-list-panel", title: "Lista de contatos", text: "Busque por nome, telefone, e-mail ou etiqueta." },
      { target: ".contact-detail-panel", title: "Ficha do contato", text: "Edite os dados, etiquetas e observações. O interesse é preenchido pelo agente." },
    ],
    articles: ["contatos-e-demandas", "historico"],
  },
  properties: {
    tip: "Cadastre sua carteira aqui. O agente só oferece aos leads os imóveis que estão nesta lista.",
    tour: [
      { target: ".page-toolbar", title: "Cadastrar imóvel", text: "Adicione um imóvel com fotos, valores e características. A IA pode melhorar as fotos e escrever a descrição." },
      { target: ".property-grid", title: "Sua carteira", text: "Clique num imóvel para ver os detalhes, editar, inativar ou compartilhar na Rede ImmobIA." },
    ],
    articles: ["cadastrar-imovel", "rede-immobia"],
  },
  propertySearch: {
    tip: "Quando um lead procura algo que você não tem, registre a demanda aqui e busque nos principais portais.",
    tour: [
      { target: ".page-toolbar", title: "Nova demanda", text: "Registre o que o cliente procura: finalidade, cidade, bairros, valor e quartos." },
      { target: ".demand-list", title: "Demandas", text: "As demandas criadas pelo agente e pela equipe aparecem aqui. Escolha uma para buscar." },
      { target: ".mission-search-actions", title: "Buscar imóveis", text: "Procura nos portais e na Rede ImmobIA e ordena pelos mais compatíveis." },
    ],
    articles: ["buscador", "rede-immobia", "planos-e-pacotes"],
  },
  "settings:company": {
    tip: "Os dados da empresa e o horário de atendimento são usados pelo agente nas conversas. Vale manter atualizado.",
    tour: [
      { target: ".settings-tabs", title: "Todas as configurações", text: "Empresa, canais, agente, equipe, rede, plano e histórico ficam nestas abas." },
      { target: ".settings-panel", title: "Dados da empresa", text: "Corretor autônomo ou imobiliária, documento, regiões de atuação e horários." },
    ],
    articles: ["primeiros-passos", "ajustar-agente"],
  },
  "settings:channels": {
    tip: "Conecte o WhatsApp da imobiliária lendo um QR Code com o celular. Leva cerca de um minuto.",
    tour: [{ target: ".connection-grid", title: "Canais", text: "O WhatsApp já está disponível. Os outros canais chegam em breve." }],
    articles: ["conectar-whatsapp"],
  },
  "settings:integrations": {
    tip: "As integrações com CRMs e portais estão chegando. Clique numa delas para ser avisado quando ficar pronta.",
    tour: [{ target: ".connection-grid", title: "Integrações", text: "Registre interesse e conte como usa o sistema; isso ajuda a priorizar." }],
    articles: [],
  },
  "settings:agents": {
    tip: "Dê um nome ao agente, escolha o tom de voz e diga quando ele deve passar a conversa para a equipe.",
    tour: [{ target: ".settings-panel", title: "Agente de IA", text: "Nome, tom, emojis, regras de transferência e a base de conhecimento com seus documentos." }],
    articles: ["ajustar-agente", "como-o-agente-atende"],
  },
  "settings:users": {
    tip: "Convide sua equipe. Cada pessoa recebe um link para criar a própria senha.",
    tour: [{ target: ".settings-panel", title: "Equipe", text: "Convide pessoas, escolha o perfil de acesso e acompanhe quem está ativo." }],
    articles: ["equipe"],
  },
  "settings:network": {
    tip: "Na Rede ImmobIA você compartilha imóveis com outras imobiliárias e fecha parcerias com comissão combinada.",
    tour: [{ target: ".settings-panel", title: "Rede ImmobIA", text: "Aceite os termos, defina a comissão de parceria e responda os pedidos recebidos." }],
    articles: ["rede-immobia"],
  },
  "settings:billing": {
    tip: "Aqui você escolhe o plano e acompanha o uso do mês. Se a franquia acabar, dá para comprar um pacote avulso.",
    tour: [
      { target: ".billing-status", title: "Situação do plano", text: "Mostra o plano atual e até quando vai o ciclo." },
      { target: ".plan-options", title: "Planos", text: "Todos têm atendimento com IA. Quanto maior o plano, menor o preço por atendimento." },
      { target: "#pacotes", title: "Pacotes adicionais", text: "Créditos extras para quando a franquia do mês acabar. Valem por 90 dias." },
    ],
    articles: ["planos-e-pacotes"],
  },
  "settings:history": {
    tip: "Tudo o que é excluído fica registrado aqui, com quem fez e uma cópia do que foi removido.",
    tour: [{ target: ".activity-list", title: "Histórico", text: "Abra um registro para ver os dados que foram excluídos ou juntados." }],
    articles: ["historico"],
  },
};

export const ARTICLES: Article[] = [
  {
    id: "primeiros-passos",
    title: "Primeiros passos",
    summary: "O que fazer para o agente começar a atender seus leads.",
    body: [
      { steps: [
        "Escolha um plano em Configurações → Plano e cobrança. O atendimento com IA começa quando a primeira mensalidade é paga.",
        "Conecte o WhatsApp da imobiliária em Configurações → Canais.",
        "Cadastre seus imóveis em Imóveis. O agente só oferece o que está na carteira.",
        "Ajuste o nome e o tom do agente em Configurações → Agente de IA.",
        "Mande uma mensagem de teste para o número conectado e veja a conversa chegar em Conversas.",
      ] },
    ],
    link: { label: "Ir para a Visão geral", href: "/" },
  },
  {
    id: "conectar-whatsapp",
    title: "Conectar o WhatsApp",
    summary: "Leia um QR Code com o celular da imobiliária e pronto.",
    body: [
      { steps: [
        "Abra Configurações → Canais e clique em Conectar no card do WhatsApp.",
        "No celular, abra o WhatsApp, toque em Aparelhos conectados e depois em Conectar aparelho.",
        "Aponte a câmera para o QR Code. A janela confirma sozinha quando a conexão termina.",
      ] },
      { heading: "Dica", text: "Use o número que os clientes já conhecem. As conversas antigas continuam no celular; as novas passam a chegar também no ImmobIA." },
    ],
    link: { label: "Abrir Canais", href: "/configuracoes?aba=channels" },
  },
  {
    id: "como-o-agente-atende",
    title: "Como o agente atende",
    summary: "O que a IA faz sozinha e quando ela passa a conversa para a equipe.",
    body: [
      { text: "O agente responde os leads pelo WhatsApp, entende o que cada um procura (compra ou aluguel, cidade, bairros, valor, quartos) e registra isso como uma demanda, ligada ao contato." },
      { text: "Com os critérios em mãos, ele procura na sua carteira e oferece os imóveis compatíveis. Ele nunca inventa imóveis nem negocia valores." },
      { heading: "Quando a equipe assume", text: "Quando o lead pede para falar com uma pessoa, quando não há imóvel compatível e o lead quer uma busca externa, ou quando uma regra que você definiu manda transferir. A conversa passa para atendimento humano e aparece em Conversas." },
      { heading: "Franquia", text: "Cada atendimento conta uma vez a cada 24 horas por contato, com até 50 respostas. Se a franquia acabar, novas conversas vão para a equipe." },
    ],
  },
  {
    id: "assumir-conversa",
    title: "Assumir uma conversa",
    summary: "Como responder você mesmo e devolver a conversa para o agente.",
    body: [
      { steps: [
        "Abra a conversa em Conversas.",
        "Clique em Assumir no topo da conversa. O agente para de responder e a conversa fica com você.",
        "Escreva no campo de mensagem. Quando terminar, ligue de novo a chave de IA da conversa para o agente voltar a atender.",
      ] },
    ],
    link: { label: "Abrir Conversas", href: "/conversas" },
  },
  {
    id: "ajustar-agente",
    title: "Ajustar o agente de IA",
    summary: "Nome, tom de voz, regras de transferência e base de conhecimento.",
    body: [
      { text: "Em Configurações → Agente de IA você define como o agente se apresenta e se comporta." },
      { steps: [
        "Nome: com nome, ele se apresenta por ele. Sem nome, diz que é o assistente virtual da imobiliária.",
        "Tom de voz e emojis: deixe com a cara do seu atendimento.",
        "Quando acionar a equipe e o que ele não pode fazer: escreva com suas palavras.",
        "Base de conhecimento: envie documentos (regras de locação, bairros, perguntas frequentes) para ele consultar.",
      ] },
    ],
    link: { label: "Abrir Agente de IA", href: "/configuracoes?aba=agents" },
  },
  {
    id: "cadastrar-imovel",
    title: "Cadastrar um imóvel",
    summary: "Fotos, valores e características para o agente oferecer certo.",
    body: [
      { steps: [
        "Em Imóveis, clique em cadastrar e preencha finalidade, tipo, cidade, bairro e valores.",
        "Envie as fotos. A otimização com IA melhora luz e enquadramento (consome a franquia de fotos).",
        "Quanto mais completo o cadastro (quartos, vagas, área), melhor o agente combina o imóvel com cada lead.",
      ] },
    ],
    link: { label: "Abrir Imóveis", href: "/imoveis" },
  },
  {
    id: "buscador",
    title: "Buscador de imóveis",
    summary: "Encontre imóveis fora da sua carteira para um cliente.",
    body: [
      { text: "Escolha uma demanda e clique em Buscar imóveis. O ImmobIA procura nos principais portais e na Rede ImmobIA e mostra os resultados do mais compatível para o menos compatível." },
      { text: "Cada busca consome uma unidade da franquia de buscas do plano." },
    ],
    link: { label: "Abrir Buscador", href: "/buscador-de-imoveis" },
  },
  {
    id: "rede-immobia",
    title: "Rede ImmobIA",
    summary: "Compartilhe imóveis e faça parcerias com outras imobiliárias.",
    body: [
      { steps: [
        "Em Configurações → Rede ImmobIA, aceite os termos e defina a comissão de parceria.",
        "Na ficha de um imóvel com foto, ative o compartilhamento. Endereço e dados do proprietário nunca aparecem para os parceiros.",
        "Pedidos de parceria chegam para você aceitar ou recusar. Os contatos só são liberados depois do aceite.",
      ] },
    ],
    link: { label: "Abrir Rede ImmobIA", href: "/configuracoes?aba=network" },
  },
  {
    id: "planos-e-pacotes",
    title: "Planos, franquias e pacotes",
    summary: "Como o uso é contado e o que fazer se a franquia acabar.",
    body: [
      { text: "Cada plano tem uma franquia mensal de atendimentos de IA, buscas de imóveis e otimizações de fotos. A franquia renova todo mês." },
      { heading: "Se acabar", text: "Compre um pacote avulso em Plano e cobrança. Os créditos entram assim que o pagamento é confirmado e valem por 90 dias. Se isso acontecer todo mês, um plano maior sai mais barato por atendimento." },
    ],
    link: { label: "Abrir Plano e cobrança", href: "/configuracoes?aba=billing" },
  },
  {
    id: "contatos-e-demandas",
    title: "Contatos e demandas",
    summary: "Como os leads viram contatos e o que é uma demanda.",
    body: [
      { text: "Quem conversa com o agente vira um contato, identificado pelo número do WhatsApp. O que o lead procura vira uma demanda, ligada a esse contato." },
      { text: "Você pode editar contatos, adicionar etiquetas e observações. Excluir um contato não apaga as conversas nem as demandas dele." },
    ],
    link: { label: "Abrir Contatos", href: "/contatos" },
  },
  {
    id: "equipe",
    title: "Equipe e permissões",
    summary: "Convide pessoas e escolha o que cada uma pode fazer.",
    body: [
      { steps: [
        "Em Configurações → Equipe, convide pelo e-mail e escolha o perfil.",
        "Administrador gerencia tudo; gestor acompanha a operação e a equipe; corretor e atendente cuidam dos atendimentos e cadastros.",
        "A pessoa recebe um link para criar a própria senha.",
      ] },
    ],
    link: { label: "Abrir Equipe", href: "/configuracoes?aba=users" },
  },
  {
    id: "historico",
    title: "Histórico de atividades",
    summary: "Quem excluiu o quê, com uma cópia do que foi removido.",
    body: [
      { text: "Exclusões de demandas, imóveis, contatos e documentos ficam registradas em Configurações → Histórico, com data, autor e os dados que foram removidos. Ajustes automáticos, como a junção de contatos duplicados, também aparecem lá." },
    ],
    link: { label: "Abrir Histórico", href: "/configuracoes?aba=history" },
  },
];
