# Telegram para testes dos agentes

## 1. Criar o bot

1. Abra o Telegram e converse com `@BotFather`.
2. Envie `/newbot`.
3. Escolha nome e username terminado em `bot`.
4. Guarde o token fornecido. Quem possui esse token controla o bot.

## 2. Criar o segredo do webhook

```bash
openssl rand -hex 32
```

## 3. Expor o backend local por HTTPS

O Telegram não consegue chamar `localhost`. Uma opção de desenvolvimento é instalar o
Cloudflare Tunnel e executar:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copie a URL HTTPS temporária exibida, sem barra no final.

## 4. Configurar o backend

No `backend/.env`, adicione ou atualize:

```dotenv
BACKEND_PUBLIC_URL=https://URL-DO-TUNEL.trycloudflare.com
TELEGRAM_AUTO_REPLY_ENABLED=true
TELEGRAM_TENANT_CONFIGS={"demo":{"bot_token":"TOKEN-DO-BOTFATHER","webhook_secret":"SEGREDO-GERADO","bot_username":"username_do_bot"}}
```

Não coloque o token no frontend, em documentos ou no Git. Reinicie o backend depois de
alterar o `.env`.

## 5. Registrar o webhook

1. Entre em `http://localhost:5173` com o tenant `demo`.
2. Abra `Configurações > Canais`.
3. No Telegram, clique em `Configurar webhook`.
4. Confirme que o canal aparece como conectado e mostra o username do bot.

O backend registra esta URL:

```text
https://URL-PUBLICA/webhooks/telegram/demo
```

O Telegram envia o segredo no cabeçalho `X-Telegram-Bot-Api-Secret-Token`; mensagens sem o
segredo correto são rejeitadas.

## 6. Conversar com o agente

1. Abra o username do bot no Telegram.
2. Pressione `Iniciar` ou envie uma mensagem.
3. Exemplo: `Olá, procuro um apartamento para comprar em São Paulo.`
4. O Agente de Leads responde no Telegram e a conversa aparece no painel ImobIA.

O mesmo chat preserva histórico, qualificação, busca de imóveis, auditoria, handoff e modo
humano. Se um operador assumir a conversa no painel, a IA para de responder e as mensagens
humanas são enviadas pelo bot.

## Diagnóstico

- `GET /integrations/telegram/status`: valida token, bot e webhook;
- `pending_updates`: mensagens aguardando processamento;
- `last_error`: último erro informado pelo Telegram;
- IDs repetidos são ignorados por idempotência;
- grupos são ignorados no MVP; apenas conversas privadas são atendidas.
