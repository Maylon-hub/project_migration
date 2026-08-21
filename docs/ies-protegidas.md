
# Walkthrough: Correção da Migração de IES para Plone 6

Foram implementadas todas as alterações solicitadas para resolver os problemas identificados no relatório de migração e no comportamento das subpáginas.

---

## 🛠️ Alterações Realizadas

### 1. [`api_client.py`](file:///d:/GitHub/project_migration/api_client.py)

- **Política de Retries & Resiliência:** Injetado `HTTPAdapter` com `urllib3.util.Retry` (backoff exponencial e até 3 retentativas para erros 429, 500, 502, 503, 504) para evitar falhas transitórias de conexão e timeout.
- **Transição para Estado Privado (`retract_to_private`):** Implementado o método `retract_to_private` que consulta o endpoint `/@workflow` de cada conteúdo e aplica a transição de workflow (`retract` / `reject`) para garantir que nenhuma página fique pública.

### 2. [`2_migrate_ies.py`](file:///d:/GitHub/project_migration/2_migrate_ies.py)

- **Ignorar IES Manuais (`IGNORED_IES`):** O script pula automaticamente as 18 IES que foram diagramadas e ajustadas manualmente (`UTFPR`, `UNILAB`, `UFPA`, `UFOPA`, `UFOP`, `UFOB`, `UFNT`, `UFMT`, `UFMG`, `UFLA`, `UFJF`, `UFG`, `UFES`, `UFDPAR`, `UFCG`, `UFCA`, `UFAPE`, `UFABC`), registrando seu status como `SKIPPED` no relatório.
- **Sufixo com Underscore (`/vida_na_ies`):** Configurado o ID da subpágina e seu link no template mantendo estritamente o formato `/vida_na_ies`.
- **Substituição Dinâmica de URLs e Títulos:**
  - Substituição de todos os 19 URLs que apontavam para a UFSCar no template [`templates/home.json`](file:///d:/GitHub/project_migration/templates/home.json) pelas URLs dinâmicas da respectiva IES (`{ies_url}/vida_na_ies`, `{ies_url}/sobre-nos`, `{ies_url}/estudantes-internacionais`).
  - Remoção de textos residuais como "Vida na UFSCar TESTE 2", normalizando para "Vida na {sigla}", "Sobre a {sigla}" e "Estudantes Internacionais na {sigla}".
- **Fluxo de Workflow Privado:** Substituída a chamada de publicação por `retract_to_private`, garantindo que todas as páginas criadas ou atualizadas permaneçam ou retornem ao estado **privado**.
- **Prevenção de Erros em Cascata:** Se a criação da página Home falhar, a criação de subpáginas filhas é interrompida para aquela IES, evitando erros 404 repetitivos.
- **Novo Arquivo de Relatório CSV:** Saída configurada para [`migracao_relatorio_atualizado.csv`](file:///d:/GitHub/project_migration/migracao_relatorio_atualizado.csv) para não sobrescrever o relatório original.

### 3. [`3_generate_html_report.py`](file:///d:/GitHub/project_migration/3_generate_html_report.py)

- Configurado para ler [`migracao_relatorio_atualizado.csv`](file:///d:/GitHub/project_migration/migracao_relatorio_atualizado.csv) e gerar [`relatorio_migracao_atualizado.html`](file:///d:/GitHub/project_migration/relatorio_migracao_atualizado.html) com suporte ao filtro e status `SKIPPED` para as IES manuais, preservando intacto o arquivo [`relatorio_migracao.html`](file:///d:/GitHub/project_migration/relatorio_migracao.html) original.

### 4. [`4_add_ies_images.py`](file:///d:/GitHub/project_migration/4_add_ies_images.py)

- Também configurado para pular o upload de imagens nas 18 IES manuais (`IGNORED_IES`) e manter todos os arquivos de mídia no estado privado.

---

## 🚀 Como Executar o Código

Para rodar a migração e gerar o novo painel:

```powershell
# 1. Ative o ambiente virtual (opcional, se não estiver ativo)
.venv\Scripts\activate

# 2. Configure ou atualize o Token JWT (caso necessário, via variável de ambiente ou em config.py)
# Exemplo PowerShell:
# $env:API_TOKEN = "Bearer SEU_TOKEN_AQUI"

# 3. Execute o script principal de migração das IES
python 2_migrate_ies.py

# 4. (Opcional) Faça o upload das imagens das IES
python 4_add_ies_images.py

# 5. Gere o novo dashboard HTML
python 3_generate_html_report.py
```

---

## 🧪 Validação dos Testes

1. **Validação das 71 IES e Links (`verify_replacements.py`):**
   - Testada a substituição de placeholders em todas as 71 universidades cadastradas em [`studyinbr/lista_ies_completa.csv`](file:///d:/GitHub/project_migration/studyinbr/lista_ies_completa.csv).
   - Confirmado que 100% das páginas apontam para suas próprias subpáginas (`{ies_url}/vida_na_ies`, `{ies_url}/sobre-nos`, `{ies_url}/estudantes-internacionais`) e que o sufixo `/vida_na_ies` foi rigorosamente preservado.
2. **Validação da Geração de Relatórios:**
   - O script de geração HTML foi executado e gerou [`relatorio_migracao_atualizado.html`](file:///d:/GitHub/project_migration/relatorio_migracao_atualizado.html) com sucesso.
