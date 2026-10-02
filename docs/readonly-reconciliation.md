# Reconciliação canônica e histórico da execução Cloud

O relato abaixo preserva o contexto histórico Cloud anterior à recuperação.
Na etapa atual, a base REST e o acesso local Bearer foram confirmados pelo
responsável; esta integração usou somente mocks e não inventariou o portal.
A reconciliação Cloud continua como autoridade editorial em studybr.reconciliation.
A comparação em studybr.inventory.comparison é apenas observacional.

Este documento histórico descreve apenas fatos verificados nas fontes locais e decisões
editoriais explicitamente autorizadas pelo usuário. Não documenta o contrato REST
real. Não houve descoberta autenticada, renovação ou inventário nesta execução:
as duas variáveis esperadas não chegaram ao executor vinculado à conversa.

`docs/plone-api.md`, `docs/architecture.md`, `docs/metadata-rules.md` e
`docs/migration-workflow.md` não receberam novos fatos sobre o portal. A exigência
desta fase é atualizar esses contratos somente com observações confirmadas por GET.

## Decisões aplicadas no modelo derivado

`config/editorial-decisions.json` registra a autoridade e o escopo das instruções:

- Nomes EN/ES: valores literais únicos e não nulos de `siglas,nomes pt en es`,
  `Tabela19`, colunas `Inglês` e `Espanhol`. Falta, divergência interna ou fórmula
  não certificada continuam conflito; não existe tradução automática.
- “Relações Internacionais”: componente `international_relations` da `home`.
  Resolver o vínculo não resolve seus caches, textos, contatos ou status.
- `international_students`: página independente. Os status da seção internacional
  não são transferidos para essa página.
- Lista de IES protegidas: somente fluxo histórico PT-BR; não aplicar ao novo fluxo.
- Divergência de slug remoto: parar a página/IES e exigir decisão humana. A regra
  está registrada, mas nenhum slug remoto foi examinado nesta execução.

O dataset diagnóstico original é imutável. A camada derivada contém resoluções
locais e referências para cada ocorrência original, sem apagar, editar ou contar
como “limpos” os conflitos anteriores. Não constitui um plano de escrita.

## Agrupamento

`src/studybr/reconciliation.py` agrupa por instituição, idioma, identidade semântica
da página, campo e, para mídia, identificação do asset. O contexto vem das tabelas
explícitas e da proveniência estabelecida pelo importador. Não se escolhe uma IES
ou página por semelhança de slug. Evidências sem identidade segura permanecem D.

Classes: A informativo; B regra autorizada; C decisão humana; D bloqueante técnico.
Um grupo pode conter várias causas: cada ocorrência tem referência e classe
próprias; a classe do grupo assume a maior gravidade. Problemas de cache não são
absorvidos por uma resolução editorial. Marcadores de metadados do fluxo histórico
podem ser A; dados técnicos não certificados permanecem D.

`source_references` retém arquivo por hash, tabela, célula e estado do cache,
sem reproduzir valores, fórmulas, contatos ou nomes de responsáveis editoriais.
As resoluções institucionais contêm somente os nomes públicos necessários.

## Executar sem rede

Instalar a fundação conforme setup. O script bloqueia sockets e DNS; exige hashes
dos XLSX e da configuração idênticos aos registrados no dataset de entrada.

```sh
python scripts/reconcile_local_evidence.py \
  --dataset artifacts/diagnostic/dataset.json \
  --creation 'sources/Criação_com_Script_via_TI.xlsx' \
  --production 'sources/Produção Portal Br.xlsx' \
  --output-dir artifacts/remote-inventory/local-pending
```

Saída 2 é esperada: a reconciliação local não confirma o contrato remoto. Saída 1
indica erro de fonte/configuração. Não há token, sessão, cliente HTTP ou operação
de conteúdo neste script. Não há código de sucesso que autorize escrita.

Arquivos de saída, ignorados pelo Git:

- `conflicts-semantic.json`: evidências agrupadas e resoluções locais.
- `conflicts-human-review.csv`: grupos C e D, com escopo local explícito.
- `reconciliation-local-summary.json`: contagens, hashes e estado não verificado.

Não tratar esses arquivos como inventário remoto. A execução desta fase também
registra `phase-status.json` para distinguir falta de configuração de 401, 403,
404, HTML inesperado, JSON inválido ou qualquer resposta HTTP efetiva.

## Próxima execução local autenticada

A base é https://www.gov.br/studyinbrazil/++api++ e /pt-br protegido funciona
localmente com Bearer válido, conforme confirmação do responsável. Não há
necessidade de redescoberta ou teste de renovação nesta etapa. @govsite é
público; Codex Cloud não deve ser usado como canal de autenticação.

Executar explicitamente roots, models, samples e schemas conforme
local-readonly-inventory.md. Buscar paths reais das cinco IES, comparar
UGM EN/ES, campos, blocks, workflow e traduções apenas com GET.
Não preencher o contrato funcional com valores presumidos ou capturas antigas.
As regras editoriais são as mesmas deste documento e config/editorial-decisions.json.
Nenhum conflito é corrigido automaticamente e ready_for_write permanece false.
