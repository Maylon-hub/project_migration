# Adicionar um idioma

Idiomas são dados, não condicionais de operações. O importador atual suporta
explicitamente as três estruturas das planilhas recebidas; uma nova estrutura de
fonte exige novo adaptador `TableSpec` e testes, sem assumir primeira aba.

Para francês ou outro idioma:

1. Definir código editorial, código aceito pelo Plone e raiz confirmada em leitura.
2. Estender `config/domain.json` e o contrato da fonte/adaptador correspondente.
3. Cadastrar nomes/traduções aprovados, títulos, navegação, slugs e taxonomia.
4. Fornecer conteúdo e metadados de mídia aprovados; não copiar PT automaticamente.
5. Testar importação, destino único, Unicode, conflitos e determinismo.

O cliente GET não contém caso especial PT/EN/ES nem injeta código de idioma.
O cadastro normalizado mantém atributos de cada idioma. Formato de URLs e slugs
existentes ainda requer inventário. Relações de tradução não estão implementadas.
