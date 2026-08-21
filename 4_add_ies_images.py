"""
Script para Adição Automática de Imagens nas IES (4_add_ies_images.py)
======================================================================

Este script lê a pasta `img/`, identifica as IES e faz o upload das imagens:
- _00: Logo -> preview_image e icone_card da página principal.
- _01: Boas vindas -> coluna esquerda do bloco de 2 colunas.
- _02, _03, _04: Carrossel -> carouselBlock da página principal.
"""

import os
import glob
import base64
import logging
from pathlib import Path
import pandas as pd
from tqdm import tqdm

from config import API_TOKEN, API_URL, EXCEL_PATH, IGNORED_IES
from api_client import PloneRestClient

# Configuração do Logger
logger = logging.getLogger("AddIESImages")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def load_dataset(data_path_str: str) -> pd.DataFrame:
    path = Path(data_path_str)
    if not path.exists():
        fallback_path = Path("studyinbr") / path.name
        if fallback_path.exists():
            path = fallback_path

    if not path.exists():
        raise FileNotFoundError(f"Arquivo de dados não encontrado: {data_path_str}")

    logger.info(f"Carregando dados de: {path}")

    if path.suffix.lower() == ".csv":
        try:
            df = pd.read_csv(path, sep=";", encoding="utf-8")
            if len(df.columns) <= 1:
                df = pd.read_csv(path, sep=",", encoding="utf-8")
        except Exception:
            df = pd.read_csv(path, sep=",", encoding="utf-8")
    else:
        df = pd.read_excel(path)

    return df

def get_image_base64(filepath: str) -> dict:
    """Lê um arquivo de imagem e retorna o dicionário no padrão Volto."""
    with open(filepath, "rb") as f:
        data = f.read()
    
    ext = filepath.split(".")[-1].lower()
    content_type = "image/jpeg"
    if ext == "png": content_type = "image/png"
    elif ext == "webp": content_type = "image/webp"
    elif ext == "gif": content_type = "image/gif"
    
    return {
        "data": base64.b64encode(data).decode("utf-8"),
        "encoding": "base64",
        "content-type": content_type,
        "filename": os.path.basename(filepath)
    }

