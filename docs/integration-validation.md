# Validação da integração local — 2026-10-02

Integração concluída em codex/local-readonly-inventory.
HEAD e main permanecem em 233ae49c25e44015e63387030bbfe6e203a8bc90.
Nenhum commit, push, mudança de branch ou chamada real ao Plone foi realizado.
Nenhuma credencial real do ambiente foi usada na validação.

## Arquitetura final

src/studybr é a implementação principal. ReadOnlyClient em api/client.py é
o único transporte da fundação. inventory/ contém CLI, lotes, snapshots e
comparação observacional. reconciliation.py mantém a autoridade Cloud;
seus adaptadores de evidência não resolvem aliases nem alteram fontes.
Modelos, importadores, schema, domínio e decisões editoriais permaneceram
byte a byte iguais à recuperação. A baseline de segredos também permaneceu igual.

A base REST confirmada pelo responsável é
https://www.gov.br/studyinbrazil/++api++. Bearer local funciona em /pt-br
protegido; @govsite público não valida autenticação. Esses fatos são contexto
verificado pelo operador, não resultados de GET desta integração.
O canal para o inventário é local; Codex Cloud não é canal de autenticação.

## Cliente e runner

- Somente GET. request rejeita explicitamente POST, PUT, PATCH, DELETE e outros
  verbos antes do transporte. O novo pacote não tem implementação de escrita.
- Redirects não são seguidos; cookies são descartados e não enviados.
  Não há netrc, proxies herdados ou fallback para config.py.
- TLS, timeout, orçamento de requisições e limite de resposta.
  Token somente do ambiente, sem repr, arquivo ou log de Authorization.
- Primeiro 401 bloqueia globalmente a instância; sem leitura de corpo ou retry.
- JSON objeto ou lista de objetos, incluindo @types; @workflow e @translations
  apenas GET. Transições são recusadas.
- URLs absolutas frontend são preservadas exatamente; origem/site externos e
  traversal são bloqueados. Paginação fica na coleção observada.
- Lotes roots → models → samples → schemas; sem crawl implícito.
  Homes PT-BR vêm de busca observada, nunca de paths inventados/CSV.
- Retomada explícita verifica novamente raízes e hashes das fontes/base.
  Somente agregados completos e autorizados são reutilizados.
  Reutilização é evidência anterior, não garantia de atualização remota.
- Raw imutável por resposta em .local/inventory/raw; estrutura sanitizada em
  .local/inventory/sanitized. Novas consultas não sobrescrevem raw.
  Destinos dentro do checkout devem ficar sob .local/, ignorada.
- ready_for_write permanece false. Slugs, nomes e conflitos não são corrigidos.

## Segurança

A Fase 0 removeu token/JWT literal de .codex/environments/environment.toml,
verificou TOML válido e ignorou esse arquivo local. Ele não aparece no conjunto
versionável e não deve ser incluído em commit. Nenhum segredo foi registrado
no relatório. As strings JWT sintéticas foram construídas em runtime; o guard
local duplicado foi eliminado em favor do guard Cloud.

Resultado do secret guard:
new_or_changed_sensitive_files=0; unchanged_historical_exceptions=4.
Os quatro HTMLs históricos foram comparados com seus hashes e com HEAD,
permaneceram intactos e não foram copiados ou incluídos como alterações.
Snapshots de rede reais não foram produzidos; fixtures usam portal.test/dados
fictícios. .env.example permanece com valores vazios.
O guard é baseado em padrões e fingerprints; não certifica todo formato de segredo.

## Cobertura e resultados

| Conjunto | Resultado | Preservação |
| --- | --- | --- |
| Cloud unit/contract | 75 pass | Todos os casos preservados |
| Local read-only | 52 pass | Mesmas finalidades e quantidade, imports integrados |
| Novos contratos de integração | 21 pass | Retomada, escopo, paginação, limites, cookies, metadata, destino privado |
| Suíte padrão integrada | 148 pass | 75 + 52 + 21; nenhuma deduplicação de casos |
| Legado separado | 8 pass / 5 known fail | As mesmas cinco falhas de URL; testes byte a byte originais |
| ruff check | pass | src, tests, scripts |
| ruff format --check | pass | 34 arquivos; legado preservado fora desse escopo |
| secret guard | pass | Zero segredo novo; quatro exceções históricas inalteradas |
| pip check | pass | Ambiente isolado consistente |
| git diff --check | pass | Sem erros de whitespace |

Adaptações dos 52 testes locais: imports apontam ao pacote principal;
ConfigurationError preserva o contrato Cloud; timeout agora é par conexão/leitura;
isolamento de cookies é conferido na sessão compartilhada; URLs frontend
permanecem literais conforme a instrução aprovada. O teste dessa URL foi
renomeado para representar o contrato atual. Nenhuma categoria de cobertura
ou teste local foi removido.

Duas leituras de JSON dos testes Cloud foram tornadas UTF-8 explícitas para
evitar divergências artificiais no Windows; asserts editoriais não mudaram.
As três cópias legadas foram comparadas byte a byte com HEAD antes da remoção
dos paths antigos. A execução mostra as cinco falhas reais; --legacy-baseline
retorna sucesso somente quando o conjunto exato de cinco falhas e oito
sucessos é reproduzido. Não usa xfail ou relaxamento de asserts.

A validação ocorreu em .local/validation com Python 3.12, dependências pinadas
da fundação e adicionais necessárias ao legado. O .venv antigo foi preservado.
Scripts/run_offline_tests.py remove credenciais herdadas e bloqueia sockets/DNS
antes de importar/coletar testes. CI foi preparado para Linux/Windows e para
baseline legado; CI remoto não foi executado nesta etapa.

