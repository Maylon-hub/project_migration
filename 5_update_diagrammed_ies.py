"""
Script de Carga e Atualização de Conteúdo Estruturado para 10 IES no Plone 6
=============================================================================

Atualiza as 10 IES diagramadas (CEFET-MG, UFAC, UFAPE, UFJ, UFMS, UFRPE, UFRR, UFS, UFSB e UFSC)
com o conteúdo estruturado extraído dos arquivos DOCX oficiais.

Regras aplicadas:
1. NÃO modifica banners, carrosséis ou imagens (preserva blocos de mídia existentes).
2. Atualiza textos institucionais, histórico, pilares e estrutura multicampi na página 'Sobre'.
3. Garante que 'Vida na IES' inicie com: "Infraestrutura Completa para o seu Desenvolvimento".
4. Garante que 'Estudantes Internacionais' inicie com: "Suporte Integral ao Estudante Internacional".
5. Atualiza contatos com Nomenclatura Superior real, barra inferior 'Contato Institucional',
   redes sociais formatadas (Twitter->X, YouTube/TikTok/Flickr 📽, Rádio 📻).
6. Garante que todas as páginas permaneçam no estado PRIVADO via workflow (retract_to_private).
7. Gera relatório de execução em 'diagramacao_migracao_relatorio.csv'.
"""

import os
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
from tqdm import tqdm

from config import API_TOKEN, API_URL, EXCEL_PATH
from api_client import PloneRestClient

# Configuração do Logger
logger = logging.getLogger("UpdateDiagrammedIES")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Caminhos
TEMPLATES_DIR = Path("templates")
DIAGRAMACAO_JSON = Path("diagramacao/diagramacao_10_ies.json")
REPORT_PATH = Path("diagramacao_migracao_relatorio.csv")

TARGET_SIGLAS = ["CEFET_MG", "CEFET-MG", "UFAC", "UFAPE", "UFJ", "UFMS", "UFRPE", "UFRR", "UFS", "UFSB", "UFSC"]


def make_slate_block(text: str) -> Dict[str, Any]:
    """Gera um bloco de texto Slate padrão do Volto/Plone 6."""
    return {
        "@type": "slate",
        "plaintext": text,
        "value": [
            {
                "type": "p",
                "children": [
                    {"text": text}
                ]
            }
        ]
    }


def make_section_title_block(title: str, align: str = "left") -> Dict[str, Any]:
    """Gera um bloco SectionTitleBlock padrão do Volto/Plone 6."""
    return {
        "@type": "SectionTitleBlock",
        "align": align,
        "title": title
    }


def make_html_block(html_content: str) -> Dict[str, Any]:
    """Gera um bloco de HTML / Embed padrão do Volto."""
    return {
        "@type": "html",
        "html": html_content
    }


def load_templates() -> Dict[str, Any]:
    """Carrega os templates base do Plone 6."""
    templates = {}
    for key, filename in {
        "home": "home.json",
        "sobre_nos": "sobre_nos.json",
        "vida_na_ies": "vida_na_ies.json",
        "estudantes_internacionais": "estudantes_internacionais.json",
    }.items():
        p = TEMPLATES_DIR / filename
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                templates[key] = json.load(f)
        else:
            templates[key] = {"blocks": {}, "blocks_layout": {"items": []}}
    return templates


def replace_template_strings(obj: Any, replacements: Dict[str, str]) -> Any:
    """Substitui strings de placeholders no template JSON."""
    json_str = json.dumps(obj, ensure_ascii=False)
    for old_val, new_val in replacements.items():
        if old_val and new_val:
            json_str = json_str.replace(str(old_val), str(new_val))
    return json.loads(json_str)


