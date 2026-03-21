import pandas as pd
import json
import boto3
import pypdf
from pathlib import Path

EXCEL_PATH = "resultados_editado.xlsx"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
PDFS_DIR = Path("pesquisas")

MAX_LOCAIS = 3
MIN_IMAGENS = 5

print("📂 Carregando dados...")
df = pd.read_excel(EXCEL_PATH, sheet_name="Dados_Completos")
df['datetime'] = pd.to_datetime(df['datetime'])
df['lat_r'] = df['center_lat'].round(2)
df['lon_r'] = df['center_lon'].round(2)

series = df.groupby(['lat_r', 'lon_r'])
big_locations = [
    (key, group.sort_values('datetime'))
    for key, group in series
    if len(group) >= MIN_IMAGENS
]
big_locations.sort(key=lambda x: -len(x[1]))
print(f"✅ {len(big_locations)} locais com {MIN_IMAGENS}+ imagens encontrados")

def extrair_texto_pdf(pdf_path: Path, max_chars: int = 4000) -> str:
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        texto = ""
        for page in reader.pages:
            texto += page.extract_text() or ""
            if len(texto) >= max_chars:
                break
        return texto[:max_chars]
    except Exception as e:
        print(f"  ⚠️ Erro ao ler PDF {pdf_path.name}: {e}")
        return ""

def encontrar_pdf_relevante(lat: float, lon: float) -> str:
    if not PDFS_DIR.exists():
        return ""
    pdfs = list(PDFS_DIR.glob("*.pdf"))
    if not pdfs:
        return ""
    texto_total = ""
    for pdf in pdfs:
        print(f"  📄 Lendo: {pdf.name}")
        texto = extrair_texto_pdf(pdf, max_chars=4000)
        if texto:
            texto_total += f"\n\n=== {pdf.stem} ===\n{texto}"
    return texto_total[:16000]

def analisar_com_bedrock(grupo: pd.DataFrame, lat: float, lon: float) -> str:
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    texto_pdf = encontrar_pdf_relevante(lat, lon)

    metadados_str = ""
    for _, row in grupo.iterrows():
        metadados_str += f"- {row['datetime'].strftime('%Y-%m-%d')} | {row['platform']} | {row['KMeans_Cluster']} | ângulo: {row['incidence_angle']}° | modo: {row['instrument_mode']}\n"

    content = []

    if texto_pdf:
        content.append({
            "type": "text",
            "text": f"""Você é um especialista em imagens de satélite SAR.

Contexto científico desta região (extraído de pesquisa acadêmica):
---
{texto_pdf}
---"""
        })
    else:
        content.append({
            "type": "text",
            "text": "Você é um especialista em análise de imagens de satélite SAR."
        })

    content.append({
        "type": "text",
        "text": f"""Abaixo estão os metadados de {len(grupo)} imagens SAR do local ({lat:.4f}, {lon:.4f}), capturadas entre {grupo['datetime'].min().date()} e {grupo['datetime'].max().date()}.

{metadados_str}

Com base nos metadados e no contexto científico da região, analise e responda:
1. O que esse local provavelmente representa? (tipo de terreno, uso, importância)
2. O que a frequência e distribuição das capturas sugere sobre o interesse nesse local?
3. As variações de ângulo, plataforma e cluster ao longo do tempo indicam alguma mudança de estratégia de observação?
4. Conte a história desse local com base nos dados disponíveis
5. Tipo de monitoramento: PONTUAL / CONTÍNUO / SAZONAL / INTENSIVO"""
    })

    content.append({
        "type": "text",
        "text": "Faça sua análise completa:"
    })

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": content}]
        })
    )
    return json.loads(response["body"].read())["content"][0]["text"]

historias = []

for i, ((lat, lon), grupo) in enumerate(big_locations[:MAX_LOCAIS]):
    print(f"\n{'='*50}")
    print(f"📍 Local {i+1}/{min(MAX_LOCAIS, len(big_locations))}: ({lat:.2f}, {lon:.2f})")
    print(f"   {len(grupo)} imagens | {grupo['datetime'].min().date()} → {grupo['datetime'].max().date()}")

    print(f"  🤖 Analisando metadados com Claude via Bedrock...")
    analise = analisar_com_bedrock(grupo, lat, lon)

    historias.append({
        'lat': lat, 'lon': lon,
        'n_imagens': len(grupo),
        'data_inicio': str(grupo['datetime'].min().date()),
        'data_fim': str(grupo['datetime'].max().date()),
        'plataformas': ', '.join(grupo['platform'].unique()),
        'analise': analise,
    })
    print("  ✅ Análise concluída!")

print(f"\n📄 Gerando relatório com {len(historias)} histórias...")

output_path = OUTPUT_DIR / "historias.md"

md = f"# 🛰️ Histórias das Séries Temporais — Capella SAR\n\n"
md += f"_{len(historias)} locais analisados_\n\n"

for h in historias:
    md += f"---\n\n"
    md += f"## 📍 {h['lat']:.2f}, {h['lon']:.2f}\n\n"
    md += f"- **Imagens:** {h['n_imagens']}\n"
    md += f"- **Período:** {h['data_inicio']} → {h['data_fim']}\n"
    md += f"- **Plataformas:** {h['plataformas']}\n\n"
    md += f"### Análise\n\n"
    md += f"{h['analise']}\n\n"

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(md)

print(f"🚀 SUCESSO! Relatório salvo em '{output_path}'")