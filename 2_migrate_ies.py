"""
Script Principal de Automação de Migração de IES para o Plone 6
===============================================================

Lê a planilha/CSV com dados das Instituições de Ensino Superior (IES),
aplica substituições dinâmicas nos templates JSON extraídos e realiza a criação
e publicação das páginas no CMS Plone 6 via REST API.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
import pandas as pd
from tqdm import tqdm

from config import API_TOKEN, API_URL, EXCEL_PATH
from api_client import PloneRestClient

# Configuração do Logger
logger = logging.getLogger("MigrateIES")
logger.setLevel(logging.INFO)

# Configuração dos caminhos
TEMPLATES_DIR = Path("templates")
REPORT_PATH = Path("migracao_relatorio.csv")

TEMPLATE_FILES = {
    "home": "home.json",
    "sobre-nos": "sobre_nos.json",
    "vida-na-ies": "vida_na_ies.json",
    "estudantes-internacionais": "estudantes_internacionais.json",
}

SUBPAGES_CONFIG = [
    {
        "id": "sobre-nos",
        "title_template": "Sobre a {sigla}",
        "nav_title": "Sobre",
        "template_key": "sobre-nos",
    },
    {
        "id": "vida-na-ies",
        "title_template": "Vida na {sigla}",
        "nav_title": "Vida na IES",
        "template_key": "vida-na-ies",
    },
    {
        "id": "estudantes-internacionais",
        "title_template": "Estudantes Internacionais na {sigla}",
        "nav_title": "Estudantes Internacionais",
        "template_key": "estudantes-internacionais",
    },
]


def load_templates() -> dict:
    """Carrega os 4 arquivos JSON de template do diretório templates/."""
    loaded_templates = {}
    for key, filename in TEMPLATE_FILES.items():
        filepath = TEMPLATES_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Template obrigatório não encontrado: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            loaded_templates[key] = json.load(f)
    return loaded_templates


def load_dataset(data_path_str: str) -> pd.DataFrame:
    """Carrega o arquivo CSV ou Excel contendo as IES."""
    path = Path(data_path_str)
    
    # Se não encontrar o arquivo no caminho relativo, busca dentro da pasta studyinbr/
    if not path.exists():
        fallback_path = Path("studyinbr") / path.name
        if fallback_path.exists():
            path = fallback_path

    if not path.exists():
        raise FileNotFoundError(f"Arquivo de dados não encontrado: {data_path_str}")

    logger.info(f"Carregando dados de: {path}")

    if path.suffix.lower() == ".csv":
        # Tenta ler com separador ';' e fallback para ','
        try:
            df = pd.read_csv(path, sep=";", encoding="utf-8")
            if len(df.columns) <= 1:
                df = pd.read_csv(path, sep=",", encoding="utf-8")
        except Exception:
            df = pd.read_csv(path, sep=",", encoding="utf-8")
    else:
        df = pd.read_excel(path)

    return df


def replace_placeholders(template_data: dict, replacements: dict) -> dict:
    """Converte a estrutura do template para string JSON, realiza as substituições e reverte para dict."""
    json_str = json.dumps(template_data, ensure_ascii=False)
    for old_text, new_text in replacements.items():
        if old_text and new_text:
            json_str = json_str.replace(str(old_text), str(new_text))
    return json.loads(json_str)


def main():
    print("[+] Inicializando processo de migração de IES para o Plone 6...")

    # 1. Carrega templates e dataset
    templates = load_templates()
    df = load_dataset(EXCEL_PATH)
    total_records = len(df)

    # 2. Inicializa o cliente Plone REST API
    client = PloneRestClient(api_url=API_URL, token=API_TOKEN)

    # 3. Estrutura para gravação do relatório de log
    report_rows = []

    print(f"[+] Total de IES para processar: {total_records}\n")

    # 4. Iteração com barra de progresso visual tqdm
    for idx, row in tqdm(df.iterrows(), total=total_records, desc="Migrando IES"):
        # Extração de metadados conforme especificação
        sigla = str(row.get("Sigla", "")).strip()
        nome_ies = str(row.get("Universidade", "")).strip()
        cidade = str(row.get("Cidade Sede", "")).strip()
        estado = str(row.get("Estado Nome", "")).strip()
        uf = str(row.get("Estado", "")).strip()
        slug = str(row.get("nome_curto", "")).strip()
        container_url = str(row.get("Onde criar", "")).strip()

        raw_tags = str(row.get("TAGs", ""))
        tags = [t.strip() for t in raw_tags.split(";") if t.strip()]

        # Dicionário de substituição de textos estáticos dos templates
        replacements = {
            "Universidade Federal de São Carlos": nome_ies,
            "UFSCar": sigla,
            "São Carlos": cidade,
            "São Paulo": estado,
            "SP": uf,
        }

        # Base URL para a IES
        base_container = container_url.rstrip("/")
        ies_url = f"{base_container}/{slug}"

        # -------------------------------------------------------------
        # ETAPA A: Criar Pasta/Página Home da IES
        # -------------------------------------------------------------
        home_template_replaced = replace_placeholders(templates["home"], replacements)
        
        home_title = row.get("Título", f"{sigla} - {nome_ies}")
        home_description = row.get("Descrição", f"{nome_ies} ({sigla}), localizada em {cidade} - {uf}.")

        home_payload = {
            "@type": "Document",
            "id": slug,
            "title": home_title,
            "description": home_description,
            "blocks": home_template_replaced.get("blocks", {}),
            "blocks_layout": home_template_replaced.get("blocks_layout", {}),
            "subjects": tags,
            "exclude_from_nav": False,
        }

        res_home = client.create_content(container_url, home_payload)
        home_success = res_home is not None
        status_home = "SUCCESS" if home_success else "ERROR"
        
        report_rows.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla,
            "tipo_pagina": "HOME",
            "url": ies_url,
            "status": status_home,
            "detalhes": "Home criada com sucesso" if home_success else "Falha ao criar Home"
        })

        # -------------------------------------------------------------
        # ETAPA B: Criar as 3 Subpáginas
        # -------------------------------------------------------------
        created_subpages = []
        for sub in SUBPAGES_CONFIG:
            sub_id = sub["id"]
            sub_template = templates[sub["template_key"]]
            sub_template_replaced = replace_placeholders(sub_template, replacements)

            sub_title = sub["title_template"].format(sigla=sigla, nome_ies=nome_ies)
            sub_nav = sub["nav_title"]
            sub_url = f"{ies_url}/{sub_id}"

            sub_payload = {
                "@type": "Document",
                "id": sub_id,
                "title": sub_title,
                "nav_title": sub_nav,
                "blocks": sub_template_replaced.get("blocks", {}),
                "blocks_layout": sub_template_replaced.get("blocks_layout", {}),
                "subjects": tags,  # Herda as tags geográficas da IES
                "exclude_from_nav": False,
            }

            res_sub = client.create_content(ies_url, sub_payload)
            sub_success = res_sub is not None
            status_sub = "SUCCESS" if sub_success else "ERROR"

            if sub_success:
                created_subpages.append(sub_url)

            report_rows.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": f"SUBPAGE ({sub_id})",
                "url": sub_url,
                "status": status_sub,
                "detalhes": "Subpágina criada com sucesso" if sub_success else "Falha ao criar Subpágina"
            })

        # -------------------------------------------------------------
        # ETAPA C: Publicação no Workflow
        # -------------------------------------------------------------
        # Publica a Home
        pub_home = client.publish_content(ies_url)
        report_rows.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla,
            "tipo_pagina": "PUBLISH_HOME",
            "url": ies_url,
            "status": "SUCCESS" if pub_home else "ERROR",
            "detalhes": "Home publicada" if pub_home else "Falha ao publicar Home"
        })

        # Publica as Subpáginas
        for sub_id in [s["id"] for s in SUBPAGES_CONFIG]:
            sub_url = f"{ies_url}/{sub_id}"
            pub_sub = client.publish_content(sub_url)
            report_rows.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": f"PUBLISH_SUBPAGE ({sub_id})",
                "url": sub_url,
                "status": "SUCCESS" if pub_sub else "ERROR",
                "detalhes": f"Subpágina {sub_id} publicada" if pub_sub else f"Falha ao publicar {sub_id}"
            })

    # 5. Salva o relatório de execução em CSV
    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(REPORT_PATH, index=False, encoding="utf-8")
    print(f"\n[+] Relatório de migração salvo em: '{REPORT_PATH.resolve()}'")
    print("[SUCCESS] Migração de IES concluída!")


if __name__ == "__main__":
    main()
