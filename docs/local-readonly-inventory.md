# Inventário REST local — somente leitura

O inventário está em studybr.inventory e usa exclusivamente
studybr.api.client.ReadOnlyClient. É isolado de api_client.py: não importa `config.py`, não faz login/renew e não oferece CRUD
ou transições. O único método HTTP aceito pelo transport é `GET`.

## Histórico anterior à recuperação Cloud

A inspeção começou no commit `233ae49`, branch `main`, sem alterações rastreadas
e com `.codex/` não rastreado. A implementação está na branch
`codex/local-readonly-inventory`, sem commit, merge ou push.

Os relatórios exportados da cloud descrevem uma fundação `src/studybr/`, uma
branch `refactor-i18n-foundation` e 75 testes. Esses arquivos/branch não estavam
no checkout local. Os relatórios são contexto, não prova de que aquele código
esteja instalado aqui. Nenhuma fonte, template, CSV ou captura foi reorganizada.
O fallback literal de token foi removido de `config.py`; o histórico Git não
foi reescrito. Scripts legados ainda possuem escrita e não integram este fluxo.

As confirmações de HTTP 200 para `/pt-br` e de endpoint são informações fornecidas
pelo usuário. Esta implementação ainda não produziu snapshots reais do portal.
`/@govsite` não é usado para testar autenticação.

## Estado integrado

Os 55 hashes do manifesto foram conferidos antes da integração. Modelos,
importadores, schemas e regras editoriais Cloud coexistem com runner por lotes,
snapshots e comparação observacional no pacote principal.
Não permanece implementação paralela inventory_readonly. A base REST confirmada
é https://www.gov.br/studyinbrazil/++api++; /pt-br protegido funciona com Bearer
local válido, conforme informação do responsável. @govsite é público.
Codex Cloud não deve ser usado como canal de autenticação do inventário.
Nesta integração não houve GET real, uso de token real, commit ou push.

## Ambiente e token na sessão PowerShell

Use o ambiente isolado e a instalação do pacote descritos no README/setup.
O .venv antigo foi preservado; esta integração usa .local/validation e Python 3.12.

```powershell
Set-Location -LiteralPath 'D:\GitHub\project_migration'
$env:PLONE_BASE_URL = 'https://www.gov.br/studyinbrazil/++api++'
$inventorySecureToken = Read-Host 'PLONE_TOKEN (somente o JWT)' -AsSecureString
$inventoryTokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($inventorySecureToken)
try {
    $env:PLONE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($inventoryTokenPointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($inventoryTokenPointer)
    $inventorySecureToken.Dispose()
    Remove-Variable inventorySecureToken, inventoryTokenPointer
}
```

O valor é digitado de forma oculta, fica no ambiente do processo PowerShell e é
herdado somente pelos processos filhos. Não se usa `setx`, `.env`, cookie,
argumento de linha de comando, header impresso ou arquivo de credencial.
Definir a variável em um PowerShell externo não a injeta automaticamente no
executor já aberto do Codex: execute o inventário nessa mesma sessão.

Depois da execução, remova o token da sessão:

```powershell
Remove-Item Env:PLONE_TOKEN
```

## Validação offline e lotes

```powershell
python -X utf8 -B scripts/run_offline_tests.py -p no:cacheprovider
python -X utf8 -B scripts/check_secrets.py
studybr inventory --help
studybr inventory --stage roots
```

O primeiro comando bloqueia DNS/conexões antes de coletar os testes e usa
somente credenciais/respostas fictícias. `--help` não precisa de credenciais.
A CLI sem variáveis retorna erro de configuração antes de qualquer GET ou arquivo.

Execute um lote por vez. As etapas posteriores repetem as três raízes para
verificar novamente o acesso; não retomam silenciosamente uma autenticação antiga.

| Etapa | GETs, relativos à base `++api++` |
| --- | --- |
| `roots` (padrão) | `/pt-br`, `/en`, `/es`; links `batching.next` quando presentes |
| `models` | raízes, `/en/higher-education-institutions/north-region/acre/ugm`, `/es/instituciones-de-educacion-superior/region-norte/acre/ugm` |
| `samples` | anteriores, filhos imediatos observados da UGM; `/pt-br/@search?SearchableText=<sigla>&b_size=50` para UFAC, UFSCar, CEFET-MG, UFAPE e UFSC; homes/filhos descobertos |
| `schemas` | anteriores, `/@types`, `/@types/<tipo observado>`, `<página observada>/@workflow`, `<página observada>/@translations` |

Depois de conferir cada lote anterior:

```powershell
studybr inventory --stage models
studybr inventory --stage samples
studybr inventory --stage schemas
```

