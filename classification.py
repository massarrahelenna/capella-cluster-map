import pandas as pd
import json
import boto3
import requests
import base64
from pathlib import Path

EXCEL_PATH = "resultados_editado.xlsx"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_IMAGENS = 1
MAX_LOCAIS = 9999

CLASSES_POSSIVEIS = [
    "Área de Mineração",
    "Vulcão / Atividade Geológica",
    "Área Portuária",
    "Base Militar",
    "Usina de Energia",
    "Zona Urbana",
    "Agricultura / Desmatamento",
    "Costa / Oceano",
    "Outro / Indeterminado",
]

CAPELLA_S3_BASE = "https://capella-open-data.s3.amazonaws.com/stac/capella-open-data-by-datetime"

def stac_id_para_urls(stac_id: str) -> dict:
    """
    Monta todas as URLs a partir do stac_id.
    Exemplo de stac_id:
      CAPELLA_C13_SP_SLC_HH_20251108032444_20251108032453
    A data está nos caracteres após o 5º underscore: 20251108 → 2025/11/08
    """
    try:
        # Extrai a data do stac_id (6ª parte após split por '_')
        partes = stac_id.split("_")
        data_str = partes[5]          # ex: "20251108032444"
        ano  = data_str[0:4]          # "2025"
        mes  = data_str[4:6]          # "11"
        dia  = data_str[6:8]          # "08"

        pasta = (
            f"{CAPELLA_S3_BASE}"
            f"/capella-open-data-{ano}"
            f"/capella-open-data-{ano}-{mes}"
            f"/capella-open-data-{ano}-{mes}-{dia}"
            f"/{stac_id}"
        )

        return {
            "thumbnail": f"{pasta}/thumbnail.png",
            "stac_json": f"{pasta}/{stac_id}.json",
            "stac_browser": (
                "https://radiantearth.github.io/stac-browser/#/external/"
                f"capella-open-data.s3.amazonaws.com/stac/capella-open-data-by-datetime"
                f"/capella-open-data-{ano}/capella-open-data-{ano}-{mes}"
                f"/capella-open-data-{ano}-{mes}-{dia}/{stac_id}/{stac_id}.json"
            ),
        }
    except Exception:
        return {"thumbnail": None, "stac_json": None, "stac_browser": None}


def baixar_thumbnail_base64(url: str) -> str | None:
    """Baixa a thumbnail e retorna como base64 para enviar ao Claude via Bedrock."""
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode("utf-8")
    except Exception:
        pass
    return None


def escolher_thumbnail_representativa(grupo: pd.DataFrame) -> tuple[str, str, str]:
    """
    Escolhe a melhor thumbnail do grupo para enviar ao Claude:
    - Prefere GEO (imagem geocodificada, mais legível visualmente)
    - Entre as GEO, pega a de resolução mais alta
    Retorna: (stac_id, thumbnail_url, stac_browser_url)
    """
    # Preferência: GEO > SLC > outros
    for tipo in ["GEO", "SLC", "GEC"]:
        sub = grupo[grupo['stac_id'].str.contains(f"_{tipo}_")]
        if not sub.empty:
            # Pega a de menor resolução_range (= maior resolução espacial)
            melhor = sub.loc[sub['resolution_range'].idxmin()]
            urls = stac_id_para_urls(melhor['stac_id'])
            return melhor['stac_id'], urls["thumbnail"], urls["stac_browser"]

    # Fallback: qualquer uma
    melhor = grupo.loc[grupo['resolution_range'].idxmin()]
    urls = stac_id_para_urls(melhor['stac_id'])
    return melhor['stac_id'], urls["thumbnail"], urls["stac_browser"]


def buscar_contexto_geo(lat: float, lon: float) -> dict:
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=14&addressdetails=1"
        r = requests.get(url, headers={"User-Agent": "capella-sar-classifier"}, timeout=10)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}


def buscar_wikipedia(lat: float, lon: float, raio_km: int = 100) -> str:
    try:
        params = {
            "action": "query", "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": raio_km * 1000,
            "gslimit": 5, "format": "json"
        }
        r = requests.get("https://en.wikipedia.org/w/api.php", params=params, timeout=10)
        if r.status_code != 200:
            return ""
        results = r.json().get("query", {}).get("geosearch", [])
        textos = []
        for item in results[:3]:
            page_r = requests.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "pageids": item["pageid"],
                "prop": "extracts", "exintro": True,
                "explaintext": True, "format": "json"
            }, timeout=10)
            if page_r.status_code == 200:
                pages = page_r.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    extract = page.get("extract", "")[:700]
                    if extract:
                        textos.append(f"### {item['title']} (~{item.get('dist',0)/1000:.0f}km)\n{extract}")
        return "\n\n".join(textos)
    except Exception:
        return ""


