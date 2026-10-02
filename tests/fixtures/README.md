# Fixtures

`historical_ufscar.json` foi extraído por allowlist do objeto de conteúdo histórico:
tipo, ID, idioma, estado privado, folderish, IDs/tipos de blocos title/description,
layout correspondente e três IDs de subpáginas. Não contém o estado Redux, sessão,
token, headers, contatos ou imagens. Não representa um inventário atual.

`factories.py` produz pequenos XLSX sintéticos nas pastas temporárias dos testes,
com as mesmas abas/tabelas do adaptador. Não são cópias das planilhas privadas.
