# ImobIA Captura Assistida

Extensão Chrome Manifest V3 para validar a captura de anúncios já renderizados na OLX e no
Facebook Marketplace. Esta primeira etapa mantém o lote local para revisão e exportação; ela não
captura cookies, senhas ou tokens de sessão.

## Teste local

1. Abra `chrome://extensions` e ative o modo do desenvolvedor.
2. Clique em **Carregar sem compactação** e selecione esta pasta.
3. Abra uma página de resultados da OLX ou do Facebook Marketplace.
4. Clique no ícone da extensão e depois em **Capturar resultados desta guia**.

O lote normalizado fica no side panel e pode ser baixado como JSON. A etapa seguinte é parear a
extensão com um dispositivo do ImobIA e enviar esse lote para uma execução de busca específica.

## Limites desta versão

- captura somente os cards presentes no DOM; role a página antes de capturar para ampliar o lote;
- mudanças de layout podem exigir uma nova versão do leitor do portal;
- a integração autenticada com o backend ainda não está habilitada;
- a extensão não agenda capturas com o Chrome fechado.
