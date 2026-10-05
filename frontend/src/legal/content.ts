/**
 * Terms of use and privacy policy shown at /termos and /privacidade and accepted at signup.
 *
 * MINUTA PARA REVISÃO JURÍDICA. Preencha COMPANY antes de abrir o cadastro ao público e,
 * a cada mudança relevante no texto, atualize TERMS_VERSION aqui e no backend
 * (app/modules/tenants/api/routes.py), para que novos aceites registrem a versão nova.
 */

export const TERMS_VERSION = "2026-10-05";

export const COMPANY = {
  brand: "ImmobIA",
  legalName: "[RAZÃO SOCIAL DA EUGEN.IA]",
  document: "[CNPJ]",
  address: "[ENDEREÇO COMPLETO]",
  supportEmail: "[E-MAIL DE SUPORTE]",
  privacyEmail: "[E-MAIL DO ENCARREGADO DE DADOS]",
  city: "[CIDADE/UF DO FORO]",
};

export type LegalSection = { heading: string; paragraphs?: string[]; items?: string[] };
export type LegalDocument = { title: string; intro: string; sections: LegalSection[] };

const c = COMPANY;

export const TERMS: LegalDocument = {
  title: "Termos de uso",
  intro: `Estes termos regem o uso da plataforma ${c.brand}, oferecida por ${c.legalName}, inscrita no CNPJ ${c.document}, com sede em ${c.address}. Ao criar uma conta, você declara que leu e aceita estes termos e a Política de privacidade.`,
  sections: [
    {
      heading: "1. O serviço",
      paragraphs: [
        `${c.brand} é uma plataforma para corretores e imobiliárias que reúne atendimento de leads por agente de inteligência artificial no WhatsApp, cadastro de imóveis e contatos, busca de imóveis em portais e a Rede ${c.brand} de parcerias entre imobiliárias.`,
      ],
    },
    {
      heading: "2. Conta e acesso",
      items: [
        "Você é responsável pelos dados informados no cadastro e por manter suas senhas em sigilo.",
        "O administrador da conta decide quem da equipe tem acesso e com qual perfil, e responde pelo uso feito pela equipe.",
        "Podemos suspender contas usadas para fraude, spam, conteúdo ilegal ou em desacordo com estes termos.",
      ],
    },
    {
      heading: "3. Planos, pagamento e cancelamento",
      items: [
        "Os planos são mensais, cobrados de forma recorrente por meio do Asaas, nosso parceiro de pagamentos. Os serviços do plano são liberados após a confirmação do pagamento.",
        "Cada plano tem franquias mensais de atendimentos de IA, buscas e otimizações de fotos, renovadas a cada ciclo e não acumuláveis. Um atendimento corresponde a um contato em uma janela de 24 horas, com até 50 respostas do agente.",
        "Pacotes adicionais são cobranças avulsas; os créditos valem por 90 dias a partir da confirmação do pagamento.",
        "Condições especiais, como a de beta tester, valem enquanto mantidas pela " + c.brand + " e podem ser encerradas com aviso prévio de 30 dias.",
        "Você pode cancelar a assinatura a qualquer momento; o acesso pago segue até o fim do ciclo já pago e não há reembolso proporcional, salvo quando a lei exigir.",
        "Em caso de atraso, os serviços do plano podem ser suspensos até a regularização.",
      ],
    },
    {
      heading: "4. Agente de inteligência artificial",
      items: [
        "As respostas do agente são geradas automaticamente e podem conter erros. Você é responsável por configurar o agente, acompanhar os atendimentos e assumir as conversas quando necessário.",
        "O agente não deve ser usado para negociar valores, prestar orientação jurídica ou financeira conclusiva, nem substituir a atuação do corretor nas etapas que a lei atribui a ele.",
        "As informações sobre imóveis oferecidas pelo agente vêm do cadastro feito por você; mantenha-o correto e atualizado.",
      ],
    },
    {
      heading: "5. WhatsApp",
      items: [
        "A conexão do WhatsApp é feita pela leitura de um QR Code com o aparelho do seu número, por meio de uma integração que não é a API oficial do WhatsApp Business. O WhatsApp pode limitar ou bloquear números que descumpram suas políticas, por exemplo pelo envio de mensagens em massa não solicitadas.",
        "Você é responsável pelo número conectado, pelo conteúdo enviado e por respeitar as políticas do WhatsApp e a legislação de proteção de dados e de consumo.",
      ],
    },
    {
      heading: "6. Conteúdo e dados da sua conta",
      items: [
        "Os dados que você cadastra ou que chegam pelos seus canais (imóveis, contatos, conversas, documentos) são seus. Em relação aos dados pessoais de leads e clientes, você é o controlador e a " + c.brand + " atua como operadora, tratando-os conforme suas instruções e a Política de privacidade.",
        "Você declara ter base legal para tratar os dados pessoais que insere na plataforma e garante não inserir conteúdo ilícito ou que viole direitos de terceiros.",
        "Exclusões ficam registradas no histórico da conta, com cópia do registro removido, para segurança e auditoria.",
      ],
    },
    {
      heading: `7. Rede ${c.brand}`,
      items: [
        "Ao aderir à Rede, você aceita compartilhar com outras imobiliárias os imóveis que escolher, sem endereço completo nem dados do proprietário.",
        "As parcerias e comissões são acordadas diretamente entre as imobiliárias. A " + c.brand + " não é parte desses acordos nem responde por eles.",
      ],
    },
    {
      heading: "8. Disponibilidade e responsabilidade",
      items: [
        "Trabalhamos para manter a plataforma disponível e segura, mas podem ocorrer interrupções para manutenção ou por falhas de terceiros (provedores de hospedagem, WhatsApp, inteligência artificial, pagamentos).",
        `Na máxima extensão permitida pela lei, a responsabilidade da ${c.brand} fica limitada ao valor pago pela conta nos 12 meses anteriores ao evento, e não abrange lucros cessantes ou negócios não realizados.`,
      ],
    },
    {
      heading: "9. Propriedade intelectual",
      paragraphs: [
        `A plataforma, a marca ${c.brand} e seus elementos visuais pertencem a ${c.legalName}. O uso da plataforma não transfere esses direitos.`,
      ],
    },
    {
      heading: "10. Alterações e contato",
      paragraphs: [
        "Podemos atualizar estes termos. Mudanças relevantes serão avisadas na plataforma com antecedência razoável; o uso continuado depois disso indica concordância.",
        `Dúvidas: ${c.supportEmail}. Fica eleito o foro de ${c.city}, salvo regra legal em contrário.`,
      ],
    },
  ],
};

