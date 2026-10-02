# StudyBR — fundação i18n e inventário REST somente leitura

Base Python para diagnosticar fontes e inventariar o portal Study in Brazil
(Plone 6/gov.br). A implementação principal está em src/studybr: diagnóstico
offline, reconciliação editorial e um único cliente HTTP GET. Nenhuma operação
de escrita é oferecida pelo pacote.

A base confirmada é https://www.gov.br/studyinbrazil/++api++.
Conforme verificação local informada pelo responsável, Bearer válido funciona
em /pt-br (protegido). @govsite é público e não valida autenticação.
O inventário deve rodar no computador local; Codex Cloud não deve ser usado
como canal de autenticação. Esta integração usou apenas mocks e nenhuma chamada real.

## Instalação e verificações

Python 3.11+. Exemplo PowerShell com ambiente isolado, sem alterar o .venv antigo:

~~~powershell
py -3.12 -m venv .local/validation
.local/validation/Scripts/python.exe -m pip install -r requirements-foundation.lock
.local/validation/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
.local/validation/Scripts/python.exe -X utf8 -B scripts/run_offline_tests.py -p no:cacheprovider
.local/validation/Scripts/python.exe -m ruff check src tests scripts
.local/validation/Scripts/python.exe -m ruff format --check src tests scripts
.local/validation/Scripts/python.exe -X utf8 -B scripts/check_secrets.py
~~~

A suíte integrada preserva os 75 casos Cloud e os 52 locais, além de 21 novos
casos de integração: 148 sucessos. Os testes originais estão em legacy/tests/
sem alteração de comportamento. Para conferir 8 sucessos e 5 falhas conhecidas:

~~~powershell
.local/validation/Scripts/python.exe -m pip install -r requirements-legacy-validation.lock
.local/validation/Scripts/python.exe -X utf8 -B scripts/run_offline_tests.py --legacy-baseline
~~~

O runner remove credenciais herdadas antes da coleta e bloqueia DNS/conexões.
Ele confere o baseline legado sem transformar falhas em sucessos ou xfail.
Instalação de dependências pode acessar o índice de pacotes.

## Inventário local por lotes

Exportar token com entrada oculta, somente para a sessão PowerShell atual:

~~~powershell
$env:PLONE_BASE_URL = 'https://www.gov.br/studyinbrazil/++api++'
$studybrCredential = Read-Host 'PLONE_TOKEN' -AsSecureString
$env:PLONE_TOKEN = [System.Net.NetworkCredential]::new('', $studybrCredential).Password
Remove-Variable studybrCredential
.local/validation/Scripts/studybr.exe inventory --stage roots
# Após revisar o lote anterior, escolher explicitamente o próximo:
# .local/validation/Scripts/studybr.exe inventory --stage models --resume '<run-id>'
# Ao terminar:
Remove-Item Env:PLONE_TOKEN
~~~

Os comandos de inventário fazem GETs reais quando executados pelo operador;
não foram executados nesta integração. O padrão consulta /pt-br, /en, /es
e sua paginação. Etapas models, samples e schemas ampliam o escopo explicitamente.
Cada execução verifica as raízes novamente e para globalmente no primeiro 401.
Veja [endpoints, snapshots e retomada](docs/local-readonly-inventory.md).

## Diagnóstico das fontes

Fontes privadas devem ficar fora do Git, por exemplo em sources/ (ignorado).

~~~powershell
studybr diagnose --creation 'sources/Criação_com_Script_via_TI.xlsx' --production 'sources/Produção Portal Br.xlsx' --base-url https://www.gov.br/studyinbrazil --domain-config config/domain.json --home-csv studyinbr/lista_ies_completa.csv --subpage-csv studyinbr/subpaginas_ies_completo.csv --media-csv 'docs/Produção Portal Br(Fotos_metadados).csv' --diagram-json diagramacao/diagramacao_10_ies.json --output-dir artifacts/diagnostic
~~~

O diagnóstico não faz requisições. Gera dataset e resumo determinísticos,
proveniência e conflitos. Saída 2 indica pendências; 1, erro; 0, ausência de
conflitos detectados. Nenhum código autoriza escrita.
Caches de fórmulas não são certificados por openpyxl. Alternativas discordantes
ficam em candidates; nenhum arquivo vence pela ordem de importação.

A reconciliação canônica em studybr.reconciliation preserva nomes EN/ES aprovados
na planilha. O overlay associa Relações Internacionais à home, mantendo Estudantes
Internacionais como página distinta e todas as ocorrências originais.
Aliases, slugs e outras divergências continuam pendentes de decisão humana.

## Segurança e histórico

PLONE_BASE_URL e PLONE_TOKEN vêm apenas do ambiente, sem fallback do legado.
O pacote não carrega .env; .env.example tem valores vazios. .local/, snapshots
raw e .codex/environments/environment.toml são privados e ignorados. A configuração
local do Codex ficou sem credencial literal e não deve ser incluída em commit.
Não imprimir tokens, Authorization ou cookies.

As quatro capturas históricas com JWT foram preservadas, sem cópia ou alteração.
O guard verifica seus hashes exatos e rejeita segredos novos; a baseline não foi
ampliada. A retirada do literal de config.py não reescreve o histórico:
revogação/rotação externa permanece pendente. Scripts operacionais da raiz
possuem escrita legada e ficam isolados do novo fluxo.

A recuperação Cloud veio de aabb8bec48ff0bcbd9c0fa9a2c10383cb5bd9af8.
O manifesto de 55 arquivos permanece evidência da recuperação original;
não é um manifesto do checkout integrado atual.

## Documentação

- [Arquitetura](docs/architecture.md) e [setup](docs/setup.md).
- [Contrato REST](docs/plone-api.md) e [inventário local](docs/local-readonly-inventory.md).
- [Reconciliação](docs/readonly-reconciliation.md) e [validação integrada](docs/integration-validation.md).
- [Adicionar idioma](docs/adding-a-language.md) e [IES](docs/adding-institutions.md).
- [Metadados](docs/metadata-rules.md), [fluxo](docs/migration-workflow.md) e [handover](docs/handover.md).
- [Limites do legado](legacy/README.md) e [README original Trensurb](legacy/README-trensurb.md).