Nenhuma dessas etapas faz crawl completo das árvores. Não existe chamada a
`/@login`, `@login-renew`, transições ou downloads de mídia. Se uma raiz retorna
404, os lotes posteriores não começam. Outros erros interrompem o lote; 401
interrompe imediatamente o cliente e bloqueia qualquer GET subsequente, sem retry.
Os modelos opcionais que retornem 404 são registrados como ausentes/inacessíveis
para aquela conta, nunca como autorização para criar conteúdo.

As buscas só produzem destinos a partir de `@id` observado no portal. Mais de um
candidato, ou ausência de candidato reconhecível, exige vínculo humano; o CSV
nunca fornece um path de requisição. Um slug longo pode impedir descoberta
automática: nesse caso o código registra pendência e não adivinha um destino.

## Transporte e cobertura

- HTTPS com verificação TLS, mesma origem e prefixo do portal; rejeição de
  travessia de diretórios, credenciais em URLs e endpoints de login/transição.
- Redirects sempre bloqueados; cookies não enviados. A sessão é reutilizada,
  mas cada GET prepara uma Request sem cookies/auth herdados; a jar é esvaziada
  antes e depois do transporte. Netrc e proxies de
  ambiente não são usados.
- Timeout de conexão/leitura de 15 segundos, limite de 100 requisições,
  20 batches por coleção e 30 filhos por home. `--timeout`, `--max-requests`,
  `--max-pages` e `--max-children` ajustam os limites explicitamente.
- Resposta limitada a 10 MiB. JSON de páginas/buscas deve ser objeto; `@types`
  também admite lista e schemas admitem `application/json+schema`.
- Paginação não deduz `b_start`: segue somente links observados e valida todos
  contra origem/prefixo. Ciclos, limites ou divergência de `items_total` são
  erros de cobertura parcial. Nenhuma contagem parcial é anunciada como total.
- Erros de transporte omitem exceções/headers originais. Respostas de erro JSON
  preservam apenas `type/message` sanitizados e limitados, status e Content-Type.
  Corpos HTML não são gravados. O código não registra headers de requisição.

O timeout do Requests limita conexão e intervalos de leitura, não a duração
total de um crawl. O inventário mede a visibilidade desta conta e deste lote,
não a completude absoluta do portal.

## Snapshots locais

```text
.local/inventory/raw/<run-id>/<hash-da-url>.json
.local/inventory/sanitized/<run-id>/<hash-da-url>.json
.local/inventory/sanitized/<run-id>/<hash-da-url>-aggregate.json
.local/inventory/sanitized/<run-id>/summary.json
```

Dentro do checkout, --output-dir aceita somente caminhos sob .local/; diretórios
fora do checkout podem ser escolhidos explicitamente para armazenamento privado.
Toda `.local/` está ignorada no Git, inclusive snapshots sanitizados ainda não
revisados. Os bodies raw são JSONs completos para inspeção privada local,
com remoção defensiva de campos de autenticação e strings contendo credenciais.
Não são capturas de headers, cookies ou tráfego. Não são publicados/versionados.
O token usado na conexão é removido antes de a resposta chegar ao armazenamento.

Snapshots estruturados preservam metadados observados, slugs, filhos,
`blocks_layout`, tipos e ordem de blocks. Modelos/filhos de IES também preservam
a estrutura recursiva dos blocks: parágrafos/textos customizados são representados
por tipo, comprimento e vazio/preenchido; títulos curtos e links estruturais
são mantidos. Campos ausentes não são convertidos para string vazia.
Agregados são derivados das respostas paginadas e não sobrescrevem batches raw.
Novas consultas da mesma URL recebem sufixo sequencial, preservando os raw anteriores.

`summary.json` registra requisições, pendências, conflitos, erros, páginas
observadas e `ready_for_write=false`. `complete` se refere ao lote solicitado,
não significa ausência de conflitos nem autorização editorial.

## Reconciliação sem correção

Os CSVs atuais são evidências de comparação PT-BR. O CSV usa `CEFET_MG`, enquanto
o pedido e o overlay aprovado usam `CEFET-MG`: o vínculo não é resolvido
automaticamente. Slugs com underscore/hífen permanecem literais.

Para carregar os 142 nomes literais aprovados do overlay exportado:

```powershell
studybr inventory --stage samples --approved-resolutions 'H:\Meu Drive\Shared Fold UFSCar\Bolsas\Portal StudyBr Internacionalização - PIDICT\Dev\conflicts-semantic.json' --approved-workbook 'H:\Meu Drive\Shared Fold UFSCar\Bolsas\Portal StudyBr Internacionalização - PIDICT\Produção Portal Br.xlsx'
```

