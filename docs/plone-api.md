# Cliente REST somente leitura

Base confirmada pelo responsável: https://www.gov.br/studyinbrazil/++api++.
Bearer válido funciona localmente em /pt-br, protegido. @govsite é público.
Estas confirmações vieram da verificação local anterior; esta integração
não realizou chamadas ao portal. Inventário autenticado roda localmente,
sem usar Codex Cloud como canal de autenticação.

## Contrato único

src/studybr/api/client.py é o único transporte. Settings lê PLONE_BASE_URL e
PLONE_TOKEN do ambiente, sem fallback de config.py ou arquivo.
request(method, path) rejeita qualquer método diferente de GET antes de I/O.
Não existem post, put, patch, delete, login, refresh ou operações de transição.

Requests preparados usam Accept: application/json, Bearer somente em memória,
TLS validado, timeout e limites de requisições/resposta (10 MiB por padrão).
Não seguem redirects, não enviam cookies, não consultam netrc ou proxies do
ambiente. Cookies recebidos são descartados antes e depois de cada GET.
Origem, esquema, porta e prefixo do portal são validados, assim como traversal,
userinfo, fragmentos, parâmetros de credenciais e destinos de login/lock/transição.

O primeiro 401 trava a instância globalmente, sem ler o corpo nem repetir.
Outros erros são tipados; status, Content-Type e type/message são sanitizados.
Exceções originais, headers de requisição e tokens não são registrados.
Sucesso admite JSON objeto ou lista de objetos; páginas/buscas exigem objeto.
HTML, JSON inválido e listas escalares interrompem o lote.

Conteúdo, @types, @types/<tipo observado>, @workflow e @translations aceitam GET.
A lista de transições retornada por @workflow é evidência, nunca executada.

## URLs e paginação

A CLI confirma explicitamente a base do ambiente com rest_path="".
O cliente genérico preserva o contrato Cloud: rest_path=None bloqueia get;
outros caminhos REST ou discover(candidates) exigem escolha explícita.
O runner não faz descoberta automática de endpoint nem renovação de token.

URLs absolutas do frontend permanecem exatamente como observadas, sem inserir
++api++. Uma resposta HTML nesse destino produz erro, sem fallback ou GET extra.
Paths relativos à API são resolvidos contra a base configurada.

Somente links batching.next observados são seguidos. Query relativa substitui a
query anterior. Paginação não pode abandonar a coleção; ciclos, repetição de
itens, alterações de items_total, limites e contagens incompletas não certificam
cobertura. HTTP 404 é distinto de falha de autenticação e reflete a visibilidade
desta conta, sem concluir ausência absoluta no portal.

## Pendências

Schemas Document/mídia, campos customizados, blocks, idioma, workflow e relações
de tradução atuais precisam ser observados no inventário local autorizado.
Capturas históricas não substituem GETs atuais. Este pacote não produz payload
de escrita, planner ou contrato funcional UGM antes dessas observações.
