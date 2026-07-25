# Operação local e acessos de desenvolvimento

> Somente desenvolvimento local. As senhas abaixo são intencionalmente conhecidas e devem
> ser removidas ou trocadas antes de qualquer publicação na internet.

## 1. Subir a ferramenta

Execute os comandos a partir da raiz do projeto:

```bash
cd /home/raymundo/projetos/agente_imobIA
```

### Terminal 1 — PostgreSQL com pgvector

```bash
docker compose --env-file backend/.env up -d postgres
docker compose --env-file backend/.env ps
```

O segundo comando deve mostrar o serviço `postgres` como `healthy`.

### Terminal 2 — backend FastAPI

```bash
cd /home/raymundo/projetos/agente_imobIA/backend
dotenv run -- alembic upgrade head
dotenv run -- uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verificações:

- API: `http://localhost:8000/health`
- documentação interativa: `http://localhost:8000/docs`

### Terminal 3 — frontend React

```bash
cd /home/raymundo/projetos/agente_imobIA/frontend
npm run dev
```

Acessos:

- painel da imobiliária: `http://localhost:5173`
- administração da plataforma: `http://localhost:5173/platform`

Para encerrar backend ou frontend, pressione `Ctrl+C` nos respectivos terminais. Para parar
somente o banco:

```bash
cd /home/raymundo/projetos/agente_imobIA
docker compose --env-file backend/.env stop postgres
```

Não use `docker compose down -v`, pois a opção `-v` remove o volume que guarda os dados.

## 2. Administrador da plataforma

- URL: `http://localhost:5173/platform`
- Login: `admin@imobia.dev.example.com`
- Senha: `ImobIA-Platform-Dev-2026!`

Esse usuário administra todas as imobiliárias, visualiza métricas globais e cria, suspende ou
reativa tenants.

## 3. Tenant de testes

- Empresa/slug: `demo`
- URL: `http://localhost:5173`
- Login: `admin@demo.example.com`
- Senha: `ImobIA-Demo-Dev-2026!`

O tenant se chama `Imobiliária Demo` e começa sem contatos, imóveis ou conversas cadastradas.

## Cuidados

- Não reutilize essas senhas em outros sistemas.
- Antes do deploy, troque as duas senhas, o `JWT_SECRET`, as credenciais do PostgreSQL e o
  `PLATFORM_BOOTSTRAP_TOKEN`.
- O `.env` e este documento não devem ser usados como secret manager em produção.
