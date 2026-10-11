# Deploy da ImmobIA no Easypanel

Tudo roda num único serviço **Compose** do Easypanel, a partir de `docker-compose.prod.yml`, na raiz do repositório.

| Serviço          | O que faz                                                        | Domínio        |
|------------------|------------------------------------------------------------------|----------------|
| `web`            | Painel da imobiliária (e a API em `/api`)                        | sim, porta 80  |
| `admin`          | Painel admin da plataforma (e a API em `/api`)                   | sim, porta 80  |
| `backend`        | API; roda as migrações do banco a cada início                    | não            |
| `message-worker` | Envia as respostas do agente pelo WhatsApp                       | não            |
| `capture-worker` | Faz as buscas de imóveis nos portais                             | não            |
| `billing-worker` | Gera a fatura mensal do corretor beta ao fim de cada ciclo      | não            |
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
- No admin, marque a conta de corretor como **Beta tester**. Confira que ela vê somente o plano
  Corretor beta (R$ 59,90, 20 buscas) e gere a primeira fatura por PIX ou cartão.
- Conecte um WhatsApp por QR Code, cadastre um imóvel e converse a partir de outro celular.
- Compre um pacote de 15 otimizações e confira os créditos. O preço é R$ 30,00.
- Confira no painel o consumo avulso de IA e imagens; a renovação soma esse consumo à próxima
  mensalidade. O `billing-worker` gera uma fatura por ciclo, e o pagamento libera a nova franquia.
- Cancele a assinatura de teste no admin.

## Backups

O serviço `backup` grava diariamente `db-*.dump` e, enquanto `BACKUP_MEDIA_ARCHIVE=true`,
`media-*.tar.gz` no volume local. Os arquivos só recebem o nome final depois de completos.
O healthcheck exige um dump das últimas 26 horas legível por `pg_restore --list`. O contêiner e
o volume ficam no mesmo VPS; essa cópia local não protege contra perda do servidor ou do disco.

O serviço opcional definido em `docker-compose.backup.prod.yml` envia os dumps para
`database/` e sincroniza somente as mídias novas ou alteradas em `media/` a cada hora. Ele monta
os três volumes da aplicação somente para leitura. Antes de ativá-lo, escolha uma conta de
armazenamento exclusiva para o ImmobIA. Configure nele o bucket, a região, os nomes reais dos
volumes e credenciais limitadas ao destino, usando `deploy/.env.backup.example` como lista de
variáveis. Nunca coloque essas credenciais no `.env` da aplicação. O bucket deve ser privado.
Esse serviço opcional não está implantado; o backup atual permanece somente no VPS.

Para **Cloudflare R2**, use armazenamento Standard, `AWS_DEFAULT_REGION=auto` e
`AWS_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. Crie uma chave S3 com permissão
**Object Read & Write** limitada somente ao bucket de backup. Configure uma regra de ciclo de vida
para apagar apenas `database/` após o prazo escolhido (por exemplo, 30 dias). **Não** aplique esse
prazo a `media/`: uma foto que não mudar deixaria de existir no backup. Para **Backblaze B2**,
preencha a região e o endpoint S3 informados pelo provedor e restrinja a chave ao bucket. Para
AWS S3, deixe `AWS_ENDPOINT_URL` vazio; são necessários `s3:ListBucket` no bucket e
`s3:PutObject`/`s3:GetObject` nos objetos.

Para conferir uma cópia externa, baixe um dump e execute `pg_restore --list <arquivo>`.
Para uma recuperação completa, restaure o dump com `pg_restore --clean --if-exists` em um banco
vazio e sincronize os diretórios `media/property-images/` e `media/conversation-media/` de volta
para os respectivos volumes. Teste a restauração antes de desativar os arquivos locais de mídia.

## Testar a stack de produção localmente

Na raiz do repositório (o `.env` criado ali fica fora do Git):

```sh
sh deploy/generate-secrets.sh > .env && grep -v -E "^(POSTGRES_PASSWORD|JWT_SECRET|INTEGRATION_SECRET_KEY|PLATFORM_BOOTSTRAP_TOKEN|ASAAS_WEBHOOK_TOKEN)=" deploy/.env.production.example >> .env
docker compose -p immobia-prodtest -f docker-compose.prod.yml -f deploy/docker-compose.localtest.yml up -d --build
# painel: http://localhost:8081  · admin: http://localhost:8082
docker compose -p immobia-prodtest -f docker-compose.prod.yml -f deploy/docker-compose.localtest.yml down -v && rm .env
```

Sem conta conectada nem chave da Evolution, o worker de mensagens não tem para quem enviar.