def analisar_metadados_tecnicos(grupo: pd.DataFrame) -> dict:
    return {
        "total_imagens": len(grupo),
        "periodo_dias": (grupo['datetime'].max() - grupo['datetime'].min()).days,
        "frequencia_media_dias": (grupo['datetime'].max() - grupo['datetime'].min()).days / max(len(grupo) - 1, 1),
        "angulo_medio": round(grupo['incidence_angle'].mean(), 2),
        "plataformas": list(grupo['platform'].unique()),
        "clusters": list(grupo['KMeans_Cluster'].unique()),
        "resolucao_media": round(grupo['resolution_range'].mean(), 3),
        "imagens_por_mes": round(len(grupo) / max((grupo['datetime'].max() - grupo['datetime'].min()).days / 30, 1), 1),
    }


def sinais_indiretos(lat: float, lon: float, grupo: pd.DataFrame) -> dict:
    periodo = (grupo['datetime'].max() - grupo['datetime'].min()).days
    n = len(grupo)
    freq = periodo / max(n - 1, 1)
    return {
        "zona_climatica": (
            "Polar/Subpolar" if abs(lat) > 60 else
            "Temperada" if abs(lat) > 35 else
            "Subtropical" if abs(lat) > 23 else "Tropical"
        ),
        "hemisferio": "Norte" if lat > 0 else "Sul",
        "proximo_equador": abs(lat) < 23,
        "costa_oeste_australia": -45 < lat < -10 and 110 < lon < 130,
        "costa_leste_australia": -45 < lat < -10 and 140 < lon < 155,
        "mediterraneo": 30 < lat < 47 and -6 < lon < 36,
        "frequencia_revisita_dias": round(freq, 1),
        "monitoramento_intensivo": freq < 3,
        "resolucao_media": round(grupo['resolution_range'].mean(), 3),
        "alta_resolucao": grupo['resolution_range'].mean() < 0.4,
        "multiplas_plataformas": len(grupo['platform'].unique()) > 1,
    }


def classificar_local(grupo: pd.DataFrame, lat: float, lon: float) -> dict:
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    geo_data = buscar_contexto_geo(lat, lon)
    endereco = geo_data.get("display_name", "Não disponível")
    address = geo_data.get("address", {})
    osm_type = geo_data.get("type", "")
    osm_class = geo_data.get("class", "")
    contexto_wiki = buscar_wikipedia(lat, lon, raio_km=100)
    tecnico = analisar_metadados_tecnicos(grupo)
    sinais = sinais_indiretos(lat, lon, grupo)

    localizacao = ", ".join(filter(None, [
        address.get("city") or address.get("town") or address.get("village"),
        address.get("state"),
        address.get("country")
    ])) or f"{lat:.2f}, {lon:.2f}"

    # ── Tenta carregar thumbnail ──────────────────
    stac_repr, thumb_url, stac_browser_url = escolher_thumbnail_representativa(grupo)
    thumb_b64 = baixar_thumbnail_base64(thumb_url) if thumb_url else None
    tem_imagem = thumb_b64 is not None

    classes_str = "\n".join(f"- {c}" for c in CLASSES_POSSIVEIS)

    texto_contexto = f"""Você é um analista sênior de inteligência geoespacial com expertise em imagens SAR.
Classifique este local monitorado pela Capella Space.

════════════════════════════════════════
DADOS GEOGRÁFICOS (OpenStreetMap)
════════════════════════════════════════
Coordenadas: ({lat:.4f}, {lon:.4f})
Endereço: {endereco}
Tipo OSM: {osm_class} / {osm_type}
País: {address.get('country','N/D')} | Estado: {address.get('state','N/D')}

════════════════════════════════════════
SINAIS INDIRETOS
════════════════════════════════════════
Zona climática: {sinais['zona_climatica']} (hemisfério {sinais['hemisferio']})
Tropical (potencial agrícola): {'SIM' if sinais['proximo_equador'] else 'NÃO'}
Costa oeste Austrália (Pilbara/mineração): {'SIM' if sinais['costa_oeste_australia'] else 'NÃO'}
Costa leste Austrália: {'SIM' if sinais['costa_leste_australia'] else 'NÃO'}
Região mediterrânea: {'SIM' if sinais['mediterraneo'] else 'NÃO'}

════════════════════════════════════════
PADRÃO DE MONITORAMENTO SAR
════════════════════════════════════════
Total de imagens: {tecnico['total_imagens']}
Período: {tecnico['periodo_dias']} dias | Frequência: 1 imagem a cada {sinais['frequencia_revisita_dias']} dias
Monitoramento intensivo (<3 dias): {'SIM ⚠️' if sinais['monitoramento_intensivo'] else 'NÃO'}
Resolução média: {tecnico['resolucao_media']}m {'(ALTA RESOLUÇÃO)' if sinais['alta_resolucao'] else ''}
Múltiplas plataformas: {'SIM' if sinais['multiplas_plataformas'] else 'NÃO'} ({', '.join(tecnico['plataformas'])})

════════════════════════════════════════
CONTEXTO WIKIPEDIA (raio 100km)
════════════════════════════════════════
{contexto_wiki if contexto_wiki else 'Nenhum artigo encontrado.'}

════════════════════════════════════════
{"THUMBNAIL SAR INCLUÍDA ACIMA — use a imagem para confirmar o tipo de uso do solo." if tem_imagem else "THUMBNAIL: não disponível — classifique apenas pelos metadados."}
════════════════════════════════════════

GUIA DE CLASSIFICAÇÃO:
• Área Portuária → guindastes, cais, navios atracados, terminal de contêineres
• Agricultura / Desmatamento → padrão de talhões, campos cultivados, desmatamento
• Área de Mineração → cratera aberta, pilhas de rejeito, estrutura de mina
• Base Militar → hangares, pistas, instalações isoladas, padrão geométrico restrito
• Vulcão → cratera, fluxo de lava, cone vulcânico
• Costa / Oceano → interface água/terra sem estrutura portuária
• Usina de Energia → estrutura de usina, painéis solares, torres eólicas, barragem
• Zona Urbana → malha urbana densa, apenas quando nenhuma outra categoria se aplica

Classes disponíveis:
{classes_str}

Responda SOMENTE com JSON válido, sem texto adicional:
{{
  "classe": "<classe escolhida>",
  "confianca": "<Alta | Média | Baixa>",
  "justificativa": "<2-3 frases incluindo o que a imagem (se disponível) revelou>"
}}"""

    # ── Monta content com ou sem imagem ──────────
    content = []

    if tem_imagem:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": thumb_b64,
            }
        })

    content.append({"type": "text", "text": texto_contexto})

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": content}]
        })
    )
    raw = json.loads(response["body"].read())["content"][0]["text"].strip()

    try:
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        resultado = json.loads(raw)
        if resultado.get("classe") not in CLASSES_POSSIVEIS:
            resultado["classe"] = "Outro / Indeterminado"
    except Exception:
        resultado = {
            "classe": "Outro / Indeterminado",
            "confianca": "Baixa",
            "justificativa": "Erro ao interpretar resposta."
        }

    resultado["localizacao"] = localizacao
    resultado["thumbnail_url"] = thumb_url or ""
    resultado["stac_browser_url"] = stac_browser_url or ""
    resultado["stac_id_repr"] = stac_repr
    resultado["thumbnail_carregada"] = tem_imagem
    return resultado


