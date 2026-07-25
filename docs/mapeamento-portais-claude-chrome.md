# Mapeamento dos portais de imóveis com Claude no Chrome

Este roteiro serve para validar como cada portal representa seus filtros na URL. Ele não deve
capturar anúncios em massa, contornar bloqueios, autenticação ou CAPTCHA. O objetivo é somente
mapear buscas que um corretor faria normalmente no navegador.

## Prompt para o Claude

```text
Você está me ajudando a mapear URLs públicas de busca de imóveis para uma aplicação chamada
ImobIA. Trabalhe somente através da interface normal do Chrome. Não tente contornar CAPTCHA,
login, rate limit ou qualquer mecanismo de proteção.

Portais a analisar:
- https://www.zapimoveis.com.br/
- https://www.vivareal.com.br/
- https://www.olx.com.br/imoveis
- https://www.lelloimoveis.com.br/

Em cada portal, faça duas buscas de teste:
A) Comprar apartamento em São Paulo, bairro Pinheiros, 2 quartos, 1 vaga, área mínima 60 m²,
   preço entre R$ 500.000 e R$ 900.000.
B) Alugar casa em São Paulo, bairro Vila Mariana, 3 quartos, 2 vagas, área mínima 100 m²,
   preço entre R$ 3.000 e R$ 8.000.

Para cada busca:
1. Aplique os filtros pela interface do site.
2. Copie a URL final completa.
3. Recarregue a URL em uma nova aba e confirme quais filtros permaneceram aplicados.
4. Altere um filtro por vez e identifique qual trecho do path ou query string mudou.
5. Informe se algum filtro fica apenas no estado interno do navegador e não pode ser
   reproduzido por uma URL compartilhável.
6. Não abra anúncios individuais e não colete dados pessoais de anunciantes.

Entregue uma tabela por portal com:
- finalidade;
- cidade/UF;
- bairro;
- tipo;
- preço mínimo e máximo;
- quartos;
- vagas;
- área mínima;
- nome do parâmetro ou segmento de URL;
- exemplo de valor codificado;
- persiste após recarregar: sim/não;
- observações.

Ao final, forneça as oito URLs completas testadas e destaque qualquer comportamento instável,
redirecionamento ou filtro que dependa de cookies/localStorage.
```

## Como usar o resultado

Salvar as URLs e a tabela retornada sem tokens, cookies ou dados de sessão. O mapeamento deve ser
comparado com `backend/app/modules/capture/portals.py`. Como os portais podem mudar, exemplos
confirmados devem registrar a data do teste.

## Mapeamento confirmado em 15/07/2026

O primeiro levantamento confirmou:

- ZAP e Viva Real: `precoMinimo`, `precoMaximo`, `quartos`, `vagas`, `areaMinima`,
  `tipos` e `onde`;
- OLX: `ps`, `pe`, `gsp`, `ss`, código de tipo `ret` e localização pelo path;
- Lello: finalidade, tipo, dormitórios, bairro/cidade e preço no path; área e vagas no
  fragmento `#`.

As localizações confirmadas para São Paulo estão declaradas em `SP_LOCATIONS`, no arquivo
`backend/app/modules/capture/portals.py`. Cada bairro precisa de zona, slugs específicos e,
para ZAP/Viva Real, latitude e longitude confirmadas. Se o bairro não estiver nessa tabela,
o sistema mantém o filtro como pendente nos portais que dependem desses metadados, evitando
uma busca silenciosamente incorreta.

## Descoberta de referências

O ImobIA possui descoberta manual sob demanda para Lello e OLX. O coletor guarda somente dados
objetivos, portal e URL original; não importa descrição integral, fotos ou contatos.

- Lello: leitura pública validada em 18/07/2026, com referências presentes no JSON estruturado
  da página;
- OLX: a tentativa direta do backend recebeu HTTP 403 em 18/07/2026. O sistema interrompe a
  consulta e não tenta contornar o bloqueio. Para essa fonte, o caminho técnico futuro é uma
  integração autorizada ou uma extensão executada pelo próprio corretor no navegador.
