"""
Script de Correção de Conteúdo das 10 IES Diagramadas no Plone 6
=================================================================

Corrige dois problemas do script anterior:
1. HOME: Substitui em profundidade (deep replace) todos os textos UFSCar
   que ficaram nas seções de contato, accordion e colunas de boas-vindas.
2. SUBPÁGINAS: Remove os blocos slate appendados erroneamente pelo script
   anterior e reconstrói cada subpágina com conteúdo correto da IES,
   sem duplicações.

Não mexe em banners, imagens ou carrosséis.
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

from config import API_TOKEN, API_URL
from api_client import PloneRestClient

# Logger
logger = logging.getLogger("FixDiagrammedIES")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(h)

TEMPLATES_DIR = Path("templates")
DIAGRAMACAO_DIR = Path("diagramacao")
DIAGRAMACAO_JSON = DIAGRAMACAO_DIR / "diagramacao_10_ies.json"
REPORT_PATH = Path("relatorio_correcao_10_ies.csv")
HTML_REPORT_PATH = Path("relatorio_correcao_10_ies.html")


def make_slate_block(text: str) -> Dict[str, Any]:
    return {
        "@type": "slate",
        "plaintext": text,
        "value": [{"type": "p", "children": [{"text": text}]}]
    }


def make_section_title_block(title: str, align: str = "left") -> Dict[str, Any]:
    return {"@type": "SectionTitleBlock", "align": align, "title": title}


def make_html_block(html_content: str) -> Dict[str, Any]:
    return {"@type": "html", "html": html_content}


def load_template(key: str) -> Dict[str, Any]:
    filename_map = {
        "sobre_nos": "sobre_nos.json",
        "vida_na_ies": "vida_na_ies.json",
        "estudantes_internacionais": "estudantes_internacionais.json",
    }
    p = TEMPLATES_DIR / filename_map.get(key, f"{key}.json")
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"blocks": {}, "blocks_layout": {"items": []}}


def get_template_block_ids(template: Dict[str, Any]) -> set:
    ids = set()
    def collect(blocks_dict: dict):
        for bid, bv in blocks_dict.items():
            ids.add(bid)
            if "blocks" in bv:
                collect(bv["blocks"])
            if "data" in bv and "blocks" in bv["data"]:
                col_blocks = bv["data"]["blocks"]
                collect(col_blocks)
                for col_val in col_blocks.values():
                    if isinstance(col_val, dict) and "blocks" in col_val:
                        collect(col_val["blocks"])
    collect(template.get("blocks", {}))
    return ids


def deep_replace(data: Any, replacements: Dict[str, str]) -> Any:
    """Serialize to JSON, apply all text replacements (longest first), deserialize."""
    json_str = json.dumps(data, ensure_ascii=False)
    for old_val in sorted(replacements.keys(), key=len, reverse=True):
        new_val = replacements.get(old_val)
        if old_val and new_val is not None:
            json_str = json_str.replace(old_val, new_val)
    return json.loads(json_str)


def build_ufscar_replacements(ies_data: Dict[str, Any]) -> Dict[str, str]:
    contatos = ies_data.get("contatos_e_redes", {})
    sigla = ies_data["sigla"]
    nome_completo = ies_data["nome_completo"]
    cidade_sede = ies_data.get("cidade_sede", "")
    estado = ies_data.get("estado", "")
    endereco_sede = ies_data.get("endereco_sede", "")
    site_oficial = ies_data.get("site_oficial", "")
    outros_campi = ies_data.get("outros_campi", "")

    email_setor = contatos.get("email_setor", ies_data.get("email_geral", ""))
    telefone_setor = contatos.get("telefone_setor", ies_data.get("telefone_geral", ""))
    site_setor = contatos.get("site_setor", site_oficial)
    endereco_setor = contatos.get("endereco_setor", endereco_sede)
    nomenclatura = contatos.get("nomenclatura_superior", "Relações Internacionais")

    def normalize_site(s: str) -> str:
        if s and not s.startswith("http"):
            return f"https://{s}"
        return s or ""

    campi_text = outros_campi if outros_campi else f"Campus sede em {cidade_sede}, {estado}."
    site_display = normalize_site(site_setor) or normalize_site(site_oficial)
    real_address = endereco_setor or endereco_sede

    replacements: Dict[str, str] = {}

    # Phone
    phone_replacement = telefone_setor if telefone_setor else f"Consulte o site: {site_display}"
    replacements["+55 16 3351-8402"] = phone_replacement
    replacements["16 3351-8402"] = phone_replacement

    # Email
    email_replacement = email_setor if email_setor else f"Consulte o site: {site_display}"
    replacements["sri@ufscar.br"] = email_replacement
    replacements["srinter@ufscar.br"] = email_replacement

    # Site (longest first to avoid partial match)
    replacements["https://www.srinter.ufscar.br/pt-br/pagina-inicial"] = site_display
    replacements["https://www.srinter.ufscar.br"] = site_display
    replacements["www.srinter.ufscar.br"] = site_display
    replacements["srinter.ufscar.br"] = site_display

    # Address
    if real_address:
        replacements["Rodovia Washington Luis, km 235 - Edificio Sergio Mascarenhas - 2 piso - Rio Branco - SP, CEP 13565-905."] = real_address
        replacements["Rodovia Washington Lu\u00eds, km 235 - Edif\u00edcio S\u00e9rgio Mascarenhas - 2\u00ba piso - Rio Branco - SP, CEP 13565-905."] = real_address
        replacements["Rodovia Washington Lu\u00eds, km 235"] = real_address
        replacements["Edif\u00edcio S\u00e9rgio Mascarenhas"] = ""
        replacements["CEP 13565-905"] = ""

    # Campus text (longest first)
    replacements["S\u00e3o Carlos, Araras, Sorocaba, Lagoa do Sino e S\u00e3o Jos\u00e9 do Rio Preto"] = campi_text
    replacements["Rio Branco, Araras, Lagoa do Sino, Sorocaba e S\u00e3o Jos\u00e9 do Rio Preto"] = campi_text
    replacements["Araras, Lagoa do Sino, Sorocaba e S\u00e3o Jos\u00e9 do Rio Preto"] = campi_text
    replacements["Araras, Sorocaba, Lagoa do Sino e S\u00e3o Jos\u00e9 do Rio Preto"] = campi_text
    replacements["Araras, Sorocaba e S\u00e3o Jos\u00e9 do Rio Preto"] = campi_text
    replacements["campi de S\u00e3o Carlos, Araras, Sorocaba, Lagoa do Sino e S\u00e3o Jos\u00e9 do Rio Preto"] = campi_text
    replacements["em seus campi de S\u00e3o Carlos, Araras, Sorocaba, Lagoa do Sino e S\u00e3o Jos\u00e9 do Rio Preto"] = f"no seu {campi_text}"

    # Sector name
    replacements["Secretaria de Rela\u00e7\u00f5es Internacionais (SRI)"] = nomenclatura
    replacements["Secretaria de Rela\u00e7\u00f5es Internacionais"] = nomenclatura
    replacements["SRINTER"] = nomenclatura

    # Institution name (longest first)
    replacements["UFSCar - Universidade Federal de S\u00e3o Carlos"] = f"{sigla} - {nome_completo}"
    replacements["Universidade Federal de S\u00e3o Carlos (UFSCar)"] = f"{nome_completo} ({sigla})"
    replacements["Universidade Federal de S\u00e3o Carlos"] = nome_completo
    replacements["UFSCar"] = sigla

    # URL replacements for ufscar slug
    replacements["ufscar-universidade-federal-de-sao-carlos"] = ies_data.get("slug", sigla.lower())

    return replacements


def remove_appended_slate_blocks(
    current_page_data: Dict[str, Any],
    template: Dict[str, Any]
) -> Dict[str, Any]:
    """Remove slate/SectionTitle blocks NOT present in the original template (appended by previous script)."""
    template_block_ids = get_template_block_ids(template)
    blocks = dict(current_page_data.get("blocks", {}))
    layout = list(current_page_data.get("blocks_layout", {}).get("items", []))

    foreign_ids = [bid for bid in layout if bid not in template_block_ids]
    removed = 0
    for bid in foreign_ids:
        bv = blocks.get(bid, {})
        btype = bv.get("@type", "")
        if btype in ("slate", "SectionTitleBlock"):
            blocks.pop(bid, None)
            layout.remove(bid)
            removed += 1
        elif btype == "html":
            html_content = bv.get("html", "")
            # Remove appended html blocks UNLESS they are Google Maps iframes or anchor divs
            if "maps.google.com" not in html_content and 'id="' not in html_content:
                blocks.pop(bid, None)
                layout.remove(bid)
                removed += 1

    if removed:
        logger.info(f"  Removidos {removed} blocos appendados erroneamente")

    result = dict(current_page_data)
    result["blocks"] = blocks
    result["blocks_layout"] = {"items": layout}
    return result


SECTION_TITLE_MARKERS = {
    "Historico e Legado", "Histórico e Legado",
    "Destaques Academicos e Reconhecimentos", "Destaques Acadêmicos e Reconhecimentos",
    "Nossos Pilares de Excelencia", "Nossos Pilares de Excelência",
    "Por que estudar nesta instituicao?", "Por que estudar nesta instituição?",
    "Infraestrutura Completa para o seu Desenvolvimento",
    "Suporte Integral ao Estudante Internacional",
    "Internacionalizacao e Acolhimento", "Internacionalização e Acolhimento",
    "Cursos de Portugues para Estrangeiros (PLE)", "Cursos de Português para Estrangeiros (PLE)",
    "Perguntas Frequentes (FAQ)", "Custo de Vida e Alojamento",
    "Viver em Rio Branco", "Viver em", "Por Que Estudar",
}


def is_section_title(text: str) -> bool:
    t = text.strip().rstrip(":")
    return (
        t in SECTION_TITLE_MARKERS
        or (len(t) < 70 and text.strip().endswith(":"))
    )


def build_subpage_from_paragraphs(
    template: Dict[str, Any],
    paragraphs: List[str],
    replacements: Dict[str, str],
    map_iframe: str = "",
    add_map_if_missing: bool = False,
) -> Dict[str, Any]:
    """
    Build subpage by:
    1. Deep-replacing UFSCar values in template
    2. Replacing slate block texts with IES-specific paragraphs
    3. Appending remaining paragraphs if template has fewer slots
    4. Optionally adding map if missing
    """
    replaced = deep_replace(template, replacements)
    blocks = replaced.get("blocks", {})
    layout = list(replaced.get("blocks_layout", {}).get("items", []))

    para_queue = list(paragraphs)

    def replace_text_in_blocks(blocks_dict: dict):
        for bid, bv in blocks_dict.items():
            if not para_queue:
                break
            btype = bv.get("@type", "")
            if btype == "slate":
                text = para_queue.pop(0)
                bv["plaintext"] = text
                bv["value"] = [{"type": "p", "children": [{"text": text}]}]
            elif btype == "SectionTitleBlock":
                text = para_queue.pop(0)
                bv["title"] = text.strip().rstrip(":")
            # Recurse into columnsBlock nested blocks
            if "blocks" in bv:
                replace_text_in_blocks(bv["blocks"])
            if "data" in bv and "blocks" in bv["data"]:
                for col_val in bv["data"]["blocks"].values():
                    if isinstance(col_val, dict) and "blocks" in col_val:
                        replace_text_in_blocks(col_val["blocks"])

    replace_text_in_blocks(blocks)

    # Append remaining paragraphs that didn't fit in template slots
    for para in para_queue:
        para = para.strip()
        if not para:
            continue
        block_id = str(uuid.uuid4())
        if is_section_title(para):
            blocks[block_id] = make_section_title_block(para.rstrip(":"))
        else:
            blocks[block_id] = make_slate_block(para)
        layout.append(block_id)

    # Add map if missing
    if add_map_if_missing and map_iframe:
        has_map = any(
            bv.get("@type") == "html" and "maps.google.com" in bv.get("html", "")
            for bv in blocks.values()
        )
        if not has_map:
            map_id = str(uuid.uuid4())
            blocks[map_id] = make_html_block(map_iframe)
            layout.append(map_id)

    return {"blocks": blocks, "blocks_layout": {"items": layout}}


PLONE_INTERNAL_FIELDS = {
    "@components", "@id", "UID", "created", "modified",
    "review_state", "allow_discussion", "contributors",
    "creators", "effective", "expires", "is_folderish",
    "language", "parent", "relatedItems", "version",
    "changeNote", "@type",
}


def fix_ies_content(
    ies_data: Dict[str, Any],
    container_url: str,
    client: PloneRestClient,
) -> List[Dict[str, Any]]:
    report_items = []
    sigla = ies_data["sigla"]
    nome_completo = ies_data["nome_completo"]
    slug = ies_data.get("slug", sigla.lower().replace("_", "-").replace(" ", "-"))
    mapa_iframe = ies_data.get("mapa_html_embed", "")
    ies_url = f"{container_url.rstrip('/')}/{slug}"

    logger.info("=" * 50)
    logger.info(f"Corrigindo: {sigla} ({nome_completo})")
    logger.info(f"URL: {ies_url}")
    logger.info("=" * 50)

    replacements = build_ufscar_replacements(ies_data)

    # ── HOME ─────────────────────────────────────────────────────────────────
    logger.info("[Home] GET conteúdo atual...")
    existing_home = client.get_content(ies_url)
    if not existing_home:
        logger.error(f"[Home] GET falhou para {sigla}. Pulando.")
        report_items.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla, "tipo_pagina": "HOME", "url": ies_url,
            "status": "ERROR", "detalhes": "GET falhou – página não encontrada"
        })
        return report_items

    fixed_home = deep_replace(existing_home, replacements)
    payload_home = {k: v for k, v in fixed_home.items() if k not in PLONE_INTERNAL_FIELDS}
    payload_home["title"] = f"{sigla} - {nome_completo}"

    res_home = client.update_content(ies_url, payload_home)
    home_success = res_home is not None
    report_items.append({
        "timestamp": datetime.now().isoformat(),
        "sigla": sigla, "tipo_pagina": "HOME", "url": ies_url,
        "status": "SUCCESS" if home_success else "ERROR",
        "detalhes": "Home corrigida: deep replace UFSCar→IES" if home_success else "Falha ao corrigir Home"
    })
    if home_success:
        r = client.retract_to_private(ies_url)
        report_items.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla, "tipo_pagina": "WORKFLOW_PRIVATE_HOME", "url": ies_url,
            "status": "SUCCESS" if r else "ERROR",
            "detalhes": "Home mantida privada" if r else "Falha ao definir privado"
        })
    else:
        return report_items

    # ── SUBPAGES ─────────────────────────────────────────────────────────────
    subpages_configs = [
        {
            "id": "sobre-nos",
            "tipo_key": "sobre",
            "template_key": "sobre_nos",
            "title": f"Sobre a {sigla}",
            "nav_title": "Sobre",
            "desc": f"História, visão geral e pilares de excelência da {sigla}.",
            "add_map": False,
        },
        {
            "id": "vida_na_ies",
            "tipo_key": "vida_na_ies",
            "template_key": "vida_na_ies",
            "title": f"Vida na {sigla}",
            "nav_title": "Vida na IES",
            "desc": f"Infraestrutura, moradia, alimentação e convivência na {sigla}.",
            "add_map": False,
        },
        {
            "id": "estudantes-internacionais",
            "tipo_key": "estudantes_internacionais",
            "template_key": "estudantes_internacionais",
            "title": f"Estudantes Internacionais na {sigla}",
            "nav_title": "Estudantes Internacionais",
            "desc": f"Suporte integral ao estudante internacional na {sigla}.",
            "add_map": True,
        },
    ]

    for sub in subpages_configs:
        sub_id = sub["id"]
        sub_url = f"{ies_url}/{sub_id}"
        sub_data = ies_data.get("paginas", {}).get(sub["tipo_key"], {})
        sub_paragraphs = sub_data.get("paragrafos", [])
        template = load_template(sub["template_key"])

        logger.info(f"[{sub['tipo_key'].upper()}] Processando: {sub_url}")
        existing_sub = client.get_content(sub_url)

        if existing_sub:
            # Remove appended blocks from previous script run
            cleaned = remove_appended_slate_blocks(existing_sub, template)
            # Deep replace UFSCar values in what remains
            fixed_sub = deep_replace(cleaned, replacements)
            # Rebuild text slots with IES paragraphs (no-op replacements since already applied)
            rebuilt = build_subpage_from_paragraphs(
                template=fixed_sub,
                paragraphs=sub_paragraphs,
                replacements={},
                map_iframe=mapa_iframe,
                add_map_if_missing=sub["add_map"],
            )
            sub_payload = {k: v for k, v in fixed_sub.items() if k not in PLONE_INTERNAL_FIELDS}
            sub_payload["title"] = sub["title"]
            sub_payload["nav_title"] = sub["nav_title"]
            sub_payload["description"] = sub["desc"]
            sub_payload["blocks"] = rebuilt["blocks"]
            sub_payload["blocks_layout"] = rebuilt["blocks_layout"]
            sub_payload["subjects"] = [sigla]
            res_sub = client.update_content(sub_url, sub_payload)
        else:
            # Page doesn't exist: build from template and create
            rebuilt = build_subpage_from_paragraphs(
                template=template,
                paragraphs=sub_paragraphs,
                replacements=replacements,
                map_iframe=mapa_iframe,
                add_map_if_missing=sub["add_map"],
            )
            sub_payload = {
                "@type": "Document",
                "id": sub_id,
                "title": sub["title"],
                "nav_title": sub["nav_title"],
                "description": sub["desc"],
                "blocks": rebuilt["blocks"],
                "blocks_layout": rebuilt["blocks_layout"],
                "subjects": [sigla],
                "exclude_from_nav": False,
            }
            res_sub = client.create_content(ies_url, sub_payload)

        sub_success = res_sub is not None
        report_items.append({
            "timestamp": datetime.now().isoformat(),
            "sigla": sigla,
            "tipo_pagina": sub["tipo_key"].upper(),
            "url": sub_url,
            "status": "SUCCESS" if sub_success else "ERROR",
            "detalhes": (
                f"'{sub_id}' corrigida: removed appended blocks + deep replace"
                if sub_success else f"Falha ao corrigir '{sub_id}'"
            ),
        })
        if sub_success:
            r = client.retract_to_private(sub_url)
            report_items.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla,
                "tipo_pagina": f"WORKFLOW_PRIVATE_{sub['tipo_key'].upper()}",
                "url": sub_url,
                "status": "SUCCESS" if r else "ERROR",
                "detalhes": f"'{sub_id}' mantida privada" if r else "Falha ao definir privado",
            })

    return report_items


def generate_html_report(all_reports: List[Dict]) -> None:
    df = pd.DataFrame(all_reports)
    total = len(df)
    total_success = int((df["status"] == "SUCCESS").sum()) if total else 0
    total_error = int((df["status"] == "ERROR").sum()) if total else 0
    success_rate = round(total_success / total * 100, 1) if total else 0
    ies_count = df["sigla"].nunique() if total else 0

    if total:
        ies_stats = (
            df.groupby("sigla")
            .agg(
                total=("status", "count"),
                sucesso=("status", lambda x: (x == "SUCCESS").sum()),
                erro=("status", lambda x: (x == "ERROR").sum())
            )
            .reset_index()
        )
        ies_stats["taxa"] = (ies_stats["sucesso"] / ies_stats["total"] * 100).round(1)
        ies_stats = ies_stats.sort_values(["erro", "sigla"], ascending=[False, True])
        records_json = df.to_json(orient="records", force_ascii=False)
        ies_stats_json = ies_stats.to_json(orient="records", force_ascii=False)
    else:
        records_json = "[]"
        ies_stats_json = "[]"

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Relatório de Correção • 10 IES • Study in Brazil</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Outfit:wght@700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--border:#334155;--txt:#f8fafc;--muted:#94a3b8;--blue:#38bdf8;--green:#22c55e;--red:#ef4444;--purple:#a855f7}}
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Plus Jakarta Sans',sans-serif}}
body{{background:var(--bg);color:var(--txt);min-height:100vh;padding:2rem}}
.container{{max-width:1400px;margin:0 auto}}
header{{display:flex;justify-content:space-between;align-items:center;padding-bottom:1.5rem;border-bottom:1px solid var(--border);margin-bottom:2rem;flex-wrap:wrap;gap:1rem}}
h1{{font-family:'Outfit',sans-serif;font-size:2rem;font-weight:800;background:linear-gradient(135deg,var(--blue),var(--purple));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.subtitle{{color:var(--muted);font-size:.9rem;margin-top:.25rem}}
.badge{{background:rgba(56,189,248,.1);color:var(--blue);padding:.4rem .9rem;border-radius:9999px;font-size:.8rem;font-weight:600;border:1px solid rgba(56,189,248,.3)}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem;margin-bottom:2rem}}
.kpi{{background:var(--card);border:1px solid var(--border);border-radius:.75rem;padding:1.25rem}}
.kpi h3{{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:.4rem}}
.kpi .val{{font-family:'Outfit',sans-serif;font-size:2rem;font-weight:700}}
.kpi .sub{{color:var(--muted);font-size:.8rem;margin-top:.2rem}}
.kpi.ok .val{{color:var(--green)}} .kpi.err .val{{color:var(--red)}}
.charts{{display:grid;grid-template-columns:2fr 1fr;gap:1.5rem;margin-bottom:2rem}}
@media(max-width:900px){{.charts{{grid-template-columns:1fr}}}}
.chart-box{{background:var(--card);border:1px solid var(--border);border-radius:.75rem;padding:1.5rem}}
.chart-box h2{{font-size:1.1rem;font-weight:700;margin-bottom:1rem}}
.chart-container{{position:relative;height:260px}}
.table-section{{background:var(--card);border:1px solid var(--border);border-radius:.75rem;padding:1.5rem;margin-bottom:2rem}}
.controls{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.75rem;margin-bottom:1rem}}
.search{{position:relative;flex:1;max-width:380px}}
.search input{{width:100%;background:rgba(15,23,42,.6);border:1px solid var(--border);border-radius:.5rem;padding:.6rem .9rem .6rem 2.2rem;color:var(--txt);font-size:.9rem;outline:none}}
.search input:focus{{border-color:var(--blue)}}
.search svg{{position:absolute;left:.75rem;top:50%;transform:translateY(-50%);width:14px;height:14px;fill:var(--muted)}}
.filters{{display:flex;gap:.5rem}}
.btn{{background:rgba(30,41,59,.6);border:1px solid var(--border);color:var(--muted);padding:.45rem .9rem;border-radius:.5rem;font-size:.8rem;font-weight:600;cursor:pointer;transition:.2s}}
.btn:hover{{color:var(--txt)}} .btn.active{{background:var(--blue);color:#0f172a;border-color:var(--blue)}}
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th{{background:rgba(30,41,59,.5);padding:.75rem 1rem;color:var(--muted);font-weight:600;border-bottom:1px solid var(--border)}}
td{{padding:.75rem 1rem;border-bottom:1px solid rgba(51,65,85,.4)}}
tr:hover td{{background:rgba(56,189,248,.03)}}
.tag{{display:inline-flex;align-items:center;padding:.25rem .65rem;border-radius:9999px;font-weight:700;font-size:.75rem}}
.tag.ok{{background:rgba(34,197,94,.12);color:var(--green);border:1px solid rgba(34,197,94,.3)}}
.tag.err{{background:rgba(239,68,68,.12);color:var(--red);border:1px solid rgba(239,68,68,.3)}}
.url-link{{color:var(--blue);text-decoration:none;font-family:monospace;font-size:.75rem}}
.url-link:hover{{text-decoration:underline}}
footer{{text-align:center;color:var(--muted);font-size:.8rem;padding:1.5rem 0;border-top:1px solid var(--border)}}
</style>
</head>
<body>
<div class="container">
  <header>
    <div>
      <h1>Painel de Correção • 10 IES</h1>
      <p class="subtitle">Deep replace UFSCar→IES + remoção de blocos errôneos • Study in Brazil / Plone 6</p>
    </div>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap">
      <div class="badge">🔒 100% Privado</div>
      <div class="badge">🔄 Deep Replace Aplicado</div>
    </div>
  </header>
  <div class="kpi-grid">
    <div class="kpi"><h3>Total de Operações</h3><div class="val">{total}</div><div class="sub">Home + 3 Subpáginas + Workflows</div></div>
    <div class="kpi"><h3>Instituições</h3><div class="val">{ies_count}</div><div class="sub">CEFET-MG · UFAC · UFAPE · UFJ · UFMS · UFRPE · UFRR · UFS · UFSB · UFSC</div></div>
    <div class="kpi ok"><h3>Sucessos</h3><div class="val">{total_success}</div><div class="sub">{success_rate}% de taxa de sucesso</div></div>
    <div class="kpi {'err' if total_error > 0 else 'ok'}"><h3>Falhas</h3><div class="val">{total_error}</div><div class="sub">Requerem atenção</div></div>
  </div>
  <div class="charts">
    <div class="chart-box"><h2>📊 Status por IES</h2><div class="chart-container"><canvas id="barChart"></canvas></div></div>
    <div class="chart-box"><h2>🎯 Proporção Geral</h2><div class="chart-container"><canvas id="pieChart"></canvas></div></div>
  </div>
  <div class="table-section">
    <div class="controls">
      <div class="search">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.5 6.5 0 1 0 14 15.5l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <input type="text" id="searchInput" placeholder="Buscar por Sigla, Tipo, Detalhes...">
      </div>
      <div class="filters">
        <button class="btn active" onclick="filterData('ALL',this)">Todos ({total})</button>
        <button class="btn" onclick="filterData('SUCCESS',this)">Sucesso ({total_success})</button>
        <button class="btn" onclick="filterData('ERROR',this)">Erros ({total_error})</button>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Timestamp</th><th>Sigla</th><th>Tipo</th><th>Status</th><th>Detalhes</th><th>URL</th></tr></thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>
  <footer>Gerado automaticamente • PloneRestClient • Study in Brazil</footer>
</div>
<script>
const rawData={records_json};
const iesStats={ies_stats_json};
let currentFilter='ALL';
function renderTable(data){{
  const tbody=document.getElementById('tableBody');
  tbody.innerHTML='';
  data.forEach(row=>{{
    const tr=document.createElement('tr');
    const ok=row.status==='SUCCESS';
    const d=new Date(row.timestamp).toLocaleString('pt-BR');
    tr.innerHTML=`<td>${{d}}</td><td><strong>${{row.sigla}}</strong></td><td>${{row.tipo_pagina}}</td><td><span class="tag ${{ok?'ok':'err'}}">${{ok?'✓ OK':'✕ ERR'}}</span></td><td>${{row.detalhes}}</td><td><a href="${{row.url}}" target="_blank" class="url-link">${{row.url}}</a></td>`;
    tbody.appendChild(tr);
  }});
}}
function filterData(status,btn){{
  currentFilter=status;
  document.querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
  if(btn)btn.classList.add('active');
  applyFilters();
}}
function applyFilters(){{
  const q=document.getElementById('searchInput').value.toLowerCase();
  const f=rawData.filter(r=>{{
    const ms=currentFilter==='ALL'||r.status===currentFilter;
    const mq=!q||[r.sigla,r.tipo_pagina,r.detalhes,r.url].some(v=>v&&v.toLowerCase().includes(q));
    return ms&&mq;
  }});
  renderTable(f);
}}
document.getElementById('searchInput').addEventListener('input',applyFilters);
document.addEventListener('DOMContentLoaded',()=>{{
  renderTable(rawData);
  new Chart(document.getElementById('barChart'),{{type:'bar',data:{{labels:iesStats.map(i=>i.sigla),datasets:[{{label:'Sucesso',data:iesStats.map(i=>i.sucesso),backgroundColor:'rgba(34,197,94,.8)',borderRadius:4}},{{label:'Erro',data:iesStats.map(i=>i.erro),backgroundColor:'rgba(239,68,68,.8)',borderRadius:4}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{x:{{stacked:true,grid:{{color:'rgba(51,65,85,.2)'}},ticks:{{color:'#94a3b8'}}}},y:{{stacked:true,grid:{{color:'rgba(51,65,85,.2)'}},ticks:{{color:'#94a3b8'}}}}}},plugins:{{legend:{{labels:{{color:'#f8fafc'}}}}}}}}}});
  new Chart(document.getElementById('pieChart'),{{type:'doughnut',data:{{labels:['Sucesso','Erro'],datasets:[{{data:[{total_success},{total_error}],backgroundColor:['#22c55e','#ef4444'],borderWidth:0}}]}},options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{position:'bottom',labels:{{color:'#f8fafc'}}}}}}}}}});
}});
</script>
</body>
</html>"""

    with open(HTML_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"[OK] Relatório HTML gerado em: '{HTML_REPORT_PATH.resolve()}'")


