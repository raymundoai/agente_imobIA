# ImobIA

MVP multiempresa para imobiliárias atenderem e qualificarem leads por WhatsApp e Telegram,
organizarem contatos e manterem sua carteira de imóveis.

## Documentação

- [Operação local](docs/OPERACAO_LOCAL.md): instalação, execução, bootstrap e testes.
- [Política de segurança](SECURITY.md): como relatar vulnerabilidades sem exposição pública.

Código, migrations e testes são a referência técnica do projeto.

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

A aplicação preserva original e versão tratada separadamente, valida o prefixo do tenant e
entrega conteúdo por rota autenticada ou URL S3 temporária. Exclusões geram tarefas persistentes
processadas pelo worker.

## Situação do MVP

Os fluxos principais estão implementados, mas “implementado” não significa “homologado”:
WhatsApp, Telegram, OpenAI, storage S3, HTTPS, backup e restauração ainda precisam ser
validados juntos em um ambiente semelhante ao de produção.

Para produção:

- use domínios HTTPS separados ou roteamento explícito para painel da imobiliária, painel da
  plataforma e API;
- configure secrets fora da imagem e do repositório;
- mantenha banco e bucket privados, com backup, retenção e teste de restauração;
- execute API e worker persistente; sem worker não há resposta automática nem limpeza de mídia;
- restrinja CORS às origens publicadas e configure as URLs públicas exatas dos webhooks.

## Licença

O código é disponibilizado para consulta pública, mas não é software de código aberto. Consulte
o arquivo [LICENSE](LICENSE) antes de copiar, modificar ou redistribuir qualquer parte do projeto.