def analisar_classe(classe: str, locais: list) -> str:
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

    resumo = ""
    for loc in locais:
        resumo += (
            f"\n- {loc['localizacao']} ({loc['lat']:.2f}, {loc['lon']:.2f})"
            f" | {loc['n_imagens']} imagens | {loc['data_inicio']} → {loc['data_fim']}"
            f" | Confiança: {loc['confianca']}"
            f"\n  {loc['justificativa']}\n"
        )

    prompt = f"""Especialista em inteligência geoespacial SAR.
A Capella Space monitorou {len(locais)} locais classificados como **{classe}**:
{resumo}

Análise consolidada:
1. **Distribuição Global** — Onde estão? Padrão regional?
2. **Intensidade** — Quais recebem mais atenção e por quê?
3. **Relevância Estratégica** — Por que a Capella monitora esses locais?
4. **Padrões em Comum** — O que une esses locais?
5. **Insight Principal** — Descoberta mais importante do grupo."""

    response = bedrock.invoke_model(
        modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}]
        })
    )
    return json.loads(response["body"].read())["content"][0]["text"]


print("📂 Carregando dados...")
df = pd.read_excel(EXCEL_PATH, sheet_name="Dados_Completos")
df['datetime'] = pd.to_datetime(df['datetime'])
df['lat_r'] = df['center_lat'].round(2)
df['lon_r'] = df['center_lon'].round(2)

all_locations = [
    (key, group.sort_values('datetime'))
    for key, group in df.groupby(['lat_r', 'lon_r'])
]
all_locations.sort(key=lambda x: -len(x[1]))
print(f"✅ {len(all_locations)} locais encontrados")


total = min(MAX_LOCAIS, len(all_locations))
print(f"\n🏷️  Classificando {total} locais (com thumbnail quando disponível)...\n")

locais_classificados = []

