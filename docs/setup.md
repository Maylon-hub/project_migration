# Setup local

Python 3.11+ em ambiente isolado. requirements-foundation.lock contém dependências
da fundação e ferramentas; requirements.txt permanece do legado. Use os comandos
PowerShell do README. Em Linux, adapte para .local/validation/bin/python.

PLONE_BASE_URL e PLONE_TOKEN são necessários apenas no inventário. A biblioteca
não carrega .env nem consulta config.py. .env.example mantém valores vazios.
config/portal.json documenta a base confirmada e não armazena acesso.

O token deve ser digitado por Read-Host -AsSecureString e convertido somente
para a variável de ambiente da sessão, como no README. Nunca incluí-lo em
comandos literais, arquivos, Git, logs ou histórico de terminal. Ao terminar,
remover Env:PLONE_TOKEN. A execução autenticada é local, sem network secrets Cloud.

TLS permanece ativo; transporte ignora proxies/netrc/cookies do ambiente.
Cliente genérico usa timeout conexão/leitura (10,30); inventário usa (15,15)
por padrão. Origem e prefixo são conferidos antes de cada GET.

Verificação offline: scripts/run_offline_tests.py, ruff check,
ruff format --check e scripts/check_secrets.py. O runner remove credenciais
herdadas e bloqueia DNS/conexões antes da coleta. Leituras JSON usam UTF-8
explicitamente; -X utf8 também facilita o terminal Windows.

Para legado, instalar somente dependências adicionais de
requirements-legacy-validation.lock e usar --legacy-baseline. O baseline
esperado é 8 pass / 5 known fail. Não executar scripts de migração para validar.
O .venv antigo com referência inválida foi preservado; esta integração
usou .local/validation com Python 3.12.
