"""
Script de Correção e Atualização de Conteúdo Estruturado para 10 IES no Plone 6
=================================================================================

v2 — Corrige o problema da v1 onde a seção de contato (columnsBlock) e o texto
"bem-vindos" da Home ainda continham dados da UFSCar (email, telefone, endereço,
URL do setor, campi de Araras/Sorocaba/Lagoa do Sino/São José do Rio Preto).

Estratégia:
  1. Para cada IES, busca o JSON atual de cada página no Plone (GET).
  2. Serializa para string JSON e aplica substituições textuais profundas (deep replace)
     cobrindo TODOS os strings UFSCar-específicos identificados no template.
  3. Para subpáginas, remove os blocos slate/SectionTitleBlock adicionados erroneamente
     pela execução anterior do script (aqueles cujos IDs não constam no template original).
  4. Mantém o accordion existente como está (não toca nele).
  5. Envia PATCH de volta ao Plone e garante estado PRIVADO.
  6. Gera relatório HTML de execução.
"""

import os
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import pandas as pd
from tqdm import tqdm

from config import API_TOKEN, API_URL
from api_client import PloneRestClient

# Configuração do Logger
logger = logging.getLogger("FixDiagrammedIES")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Caminhos
TEMPLATES_DIR = Path("templates")
DIAGRAMACAO_JSON = Path("diagramacao/diagramacao_10_ies.json")
REPORT_PATH = Path("diagramacao_correcao_relatorio.csv")
HTML_REPORT_PATH = Path("relatorio_diagramacao_correcao.html")

TARGET_SIGLAS = {"CEFET_MG", "CEFET-MG", "UFAC", "UFAPE", "UFJ", "UFMS", "UFRPE", "UFRR", "UFS", "UFSB", "UFSC"}


def load_templates() -> Dict[str, Any]:
    """Carrega os templates base e retorna também o conjunto de block IDs originais."""
    templates = {}
    template_block_ids: Dict[str, Set[str]] = {}

    for key, filename in {
        "home": "home.json",
        "sobre_nos": "sobre_nos.json",
        "vida_na_ies": "vida_na_ies.json",
        "estudantes_internacionais": "estudantes_internacionais.json",
    }.items():
        p = TEMPLATES_DIR / filename
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                tmpl = json.load(f)
            templates[key] = tmpl
            # Coleta todos os IDs de blocos RAIZ do template
            template_block_ids[key] = set(tmpl.get("blocks", {}).keys())
        else:
            templates[key] = {"blocks": {}, "blocks_layout": {"items": []}}
            template_block_ids[key] = set()

    return templates, template_block_ids


def build_contact_section_text(ies_data: Dict[str, Any]) -> str:
    """Gera o texto descritivo correto da equipe de RI para substituir o da UFSCar."""
    sigla = ies_data["sigla"]
    nome_completo = ies_data["nome_completo"]
    cidade_sede = ies_data["cidade_sede"]
    outros_campi = ies_data.get("outros_campi", "")
    
    # Montar lista de cidades de campi a partir de outros_campi
    # Ex: "campus na cidade de Cruzeiro do Sul" → menciona só Rio Branco e Cruzeiro do Sul
    campi_texto = f"{cidade_sede}"
    if outros_campi:
        # Extrai nomes de cidades de outros_campi de forma simples
        import re
        cidades_adicionais = re.findall(r'(?:em|de|do|da)\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÜ][a-záéíóúâêîôûãõàü]+(?:\s+[a-záéíóúâêîôûãõàüA-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÜ][a-záéíóúâêîôûãõàüA-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÜ]+)*)', outros_campi)
        if cidades_adicionais:
            campi_texto = f"{cidade_sede} e {', '.join(cidades_adicionais[:3])}"
    
    return (
        f"Nossa equipe está à disposição para apoiar estudantes e parceiros internacionais em todas as etapas "
        f"da experiência na {sigla}, oferecendo orientações sobre vistos e registro no Brasil, informações sobre "
        f"bolsas e oportunidades de financiamento, apoio ao aprendizado de português, dicas de moradia na cidade "
        f"de {campi_texto}, assistência em parcerias e programas de intercâmbio acadêmico, além de facilitar sua "
        f"integração cultural e acadêmica à universidade e à região."
    )


