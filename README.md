# ImobIA

MVP multiempresa para imobiliárias atenderem e qualificarem leads por WhatsApp e Telegram,
organizarem contatos e manterem sua carteira de imóveis.

## Documentação

- [PRD do MVP](PRD-DEV.md): escopo, estado atual e critérios de aceite.
- [Operação local](docs/OPERACAO_LOCAL.md): instalação, execução, bootstrap e testes.
- [Créditos e custos](docs/CREDITOS_E_CUSTOS.md): preços de IA, unidade econômica e cobrança.
- [Pós-lançamento](docs/ROADMAP_POS_MVP.md): recursos adiados para V2.

## Stack

FastAPI + PostgreSQL/pgvector no backend e React/Vite no frontend. OpenAI é usada pelo Agente
de Leads, pela base de conhecimento e, quando solicitado, pelo tratamento das imagens.

Não adicione `.env`, chaves, tokens ou senhas ao Git.
