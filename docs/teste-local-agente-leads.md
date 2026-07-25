# Teste local do Agente de Leads

Este roteiro valida o atendimento sem enviar mensagens para um WhatsApp real.

## Configuração segura

No `backend/.env`:

```dotenv
OPENAI_API_KEY=...
AI_AUTO_REPLY_ENABLED=true
AI_AUTO_SEND_TO_CHANNEL=false
```

Com o envio ao canal desativado, a resposta da IA é salva na conversa e devolvida na
resposta HTTP, mas não é enviada pela Evolution API. O tenant também precisa de uma entrada
em `EVOLUTION_TENANT_CONFIGS`, pois o webhook valida seu segredo mesmo no teste local.

## Iniciar

```bash
docker compose --env-file backend/.env up -d postgres
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

## Simular uma mensagem da Evolution

Substitua `demo` pelo slug do tenant e o segredo pelo valor configurado para ele:

```bash
curl -X POST 'http://127.0.0.1:8000/webhooks/whatsapp/demo' \
  -H 'Content-Type: application/json' \
  -H 'X-ImobIA-Webhook-Secret: SEGREDO_DO_WEBHOOK' \
  -d '{
    "event": "MESSAGES_UPSERT",
    "data": {
      "key": {
        "id": "teste-local-001",
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": false
      },
      "pushName": "Cliente Teste",
      "message": {
        "conversation": "Olá, quero comprar um apartamento em São Paulo"
      }
    }
  }'
```

A resposta deve conter `status: "processed"` e `ai_response`. A conversa e as duas
mensagens ficam persistidas e aparecem no painel.

Use um novo valor em `data.key.id` a cada mensagem. Repetir o ID é tratado como duplicata e
não chama a IA novamente. Para continuar a mesma conversa, mantenha o `remoteJid` e altere
apenas o ID e o texto.

O agente usa as últimas mensagens como histórico, coleta os critérios gradualmente, salva a
demanda quando estiver qualificada e pode consultar imóveis reais do tenant. Quando a conversa
está em modo humano, novas respostas da IA são bloqueadas até ela voltar ao modo `ai`.
