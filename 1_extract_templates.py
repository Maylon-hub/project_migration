"""
Extractor de Templates Plone 6 / Volto
======================================

Este script localiza a variável de estado do Redux (`window.__data`) em páginas HTML salvas do Plone 6 (Volto),
extrai os objetos `blocks` e `blocks_layout` e gera arquivos JSON padronizados dentro do diretório `templates/`.

Mapeamento de arquivos:
- html/UFSCar - Universidade Federal de São Carlos TESTE.html  -> templates/home.json
- html/Sobre a UFSCar.html                                  -> templates/sobre_nos.json
- html/Vida na UFSCar.html                                  -> templates/vida_na_ies.json
- html/Estudantes Internacionais na UFSCar.html             -> templates/estudantes_internacionais.json
"""

import os
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

# Configuração dos caminhos e mapeamentos
HTML_DIR = Path("html")
TEMPLATES_DIR = Path("templates")

FILE_MAPPING = {
    "UFSCar - Universidade Federal de São Carlos TESTE.html": "home.json",
    "Sobre a UFSCar.html": "sobre_nos.json",
    "Vida na UFSCar.html": "vida_na_ies.json",
    "Estudantes Internacionais na UFSCar.html": "estudantes_internacionais.json",
}

def extract_plone_blocks(html_content: str) -> dict:
    """Localiza a variável window.__data no HTML e extrai os blocos Volto/Slate."""
    # 1. Utiliza BeautifulSoup para encontrar a tag <script> com window.__data
    soup = BeautifulSoup(html_content, "html.parser")
    target_script = None
    
    for script in soup.find_all("script"):
        if script.string and "window.__data" in script.string:
            target_script = script.string
            break

    raw_json = None
    if target_script:
        # Extrai o trecho do JSON após 'window.__data='
        match = re.search(r'window\.__data\s*=\s*({.+?});?\s*$', target_script.strip(), re.DOTALL)
        if match:
            raw_json = match.group(1)

    # Fallback com regex no documento completo caso a tag script esteja inline sem nó de texto
    if not raw_json:
        match = re.search(r'window\.__data\s*=\s*({.+?});?\s*</script>', html_content, re.DOTALL)
        if match:
            raw_json = match.group(1)

    if not raw_json:
        raise ValueError("Não foi possível encontrar a variável 'window.__data' no arquivo HTML.")

    # 2. Tratamento do JSON JS: Substitui 'undefined' sem aspas por 'null' para compatibilidade com o parser JSON
    clean_json = re.sub(r':\s*undefined\b', ':null', raw_json)

    # 3. Parse do JSON
    redux_state = json.loads(clean_json)

    # 4. Extração exclusiva de content.data.blocks e content.data.blocks_layout
    content_data = redux_state.get("content", {}).get("data", {})
    blocks = content_data.get("blocks", {})
    blocks_layout = content_data.get("blocks_layout", {})

    return {
        "blocks": blocks,
        "blocks_layout": blocks_layout
    }

def main():
    # Cria o diretório de destino se não existir
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[+] Diretorio de saida preparado: {TEMPLATES_DIR.resolve()}\n")

    for html_filename, template_filename in FILE_MAPPING.items():
        html_path = HTML_DIR / html_filename
        output_path = TEMPLATES_DIR / template_filename

        print(f"[*] Processando: '{html_filename}'...")

        if not html_path.exists():
            print(f"[-] Arquivo nao encontrado: {html_path}. Pulando.")
            continue

        try:
            with open(html_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            extracted_data = extract_plone_blocks(html_content)

            # Salva o resultado limpo e formatado
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(extracted_data, f, ensure_ascii=False, indent=2)

            num_blocks = len(extracted_data["blocks"])
            num_layout = len(extracted_data["blocks_layout"].get("items", []))
            print(f"[OK] Salvo em: '{output_path}' ({num_blocks} blocos / {num_layout} no layout)\n")

        except Exception as e:
            print(f"[ERRO] Erro ao processar '{html_filename}': {e}\n")

    print("[SUCCESS] Extracao concluida com sucesso!")

if __name__ == "__main__":
    main()
