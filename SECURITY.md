# Política de segurança

## Relato de vulnerabilidades

Não abra uma issue pública para relatar uma vulnerabilidade ou possível exposição de dados.
Use o recurso **Report a vulnerability** na aba **Security** deste repositório para enviar um
relato privado ao mantenedor.

Inclua, quando possível:

- descrição e impacto esperado;
- passos mínimos para reprodução;
- versão, commit ou componente afetado;
- sugestão de mitigação, sem incluir dados pessoais ou credenciais reais.

## Segredos e dados de teste

Nunca envie arquivos `.env`, chaves, tokens, senhas, credenciais de terceiros, dados de clientes
ou exports de bancos de dados. Use somente valores fictícios nos exemplos e testes.

Credenciais eventualmente expostas devem ser revogadas no provedor de origem; removê-las do
Git não é suficiente.
