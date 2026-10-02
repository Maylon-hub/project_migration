# Arquitetura integrada

`src/studybr` é o pacote instalável; os scripts da raiz não são importados pela
CLI. Importar o pacote não cria sessão autenticada, faz login ou executa I/O.

Camadas:

- `settings.py`: valida variáveis explícitas, HTTPS e timeout; token sem repr.
- `security.py`: redaction recursiva e logs JSON; mensagens e tracebacks são
  sanitizados antes da serialização, preservando o formato estruturado.
- `api/`: cliente somente GET, validação de origem/site, erros tipados e paginação.
- `models.py`: oito modelos de domínio, observações e conflitos.
- `importers/`: adaptadores de tabelas XLSX e CSV; compilação diagnóstica.
- reconciliation.py: autoridade única para nomes, aliases, slugs, decisões
  editoriais e conflitos; lê também evidências de comparação.
- inventory/: runner por lotes e retomada, snapshots locais e comparação
  portal × fontes, sem redefinir regras editoriais ou modelos do domínio.
- cli.py: diagnose offline e despacho explícito para inventory; ambos
  isolados da configuração operacional legada.
- `schemas/diagnostic.schema.json`: contrato versionado, gerado dos dataclasses.

Identidade da IES é independente de título e slug. Siglas recebem Unicode NFC,
trim, uppercase e underscore → hífen; agrupamentos são propostas de aliases,
com conflito pendente de aprovação. O identificador `br-<sigla normalizada>` é
provisório: mudança de sigla deverá manter binding/ID estável em etapa posterior.

Páginas têm chave semântica `home`, `about`, `campus_life` ou
`international_students`. Cada idioma tem atributos próprios. A origem
“Relações Internacionais” fica em `unassigned_editorial_rows`, sem alterar uma
página de estudantes internacionais. A reconciliação derivada associa explicitamente
Relações Internacionais à home, preservando a página independente.

Um campo recebe valor somente quando as observações concordam. Ausência versus
valor conhecido também gera divergência se ambos estiverem declarados. Nenhuma
fonte “vence” por ordem de importação. Caches presentes são somente evidência
diagnóstica; caches ausentes, com erro ou externos são igualmente reportados.

Ainda não existem planejamento de escrita, templates neutros, ownership por
bloco, idempotência de aplicação nem recuperação de escrita. O pacote não exporta
essas operações. A fundação define seus contratos sem sugerir que o portal tenha
sido inventariado.

O cliente é único: GET, sem redirects/cookies, mesma origem/site, limite de
resposta/requisições e latch global no primeiro 401. Só lotes solicitados e
links observados passam pelo escopo do runner. URLs absolutas do frontend
permanecem literais. Raw e sanitized ficam sob .local/ ignorada; fixtures mínimas
são versionáveis. Consulte plone-api.md e local-readonly-inventory.md.
