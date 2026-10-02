"""
Módulo de Configuração
======================

Carrega as variáveis de ambiente com fallbacks padronizados para o ambiente do Plone 6.
"""

import os

# URL base da API REST do Plone 6
API_URL: str = os.getenv("API_URL", "https://www.gov.br/studyinbrazil")

# Token de Autenticação JWT
API_TOKEN: str = os.getenv("PLONE_TOKEN", "")

# Credenciais de Login (opcionais para autenticação via /@login)
API_USERNAME: str = os.getenv("API_USERNAME", "")
API_PASSWORD: str = os.getenv("API_PASSWORD", "")

# Caminho para a planilha de dados de IES
EXCEL_PATH: str = os.getenv("EXCEL_PATH", "studyinbr/lista_ies_completa.csv")

# Lista de IES ajustadas manualmente que não devem ser modificadas pelo script
IGNORED_IES = [
    "UTFPR", "UNILAB", "UFPA", "UFOPA", "UFOP", "UFOB", "UFNT", "UFMT",
    "UFMG", "UFLA", "UFJF", "UFG", "UFES", "UFDPAR", "UFCG", "UFCA",
    "UFAPE", "UFABC"
]

