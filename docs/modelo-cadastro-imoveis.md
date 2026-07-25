# Modelo de cadastro de imóveis do MVP

O cadastro separa informações usadas em busca e comparação de detalhes descritivos. Campos
condicionais aparecem conforme a oferta selecionada.

## Identificação e classificação

- código interno do imóvel;
- título e descrição;
- status: rascunho, ativo ou inativo;
- finalidade: venda, locação ou ambas;
- categoria: residencial, comercial ou mista;
- tipo: apartamento, casa, sobrado, studio, kitnet, loft, cobertura, terreno, chácara,
  sítio, fazenda, sala comercial, loja, galpão ou prédio.

## Endereço

- logradouro, número e complemento;
- bairro, cidade, UF e CEP.

Coordenadas e regras de ocultação do número podem ser acrescentadas quando houver mapa e
publicação em portais. Não são necessárias para a primeira operação interna.

## Oferta

Venda:

- preço de venda obrigatório;
- aceita financiamento;
- aceita permuta.

Locação:

- aluguel mensal obrigatório;
- condomínio, IPTU e seguro-incêndio;
- garantias aceitas;
- aceita pet e mobiliado;
- prazo mínimo de locação, quando aplicável.

Quando o imóvel tem as duas finalidades, preço de venda e aluguel são obrigatórios.

## Características físicas

- área principal/construída e área do terreno;
- áreas útil e total nos detalhes, quando conhecidas;
- quartos, suítes, banheiros e vagas;
- andar, unidade e ano de construção, quando aplicáveis;
- lista de ambientes;
- lista de comodidades.

Ambientes e comodidades são listas extensíveis porque variam muito entre casa, apartamento,
terreno e imóvel comercial. Os campos mais usados na busca permanecem normalizados.

## Pessoas e origem

- proprietário/anunciante e telefone;
- fonte e URL de origem;
- fotos e metadados.

Matrícula, documentos pessoais, chaves e instruções de acesso não pertencem ao cadastro
comercial do MVP. Caso sejam adicionados futuramente, deverão ter acesso restrito e trilha de
auditoria.