def build_welcome_text(ies_data: Dict[str, Any]) -> str:
    """Gera o texto de boas-vindas correto para substituir o da UFSCar."""
    sigla = ies_data["sigla"]
    nome_completo = ies_data["nome_completo"]
    cidade_sede = ies_data["cidade_sede"]
    estado = ies_data["estado"]
    return (
        f"Bem-vindo(a) à {nome_completo} ({sigla})! Somos uma das principais universidades federais do Brasil, "
        f"reconhecida pela excelência em ensino, pesquisa e extensão. Explore nossas páginas para conhecer "
        f"nossos cursos, a vida vibrante em nosso campus em {cidade_sede} - {estado}, e as oportunidades "
        f"incríveis que a {sigla} oferece para estudantes internacionais."
    )


def build_deep_replacements(ies_data: Dict[str, Any]) -> List[tuple]:
    """
    Constrói a lista ordenada de substituições textuais profundas para remover
    todos os strings UFSCar-específicos do template e substituir pelos dados reais da IES.
    
    Ordem importa: strings mais longos e específicos primeiro.
    """
    sigla = ies_data["sigla"]
    slug = ies_data["slug"]
    nome_completo = ies_data["nome_completo"]
    cidade_sede = ies_data["cidade_sede"]
    estado = ies_data["estado"]
    endereco = ies_data.get("endereco_sede", "")
    site_oficial = ies_data.get("site_oficial", "")
    
    contatos = ies_data.get("contatos_e_redes", {})
    setor_nome = contatos.get("nomenclatura_superior", f"Relações Internacionais da {sigla}")
    email_setor = contatos.get("email_setor", "")
    telefone_setor = contatos.get("telefone_setor", "")
    site_setor = contatos.get("site_setor", site_oficial)
    endereco_setor = contatos.get("endereco_setor", endereco)
    
    # Redes sociais
    redes = contatos.get("redes_sociais", [])
    instagram_url = next((r["url"] for r in redes if r["rede"] == "Instagram"), "")
    facebook_url = next((r["url"] for r in redes if r["rede"] == "Facebook"), "")
    twitter_url = next((r["url"] for r in redes if r["rede"] in ("X", "Twitter")), "")
    youtube_url = next((r["url"] for r in redes if r["rede"] == "YouTube"), "")
    
    contact_text = build_contact_section_text(ies_data)
    welcome_text = build_welcome_text(ies_data)
    
    base_url = "https://www.gov.br/studyinbrazil"
    ufscar_url = f"{base_url}/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos"
    ies_url = f"{base_url}/pt-br/instituicoes_brasileiras"
    
    # Determinar URL correta da IES (será obtida pelo container_url + slug)
    # Usamos placeholder que será resolvido depois
    
    replacements = [
        # ========================
        # 1. TEXTOS LONGOS ESPECÍFICOS (antes dos genéricos para evitar substituição parcial)
        # ========================
        
        # Texto completo de suporte com campi UFSCar
        (
            "Nossa equipe está à disposição para apoiar estudantes e parceiros internacionais em todas as etapas da experiência na UFSCar, oferecendo orientações sobre vistos e registro no Brasil, informações sobre bolsas e oportunidades de financiamento, apoio ao aprendizado de português, dicas de moradia nas cidades dos campi (São Carlos, Araras, Lagoa do Sino, Sorocaba e São José do Rio Preto), assistência em parcerias e programas de intercâmbio acadêmico, além de facilitar sua integração cultural e acadêmica à universidade e ao vibrante ecossistema científico e tecnológico da região.",
            contact_text
        ),
        # Versão parcialmente substituída (onde UFSCar→sigla e São Carlos→cidade já foram aplicados)
        (
            f"Nossa equipe está à disposição para apoiar estudantes e parceiros internacionais em todas as etapas da experiência na {sigla}, oferecendo orientações sobre vistos e registro no Brasil, informações sobre bolsas e oportunidades de financiamento, apoio ao aprendizado de português, dicas de moradia nas cidades dos campi ({cidade_sede}, Araras, Lagoa do Sino, Sorocaba e São José do Rio Preto), assistência em parcerias e programas de intercâmbio acadêmico, além de facilitar sua integração cultural e acadêmica à universidade e ao vibrante ecossistema científico e tecnológico da região.",
            contact_text
        ),
        # Fallback com Rio Branco (caso cidade_sede já tenha sido substituída)
        (
            f"dicas de moradia nas cidades dos campi ({cidade_sede}, Araras, Lagoa do Sino, Sorocaba e São José do Rio Preto)",
            f"dicas de moradia na cidade de {cidade_sede}"
        ),
        # Fallback genérico para qualquer menção ao campus UFSCar
        (
            "campi (São Carlos, Araras, Lagoa do Sino, Sorocaba e São José do Rio Preto)",
            f"campus em {cidade_sede}"
        ),
        (
            "Araras, Lagoa do Sino, Sorocaba e São José do Rio Preto",
            cidade_sede
        ),
        
        # Texto de boas-vindas UFSCar
        (
            "Bem-vindo(a) à Universidade Federal de São Carlos (UFSCar)! Somos uma das principais universidades federais do Brasil, reconhecida pela excelência em ensino, pesquisa e inovação, especialmente na área tecnológica. Explore nossas páginas para conhecer nossos cursos inovadores, a vida vibrante em nosso campus em São Carlos - SP, e as oportunidades incríveis que a UFSCar oferece para estudantes internacionais.",
            welcome_text
        ),
        # Versão parcialmente substituída
        (
            f"Bem-vindo(a) à {nome_completo} ({sigla})! Somos uma das principais universidades federais do Brasil, reconhecida pela excelência em ensino, pesquisa e inovação, especialmente na área tecnológica. Explore nossas páginas para conhecer nossos cursos inovadores, a vida vibrante em nosso campus em {cidade_sede} - {estado}, e as oportunidades incríveis que a {sigla} oferece para estudantes internacionais.",
            welcome_text
        ),
        
        # ========================
        # 2. URLs
        # ========================
        (ufscar_url + "/vida_na_ies", f"__IES_URL__/vida_na_ies"),
        (ufscar_url + "/vida-na-ies", f"__IES_URL__/vida_na_ies"),
        (ufscar_url + "/sobre-nos", f"__IES_URL__/sobre-nos"),
        (ufscar_url + "/estudantes-internacionais", f"__IES_URL__/estudantes-internacionais"),
        (ufscar_url, f"__IES_URL__"),
        ("/Plone/pt-br/instituicoes_brasileiras/regiao_sudeste/sao_paulo/ufscar-universidade-federal-de-sao-carlos", f"__PLONE_IES_URL__"),
        
        # ========================
        # 3. CONTATOS ESPECÍFICOS UFSCar
        # ========================
        
        # Email
        ("sri@ufscar.br", email_setor if email_setor else f"Para informações, consulte o site oficial: {site_oficial}"),
        ("srinter@ufscar.br", email_setor if email_setor else f"Para informações, consulte o site oficial: {site_oficial}"),
        
        # Telefone
        ("+55 16 3351-8402", telefone_setor if telefone_setor else "Consulte o site oficial"),
        ("3351-8402", telefone_setor if telefone_setor else "Consulte o site oficial"),
        
        # Site setor RI
        ("https://www.srinter.ufscar.br/pt-br/pagina-inicial", f"https://{site_setor}" if not site_setor.startswith("http") else site_setor),
        ("www.srinter.ufscar.br/pt-br/pagina-inicial", site_setor if site_setor else site_oficial),
        ("srinter.ufscar.br", site_setor if site_setor else site_oficial),
        
        # Endereço físico setor RI
        (
            "Rodovia Washington Luís, km 235 - Edifício Sérgio Mascarenhas - 2º piso - São Carlos - SP, CEP 13565-905",
            endereco_setor if endereco_setor else endereco
        ),
        (
            "Rodovia Washington Luís, km 235 - Edifício Sérgio Mascarenhas - 2º piso - Rio Branco - SP, CEP 13565-905",
            endereco_setor if endereco_setor else endereco
        ),
        
        # Endereço sede Contato Institucional
        (
            "Rodovia Washington Luís, km 235 - SP-310, São Carlos - SP, CEP 13565-905",
            endereco if endereco else endereco_setor
        ),
        
        # Site oficial UFSCar
        ("http://www.ufscar.br/", f"https://{site_oficial}" if not site_oficial.startswith("http") else site_oficial),
        ("www.ufscar.br", site_oficial),
        
        # Nome da IES (Contato Institucional block)
        ("UFSCar - Universidade Federal de São Carlos", f"{sigla} - {nome_completo}"),
        
        # ========================
        # 4. REDES SOCIAIS UFSCar
        # ========================
        
        # Instagram
        ("https://www.instagram.com/ufscaroficial/?hl=pt", instagram_url if instagram_url else ""),
        ("https://www.instagram.com/ufscaroficial", instagram_url if instagram_url else ""),
        ("ufscaroficial", sigla.lower()),
        
        # Facebook
        ("https://www.facebook.com/ufscaroficial", facebook_url if facebook_url else ""),
        
        # Mapa UFSCar (URL do Google Maps embed)
        (
            "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3699.740170538441!2d-47.88557932380326!3d-21.98293310550975",
            ies_data.get("mapa_html_embed", "").replace('<iframe width="100%" height="480" src="', "").split('"')[0] if ies_data.get("mapa_html_embed") else ""
        ),
        
        # Alts e títulos de imagens UFSCar
        ("Faixada da UFSCar do campus de São Carlos.jpg", f"Campus principal da {sigla} em {cidade_sede}"),
        ("Faixada da UFSCar do campus de ", f"Campus da {sigla} em "),
        ("mapa mostrando a loclizaçao do campus de São Carlos da UFSCar", f"Mapa de localização do campus da {sigla} em {cidade_sede}"),
        ("quadras-externas-da-ufscar-do-campus-de-sao-carlos.jpg", f"campus-da-{slug}.jpg"),
        ("Quadras Externas da UFSCar do campus de São Carlos.jpg", f"Campus da {sigla} em {cidade_sede}"),
        
        # ========================
        # 5. TEXTOS GENÉRICOS UFSCar
        # ========================
        
        ("Universidade Federal de São Carlos", nome_completo),
        ("UFSCar", sigla),
        ("São Carlos", cidade_sede),
        ("São Paulo", estado),
        ("SP,", f"{estado[:2].upper()},"),
        ("- SP,", f"- {estado[:2].upper()},"),
        ("- SP", f"- {estado[:2].upper()}"),
    ]
    
    return replacements


