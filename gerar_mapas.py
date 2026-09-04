import docx
import urllib.parse
import csv
import re

def extrair_enderecos(caminho_docx):
    """
    Lê o documento Word e extrai os textos dos endereços.
    O script busca por linhas que começam com "Endereço:".
    """
    doc = docx.Document(caminho_docx)
    enderecos = []
    
    # Regex para capturar tudo que vier após a palavra "Endereço:"
    padrao = re.compile(r'Endereço:\s*(.+)', re.IGNORECASE)
    
    for paragrafo in doc.paragraphs:
        match = padrao.search(paragrafo.text)
        if match:
            # Armazena o endereço encontrado removendo espaços extras
            enderecos.append(match.group(1).strip())
            
    return enderecos

def gerar_iframe(endereco):
    """
    Gera o código HTML de incorporação (iframe) do Google Maps.
    """
    # Codifica o endereço para ser colocado na URL (ex: "São Paulo" vira "S%C3%A3o+Paulo")
    endereco_codificado = urllib.parse.quote(endereco)
    
    # URL padrão gratuita do Google Maps Embed
    url = f"https://maps.google.com/maps?q={endereco_codificado}&t=&z=15&ie=UTF8&iwloc=&output=embed"
    
    # Monta a estrutura final do iframe, baseada no padrão sugerido
    iframe = (
        f'<iframe width="100%" height="480" src="{url}" '
        f'style="border:0;" allowfullscreen="" loading="lazy"></iframe>'
    )
    return iframe

def main():
    # Substitua pelo nome do seu arquivo real
    arquivo_entrada = 'documento_ies.docx' 
    arquivo_saida = 'mapas_gerados.csv'
    
    print("Iniciando a leitura do documento...")
    enderecos = extrair_enderecos(arquivo_entrada)
    
    if not enderecos:
        print("Nenhum endereço encontrado. Verifique se o formato no texto possui 'Endereço: '")
        return
        
    # Salva o resultado em um CSV para que você possa copiar os blocos HTML 
    with open(arquivo_saida, 'w', newline='', encoding='utf-8-sig') as csvfile:
        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow(['Endereço', 'Código HTML Embed'])
        
        for end in enderecos:
            codigo_embed = gerar_iframe(end)
            writer.writerow([end, codigo_embed])
            
    print(f"Sucesso! {len(enderecos)} endereços convertidos.")
    print(f"Os códigos de incorporação foram salvos no arquivo: {arquivo_saida}")

if __name__ == '__main__':
    main()