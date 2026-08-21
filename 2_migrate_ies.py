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

from config import API_TOKEN, API_URL, EXCEL_PATH, IGNORED_IES
from api_client import PloneRestClient

# Configuração do Logger
logger = logging.getLogger("MigrateIES")
logger.setLevel(logging.INFO)

# Configuração dos caminhos
TEMPLATES_DIR = Path("templates")
REPORT_PATH = Path("migracao_relatorio_atualizado.csv")

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
        "tipo3": "sobre_nos",
    },
    {
        "id": "vida_na_ies",  # Mantendo underscore conforme instrução expressa
        "title_template": "Vida na {sigla}",
        "nav_title": "Vida na IES",
        "template_key": "vida-na-ies",
        "tipo3": "vida_na_ies",
    },
    {
        "id": "estudantes-internacionais",
        "title_template": "Estudantes Internacionais na {sigla}",
        "nav_title": "Estudantes Internacionais",
        "template_key": "estudantes-internacionais",
        "tipo3": "estudantes-internacionais",
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
    print("[+] Inicializando processo de migração de IES para o Plone 6 (Estado: PRIVADO)...")

    # 1. Carrega templates e datasets
    templates = load_templates()
    df = load_dataset(EXCEL_PATH)
    total_records = len(df)
    
    try:
        df_subpages = load_dataset("studyinbr/subpaginas_ies_completo.csv")
    except Exception as e:
        logger.warning(f"Não foi possível carregar as subpáginas ({e}). Usando defaults.")
        df_subpages = pd.DataFrame()

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

        # Base URL para a IES
        base_container = container_url.rstrip("/")
        ies_url = f"{base_container}/{slug}"
        portal_rel_path = ies_url.replace("https://www.gov.br/studyinbrazil/", "")

        # Pula IES que já foram ajustadas/diagramadas manualmente
        if sigla.upper() in [x.upper() for x in IGNORED_IES]:
            logger.info(f"⏭️ IES {sigla} ignorada (ajustada manualmente). Não será modificada.")
            report_rows.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": "ALL",
                "url": ies_url,
                "status": "SKIPPED",
                "detalhes": "Ignorada - IES ajustada/diagramada manualmente"
            })
            continue

        # Dicionário de substituição de textos estáticos e URLs dos templates
        replacements = {
            # Substituição precisa de URLs completas para evitar redirecionamento para UFSCar
            "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/vida_na_ies": f"{ies_url}/vida_na_ies",
            "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/vida-na-ies": f"{ies_url}/vida_na_ies",
            "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/sobre-nos": f"{ies_url}/sobre-nos",
            "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/estudantes-internacionais": f"{ies_url}/estudantes-internacionais",
            "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos": ies_url,
            "/Plone/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos": f"/Plone/{portal_rel_path}",

            # Substituição de títulos personalizados e textos de teste
            "Vida na UFSCar TESTE 2": f"Vida na {sigla}",
            "Vida na UFSCar TESTE": f"Vida na {sigla}",
            "Vida na UFSCar": f"Vida na {sigla}",
            "Estudantes Internacionais na UFSCar  TESTE": f"Estudantes Internacionais na {sigla}",
            "Estudantes Internacionais na UFSCar TESTE": f"Estudantes Internacionais na {sigla}",
            "Estudantes Internacionais na UFSCar": f"Estudantes Internacionais na {sigla}",
            "Sobre a UFSCar TESTE": f"Sobre a {sigla}",
            "Sobre a UFSCar": f"Sobre a {sigla}",

            # Substituição de entidades institucionais
            "Universidade Federal de São Carlos": nome_ies,
            "UFSCar": sigla,
            "São Carlos": cidade,
            "São Paulo": estado,
            "SP": uf,
        }

        # -------------------------------------------------------------
        # ETAPA A: Criar ou Atualizar Pasta/Página Home da IES
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
        # Se o conteúdo já existir (ex: 400 ou existente), tenta PATCH para atualizar blocos e links
        if res_home is None:
            res_home = client.update_content(ies_url, home_payload)

        home_success = res_home is not None
        status_home = "SUCCESS" if home_success else "ERROR"
        
        report_rows.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla,
            "tipo_pagina": "HOME",
            "url": ies_url,
            "status": status_home,
            "detalhes": "Home criada/atualizada com sucesso" if home_success else "Falha ao criar/atualizar Home"
        })

        # -------------------------------------------------------------
        # ETAPA B: Garantir Estado PRIVADO na Home
        # -------------------------------------------------------------
        if home_success:
            retract_home = client.retract_to_private(ies_url)
            report_rows.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": "WORKFLOW_PRIVATE_HOME",
                "url": ies_url,
                "status": "SUCCESS" if retract_home else "ERROR",
                "detalhes": "Home mantida/definida como privada" if retract_home else "Falha ao definir Home como privada"
            })
        else:
            logger.warning(f"⚠️ Criação da Home falhou para {sigla}. Pulando subpáginas para evitar falhas em cascata.")
            continue

        # -------------------------------------------------------------
        # ETAPA C: Criar ou Atualizar as 3 Subpáginas
        # -------------------------------------------------------------
        for sub in SUBPAGES_CONFIG:
            sub_id = sub["id"]
            sub_tipo3 = sub.get("tipo3", sub_id)
            sub_template = templates[sub["template_key"]]
            sub_template_replaced = replace_placeholders(sub_template, replacements)

            sub_title = sub["title_template"].format(sigla=sigla, nome_ies=nome_ies)
            sub_nav = sub["nav_title"]
            sub_desc = ""

            if not df_subpages.empty:
                match_sub = df_subpages[
                    (df_subpages["Sigla"] == sigla) &
                    ((df_subpages["nome_curto"] == sub_id) |
                     (df_subpages["tipo3"] == sub_tipo3) |
                     (df_subpages["nome_curto"] == sub_id.replace("_", "-")))
                ]
                if not match_sub.empty:
                    sub_title = str(match_sub.iloc[0].get("Título", sub_title)).strip()
                    sub_nav = str(match_sub.iloc[0].get("nav_title", sub_nav)).strip()
                    sub_desc = str(match_sub.iloc[0].get("Descrição", "")).strip()

            sub_url = f"{ies_url}/{sub_id}"

            sub_payload = {
                "@type": "Document",
                "id": sub_id,
                "title": sub_title,
                "nav_title": sub_nav,
                "description": sub_desc,
                "blocks": sub_template_replaced.get("blocks", {}),
                "blocks_layout": sub_template_replaced.get("blocks_layout", {}),
                "subjects": tags,  # Herda as tags geográficas da IES
                "exclude_from_nav": False,
            }

            res_sub = client.create_content(ies_url, sub_payload)
            if res_sub is None:
                res_sub = client.update_content(sub_url, sub_payload)

            sub_success = res_sub is not None
            status_sub = "SUCCESS" if sub_success else "ERROR"

            report_rows.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": f"SUBPAGE ({sub_id})",
                "url": sub_url,
                "status": status_sub,
                "detalhes": f"Subpágina {sub_id} criada/atualizada com sucesso" if sub_success else f"Falha ao criar/atualizar {sub_id}"
            })

            # Garantir estado PRIVADO na subpágina
            if sub_success:
                retract_sub = client.retract_to_private(sub_url)
                report_rows.append({
                    "timestamp": datetime.now().isoformat(),
                    "sigla": sigla,
                    "tipo_pagina": f"WORKFLOW_PRIVATE_SUBPAGE ({sub_id})",
                    "url": sub_url,
                    "status": "SUCCESS" if retract_sub else "ERROR",
                    "detalhes": f"Subpágina {sub_id} mantida/definida como privada" if retract_sub else f"Falha ao definir {sub_id} como privada"
                })

    # 5. Salva o NOVO relatório de execução em CSV sem sobrescrever o antigo
    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(REPORT_PATH, index=False, encoding="utf-8")
    print(f"\n[+] Novo relatório de migração salvo em: '{REPORT_PATH.resolve()}'")
    print("[SUCCESS] Migração e ajuste de IES concluídos!")


if __name__ == "__main__":
    main()

