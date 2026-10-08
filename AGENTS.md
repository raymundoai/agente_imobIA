# Instruções para agentes (Codex, Claude e outros)

Leia este arquivo antes de começar. Depois, siga a ordem de leitura abaixo.

## 1. Onde paramos e o que falta

Antes de qualquer tarefa, leia nesta ordem:

1. **`docs/estado-atual.md`**: retrato do produto e da operação hoje. Inclui:
   - o que está em produção e o último deploy;
   - o que vai no próximo deploy;
   - os testes feitos e os pendentes;
   - onde ficam as variáveis e os acessos (só a localização, nunca o valor);
   - o ambiente local e os cuidados de segurança.
2. **`docs/Changelog.md`**: o que mudou, por data. O bloco **"Não publicado"** é o que já está no
   Git mas ainda não foi para a produção.
3. **`docs/BACKLOG.md`**: pendências, ideias, correções e feedback dos beta testers, em itens
   `B-NNN` com status.

`estado-atual.md` e `Changelog.md` são internos e ficam **fora do Git** (estão no `.gitignore`).
Eles existem só na máquina de desenvolvimento. Se não estiverem lá, avise a pessoa em vez de
recriá-los do zero.

## 2. Mantenha a documentação em dia

Os documentos são um registro paralelo ao Git. Atualize-os no mesmo trabalho em que a mudança
acontece:

| Aconteceu | Atualize |
|---|---|
| Mudança no produto (código, configuração, visual) | `Changelog.md`, no bloco "Não publicado", com o hash do commit |
| Deploy em produção | `Changelog.md` (o bloco "Não publicado" vira uma data, "publicado em produção") e `estado-atual.md` (último deploy, testes, lista do próximo deploy) |
| Ideia, pedido, feedback ou correção para depois | `BACKLOG.md`: novo item `B-NNN`, com a linha na tabela de resumo |
| Item do backlog implementado ou descartado | `BACKLOG.md`: status e **Decisão** (data, motivo ou commit) |
| Mudança de infraestrutura, domínio, integração ou acesso | `estado-atual.md` |

Escreva em português, em linguagem de produto, e atualize a data de "Última atualização" do
`estado-atual.md`.

## 3. Regras do projeto

- **Idioma:** converse e documente em português do Brasil. Código e comentários seguem o padrão
  do arquivo em que você está mexendo.
- **O repositório é público.** Nunca commite:
  - `.env`, chaves, tokens ou senhas;
  - transcrições, dados de clientes ou detalhes da infraestrutura.

  O `BACKLOG.md` é público: não use nomes nem contatos de pessoas nele.
- **Nunca grave segredos nos documentos.** Registre só onde estão.
- **Commit, push e deploy:** só quando a pessoa pedir ou aprovar. Deploy em produção sempre com
  aprovação explícita. Não inclua `.claude/` nos commits.
- **Docker local:** sempre `docker compose --env-file backend/.env ...`.
- **Nunca suba o `message-worker` local.** Com o envio automático ligado, ele mandaria mensagens
  reais de WhatsApp. Suba só `postgres`, `backend` e `capture-worker`.
- **Formatação:** rode o `ruff format` só nos arquivos que você alterou, não no backend inteiro.

## 4. Como rodar e testar

- **Backend:** FastAPI, SQLAlchemy 2, Alembic e PostgreSQL com pgvector.
  - Lint e formatação: `cd backend && ruff check <arquivos> && ruff format <arquivos>` (linhas de
    até 100 caracteres).
  - Testes:
    ```sh
    cd backend && set -a && . ./.env && set +a
    export TEST_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/imobos_test"
    pytest -p no:cacheprovider tests
    ```
  - O teste `test_property_image_order_and_primary_delete_are_atomic_and_isolated` falha de vez
    em quando (concorrência). Ao rodar sozinho, passa.
  - Migrações novas ficam em `backend/alembic/versions/`, no padrão `AAAAMMDD_NNNN_nome.py`.
- **Frontend:** React e Vite, em `frontend/`.
  - Testes: `npm test`.
  - Build: `npm run build` e `npx vite build -c vite.platform.config.ts`.
  - Rodar local: `npm run dev` (painel das imobiliárias) e `npm run dev:platform` (admin). Se a
    porta 5173 estiver ocupada, o Vite usa a próxima livre.
- **Produção:** `docker-compose.prod.yml` na raiz, publicado pelo Easypanel. O passo a passo está
  em `deploy/README.md`.
