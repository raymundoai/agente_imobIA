# Painel de administração da plataforma

O painel exclusivo da ImobIA fica em `/platform`. Seus usuários são armazenados em
`platform_users` e não pertencem a nenhuma imobiliária.

## Criar o primeiro acesso

O bootstrap funciona uma única vez. Primeiro, gere um segredo forte e salve somente no
`backend/.env`:

```bash
openssl rand -hex 32
```

```dotenv
PLATFORM_BOOTSTRAP_TOKEN=VALOR_GERADO
```

Reinicie o backend e crie o primeiro administrador, substituindo os valores:

```bash
curl -X POST 'http://127.0.0.1:8000/platform/auth/bootstrap' \
  -H 'Content-Type: application/json' \
  -H 'X-Platform-Bootstrap-Token: VALOR_GERADO' \
  -d '{
    "name": "Administrador da ImobIA",
    "email": "seu-email@exemplo.com",
    "password": "UMA-SENHA-FORTE-COM-MAIS-DE-12-CARACTERES"
  }'
```

Depois do primeiro cadastro, novas chamadas ao bootstrap são rejeitadas. O acesso normal é
feito em `http://localhost:5173/platform`.

## Recursos

- dashboard com clientes ativos e inativos;
- usuários, conversas, leads, contatos e imóveis globais;
- chamadas e custo estimado de IA;
- lista e detalhe de imobiliárias;
- status não sensível das integrações;
- criação de tenant e primeiro administrador;
- suspensão e reativação de cliente.

Administradores de imobiliárias não conseguem usar seus tokens nas rotas `/platform`. Em
produção, o cadastro público em `/tenants` também é bloqueado e o onboarding passa pelo painel.