def main():
    print("[+] Iniciando correção profunda das 10 IES diagramadas...")

    if not DIAGRAMACAO_JSON.exists():
        logger.error(f"'{DIAGRAMACAO_JSON}' não encontrado! Execute generate_diagramation_data.py primeiro.")
        return

    with open(DIAGRAMACAO_JSON, "r", encoding="utf-8") as f:
        records = json.load(f)
    print(f"[+] {len(records)} IES carregadas.")

    df_lista = pd.read_csv("studyinbr/lista_ies_completa.csv", sep=";", encoding="utf-8")
    if len(df_lista.columns) <= 1:
        df_lista = pd.read_csv("studyinbr/lista_ies_completa.csv", sep=",", encoding="utf-8")

    containers_map: Dict[str, str] = {}
    for _, row in df_lista.iterrows():
        s = str(row.get("Sigla", "")).strip().upper()
        onde = str(row.get("Onde criar", "")).strip()
        if s and onde:
            containers_map[s] = onde

    client = PloneRestClient(api_url=API_URL, token=API_TOKEN)
    all_reports: List[Dict] = []

    for ies_item in tqdm(records, desc="Corrigindo IES no Plone 6"):
        sigla = ies_item["sigla"]
        sigla_alt = ies_item.get("sigla_alt", sigla)
        container_url = (
            containers_map.get(sigla.upper())
            or containers_map.get(sigla_alt.upper())
        )
        if not container_url:
            logger.error(f"Container não encontrado para {sigla}. Pulando...")
            all_reports.append({
                "timestamp": datetime.now().isoformat(),
                "sigla": sigla, "tipo_pagina": "ALL", "url": "",
                "status": "ERROR", "detalhes": "Container 'Onde criar' não encontrado",
            })
            continue
        reports = fix_ies_content(ies_item, container_url, client)
        all_reports.extend(reports)

    df_rep = pd.DataFrame(all_reports)
    df_rep.to_csv(REPORT_PATH, index=False, sep=",", encoding="utf-8-sig")
    print(f"\n[OK] CSV salvo em: '{REPORT_PATH.resolve()}'")

    generate_html_report(all_reports)
    print(f"[OK] HTML salvo em: '{HTML_REPORT_PATH.resolve()}'")


if __name__ == "__main__":
    main()