def main():
    print("[+] Inicializando processo de adição de imagens de IES...")

    df = load_dataset(EXCEL_PATH)
    client = PloneRestClient(api_url=API_URL, token=API_TOKEN)

    img_dir = Path("img")
    if not img_dir.exists():
        logger.error("Pasta 'img' não encontrada.")
        return

    ies_folders = [f for f in img_dir.iterdir() if f.is_dir()]
    print(f"[+] Total de pastas (IES) encontradas em img/: {len(ies_folders)}\n")

    for ies_folder in tqdm(ies_folders, desc="Processando IES"):
        sigla = ies_folder.name

        if sigla.upper() in [x.upper() for x in IGNORED_IES]:
            logger.info(f"⏭️ IES {sigla} ignorada (ajustada manualmente). Pulando upload de imagens...")
            continue
        
        # Encontrar a IES no dataframe
        match = df[df["Sigla"] == sigla]
        if match.empty:
            logger.warning(f"IES {sigla} não encontrada na planilha. Pulando...")
            continue
            
        row = match.iloc[0]
        slug = str(row.get("nome_curto", "")).strip()
        container_url = str(row.get("Onde criar", "")).strip()
        ies_url = f"{container_url.rstrip('/')}/{slug}"
        
        logger.info(f"\n--- Processando {sigla} ({ies_url}) ---")
        
        # Obter o documento atual
        target_url = client._resolve_url(ies_url)
        resp = client.session.get(target_url, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            logger.error(f"Erro ao obter página da IES ({resp.status_code}). Pulando...")
            continue
            
        doc_data = resp.json()
        blocks = doc_data.get("blocks", {})
        blocks_layout = doc_data.get("blocks_layout", {}).get("items", [])
        
        needs_patch = False
        patch_payload = {}
        updated_blocks = blocks.copy()

        # 1. Processar Logo (_00)
        logo_files = glob.glob(str(ies_folder / f"{sigla}_00.*"))
        if logo_files:
            logo_path = logo_files[0]
            logger.info(f"Fazendo upload do Logo: {logo_path}")
            fn = os.path.basename(logo_path)
            
            # Upload como objeto Image dentro da IES
            logo_img_payload = {
                "@type": "Image",
                "title": fn,
                "alt": f"{sigla}_logo",
                "image": get_image_base64(logo_path)
            }
            created_logo = client.create_content(ies_url, logo_img_payload)
            if created_logo:
                logo_url = created_logo.get("@id")
                client.retract_to_private(logo_url)
                
                # Atualiza campos do documento (Preview Image e Card)
                patch_payload["preview_image"] = get_image_base64(logo_path)
                patch_payload["icone_card"] = logo_url  # icone_card é TextLine (string URL)
                patch_payload["alt_card"] = f"{sigla}_logo"
                needs_patch = True
            else:
                # Fallback caso a criação falhe
                patch_payload["preview_image"] = get_image_base64(logo_path)
                patch_payload["alt_card"] = f"{sigla}_logo"
                needs_patch = True
        
        # 2. Processar Boas Vindas (_01)
        welcome_files = glob.glob(str(ies_folder / f"{sigla}_01.*"))
        if welcome_files:
            welcome_path = welcome_files[0]
            logger.info(f"Processando Boas-vindas: {welcome_path}")
            
            fn = os.path.basename(welcome_path)
            welcome_img_payload = {
                "@type": "Image",
                "title": fn,
                "alt": f"Boas-vindas {sigla}",
                "image": get_image_base64(welcome_path)
            }
            
            # Upload para dentro da pasta da IES
            created_img = client.create_content(ies_url, welcome_img_payload)
            if created_img:
                img_url = created_img.get("@id")
                client.retract_to_private(img_url)
                
                # Encontrar o bloco de imagem abaixo de "Sejam bem-vindos"
                for b_id, block in updated_blocks.items():
                    if block.get("@type") == "columnsBlock":
                        inner_blocks = block.get("data", {}).get("blocks", {})
                        for inner_id, inner_block in inner_blocks.items():
                            sub_blocks = inner_block.get("blocks", {})
                            for sub_id, sub_block in sub_blocks.items():
                                if sub_block.get("@type") == "image":
                                    sub_block["url"] = img_url
                                    needs_patch = True
                                    logger.info(f"Bloco de boas-vindas atualizado com @id: {img_url}")

        # 3. Processar Carrossel (_02, _03, _04)
        carousel_files = glob.glob(str(ies_folder / f"{sigla}_0[234].*"))
        if carousel_files:
            carousel_block_id = None
            for b_id, block in updated_blocks.items():
                if block.get("@type") == "carouselBlock":
                    carousel_block_id = b_id
                    break
            
            if carousel_block_id:
                logger.info("Atualizando carrossel...")
                columns = updated_blocks[carousel_block_id].get("columns", [])
                
                for idx, c_path in enumerate(sorted(carousel_files)):
                    fn = os.path.basename(c_path)
                    c_img_payload = {
                        "@type": "Image",
                        "title": fn,
                        "alt": f"Banner {idx+1} {sigla}",
                        "image": get_image_base64(c_path)
                    }
                    created_img = client.create_content(ies_url, c_img_payload)
                    
                    if created_img:
                        img_url = created_img.get("@id")
                        client.retract_to_private(img_url)
                        
                        if idx < len(columns):
                            col = columns[idx]
                            if "customized" not in col:
                                col["customized"] = {}
                            col["customized"]["preview_image_desktop"] = {
                                "@id": img_url,
                                "alt": f"Banner {idx+1} {sigla}"
                            }
                            needs_patch = True
            else:
                logger.warning("carouselBlock não encontrado nesta página.")

        if needs_patch:
            if "blocks" not in patch_payload:
                patch_payload["blocks"] = updated_blocks
            patch_payload["blocks_layout"] = {"items": blocks_layout}
            
            logger.info("Enviando PATCH para a página principal da IES...")
            patch_res = client.update_content(ies_url, patch_payload)
            if patch_res is not None:
                logger.info(f"✅ IES {sigla} atualizada com sucesso.")
            else:
                logger.error(f"❌ Falha ao atualizar IES {sigla}.")

if __name__ == "__main__":
    main()
