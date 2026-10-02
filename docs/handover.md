# Handover da fundação integrada

Responsáveis editoriais, armazenamento definitivo e permissões ainda devem ser
formalmente definidos. A documentação não contém valores de acesso.

Rotina reproduzível:

1. Conferir branch `codex/local-readonly-inventory` e alterações locais.
2. Preparar ambiente com o lock da fundação e instalar pacote.
3. Executar testes/lint/secret guard.
4. Executar `studybr diagnose` com os dois XLSX e exportações explicitamente
   selecionadas; conferir código de saída e os dois artefatos.
5. Revisar conflitos por campo com responsáveis; registrar decisão fora do
   diagnóstico antes de construir um conjunto aprovado em etapa posterior.

Não presumir autoridade do último arquivo lido. Registrar hash/versão das fontes
e garantir backup das planilhas e documentos. Não armazenar o dataset privado em
Git. Fixtures usam dados sintéticos e apenas campos mínimos do conteúdo histórico.

Bloqueantes: inventário PT/EN/ES e contrato funcional UGM; slugs
CEFET/UFSCar/Vida e aliases; fonte canônica
por campo; certificação dos caches/external links; política manual/gerenciada;
schemas/mídias/custom blocks; revogação das credenciais históricas e tratamento
posterior do histórico público. Não há aprovação para merge ou escrita no portal.

O código legado continua na raiz por dependências de caminho; testes legados
estão em `legacy/tests/` e README antigo em `legacy/README-trensurb.md`.
Preservação dessas evidências não autoriza executá-las nem reutilizar credenciais.

O secret guard conhece quatro capturas históricas por hash integral. Alteração
nessas exceções falha. Não expandir a baseline para fazer um vazamento novo passar.
O guard é uma proteção adicional por padrões e fingerprints, não prova de ausência
de todo formato possível de segredo (especialmente imagens/binários).

A base REST e o acesso local Bearer a /pt-br foram confirmados pelo responsável.
Nomes EN/ES aprovados e Relações Internacionais na home são decisões fixadas.
Use inventário por lotes localmente, após revisão dos testes; @govsite público
não prova autenticação e Codex Cloud não deve ser o canal de acesso.
Não há aprovação para commit/push nesta execução: aguardar aprovação final.
