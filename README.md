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

## Armazenamento das imagens

No Docker de desenvolvimento, backend e worker compartilham o volume persistente
`imobos_property_media`, montado em `/data/property-images`. Uploads e limpezas
pendentes sobrevivem à recriação dos containers.

Em produção, configure armazenamento S3 ou compatível e mantenha o bucket privado:

```env
PROPERTY_STORAGE_BACKEND=s3
PROPERTY_S3_BUCKET=imobia-property-media
PROPERTY_S3_REGION=us-east-1
PROPERTY_S3_ENDPOINT_URL=https://s3.example.com
PROPERTY_S3_ACCESS_KEY=...
PROPERTY_S3_SECRET_KEY=...
```

A aplicação valida o prefixo do tenant e entrega URLs temporárias assinadas.