for i, ((lat, lon), grupo) in enumerate(all_locations[:MAX_LOCAIS]):
    n = len(grupo)
    print(f"📍 [{i+1}/{total}] ({lat:.2f}, {lon:.2f}) — {n} imagens", end="")

    resultado = classificar_local(grupo, lat, lon)

    img_flag = "🖼️" if resultado["thumbnail_carregada"] else "📊"
    print(f" {img_flag} → {resultado['classe']} [{resultado['confianca']}]")

    locais_classificados.append({
        "lat": lat,
        "lon": lon,
        "localizacao": resultado["localizacao"],
        "classe": resultado["classe"],
        "confianca": resultado["confianca"],
        "justificativa": resultado["justificativa"],
        "n_imagens": n,
        "data_inicio": str(grupo['datetime'].min().date()),
        "data_fim": str(grupo['datetime'].max().date()),
        "plataformas": ', '.join(grupo['platform'].unique()),
        "thumbnail_url": resultado["thumbnail_url"],
        "stac_browser_url": resultado["stac_browser_url"],
        "stac_id_repr": resultado["stac_id_repr"],
        "thumbnail_carregada": resultado["thumbnail_carregada"],
    })

# ── CSV ──────────────────────────────────────
df_resultado = pd.DataFrame(locais_classificados)
csv_path = OUTPUT_DIR / "locais_classificados_v3.csv"
df_resultado.to_csv(csv_path, index=False, encoding='utf-8')
print(f"\n💾 CSV salvo: {csv_path}")

# ── Agrupamento e análise por classe ─────────
print("\n📊 Analisando por classe...\n")
grupos_por_classe = {}
for loc in locais_classificados:
    grupos_por_classe.setdefault(loc["classe"], []).append(loc)

analises_por_classe = {}
for classe, locais in sorted(grupos_por_classe.items(), key=lambda x: -len(x[1])):
    print(f"🗂️  {classe}: {len(locais)} locais", end="")
    analises_por_classe[classe] = analisar_classe(classe, locais)
    print(" ✅")

# ── Relatório Markdown ────────────────────────
md = "# 🛰️ Classificação de Locais — Capella SAR (v3 + Thumbnails)\n\n"
md += f"_{len(locais_classificados)} locais classificados em {len(grupos_por_classe)} categorias_\n\n"

md += "## 📋 Resumo por Classe\n\n"
md += "| Classe | Nº Locais | Total Imagens | Com Imagem | Confiança Alta |\n"
md += "|--------|-----------|---------------|------------|----------------|\n"
for classe, locais in sorted(grupos_por_classe.items(), key=lambda x: -len(x[1])):
    total_imgs = sum(l['n_imagens'] for l in locais)
    com_img = sum(1 for l in locais if l['thumbnail_carregada'])
    alta = sum(1 for l in locais if l['confianca'] == 'Alta')
    md += f"| {classe} | {len(locais)} | {total_imgs} | {com_img}/{len(locais)} | {alta}/{len(locais)} |\n"
md += "\n"

for classe, locais in sorted(grupos_por_classe.items(), key=lambda x: -len(x[1])):
    md += "---\n\n"
    md += f"## 🏷️ {classe}\n\n"

    for loc in sorted(locais, key=lambda x: -x['n_imagens']):
        emoji_conf = {"Alta": "🟢", "Média": "🟡", "Baixa": "🔴"}.get(loc['confianca'], "⚪")
        emoji_img  = "🖼️" if loc['thumbnail_carregada'] else "📊"
        md += f"### 📍 {loc['localizacao']}\n\n"
        md += f"> `{loc['lat']:.4f}, {loc['lon']:.4f}`\n\n"
        md += f"- **Imagens:** {loc['n_imagens']} | **Período:** {loc['data_inicio']} → {loc['data_fim']}\n"
        md += f"- **Plataformas:** {loc['plataformas']}\n"
        md += f"- **Confiança:** {emoji_conf} {loc['confianca']} {emoji_img}\n"
        md += f"- **Justificativa:** {loc['justificativa']}\n"
        if loc['thumbnail_url']:
            md += f"- **Thumbnail:** [{loc['stac_id_repr']}]({loc['thumbnail_url']})\n"
        if loc['stac_browser_url']:
            md += f"- **STAC Browser:** [Ver imagem completa]({loc['stac_browser_url']})\n"
        md += "\n"

    md += f"### 🔍 Análise Consolidada\n\n{analises_por_classe.get(classe, '')}\n\n"

output_path = OUTPUT_DIR / "relatorio_classificado_v3.md"
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(md)

print(f"\n🚀 SUCESSO!")
print(f"   📄 Relatório: {output_path}")
print(f"   💾 CSV:       {csv_path}")

com_img = sum(1 for l in locais_classificados if l['thumbnail_carregada'])
print(f"\n📊 {com_img}/{len(locais_classificados)} locais classificados com thumbnail visual")
print(f"\n📊 Distribuição final:")
for classe, locais in sorted(grupos_por_classe.items(), key=lambda x: -len(x[1])):
    print(f"   {classe:<35} {len(locais):>3} locais")