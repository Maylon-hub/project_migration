"""
Módulo de Configuração
======================

Carrega as variáveis de ambiente com fallbacks padronizados para o ambiente do Plone 6.
"""

import os

# URL base da API REST do Plone 6
API_URL: str = os.getenv("API_URL", "https://www.gov.br/studyinbrazil")

# Token de Autenticação JWT
API_TOKEN: str = os.getenv("API_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMzM3NDIzOTYzMyIsImV4cCI6MTc4ODMxNDY0NywiZnVsbG5hbWUiOiJNQVlMT04gTUFSVElOUyBERSBNRUxPIiwibG9naW51bmljb190b2tlbiI6ImV5SmhiR2NpT2lKSVV6STFOaUlzSW5SNWNDSTZJa3BYVkNKOS5leUp6ZFdJaU9pSXhNek0zTkRJek9UWXpNeUlzSW1WdFlXbHNYM1psY21sbWFXVmtJam9pZEhKMVpTSXNJbUZ0Y2lJNld5SndZWE56ZDJRaUxDSmpZWEIwWTJoaElpd2liV1poSWl3aWIzUndYMjltWm14cGJtVWlYU3dpY0hKdlptbHNaU0k2SW1oMGRIQnpPaTh2YzJWeWRtbGpiM011WVdObGMzTnZMbWR2ZGk1aWNpOGlMQ0pyYVdRaU9pSnljMkV4SWl3aWFYTnpJam9pYUhSMGNITTZMeTl6YzI4dVlXTmxjM052TG1kdmRpNWljaThpTENKd2FHOXVaVjl1ZFcxaVpYSmZkbVZ5YVdacFpXUWlPaUowY25WbElpd2ljSEpsWm1WeWNtVmtYM1Z6WlhKdVlXMWxJam9pTVRNek56UXlNemsyTXpNaUxDSnViMjVqWlNJNklqa3dNMkZtTmpGaE9UaGhNeUlzSW5CcFkzUjFjbVVpT2lKb2RIUndjem92TDNOemJ5NWhZMlZ6YzI4dVoyOTJMbUp5TDNWelpYSnBibVp2TDNCcFkzUjFjbVVpTENKaGRXUWlPaUpuYjNaaWNpSXNJbUYxZEdoZmRHbHRaU0k2TVRjNE9ETXhNVEEwTml3aWMyTnZjR1VpT2xzaWNHaHZibVVpTENKdmNHVnVhV1FpTENKbmIzWmljbDlqYjI1bWFXRmlhV3hwWkdGa1pYTWlMQ0p3Y205bWFXeGxJaXdpWlcxaGFXd2lYU3dpYm1GdFpTSTZJazFCV1V4UFRpQk5RVkpVU1U1VElFUkZJRTFGVEU4aUxDSndhRzl1WlY5dWRXMWlaWElpT2lJek5UazVNakl4TnpRMU9TSXNJbVY0Y0NJNk1UYzRPRE14TVRZME55d2lhV0YwSWpveE56ZzRNekV4TURRM0xDSnFkR2tpT2lJeE56SXdPVGt4Wmkxa1l6WmtMVFExTkdFdFltVm1OeTFqTWpnek16ZzNOREJtT0RVaUxDSmxiV0ZwYkNJNkltMWhlV3h2Ym0xaGNuUnBibk13TjBCbmJXRnBiQzVqYjIwaWZRLlJ3ODFWSldJdHBEdTJPSkZUX1VFWko2X2RpY1VKOW5WOUxTSU5EX2puam8ifQ.r1RnZQEFNgPRhfipVcWRICOmz-Hr5sQPkwU5F1YR3M0")

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