Esse parâmetro usa apenas resoluções `approved_institutional_translations` com
`translated_name` e `resolved_in_overlay`, mantendo referências de origem.
Não importa os demais conflitos, não altera o dataset e não traduz nomes.
Homes EN/ES das amostras PT-BR não são coletadas neste lote: nomes são registrados
como referências pendentes de comparação, sem construir títulos por conta própria.
O overlay não substitui silenciosamente uma revisão diferente da planilha.
Com `--approved-workbook`, o SHA-256 atual deve ser exatamente o da origem
registrada no overlay; divergência interrompe antes de qualquer GET. Os hashes
das fontes são registrados no sumário. Sem essa opção, o sumário deixa explícito
que a planilha atual não foi conferida. Esta execução conferiu a coincidência do
hash do XLSX original de produção com as 142 referências aprovadas exportadas.

Para comparar expectativas explicitamente aprovadas de páginas já coletadas,
coloque um JSON privado em `.local/inventory/expectations.json` e passe
`--expectations .local/inventory/expectations.json`. Exemplo **fictício de formato**:

```json
{
  "/en/higher-education-institutions/north-region/acre/ugm": {
    "fields": {"language": "en"}
  }
}
```

Não se pressupõe tipo, workflow, nomes, slugs de filhos ou blocks da UGM antes
do GET. Expectativas adicionais usam `fields`, `block_types` e `children`.
As nove categorias são: `slug conflict`, `missing page`, `unexpected page`,
`structure mismatch`, `block mismatch`, `language mismatch`, `title/name mismatch`,
`workflow mismatch`, `metadata mismatch`. Comparação EN/ES não exige UUIDs iguais.
Este mecanismo registra divergências e conserva os dados observados; não gera
payloads, não planeja writes e não aplica correções.

Permanecem pendentes a comparação completa com os XLSX originais/certificação
de fórmulas, aliases, títulos, modelo funcional de filhos EN/ES e interpretação
de blocks customizados. A seção Relações Internacionais pertence à home e
Estudantes Internacionais continua distinta; nenhum novo path é inferido dessa
decisão conceitual.

## Códigos de saída

- `0`: lote coletado sem conflitos ou pendências registrados.
- `2`: dados diagnósticos com conflitos/pendências ou lote incompleto sem erro fatal.
- `1`: configuração, entrada, transporte, autenticação ou cobertura com erro.

Nenhum código de saída autoriza escrita. Revisão humana continua necessária.

## Retomada incremental

Escolha explicitamente o run-id da pasta sanitizada do lote anterior:

~~~powershell
studybr inventory --stage models --resume '<run-id>'
~~~

Todas as execuções verificam novamente /pt-br, /en e /es. Agregados completos
salvos são reutilizados somente quando o novo lote autoriza sua página.
Snapshots antigos não ampliam o escopo nem geram requisições implícitas.
Depois de um 401, a instância antiga continua bloqueada; a retomada cria uma nova
e só usa o cache após as raízes responderem. A base e os hashes das fontes devem
ser idênticos, incluindo expectativas/overlay/planilha quando fornecidos.
Agregados incompletos ou incoerentes interrompem a retomada.

O resumo registra previous_batches e reused_pages. Reutilização é comparação
contra evidência anterior, não prova de que a página continua igual no portal.
Para atualizar todo o lote, omita --resume e crie um run-id novo.

## Verificação desta integração

148 testes offline passaram: 75 Cloud, 52 locais preservados e 21 adicionais.
O legado manteve 8 pass / 5 known fail, sem alterar asserts.
Lint, formatter e secret guard fazem parte da validação; detalhes e comandos
estão em [integration-validation.md](integration-validation.md).
Não houve chamadas reais ao Plone, token real usado, workflow, commit ou push.

A configuração local .codex/environments/environment.toml ficou sem credencial
literal e ignorada. Os quatro HTMLs históricos permaneceram intactos e a
baseline de segredos não foi ampliada. Credenciais anteriormente expostas em
material histórico/configuração local precisam de revogação/rotação externa;
essa pendência não se resolve removendo o literal da árvore atual.

## Referências técnicas

- [Requests: preparação de requests, cookies e TLS](https://requests.readthedocs.io/en/latest/user/advanced/).
- [Plone: tipos/schemas](https://6.docs.plone.org/plone.restapi/docs/source/endpoints/types.html).
- [Plone: paginação](https://6.docs.plone.org/plone.restapi/docs/source/usage/batching.html).
- [Plone: busca](https://6.docs.plone.org/plone.restapi/docs/source/endpoints/searching.html).

Essas referências orientam o contrato do cliente; a presença desses serviços
no gov.br só será estabelecida pelos GETs autorizados.
