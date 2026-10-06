# Deploy da ImmobIA no Easypanel

Tudo roda num único serviço **Compose** do Easypanel, a partir de `docker-compose.prod.yml`, na raiz do repositório.

| Serviço          | O que faz                                                        | Domínio        |
|------------------|------------------------------------------------------------------|----------------|
| `web`            | Painel da imobiliária (e a API em `/api`)                        | sim, porta 80  |
| `admin`          | Painel admin da plataforma (e a API em `/api`)                   | sim, porta 80  |
| `backend`        | API; roda as migrações do banco a cada início                    | não            |
| `message-worker` | Envia as respostas do agente pelo WhatsApp                       | não            |
| `capture-worker` | Faz as buscas de imóveis nos portais                             | não            |
| `postgres`       | Banco de dados (com pgvector)                                    | não            |
| `backup`         | Cópia diária do banco e das mídias (mantém 14 dias)              | não            |

## 1. Preparar as variáveis

1. Rode `sh deploy/generate-secrets.sh` no seu computador e guarde a saída num cofre de senhas.
2. Copie `deploy/.env.production.example` para `deploy/.env.production` (fica fora do Git) e preencha:
   - as chaves geradas no passo 1;
   - `APP_PUBLIC_URL` e `BACKEND_PUBLIC_URL` com o domínio do serviço `web` (este último terminando em `/api`);
   - `EVOLUTION_BASE_URL` e `EVOLUTION_API_KEY` da Evolution que já está no Easypanel;
   - `OPENAI_API_KEY` e `ASAAS_API_KEY` (podem ficar vazias no primeiro teste: o sistema sobe, mas sem IA e sem cobrança).
3. Confira: `AI_AUTO_REPLY_ALLOWED_PHONES=[]` (vazio, para o agente responder todos os números).

## 2. Criar o serviço

1. No projeto do Easypanel, **+ Service → Compose**.
2. Fonte: o repositório do GitHub, branch `main`, arquivo `docker-compose.prod.yml`.
3. Em **Environment**, cole o conteúdo de `deploy/.env.production` e marque a opção de criar o
   arquivo `.env`. O Easypanel grava esse arquivo na raiz do repositório, ao lado de
   `docker-compose.prod.yml`, que é de onde o compose lê as variáveis.
4. **Deploy**. O primeiro build leva alguns minutos.
5. Em **Domains**, adicione um domínio para `web` (porta 80) e outro para `admin` (porta 80).
   O Easypanel oferece domínios temporários; o HTTPS é automático.

Se mudar o domínio do `web`, atualize `APP_PUBLIC_URL` e `BACKEND_PUBLIC_URL` e faça novo deploy.

## 3. Primeiro acesso

1. Crie o admin da plataforma (uma vez só), trocando os valores:

   ```sh
   curl -X POST https://DOMINIO-DO-ADMIN/api/platform/auth/bootstrap \
     -H "Content-Type: application/json" \
     -H "X-Platform-Bootstrap-Token: VALOR_DO_PLATFORM_BOOTSTRAP_TOKEN" \
     -d '{"name":"Seu nome","email":"voce@exemplo.com","password":"uma-senha-forte-de-12+"}'
   ```

2. Entre no painel admin, abra **Configurações → Asaas**, confira a conexão e clique em **Configurar webhook**.
3. Ainda em Configurações, revise os **Preços beta**.

## 4. Teste em produção

- Crie uma conta pelo cadastro do painel `web` e passe pelo assistente de configuração.
- No admin, marque a conta como **Beta tester**; assine o Essencial por PIX (R$ 49).
- Conecte um WhatsApp por QR Code, cadastre um imóvel e converse a partir de outro celular.
- Compre um pacote adicional e confira os créditos.
- Cancele a assinatura de teste no admin.

## Backups

O serviço `backup` grava em seu volume `backups`, todo dia, `db-*.dump` (banco) e `media-*.tar.gz` (fotos e mídias das conversas).
Para restaurar o banco: `pg_restore --clean --if-exists -d immobia db-AAAA-MM-DD...dump` dentro do container `postgres`.
Vale também copiar os arquivos para fora do servidor de tempos em tempos.

## Testar a stack de produção localmente

Na raiz do repositório (o `.env` criado ali fica fora do Git):

```sh
sh deploy/generate-secrets.sh > .env && grep -v -E "^(POSTGRES_PASSWORD|JWT_SECRET|INTEGRATION_SECRET_KEY|PLATFORM_BOOTSTRAP_TOKEN|ASAAS_WEBHOOK_TOKEN)=" deploy/.env.production.example >> .env
docker compose -p immobia-prodtest -f docker-compose.prod.yml -f deploy/docker-compose.localtest.yml up -d --build
# painel: http://localhost:8081  · admin: http://localhost:8082
docker compose -p immobia-prodtest -f docker-compose.prod.yml -f deploy/docker-compose.localtest.yml down -v && rm .env
```

Sem conta conectada nem chave da Evolution, o worker de mensagens não tem para quem enviar.
