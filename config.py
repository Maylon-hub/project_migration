"""
Módulo de Configuração
======================

Carrega as variáveis de ambiente com fallbacks padronizados para o ambiente do Plone 6.
"""

import os

# URL base da API REST do Plone 6
API_URL: str = os.getenv("API_URL", "https://www.gov.br/studyinbrazil/pt-br")

# Token de Autenticação JWT
API_TOKEN: str = os.getenv("API_TOKEN", "SEU_TOKEN_JWT_AQUI")

# Caminho para a planilha de dados de IES
EXCEL_PATH: str = os.getenv("EXCEL_PATH", "studyinbr/lista_ies_completa.csv")
