# Metadados e prioridade das fontes

Nomes institucionais EN/ES seguem a tradução literal aprovada em Tabela19,
conforme config/editorial-decisions.json e a reconciliação canônica.
Não são traduzidos automaticamente. Essa aprovação não resolve fórmulas
incertas, aliases ou composição de títulos completos de página.
As demais fontes/campos continuam sujeitos a reconciliação e decisão humana:

| Informação | Fonte examinada |
| --- | --- |
| Nomes/traduções | Produção: `siglas,nomes pt en es` / `Tabela19` |
| Destinos/taxonomia | Criação: seis tabelas de home/subpáginas |
| Estado editorial | Produção: `IES` / `Tabela1`, somente sua tabela principal |
| Mídia | Produção: `Fotos_metadados` / `Tabela113` |
| Enriquecimento/histórico | CSVs e JSON de diagramação; comparar, não sobrescrever |

O importer também confere as duas tabelas compiladas da criação como evidência
derivada. Não lê dashboards ou abas `old` como cadastro.

`title`, `nav_title`, `description`, `subjects`, idioma, slug e container são
atributos diferentes. Falta de descrição ou conflito permanece nulo. Tags são
normalizadas como conjunto ordenado, sem pressupor vocabulário remoto. Regra de
título EN/ES preservando nome PT continua uma decisão pendente.

Fotos: título, descrição, legenda e alt são localizados por idioma. Logo e banners
têm papel explícito pelo sufixo da fonte; typo de nome de arquivo é conflito de
alias. Não inferir metadados da sigla. Status editorial não é workflow do Plone.

Fórmulas: `not_applicable`, `missing`, `error`, `external_dependency`, `unverified`.
`openpyxl` não recalcula nem certifica caches; toda fórmula é reportada como
pendência. Fórmula, célula, tabela, hash do arquivo e valor lido ficam registrados.

Conflitos são emitidos para nomes, slugs, caminhos, aliases, metadados, caches,
destinos duplicados, categorias desconhecidas, identidade e divergências XLSX/CSV.
