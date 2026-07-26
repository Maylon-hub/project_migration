# Análise e Mapeamento do Projeto: Migração Plone 6

> Documento de referência sobre a estrutura, arquitetura, dependências e convenções do projeto de migração de notícias e conteúdos do Plone 4 / Gov.br para o Plone 6 (Volto).

---

## 1. Mapeamento da Estrutura de Diretórios e Arquivos

```
project_migration/
├── app.py                      # Interface Gráfica em Tkinter para gerenciar a migração
├── migration_to_plone_6.py     # Script principal (Scraping, parsing HTML -> Slate, REST API Plone 6)
├── config.example.json         # Modelo de configuração exigido pelo script e pela GUI
├── requirements.txt            # Dependências Python do projeto
├── .gitignore                  # Arquivos ignorados pelo Git (tokens, logs, caches)
├── CONFIG.md                   # Documentação detalhada dos parâmetros do config.json
├── Manual-de-migração.md       # Guia operacional de migração e autenticação JWT no Plone 6
├── README.md                   # Visão geral e instruções rápidas do projeto
├── docs/                       # Documentação técnica adicional do repositório
│   └── analise_projeto.md      # Este documento de análise estrutural
├── tests/                      # Suíte de testes unitários
│   └── test_migration.py       # Testes de conversão de HTML para blocos e controle de progresso
├── _assets/                    # Imagens e materiais de suporte/apresentação
└── html/                       # Dumps de amostras HTML locais para testes de extração
```

---

## 2. Stack & Tecnologias

- **Linguagem Principal:** Python 3.9+
- **Interface Gráfica (GUI):** Tkinter (`ttk`, `scrolledtext`, `messagebox`)
- **Web Scraping & Parsing:** `BeautifulSoup4`, `lxml`
- **Comunicação HTTP & API:** `requests` (com suporte a retentativas via `urllib3.util.retry.Retry`)
- **Formatos de Dados:** JSON (`config.json`, `migracao_progresso.json`), Slate Blocks (Formato de blocos do Volto/Plone 6)
- **CMS Alvo:** Plone 6 (Backend REST API com autenticação via Bearer JWT)
- **Framework de Testes:** `unittest` (biblioteca padrão) / `pytest`

---

## 3. Resumo Executivo

1. **Propósito:** Automatizar o processo de scraping de notícias e páginas institucionais de sistemas legados (ex: Plone 4 no portal gov.br da Trensurb), converter a estrutura de conteúdo HTML em blocos modernos (Slate/Volto) e realizar a ingestão idempotente no Plone 6.
2. **Pontos de Entrada (Entrypoints):**
   - `python migration_to_plone_6.py`: Execução CLI utilizando as configurações presentes no `config.json`.
   - `python app.py`: Execução GUI via Tkinter com painel de parâmetros, botões de controle e console de log em tempo real.
3. **Fluxo do Código:**
   - **Inicialização:** Leitura de `config.json` e do histórico em `migracao_progresso.json`.
   - **Navegação & Coleta:** Scraping paginado a partir de `source_start` para coletar URLs.
   - **Parsing & Transformação:** Extração de título, resumo, data, tags e conversão do corpo HTML para blocos Slate (JSON estruturado).
   - **Ingestão no Plone 6:** Chamada à REST API (`POST`/`PATCH`), upload de imagens/anexos e alteração de workflow para publicação (`@workflow/publish`).
   - **Idempotência:** Gravação contínua do progresso no disco para suportar interrupção e retomada sem duplicar itens.

---

## 4. Convenções e Padrões de Código

- **Tipagem Parcial:** Uso de `@dataclass` (`NewsItem`) e anotações de tipo (`Optional[str]`, `list[str]`).
- **Padrão de Nomenclatura:** PEP 8 (`snake_case` para funções e variáveis, `PascalCase` para classes como `PloneClient` e `MigrationApp`).
- **Arquitetura em Thread Separada:** A GUI (`app.py`) roda o processamento do módulo `migration_to_plone_6.py` em uma thread secundária (`threading.Thread`) para evitar o congelamento da interface gráfica.
- **Redirecionamento de Logs:** `TextHandler` customizado intercepta os registros do `logging` e direciona para o widget `ScrolledText` com destaque para erros e avisos.

---

## 5. Requisitos de Ambiente e Configuração Local

### Dependências Python
Instale as dependências via `requirements.txt`:
```bash
pip install -r requirements.txt
```

### Configuração (`config.json`)
Crie o arquivo `config.json` na raiz do repositório a partir do `config.example.json`:
```json
{
    "plone_url": "https://seu-plone.exemplo.gov.br/site/pt-br",
    "plone_token": "Bearer JWT_TOKEN_AQUI",
    "plone_news_folder": "/noticias",
    "source_base": "https://www.gov.br",
    "source_start": "https://www.gov.br/orgaos/exemplo/pt-br/assuntos/noticias",
    "delay": 1,
    "max_news": 0,
    "all_pages": true,
    "progress_file": "migracao_progresso.json",
    "portal_type": "Document",
    "migrate_as_self": true,
    "skip_files": false
}
```

---

## 6. Boas Práticas ao Solicitar Alterações

- **Soluções Modulares e Legíveis:** Manter funções com responsabilidade única e desacopladas.
- **Notificação sobre Dependências:** Não adicionar bibliotecas externas sem comunicação prévia.
- **Formato de Resposta:** Apresentar snippets focados das alterações em vez de reescrever arquivos inteiros, a menos que solicitado.