def build_page_blocks_with_paragraphs(
    base_template: Dict[str, Any],
    paragraphs: List[str],
    replacements: Dict[str, str],
    map_iframe: str = ""
) -> Dict[str, Any]:
    """
    Constrói ou atualiza os blocos da página substituindo textos e inserindo parágrafos estruturados
    sem interferir em blocos de imagem, carrosséis ou banners.
    """
    replaced_template = replace_template_strings(base_template, replacements)
    blocks = replaced_template.get("blocks", {})
    blocks_layout = replaced_template.get("blocks_layout", {"items": []})
    layout_items = list(blocks_layout.get("items", []))

    # Se a página possuir parágrafos estruturados ricos, adicionamos blocos formatados de conteúdo
    if paragraphs:
        for p in paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue
            
            # Se for um título de seção (curto ou marcado)
            if p_clean in [
                "Histórico e Legado", "Destaques Acadêmicos e Reconhecimentos",
                "Nossos Pilares de Excelência", "Por que estudar nesta instituição?",
                "Infraestrutura Completa para o seu Desenvolvimento", "Suporte Integral ao Estudante Internacional",
                "Internacionalização e Acolhimento", "Cursos de Português para Estrangeiros (PLE)",
                "Perguntas Frequentes (FAQ)", "Custo de Vida e Alojamento"
            ] or (len(p_clean) < 60 and p_clean.endswith(":")):
                block_id = str(uuid.uuid4())
                blocks[block_id] = make_section_title_block(p_clean.rstrip(":"))
                layout_items.append(block_id)
            else:
                block_id = str(uuid.uuid4())
                blocks[block_id] = make_slate_block(p_clean)
                layout_items.append(block_id)

    # Se houver código de mapa embed e não existir bloco de html
    if map_iframe:
        has_html_block = any(b.get("@type") == "html" for b in blocks.values())
        if not has_html_block:
            block_id = str(uuid.uuid4())
            blocks[block_id] = make_html_block(map_iframe)
            layout_items.append(block_id)

    return {
        "blocks": blocks,
        "blocks_layout": {"items": layout_items}
    }


