# Adicionar instituições

Cada IES requer identidade, aliases propostos, nome oficial, localização, tipo,
administração, natureza, nomes localizados e proveniência. A sigla normalizada não
deve ser usada para renomear páginas ou decidir uma URL existente.

`institution_type`, `administration` e `ownership` são eixos independentes.
`config/domain.json` registra categorias observadas nos anexos. Estender o registro
para universidades estaduais, institutos federais, CEFETs, FATECs ou outras IES
exige dados explícitos e testes; desconhecidos geram conflitos em vez de defaults.

Não inserir centenas de linhas sem validar unicidade de destino. O diagnóstico
preserva todos os candidatos e assinala duplicatas por fonte. Confirmar aliases,
nome oficial, tradução aprovada, slug e container antes de qualquer plano futuro.

EditorialPolicy começa `unconfirmed`; RemoteBinding só deverá conter UID/URL
obtidos em inspeção autorizada. Nenhum binding remoto é inventado pelas planilhas.