## Duplicações removidas

O comportamento de inventory_readonly foi incorporado em studybr.inventory,
no cliente único e na reconciliação canônica. Foram removidos os sete módulos
da implementação paralela:
client.py, reconciliation.py, runner.py, security.py, snapshots.py,
__init__.py e __main__.py.

scripts/run_inventory_tests.py e scripts/check_inventory_secrets.py foram
removidos em favor de run_offline_tests.py e check_secrets.py.
Não permanecem cópias dos três testes originais nos paths antigos de tests/.
Scripts operacionais legados na raiz continuam preservados e isolados;
seus métodos de escrita foram apenas simulados nos testes legados, sem rede.

## Recuperação e arquivos

Antes da integração, os 55 arquivos recuperados coincidiram com o manifesto
e o ZIP fornecido. O manifesto original foi preservado como evidência histórica;
não corresponde aos hashes finais dos arquivos adaptados nesta integração.

32 arquivos Cloud permanecem exatamente iguais; 23 foram adaptados.

Arquivos Cloud adaptados nesta integração:

- .github/workflows/offline.yml
- .gitignore
- README.md
- config/portal.json
- docs/architecture.md
- docs/handover.md
- docs/metadata-rules.md
- docs/migration-workflow.md
- docs/plone-api.md
- docs/readonly-reconciliation.md
- docs/setup.md
- pyproject.toml
- scripts/check_secrets.py
- scripts/run_offline_tests.py
- src/studybr/api/client.py
- src/studybr/api/errors.py
- src/studybr/api/urls.py
- src/studybr/cli.py
- src/studybr/reconciliation.py
- src/studybr/security.py
- src/studybr/settings.py
- tests/contract/test_dataset_schema.py
- tests/unit/test_reconciliation.py

Arquivos rastreados alterados em relação a HEAD:

- .gitignore
- README.md
- config.py

Paths originais removidos do checkout (preservados em legacy/tests):

- tests/test_api_client.py
- tests/test_migrate_ies.py
- tests/test_migration.py

Arquivos novos/versionáveis presentes, incluindo recuperação e integração (64):

- .env.example
- .github/workflows/offline.yml
- .secrets-baseline.json
- config/domain.json
- config/editorial-decisions.json
- config/portal.json
- docs/adding-a-language.md
- docs/adding-institutions.md
- docs/architecture.md
- docs/handover.md
- docs/integration-validation.md
- docs/local-readonly-inventory.md
- docs/metadata-rules.md
- docs/migration-workflow.md
- docs/plone-api.md
- docs/readonly-reconciliation.md
- docs/setup.md
- legacy/README-trensurb.md
- legacy/README.md
- legacy/tests/conftest.py
- legacy/tests/test_api_client.py
- legacy/tests/test_migrate_ies.py
- legacy/tests/test_migration.py
- pyproject.toml
- requirements-foundation.lock
- requirements-legacy-validation.lock
- reviewed-files-manifest.json
- schemas/diagnostic.schema.json
- scripts/check_secrets.py
- scripts/generate_schema.py
- scripts/reconcile_local_evidence.py
- scripts/run_offline_tests.py
- src/studybr/__init__.py
- src/studybr/api/__init__.py
- src/studybr/api/client.py
- src/studybr/api/errors.py
- src/studybr/api/urls.py
- src/studybr/cli.py
- src/studybr/importers/__init__.py
- src/studybr/importers/diagnostic.py
- src/studybr/importers/workbooks.py
- src/studybr/inventory/__init__.py
- src/studybr/inventory/cli.py
- src/studybr/inventory/comparison.py
- src/studybr/inventory/runner.py
- src/studybr/inventory/snapshots.py
- src/studybr/models.py
- src/studybr/reconciliation.py
- src/studybr/security.py
- src/studybr/settings.py
- tests/conftest.py
- tests/contract/test_dataset_schema.py
- tests/contract/test_readonly_client.py
- tests/fixtures/README.md
- tests/fixtures/__init__.py
- tests/fixtures/factories.py
- tests/fixtures/historical_ufscar.json
- tests/fixtures/inventory-page.json
- tests/integration/test_inventory_integration.py
- tests/test_readonly_inventory.py
- tests/unit/test_importers.py
- tests/unit/test_reconciliation.py
- tests/unit/test_secret_guard.py
- tests/unit/test_security_models.py

Configuração local alterada, ignorada e excluída do conjunto de commit:
.codex/environments/environment.toml. Ambiente/dependências em .local/ também
não são versionáveis. desktop.ini do Windows/Drive foi ignorado.

## Pendências humanas e próximo passo

- Aprovação do commit do conjunto integrado. Nenhum staging/commit/push foi feito.
- Revogação/rotação externa das credenciais anteriormente presentes em material
  histórico ou configuração local; não reescrever histórico nesta etapa.
- Inventário local real por lotes e contrato funcional UGM EN/ES.
- Bindings ambíguos, aliases CEFET_MG/CEFET-MG, slugs, títulos completos,
  caches de fórmulas e interpretação dos campos/blocks/workflow atuais.
  Nenhuma dessas divergências foi resolvida automaticamente.

O conjunto integrado está seguro para revisão e commit conforme este escopo:
não incluir a configuração local sensível, raw, ambiente ou mudanças nos HTMLs.
Os HTMLs permanecem material histórico conhecido, fora das alterações.
Nenhuma aprovação de escrita no Plone decorre deste estado.

Comandos PowerShell exatos de token somente em sessão e inventário roots
estão no README. Endpoints e expansão explícita estão em
local-readonly-inventory.md. Após concluir, aguardar aprovação antes de commit.
