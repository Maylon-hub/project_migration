# Fluxo atual e etapas futuras

Esta versão executa apenas:

1. Ler fontes locais das tabelas explícitas.
2. Normalizar sem escolher candidatos discordantes.
3. Emitir dataset diagnóstico, proveniência, conflitos e resumo determinísticos.
4. Executar testes/lint/secret guard sem conexão com o portal.
5. Sob seleção explícita do operador, inventariar por lotes GET locais,
   persistir snapshots privados e comparar observações sem corrigir conteúdo.

O dataset possui `diagnostic_only=true`. O resumo possui `ready_for_write=false`.
Conflitos fazem a CLI sair com código 2. Isso é comportamento esperado e não
significa que nenhum artefato foi produzido. Saída 0 também não autoriza escrita.

Em etapa posterior, sob nova instrução: concluir contrato observado, aprovação das
fontes, templates neutros, ownership, planner/diff, dry-run de operações e piloto
controlado com pós-validação. Create/update/workflow não existem no novo pacote.

Aliases/slugs não são automaticamente corrigidos, páginas não são criadas,
estado editorial não dispara workflow e nomes traduzidos não são aprovados pela
importação. Os relatórios históricos permanecem evidência, não estado remoto.

Para comparar diagnósticos, use o hash do dataset em `summary.json`; não há timestamp
ou caminho absoluto do ambiente no conteúdo. A ordem de arquivos no disco não
define autoridade. Conserve fontes originais e artefatos fora do Git quando privados.
