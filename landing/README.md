# Landing page do ImmobIA

Página estática da oferta beta. Os botões de cadastro apontam para
`https://app.immob.ia.br/criar-conta`.

Para visualizar:

```sh
cd landing
python3 -m http.server 4175
```

Abra `http://localhost:4175`.

Em produção, a página roda em um serviço Compose separado no Easypanel, usando
`docker-compose.landing.prod.yml`. O domínio público é configurado no painel e no DNS.

Os preços e benefícios exibidos refletem a oferta beta para corretores convidados. Ao alterar a
oferta, revise também esta página.
