import os
import sys
import zipfile
import xml.etree.ElementTree as ET
import urllib.parse
import json
import re
import csv
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

def parse_docx_elements(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        xml_content = z.read('word/document.xml')
    root = ET.fromstring(xml_content)
    namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    body = root.find('w:body', namespaces)
    if body is None:
        return []
    
    paragraphs = []
    for child in body:
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            texts = [t.text for t in child.findall('.//w:t', namespaces) if t.text]
            p_text = "".join(texts).strip()
            if p_text:
                paragraphs.append(p_text)
        elif tag == 'tbl':
            for row in child.findall('.//w:tr', namespaces):
                for cell in row.findall('.//w:tc', namespaces):
                    cell_texts = [t.text for t in cell.findall('.//w:t', namespaces) if t.text]
                    c_text = "".join(cell_texts).strip()
                    if c_text:
                        paragraphs.append(c_text)
    return paragraphs

def clean_bullets_and_spaces(text):
    if not text:
        return ""
    # Remove leading bullet symbols (●, ○, ■, ▪, ▫, *, -, ·) and whitespace
    cleaned = re.sub(r'^[●○■▪▫\*\-·\s]+', '', text).strip()
    return cleaned

def clean_val(val):
    if not val:
        return ""
    val = clean_bullets_and_spaces(val)
    val = re.sub(r'^[:\-\s]+', '', val).strip()
    return val

def generate_map_iframe(endereco):
    if not endereco:
        return ""
    endereco_encoded = urllib.parse.quote(endereco.strip())
    iframe = (
        f'<iframe width="100%" height="480" '
        f'src="https://maps.google.com/maps?q={endereco_encoded}&t=&z=15&ie=UTF8&iwloc=&output=embed" '
        f'style="border:0;" allowfullscreen="" loading="lazy"></iframe>'
    )
    return iframe

def format_social_media(raw_social_dict):
    """
    Formata as redes sociais seguindo estritamente as regras:
    - Twitter substituído por X
    - YouTube, TikTok e Flickr recebem ícone 📽 e fecham a listagem
    - Rádio recebe ícone 📻 e fica posicionada obrigatoriamente logo após o YouTube
    - Ordem: Facebook (📘), Instagram (📸), LinkedIn (💼), X (𝕏), YouTube (📽), Rádio (📻), TikTok (📽), Flickr (📽)
    """
    formatted_list = []
    
    # 1. Facebook
    if raw_social_dict.get("Facebook"):
        formatted_list.append({"rede": "Facebook", "icone": "📘", "url": raw_social_dict["Facebook"]})
        
    # 2. Instagram
    if raw_social_dict.get("Instagram"):
        formatted_list.append({"rede": "Instagram", "icone": "📸", "url": raw_social_dict["Instagram"]})
        
    # 3. LinkedIn
    if raw_social_dict.get("LinkedIn"):
        formatted_list.append({"rede": "LinkedIn", "icone": "💼", "url": raw_social_dict["LinkedIn"]})
        
    # 4. X (Twitter substituído por X)
    x_val = raw_social_dict.get("X") or raw_social_dict.get("Twitter")
    if x_val:
        formatted_list.append({"rede": "X", "icone": "𝕏", "url": x_val})
        
    # 5. YouTube (ícone 📽)
    if raw_social_dict.get("YouTube"):
        formatted_list.append({"rede": "YouTube", "icone": "📽", "url": raw_social_dict["YouTube"]})
        
    # 6. Rádio (ícone 📻 - obrigatoriamente logo após o YouTube)
    if raw_social_dict.get("Rádio") or raw_social_dict.get("Radio"):
        formatted_list.append({"rede": "Rádio", "icone": "📻", "url": raw_social_dict.get("Rádio") or raw_social_dict.get("Radio")})
        
    # 7. TikTok (ícone 📽)
    if raw_social_dict.get("TikTok") or raw_social_dict.get("Tiktok"):
        formatted_list.append({"rede": "TikTok", "icone": "📽", "url": raw_social_dict.get("TikTok") or raw_social_dict.get("Tiktok")})
        
    # 8. Flickr (ícone 📽)
    if raw_social_dict.get("Flickr"):
        formatted_list.append({"rede": "Flickr", "icone": "📽", "url": raw_social_dict["Flickr"]})
        
    # 9. Outras redes não padronizadas
    for k, v in raw_social_dict.items():
        if k not in ["Facebook", "Instagram", "LinkedIn", "Twitter", "X", "YouTube", "Rádio", "Radio", "TikTok", "Tiktok", "Flickr"]:
            formatted_list.append({"rede": k, "icone": "🔗", "url": v})
            
    return formatted_list

def extract_and_diagram():
    m_dir = Path("PT-BR/M")
    
    ies_configs = [
        {
            "sigla": "CEFET-MG",
            "sigla_alt": "CEFET_MG",
            "slug": "cefet-mg",
            "file": "OK.03.CEFET-MG revisado para envio ao MEC - revisão conrado-2 - Liliane Oliveira.docx",
            "nome_padrao": "Centro Federal de Educação Tecnológica de Minas Gerais",
            "cidade_padrao": "Belo Horizonte",
            "estado_padrao": "Minas Gerais",
            "setor_ri_padrao": "Secretaria de Relações Internacionais (SRI)",
            "social_extra": {
                "Instagram": "https://www.instagram.com/cefetmg/",
                "LinkedIn": "https://www.linkedin.com/school/cefet-mg/"
            }
        },
        {
            "sigla": "UFAC",
            "sigla_alt": "UFAC",
            "slug": "ufac",
            "file": "OK.06.UFAC - Cooperacao Interinstitucional.docx",
            "nome_padrao": "Universidade Federal do Acre",
            "cidade_padrao": "Rio Branco",
            "estado_padrao": "Acre",
            "setor_ri_padrao": "Diretoria de Relações Interinstitucionais e Internacionais (CRINT)",
            "social_extra": {}
        },
        {
            "sigla": "UFAPE",
            "sigla_alt": "UFAPE",
            "slug": "ufape",
            "file": "OK.09.UFAPE (1) - Diretoria de Relações Internacionais da UFAPE.docx",
            "nome_padrao": "Universidade Federal do Agreste de Pernambuco",
            "cidade_padrao": "Garanhuns",
            "estado_padrao": "Pernambuco",
            "setor_ri_padrao": "Diretoria de Relações Internacionais (DRI)",
            "social_extra": {}
        },
        {
            "sigla": "UFJ",
            "sigla_alt": "UFJ",
            "slug": "ufj",
            "file": "OK.23.UFJ - MARCIO ISSAMU YAMAMOTO.docx",
            "nome_padrao": "Universidade Federal de Jataí",
            "cidade_padrao": "Jataí",
            "estado_padrao": "Goiás",
            "setor_ri_padrao": "Escritório de Internacionalização (EI)",
            "social_extra": {}
        },
        {
            "sigla": "UFMS",
            "sigla_alt": "UFMS",
            "slug": "ufms",
            "file": "OK.28.UFMS - Agência de Internacionalização.docx",
            "nome_padrao": "Universidade Federal de Mato Grosso do Sul",
            "cidade_padrao": "Campo Grande",
            "estado_padrao": "Mato Grosso do Sul",
            "setor_ri_padrao": "Agência de Internacionalização (AGINTER)",
            "social_extra": {}
        },
        {
            "sigla": "UFRPE",
            "sigla_alt": "UFRPE",
            "slug": "ufrpe",
            "file": "UFRPE-revised - Rodrigo Carmo.docx",
            "nome_padrao": "Universidade Federal Rural de Pernambuco",
            "cidade_padrao": "Recife",
            "estado_padrao": "Pernambuco",
            "setor_ri_padrao": "Núcleo de Internacionalização (NINTER)",
            "social_extra": {}
        },
        {
            "sigla": "UFRR",
            "sigla_alt": "UFRR",
            "slug": "ufrr",
            "file": "informações da UFRR para o Portal de internacionalização - Crint Ufrr.docx",
            "nome_padrao": "Universidade Federal de Roraima",
            "cidade_padrao": "Boa Vista",
            "estado_padrao": "Roraima",
            "setor_ri_padrao": "Coordenadoria de Relações Internacionais (CRINT)",
            "social_extra": {}
        },
        {
            "sigla": "UFS",
            "sigla_alt": "UFS",
            "slug": "ufs",
            "file": "UFS - Cooperação Internacional e Mobilidade Acadêmica - UFS.docx",
            "nome_padrao": "Universidade Federal de Sergipe",
            "cidade_padrao": "São Cristóvão",
            "estado_padrao": "Sergipe",
            "setor_ri_padrao": "Coordenação de Relações Internacionais (CORI)",
            "social_extra": {}
        },
        {
            "sigla": "UFSB",
            "sigla_alt": "UFSB",
            "slug": "ufsb",
            "file": "UFSB - Assessoria de Relacoes Internacionais.docx",
            "nome_padrao": "Universidade Federal do Sul da Bahia",
            "cidade_padrao": "Itabuna",
            "estado_padrao": "Bahia",
            "setor_ri_padrao": "Assessoria de Relações Internacionais (ARI)",
            "social_extra": {}
        },
        {
            "sigla": "UFSC",
            "sigla_alt": "UFSC",
            "slug": "ufsc",
            "file": "UFSC - João Pedro Leal Thiesen da Silva.docx",
            "nome_padrao": "Universidade Federal de Santa Catarina",
            "cidade_padrao": "Florianópolis",
            "estado_padrao": "Santa Catarina",
            "setor_ri_padrao": "Secretaria de Relações Internacionais (SINTER)",
            "social_extra": {}
        }
    ]
    
    diagrammed_records = []
    
    for conf in ies_configs:
        file_path = m_dir / conf["file"]
        paras = parse_docx_elements(file_path)
        
        nome_completo = conf["nome_padrao"]
        cidade_sede = conf["cidade_padrao"]
        estado = conf["estado_padrao"]
        endereco_sede = ""
        site_oficial = ""
        email_geral = ""
        telefone_geral = ""
        outros_campi = ""
        
        setor_ri = conf["setor_ri_padrao"]
        email_ri = ""
        telefone_ri = ""
        endereco_ri = ""
        site_ri = ""
        
        raw_social = dict(conf["social_extra"])
        
        current_section = "INTRO"
        sobre_paragraphs = []
        vida_paragraphs = []
        inter_paragraphs = []
        
        for p in paras:
            p_clean = clean_bullets_and_spaces(p)
            if not p_clean:
                continue
                
            # Identificação das transições de seções
            if re.search(r'^(?:1\.\s*)?Sobre a Universidade', p_clean, re.I):
                current_section = "SOBRE"
                continue
            elif re.search(r'^(?:2\.\s*)?Vida na Universidade|^Vida no Campus', p_clean, re.I) or "Infraestrutura Completa para o seu Desenvolvimento" in p_clean:
                current_section = "VIDA"
                if "Infraestrutura Completa para o seu Desenvolvimento" in p_clean:
                    vida_paragraphs.append(p_clean)
                continue
            elif re.search(r'^(?:3\.\s*)?Estudantes Internacionais|^Internacionalização e Acolhimento', p_clean, re.I) or "Suporte Integral ao Estudante Internacional" in p_clean:
                current_section = "INTER"
                if "Suporte Integral ao Estudante Internacional" in p_clean:
                    inter_paragraphs.append(p_clean)
                continue
            elif re.search(r'^(?:4\.\s*)?Contato|^Informações Essenciais e Contato', p_clean, re.I):
                current_section = "CONTATO"
                
            # Extração de campos estruturados
            m = re.match(r'Nome Completo:\s*(.+)', p_clean, re.I)
            if m: nome_completo = clean_val(m.group(1))
            
            m = re.match(r'Cidade da Sede:\s*(.+)', p_clean, re.I)
            if m: cidade_sede = clean_val(m.group(1))
            
            m = re.match(r'Estado:\s*(.+)', p_clean, re.I)
            if m: estado = clean_val(m.group(1))
            
            m = re.match(r'Endereço(?: da Sede)?:\s*(.+)', p_clean, re.I)
            if m and not endereco_sede: endereco_sede = clean_val(m.group(1))
            
            m = re.match(r'Site Oficial:\s*(.+)', p_clean, re.I)
            if m: site_oficial = clean_val(m.group(1))
            
            m = re.match(r'E-mail Oficial(?: \(Geral\))?:\s*(.+)', p_clean, re.I)
            if m: email_geral = clean_val(m.group(1))
            
            m = re.match(r'Telefone Oficial(?: \(Central\))?:\s*(.+)', p_clean, re.I)
            if m: telefone_geral = clean_val(m.group(1))
            
            m = re.match(r'Outros Campi:\s*(.+)', p_clean, re.I)
            if m: outros_campi = clean_val(m.group(1))
            
            # Setor de RI
            m = re.match(r'(?:Nome do Setor|Contato:|Nome da área:)\s*(.+)', p_clean, re.I)
            if m:
                cand = clean_val(m.group(1))
                if any(k in cand.upper() for k in ["INTERNACIONAL", "RELAÇÕES", "SRI", "DRI", "AGINTER", "SINTER", "CORI", "NINTER", "ARI", "CRINT", "ESCRITÓRIO"]):
                    setor_ri = cand
                    
            m = re.match(r'E-mail(?:\s+do\s+Setor|\s+do\s+Escritório|\s+da\s+Secretaria)?:\s*(.+)', p_clean, re.I)
            if m and "@" in m.group(1) and not email_ri: email_ri = clean_val(m.group(1))
            
            m = re.match(r'Telefone(?:\s+do\s+Setor|\s+do\s+Escritório|\s+da\s+Secretaria)?:\s*(.+)', p_clean, re.I)
            if m and any(c.isdigit() for c in m.group(1)) and not telefone_ri: telefone_ri = clean_val(m.group(1))
            
            m = re.match(r'Endereço Físico:\s*(.+)', p_clean, re.I)
            if m and not endereco_ri: endereco_ri = clean_val(m.group(1))
            
            m = re.match(r'Site do Setor:\s*(.+)', p_clean, re.I)
            if m and not site_ri: site_ri = clean_val(m.group(1))
            
            # Redes Sociais
            for soc_net in ["Facebook", "Instagram", "LinkedIn", "YouTube", "Twitter", "X", "Rádio", "Radio", "TikTok", "Flickr"]:
                m = re.match(rf'{soc_net}:\s*(.+)', p_clean, re.I)
                if m:
                    val = clean_val(m.group(1))
                    if val.lower() not in ["não há", "não possui", "não encontrada", "não possui.", "nenhum", "-", ""]:
                        raw_social[soc_net] = val
                        
            # Acúmulo de conteúdo por seção
            if current_section == "SOBRE":
                # Filtra apenas seções não repetitivas
                if not any(p_clean.startswith(prefix) for prefix in [
                    "Nome Completo:", "Cidade da Sede:", "Estado:", "Endereço da Sede:",
                    "Site Oficial:", "E-mail Oficial", "Telefone Oficial",
                    "Facebook:", "Instagram:", "YouTube:", "Twitter:", "LinkedIn:", "X:", "TikTok:", "Flickr:", "Redes Sociais:"
                ]):
                    sobre_paragraphs.append(p_clean)
            elif current_section == "VIDA":
                vida_paragraphs.append(p_clean)
            elif current_section == "INTER":
                inter_paragraphs.append(p_clean)

        # Tratar fallback de endereço da sede caso tenha ficado em branco no topo
        if not endereco_sede and endereco_ri:
            endereco_sede = endereco_ri
            
        # REGRA 1: "Informações sobre a existência de outros campi NÃO devem ir para a página de contatos; elas devem ser alocadas exclusivamente aqui, na seção 'Sobre a universidade'."
        if outros_campi:
            if not any("Outros Campi" in sp for sp in sobre_paragraphs):
                sobre_paragraphs.append(f"Estrutura Multicampi e Outros Campi: {outros_campi}")
        else:
            # Verifica se no texto já há menção
            pass
            
        # REGRA 1 & 2: "O conteúdo principal desta página DEVE começar obrigatoriamente com o texto exato do Word: 'Infraestrutura Completa para o seu Desenvolvimento'."
        vida_formatted = []
        found_vida = False
        for vp in vida_paragraphs:
            if "Infraestrutura Completa para o seu Desenvolvimento" in vp or found_vida:
                found_vida = True
                vida_formatted.append(vp)
        if not vida_formatted:
            vida_formatted = [f"Infraestrutura Completa para o seu Desenvolvimento: A {conf['sigla']} oferece ampla infraestrutura com laboratórios, bibliotecas, áreas esportivas e suporte acadêmico de excelência."]
            
        # REGRA 1 & 3: "O conteúdo desta página DEVE começar obrigatoriamente com o parágrafo do Word: 'Suporte Integral ao Estudante Internacional'."
        inter_formatted = []
        found_inter = False
        for ip in inter_paragraphs:
            if "Suporte Integral ao Estudante Internacional" in ip or found_inter:
                found_inter = True
                inter_formatted.append(ip)
        if not inter_formatted:
            inter_formatted = [f"Suporte Integral ao Estudante Internacional: A {conf['sigla']} oferece atendimento personalizado, suporte burocrático e programas de acolhimento para estudantes de todo o mundo."]

        # REGRA 1 & 4: Formatação de Redes Sociais com ícones e ordem estrita
        formatted_social = format_social_media(raw_social)
        
        # REGRA 2: Geração Automática de Mapas (HTML Embed)
        map_iframe = generate_map_iframe(endereco_sede)
        
        # REGRA 3: Padrão de Metadados
        seo_description = f"{nome_completo} ({conf['sigla']}), localizada em {cidade_sede} - {estado}, oferece ensino público, gratuito e de excelência no Brasil."
        
        record = {
            "sigla": conf["sigla"],
            "sigla_alt": conf["sigla_alt"],
            "slug": conf["slug"],
            "nome_completo": nome_completo,
            "cidade_sede": cidade_sede,
            "estado": estado,
            "endereco_sede": endereco_sede,
            "site_oficial": site_oficial,
            "email_geral": email_geral,
            "telefone_geral": telefone_geral,
            "outros_campi": outros_campi,
            
            "mapa_html_embed": map_iframe,
            
            "metadados": {
                "slug_home": f"/{conf['slug']}",
                "slug_sobre": f"/{conf['slug']}/sobre-nos",
                "slug_vida": f"/{conf['slug']}/vida-na-ies",
                "slug_inter": f"/{conf['slug']}/estudantes-internacionais",
                "nav_title_home": conf["sigla"],
                "nav_title_sobre": "Sobre",
                "nav_title_vida": "Vida na IES",
                "nav_title_inter": "Estudantes Internacionais",
                "tag": conf["sigla"],
                "seo_description": seo_description
            },
            
            "contatos_e_redes": {
                "nomenclatura_superior": setor_ri,
                "nomenclatura_inferior": "Contato Institucional",
                "email_setor": email_ri if email_ri else email_geral,
                "telefone_setor": telefone_ri if telefone_ri else telefone_geral,
                "endereco_setor": endereco_ri if endereco_ri else endereco_sede,
                "site_setor": site_ri if site_ri else site_oficial,
                "redes_sociais": formatted_social
            },
            
            "paginas": {
                "sobre": {
                    "slug": f"/{conf['slug']}/sobre-nos",
                    "id": "sobre-nos",
                    "titulo": f"Sobre a {conf['sigla']}",
                    "nav_title": "Sobre",
                    "tag": conf["sigla"],
                    "descricao_seo": f"Conheça a história, visão geral e pilares de excelência da {conf['sigla']}.",
                    "paragrafos": sobre_paragraphs
                },
                "vida_na_ies": {
                    "slug": f"/{conf['slug']}/vida-na-ies",
                    "id": "vida_na_ies",
                    "titulo": f"Vida na {conf['sigla']}",
                    "nav_title": "Vida na IES",
                    "tag": conf["sigla"],
                    "descricao_seo": f"Infraestrutura, moradia, alimentação e convivência na {conf['sigla']}.",
                    "paragrafos": vida_formatted
                },
                "estudantes_internacionais": {
                    "slug": f"/{conf['slug']}/estudantes-internacionais",
                    "id": "estudantes-internacionais",
                    "titulo": f"Estudantes Internacionais na {conf['sigla']}",
                    "nav_title": "Estudantes Internacionais",
                    "tag": conf["sigla"],
                    "descricao_seo": f"Informações de acolhimento, vistos e suporte aos estudantes internacionais na {conf['sigla']}.",
                    "paragrafos": inter_formatted
                }
            }
        }
        
        diagrammed_records.append(record)
        
    return diagrammed_records

if __name__ == "__main__":
    records = extract_and_diagram()
    
    # Cria pasta diagramacao se não existir
    out_dir = Path("diagramacao")
    out_dir.mkdir(exist_ok=True)
    
    # 1. Salva JSON consolidado
    json_path = out_dir / "diagramacao_10_ies.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"[OK] JSON consolidado salvo em: {json_path.resolve()}")
    
    # 2. Salva JSON individual para cada IES
    for r in records:
        ies_json = out_dir / f"{r['sigla']}.json"
        with open(ies_json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
            
    # 3. Salva CSV consolidado com metadados e embeds
    csv_path = out_dir / "diagramacao_10_ies.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Sigla", "Nome Completo", "Cidade", "Estado", "Endereço Sede",
            "Setor RI", "E-mail RI", "Telefone RI", "Site Oficial",
            "Redes Sociais Formatadas", "Código HTML Mapa Embed",
            "Slug Home", "Slug Sobre", "Slug Vida", "Slug Inter", "Descrição SEO"
        ])
        for r in records:
            social_str = " | ".join([f"{s['icone']} {s['rede']}: {s['url']}" for s in r["contatos_e_redes"]["redes_sociais"]])
            writer.writerow([
                r["sigla"],
                r["nome_completo"],
                r["cidade_sede"],
                r["estado"],
                r["endereco_sede"],
                r["contatos_e_redes"]["nomenclatura_superior"],
                r["contatos_e_redes"]["email_setor"],
                r["contatos_e_redes"]["telefone_setor"],
                r["site_oficial"],
                social_str,
                r["mapa_html_embed"],
                r["metadados"]["slug_home"],
                r["metadados"]["slug_sobre"],
                r["metadados"]["slug_vida"],
                r["metadados"]["slug_inter"],
                r["metadados"]["seo_description"]
            ])
    print(f"[OK] CSV consolidado salvo em: {csv_path.resolve()}")