def apply_deep_replacements(data: Dict[str, Any], replacements: List[tuple], ies_url: str, portal_rel_path: str) -> Dict[str, Any]:
    """Serializa para JSON string, aplica substituições profundas e desserializa."""
    json_str = json.dumps(data, ensure_ascii=False)
    
    for old, new in replacements:
        if old and old in json_str:
            json_str = json_str.replace(old, new)
    
    # Resolve placeholders de URL
    json_str = json_str.replace("__IES_URL__", ies_url)
    json_str = json_str.replace("__PLONE_IES_URL__", f"/Plone/{portal_rel_path}")
    
    return json.loads(json_str)


def remove_script_added_blocks(current_data: Dict[str, Any], template_block_ids: Set[str]) -> Dict[str, Any]:
    """
    Remove da página os blocos adicionados pelo script anterior (que NÃO estão no template original).
    Mantém todos os blocos cujo ID consta no template.
    
    Retorna o data modificado.
    """
    current_blocks = dict(current_data.get("blocks", {}))
    current_layout = list(current_data.get("blocks_layout", {}).get("items", []))
    
    # Identifica blocos adicionados pelo script (IDs não presentes no template)
    added_ids = [bid for bid in current_layout if bid not in template_block_ids]
    
    removed_count = 0
    for bid in added_ids:
        btype = current_blocks.get(bid, {}).get("@type", "")
        if btype in ("slate", "SectionTitleBlock", "html"):
            # Remove da layout e do dicionário de blocos
            if bid in current_layout:
                current_layout.remove(bid)
            if bid in current_blocks:
                del current_blocks[bid]
            removed_count += 1
    
    if removed_count:
        logger.info(f"  Removidos {removed_count} blocos adicionados erroneamente pela execução anterior.")
    
    return {
        **current_data,
        "blocks": current_blocks,
        "blocks_layout": {"items": current_layout}
    }


