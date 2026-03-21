import pandas as pd
import pydeck as pdk
import os

file_path = "resultados_editado.xlsx"

if not os.path.exists(file_path):
    print(f"❌ Arquivo '{file_path}' não encontrado!")
    exit()

print("🔍 Analisando as abas do Excel para encontrar os dados geográficos...")

excel_file = pd.ExcelFile(file_path)
df = None
aba_encontrada = ""

for sheet in excel_file.sheet_names:
    temp_df = pd.read_excel(file_path, sheet_name=sheet)
    temp_df.columns = temp_df.columns.astype(str).str.strip()
    if 'center_lat' in temp_df.columns and 'center_lon' in temp_df.columns:
        df = temp_df
        aba_encontrada = sheet
        break

if df is None:
    print("❌ ERRO: Não encontrei as colunas 'center_lat' e 'center_lon'.")
    exit()

print(f"✅ Dados encontrados na aba: '{aba_encontrada}'")

color_map = {
    'Grupo 0': [255, 87,  34,  200],
    'Grupo 1': [33,  150, 243, 200],
    'Grupo 2': [76,  175, 80,  200],
    'Grupo 3': [156, 39,  176, 200],
}


data = []
for _, row in df.iterrows():
    data.append({
        "center_lon":    float(row["center_lon"]),
        "center_lat":    float(row["center_lat"]),
        "color":         color_map.get(str(row["KMeans_Cluster"]).strip(), [128, 128, 128, 200]),
        "stac_id":       str(row["stac_id"]),
        "platform":      str(row["platform"]),
        "KMeans_Cluster": str(row["KMeans_Cluster"]),
    })

layer = pdk.Layer(
    'ScatterplotLayer',
    data,                          
    get_position='[center_lon, center_lat]',
    get_color='color',
    get_radius=30000,
    pickable=True,
    opacity=0.8,
)

view_state = pdk.ViewState(
    latitude=df['center_lat'].mean(),
    longitude=df['center_lon'].mean(),
    zoom=2.5,
    pitch=45,
)

r = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={
        "html": "<b>ID:</b> {stac_id}<br/><b>Plataforma:</b> {platform}<br/><b>Cluster:</b> {KMeans_Cluster}",
        "style": {"backgroundColor": "#1a1a2e", "color": "white"}
    },
    map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'  
)

r.to_html('meu_globo_3d.html', open_browser=True)
print(f"🚀 SUCESSO! Arquivo criado com dados da aba '{aba_encontrada}'.")