export const PRIVACY: LegalDocument = {
  title: "Política de privacidade",
  intro: `Esta política explica como ${c.legalName} (${c.brand}) trata dados pessoais, em conformidade com a Lei Geral de Proteção de Dados (Lei 13.709/2018).`,
  sections: [
    {
      heading: "1. Papéis",
      items: [
        `Dados de quem usa a plataforma (corretores, imobiliárias e suas equipes): a ${c.brand} é a controladora.`,
        `Dados de leads, clientes e proprietários inseridos pelas imobiliárias ou recebidos pelos canais delas: a imobiliária é a controladora e a ${c.brand} é a operadora, tratando os dados apenas para prestar o serviço contratado.`,
      ],
    },
    {
      heading: "2. Dados tratados",
      items: [
        "Cadastro e conta: nome, e-mail, telefone, CPF ou CNPJ, razão social e dados de faturamento.",
        "Uso da plataforma: registros de acesso, endereço IP, ações realizadas e histórico de exclusões.",
        "Dados operados para a imobiliária: contatos, conversas de WhatsApp (textos, áudios e imagens), demandas de imóveis, imóveis e documentos da base de conhecimento.",
        "Não usamos cookies de rastreamento ou publicidade. O navegador guarda apenas preferências e a sessão de acesso.",
      ],
    },
    {
      heading: "3. Finalidades e bases legais",
      items: [
        "Prestar o serviço contratado, incluindo o atendimento por inteligência artificial (execução de contrato).",
        "Cobrança e emissão de documentos fiscais (execução de contrato e obrigação legal).",
        "Segurança, prevenção a fraudes e registro de acessos (legítimo interesse e obrigação legal, conforme o Marco Civil da Internet).",
        "Suporte e comunicações sobre a conta (execução de contrato).",
      ],
    },
    {
      heading: "4. Com quem compartilhamos",
      items: [
        "Provedores de inteligência artificial (como a OpenAI), para gerar as respostas do agente, transcrever áudios e otimizar fotos. Esse tratamento pode ocorrer fora do Brasil, com salvaguardas contratuais.",
        "Asaas, para processar pagamentos.",
        "WhatsApp, por meio da conexão do número da imobiliária, para enviar e receber mensagens.",
        "Provedores de hospedagem e infraestrutura.",
        "Outras imobiliárias da Rede, apenas os dados de imóveis que você escolher compartilhar e, após uma parceria aceita, os contatos comerciais informados por você.",
        "Autoridades, quando houver obrigação legal ou ordem judicial.",
      ],
    },
    {
      heading: "5. Retenção",
      paragraphs: [
        "Mantemos os dados enquanto a conta estiver ativa. Após o encerramento, os dados operados para a imobiliária são excluídos ou devolvidos em até 90 dias, salvo os que a lei exija guardar (por exemplo, registros de acesso por 6 meses e dados fiscais pelo prazo legal). Cópias de segurança são eliminadas no ciclo normal de backup.",
      ],
    },
    {
      heading: "6. Segurança",
      paragraphs: [
        "Usamos conexão criptografada, senhas armazenadas com algoritmo de hash, credenciais de integrações criptografadas, controle de acesso por perfil e cópias de segurança diárias. Nenhum sistema é totalmente imune a incidentes; se algum afetar seus dados, avisaremos você e a autoridade competente nos termos da lei.",
      ],
    },
    {
      heading: "7. Seus direitos",
      paragraphs: [
        `Você pode pedir confirmação de tratamento, acesso, correção, anonimização, portabilidade, eliminação, informação sobre compartilhamentos e revisão de decisões automatizadas, além de revogar consentimentos, pelo e-mail ${c.privacyEmail}. Pedidos de leads e clientes de uma imobiliária serão encaminhados a ela, que é a controladora desses dados.`,
      ],
    },
    {
      heading: "8. Encarregado e alterações",
      paragraphs: [
        `Encarregado pelo tratamento de dados: ${c.privacyEmail}. Esta política pode ser atualizada; a versão vigente fica sempre nesta página, com a data abaixo.`,
      ],
    },
  ],
};