def update_ies_content_v2(
    ies_data: Dict[str, Any],
    container_url: str,
    client: PloneRestClient,
    template_block_ids: Dict[str, Set[str]]
) -> List[Dict[str, Any]]:
    """
    v2: Corrige páginas das IES via substituição profunda de texto + remoção de blocos extras.
    """
    sigla = ies_data["sigla"]
    slug = ies_data["slug"]
    nome_completo = ies_data["nome_completo"]
    
    base_container = container_url.rstrip("/")
    ies_url = f"{base_container}/{slug}"
    portal_rel_path = ies_url.replace("https://www.gov.br/studyinbrazil/", "")
    
    report_items = []
    
    logger.info(f"\n{'='*50}")
    logger.info(f"[v2] Corrigindo IES: {sigla} ({nome_completo})")
    logger.info(f"URL: {ies_url}")
    logger.info(f"{'='*50}")
    
    deep_replacements = build_deep_replacements(ies_data)
    home_seo_desc = ies_data["metadados"]["seo_description"]
    
    # ----------------------------------------------------------------
    # 1. HOME
    # ----------------------------------------------------------------
    existing_home = client.get_content(ies_url)
    if not existing_home:
        logger.warning(f"  ⚠️ Não foi possível obter a Home da {sigla}. Pulando.")
        report_items.append({
            "timestamp": datetime.now().isoformat(), "sigla": sigla,
            "tipo_pagina": "HOME", "url": ies_url,
            "status": "ERROR", "detalhes": "Falha ao obter conteúdo existente da Home"
        })
        return report_items
    
    # Aplica deep replacement na Home existente
    home_fixed = apply_deep_replacements(existing_home, deep_replacements, ies_url, portal_rel_path)
    
    # Para HOME: remove apenas blocos slate ROOT adicionados pelo script (não os aninhados)
    home_current_layout = list(home_fixed.get("blocks_layout", {}).get("items", []))
    home_blocks = dict(home_fixed.get("blocks", {}))
    
    tmpl_home_ids = template_block_ids.get("home", set())
    root_added = [bid for bid in home_current_layout if bid not in tmpl_home_ids]
    home_removed = 0
    for bid in root_added:
        btype = home_blocks.get(bid, {}).get("@type", "")
        if btype in ("slate", "SectionTitleBlock"):
            home_current_layout.remove(bid)
            del home_blocks[bid]
            home_removed += 1
    if home_removed:
        logger.info(f"  Home: removidos {home_removed} blocos extras da execução anterior.")
    
    home_payload = {
        "@type": "Document",
        "id": slug,
        "title": f"{sigla} - {nome_completo}",
        "description": home_seo_desc,
        "blocks": home_blocks,
        "blocks_layout": {"items": home_current_layout},
        "subjects": [sigla],
        "exclude_from_nav": False
    }
    
    res_home = client.update_content(ies_url, home_payload)
    home_success = res_home is not None
    report_items.append({
        "timestamp": datetime.now().isoformat(), "sigla": sigla,
        "tipo_pagina": "HOME", "url": ies_url,
        "status": "SUCCESS" if home_success else "ERROR",
        "detalhes": "Home corrigida com dados reais da IES" if home_success else "Falha ao corrigir Home"
    })
    
    if home_success:
        retract = client.retract_to_private(ies_url)
        report_items.append({
            "timestamp": datetime.now().isoformat(), "sigla": sigla,
            "tipo_pagina": "WORKFLOW_HOME", "url": ies_url,
            "status": "SUCCESS" if retract else "ERROR",
            "detalhes": "Home mantida privada" if retract else "Falha ao definir privado"
        })
    else:
        logger.warning(f"  ⚠️ Falha na Home de {sigla}. Continuando com subpáginas mesmo assim.")
    
    # ----------------------------------------------------------------
    # 2. SUBPÁGINAS
    # ----------------------------------------------------------------
    subpages = [
        {
            "id": "sobre-nos",
            "tipo": "SOBRE",
            "template_key": "sobre_nos",
            "title": f"Sobre a {sigla}",
            "nav_title": "Sobre",
            "desc": f"Conheça a história, visão geral e pilares de excelência da {sigla}.",
        },
        {
            "id": "vida_na_ies",
            "tipo": "VIDA_NA_IES",
            "template_key": "vida_na_ies",
            "title": f"Vida na {sigla}",
            "nav_title": "Vida na IES",
            "desc": f"Infraestrutura, moradia, alimentação e convivência na {sigla}.",
        },
        {
            "id": "estudantes-internacionais",
            "tipo": "ESTUDANTES_INTERNACIONAIS",
            "template_key": "estudantes_internacionais",
            "title": f"Estudantes Internacionais na {sigla}",
            "nav_title": "Estudantes Internacionais",
            "desc": f"Informações de acolhimento, vistos e suporte aos estudantes internacionais na {sigla}.",
        },
    ]
    
    for sub in subpages:
        sub_url = f"{ies_url}/{sub['id']}"
        tmpl_ids = template_block_ids.get(sub["template_key"], set())
        
        existing_sub = client.get_content(sub_url)
        if not existing_sub:
            logger.warning(f"  ⚠️ Não encontrou {sub['id']} para {sigla}.")
            report_items.append({
                "timestamp": datetime.now().isoformat(), "sigla": sigla,
                "tipo_pagina": sub["tipo"], "url": sub_url,
                "status": "ERROR", "detalhes": f"Falha ao obter {sub['id']}"
            })
            continue
        
        # Passo 1: Aplica deep replacement
        sub_fixed = apply_deep_replacements(existing_sub, deep_replacements, ies_url, portal_rel_path)
        
        # Passo 2: Remove blocos extras adicionados pelo script anterior
        sub_fixed = remove_script_added_blocks(sub_fixed, tmpl_ids)
        
        sub_payload = {
            "@type": "Document",
            "id": sub["id"],
            "title": sub["title"],
            "nav_title": sub["nav_title"],
            "description": sub["desc"],
            "blocks": sub_fixed.get("blocks", {}),
            "blocks_layout": sub_fixed.get("blocks_layout", {}),
            "subjects": [sigla],
            "exclude_from_nav": False
        }
        
        res_sub = client.update_content(sub_url, sub_payload)
        if res_sub is None:
            res_sub = client.create_content(ies_url, sub_payload)
        
        sub_success = res_sub is not None
        report_items.append({
            "timestamp": datetime.now().isoformat(), "sigla": sigla,
            "tipo_pagina": sub["tipo"], "url": sub_url,
            "status": "SUCCESS" if sub_success else "ERROR",
            "detalhes": f"'{sub['id']}' corrigida e limpa" if sub_success else f"Falha em '{sub['id']}'"
        })
        
        if sub_success:
            retract = client.retract_to_private(sub_url)
            report_items.append({
                "timestamp": datetime.now().isoformat(), "sigla": sigla,
                "tipo_pagina": f"WORKFLOW_{sub['tipo']}", "url": sub_url,
                "status": "SUCCESS" if retract else "ERROR",
                "detalhes": f"'{sub['id']}' mantida privada" if retract else "Falha ao definir privado"
            })
    
    return report_items