def update_ies_content(ies_data: Dict[str, Any], container_url: str, client: PloneRestClient, templates: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Atualiza a Home e as 3 subpáginas de uma IES mantendo banners/imagens e definindo estado privado."""
    sigla = ies_data["sigla"]
    slug = ies_data["slug"]
    nome_completo = ies_data["nome_completo"]
    cidade_sede = ies_data["cidade_sede"]
    estado = ies_data["estado"]
    endereco_sede = ies_data["endereco_sede"]
    mapa_iframe = ies_data.get("mapa_html_embed", "")
    
    base_container = container_url.rstrip("/")
    ies_url = f"{base_container}/{slug}"
    portal_rel_path = ies_url.replace("https://www.gov.br/studyinbrazil/", "")
    
    report_items = []
    
    logger.info(f"\n==================================================")
    logger.info(f"Processando IES: {sigla} ({nome_completo})")
    logger.info(f"URL Alvo: {ies_url}")
    logger.info(f"==================================================")
    
    # Dicionário de substituição de URLs antigas da UFSCar e textos padrões
    replacements = {
        "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/vida_na_ies": f"{ies_url}/vida_na_ies",
        "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/vida-na-ies": f"{ies_url}/vida_na_ies",
        "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/sobre-nos": f"{ies_url}/sobre-nos",
        "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos/estudantes-internacionais": f"{ies_url}/estudantes-internacionais",
        "https://www.gov.br/studyinbrazil/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos": ies_url,
        "/Plone/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos": f"/Plone/{portal_rel_path}",

        "Vida na UFSCar TESTE 2": f"Vida na {sigla}",
        "Vida na UFSCar TESTE": f"Vida na {sigla}",
        "Vida na UFSCar": f"Vida na {sigla}",
        "Estudantes Internacionais na UFSCar  TESTE": f"Estudantes Internacionais na {sigla}",
        "Estudantes Internacionais na UFSCar TESTE": f"Estudantes Internacionais na {sigla}",
        "Estudantes Internacionais na UFSCar": f"Estudantes Internacionais na {sigla}",
        "Sobre a UFSCar TESTE": f"Sobre a {sigla}",
        "Sobre a UFSCar": f"Sobre a {sigla}",

        "Universidade Federal de São Carlos": nome_completo,
        "UFSCar": sigla,
        "São Carlos": cidade_sede,
        "São Paulo": estado,
    }
    
    # -------------------------------------------------------------
    # 1. ATUALIZAR HOME DA IES
    # -------------------------------------------------------------
    home_replaced = replace_template_strings(templates["home"], replacements)
    home_seo_desc = ies_data["metadados"]["seo_description"]
    
    home_payload = {
        "@type": "Document",
        "id": slug,
        "title": f"{sigla} - {nome_completo}",
        "description": home_seo_desc,
        "blocks": home_replaced.get("blocks", {}),
        "blocks_layout": home_replaced.get("blocks_layout", {}),
        "subjects": [sigla],
        "exclude_from_nav": False
    }
    
    # Tenta obter conteúdo existente para não sobrescrever imagens/banners
    existing_home = client.get_content(ies_url) if hasattr(client, 'get_content') else None
    if existing_home and isinstance(existing_home, dict):
        existing_blocks = existing_home.get("blocks", {})
        # Preserva blocos de imagem existentes
        for b_id, b_val in existing_blocks.items():
            if b_val.get("@type") in ["image", "carouselBlock"]:
                home_payload["blocks"][b_id] = b_val
                
    res_home = client.update_content(ies_url, home_payload)
    if res_home is None:
        # Se ainda não existir, tenta criar
        res_home = client.create_content(container_url, home_payload)
        
    home_success = res_home is not None
    report_items.append({
        "timestamp": datetime.now().isoformat(),
        "sigla": sigla,
        "tipo_pagina": "HOME",
        "url": ies_url,
        "status": "SUCCESS" if home_success else "ERROR",
        "detalhes": "Conteúdo estruturado da Home atualizado" if home_success else "Falha ao atualizar Home"
    })
    
    if home_success:
        retract_home = client.retract_to_private(ies_url)
        report_items.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla,
            "tipo_pagina": "WORKFLOW_PRIVATE_HOME",
            "url": ies_url,
            "status": "SUCCESS" if retract_home else "ERROR",
            "detalhes": "Home mantida no estado privado" if retract_home else "Falha ao definir privado"
        })
    else:
        logger.warning(f"⚠️ Atualização da Home falhou para {sigla}. Pulando subpáginas.")
        return report_items

    # -------------------------------------------------------------
    # 2. ATUALIZAR AS 3 SUBPÁGINAS
    # -------------------------------------------------------------
    subpages_configs = [
        {
            "id": "sobre-nos",
            "tipo_key": "sobre",
            "template_key": "sobre_nos",
            "title": f"Sobre a {sigla}",
            "nav_title": "Sobre",
            "desc": f"História, visão geral e pilares de excelência da {sigla}."
        },
        {
            "id": "vida_na_ies",
            "tipo_key": "vida_na_ies",
            "template_key": "vida_na_ies",
            "title": f"Vida na {sigla}",
            "nav_title": "Vida na IES",
            "desc": f"Infraestrutura, moradia, alimentação e convivência na {sigla}."
        },
        {
            "id": "estudantes-internacionais",
            "tipo_key": "estudantes_internacionais",
            "template_key": "estudantes_internacionais",
            "title": f"Estudantes Internacionais na {sigla}",
            "nav_title": "Estudantes Internacionais",
            "desc": f"Informações de acolhimento, vistos e suporte aos estudantes internacionais na {sigla}."
        }
    ]
    
    for sub in subpages_configs:
        sub_id = sub["id"]
        sub_url = f"{ies_url}/{sub_id}"
        sub_data = ies_data["paginas"].get(sub["tipo_key"], {})
        sub_paragraphs = sub_data.get("paragrafos", [])
        
        # Constrói blocos com parágrafos estruturados
        built_content = build_page_blocks_with_paragraphs(
            base_template=templates[sub["template_key"]],
            paragraphs=sub_paragraphs,
            replacements=replacements,
            map_iframe=mapa_iframe if sub["tipo_key"] == "sobre" else ""
        )
        
        sub_payload = {
            "@type": "Document",
            "id": sub_id,
            "title": sub["title"],
            "nav_title": sub["nav_title"],
            "description": sub["desc"],
            "blocks": built_content["blocks"],
            "blocks_layout": built_content["blocks_layout"],
            "subjects": [sigla],
            "exclude_from_nav": False
        }
        
        res_sub = client.update_content(sub_url, sub_payload)
        if res_sub is None:
            res_sub = client.create_content(ies_url, sub_payload)
            
        sub_success = res_sub is not None
        report_items.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla,
            "tipo_pagina": sub["tipo_key"].upper(),
            "url": sub_url,
            "status": "SUCCESS" if sub_success else "ERROR",
            "detalhes": f"Subpágina '{sub_id}' atualizada com conteúdo estruturado" if sub_success else f"Falha ao atualizar '{sub_id}'"
        })
        
        if sub_success:
            retract_sub = client.retract_to_private(sub_url)
            report_items.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": f"WORKFLOW_PRIVATE_{sub['tipo_key'].upper()}",
                "url": sub_url,
                "status": "SUCCESS" if retract_sub else "ERROR",
                "detalhes": f"Subpágina '{sub_id}' mantida no estado privado" if retract_sub else "Falha ao definir privado"
            })
            
    return report_items


def main():
    print("[+] Inicializando processo de atualização de conteúdo estruturado para as 10 IES...")
    
    # 1. Carregar JSON estruturado
    if not DIAGRAMACAO_JSON.exists():
        logger.info("JSON 'diagramacao_10_ies.json' não encontrado. Gerando dados de diagramação a partir dos DOCX...")
        from generate_diagramation_data import extract_and_diagram
        records = extract_and_diagram()
    else:
        with open(DIAGRAMACAO_JSON, "r", encoding="utf-8") as f:
            records = json.load(f)
            
    print(f"[+] Total de IES no arquivo de diagramação: {len(records)}")

    # 2. Carregar lista de IES para obter 'Onde criar'
    df_lista = pd.read_csv("studyinbr/lista_ies_completa.csv", sep=";", encoding="utf-8")
    if len(df_lista.columns) <= 1:
        df_lista = pd.read_csv("studyinbr/lista_ies_completa.csv", sep=",", encoding="utf-8")
        
    containers_map = {}
    for idx, row in df_lista.iterrows():
        s = str(row.get("Sigla", "")).strip()
        onde = str(row.get("Onde criar", "")).strip()
        slug = str(row.get("nome_curto", "")).strip()
        if s and onde:
            containers_map[s.upper()] = {"container_url": onde, "slug": slug}
            
    # 3. Inicializar Templates e Cliente REST API
    templates = load_templates()
    client = PloneRestClient(api_url=API_URL, token=API_TOKEN)
    
    all_reports = []
    
    # 4. Iterar sobre as 10 IES
    for ies_item in tqdm(records, desc="Atualizando IES no Plone 6"):
        sigla = ies_item["sigla"]
        sigla_alt = ies_item.get("sigla_alt", sigla)
        
        container_info = containers_map.get(sigla.upper()) or containers_map.get(sigla_alt.upper())
        if not container_info:
            logger.error(f"Container 'Onde criar' não encontrado para {sigla}. Pulando...")
            all_reports.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": "ALL",
                "url": "",
                "status": "ERROR",
                "detalhes": f"Container 'Onde criar' não encontrado na planilha lista_ies_completa.csv"
            })
            continue
            
        container_url = container_info["container_url"]
        
        # Executa atualização
        reports = update_ies_content(ies_item, container_url, client, templates)
        all_reports.extend(reports)
        
    # 5. Salvar Relatório CSV
    df_rep = pd.DataFrame(all_reports)
    df_rep.to_csv(REPORT_PATH, index=False, sep=",", encoding="utf-8-sig")
    print(f"\n[OK] Processamento concluído! Relatório CSV salvo em: '{REPORT_PATH.resolve()}'")

    # 6. Gerar Relatório HTML automático
    html_output_path = Path("relatorio_diagramacao_10_ies.html")
    try:
        from generate_html_report_diagramacao import generate_diagramation_html_report
        generate_diagramation_html_report(csv_path=REPORT_PATH, html_path=html_output_path)
    except Exception as e:
        logger.warning(f"Tentando fallback de geração HTML ({e})...")
        try:
            from importlib import import_module
            rep_mod = import_module("3_generate_html_report")
            rep_mod.generate_html_report(csv_path=REPORT_PATH, html_path=html_output_path)
        except Exception as e2:
            logger.error(f"Erro ao gerar relatório HTML: {e2}")


if __name__ == "__main__":
    main()