def main():
    print("[v2] Iniciando correção de conteúdo estruturado das 10 IES...")
    
    if not DIAGRAMACAO_JSON.exists():
        print(f"[ERRO] {DIAGRAMACAO_JSON} não encontrado!")
        return
    
    with open(DIAGRAMACAO_JSON, "r", encoding="utf-8") as f:
        records = json.load(f)
    print(f"[+] {len(records)} IES carregadas do JSON de diagramação.")
    
    df_lista = pd.read_csv("studyinbr/lista_ies_completa.csv", sep=";", encoding="utf-8")
    if len(df_lista.columns) <= 1:
        df_lista = pd.read_csv("studyinbr/lista_ies_completa.csv", sep=",", encoding="utf-8")
    
    containers_map = {}
    for _, row in df_lista.iterrows():
        s = str(row.get("Sigla", "")).strip()
        onde = str(row.get("Onde criar", "")).strip()
        slug_col = str(row.get("nome_curto", "")).strip()
        if s and onde:
            containers_map[s.upper()] = {"container_url": onde, "slug": slug_col}
    
    templates, template_block_ids = load_templates()
    client = PloneRestClient(api_url=API_URL, token=API_TOKEN)
    
    all_reports = []
    
    for ies_item in tqdm(records, desc="Corrigindo IES"):
        sigla = ies_item["sigla"]
        sigla_alt = ies_item.get("sigla_alt", sigla)
        
        container_info = containers_map.get(sigla.upper()) or containers_map.get(sigla_alt.upper())
        if not container_info:
            logger.error(f"Container não encontrado para {sigla}. Pulando.")
            all_reports.append({
                "timestamp": datetime.now().isoformat(), "sigla": sigla,
                "tipo_pagina": "ALL", "url": "",
                "status": "ERROR", "detalhes": "Container não encontrado na planilha"
            })
            continue
        
        container_url = container_info["container_url"]
        reports = update_ies_content_v2(ies_item, container_url, client, template_block_ids)
        all_reports.extend(reports)
    
    # Salvar CSV
    df_rep = pd.DataFrame(all_reports)
    df_rep.to_csv(REPORT_PATH, index=False, sep=",", encoding="utf-8-sig")
    print(f"\n[OK] Relatório CSV: '{REPORT_PATH.resolve()}'")
    
    # Gerar HTML
    try:
        from generate_html_report_diagramacao import generate_diagramation_html_report
        generate_diagramation_html_report(csv_path=REPORT_PATH, html_path=HTML_REPORT_PATH)
        print(f"[OK] Relatório HTML: '{HTML_REPORT_PATH.resolve()}'")
    except Exception as e:
        logger.error(f"Falha ao gerar relatório HTML: {e}")


if __name__ == "__main__":
    main()
