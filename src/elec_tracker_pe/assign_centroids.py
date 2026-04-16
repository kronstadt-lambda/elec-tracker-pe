import json
import unicodedata
import geopandas as gpd
from pathlib import Path
import difflib
from geopy.geocoders import ArcGIS
from geopy.extra.rate_limiter import RateLimiter

# ==========================================
# CONFIGURACIÓN DE RUTAS
# ==========================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SHP_FILE = BASE_DIR / "data" / "limite_distrital" / "Limite Distrital INEI 2025 CPV.shp"
DIC_ORIGEN = BASE_DIR / "data" / "ubigeo_diccionario.json"
GEO_DESTINO = BASE_DIR / "data" / "ubigeo_georeferenciado.json"

# ==========================================
# DICCIONARIO DE RESCATE (ONPE -> INEI)
# ==========================================
OVERRIDES = {
    # Resolvemos la discrepancia asignando el centroide de Yavari
    "SANTA ROSA DE LORETO": "YAVARI"
}

def normalize(text):
    """Limpia textos base para hacer emparejamientos exactos."""
    if not isinstance(text, str): return ""
    text = text.upper().strip()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    text = text.replace("-", " ").replace(".", "").replace(",", "")
    return " ".join(text.split())

def fuzzy_match(target, choices, cutoff=0.75):
    """Busca la coincidencia más cercana en una lista si supera el porcentaje (cutoff)."""
    matches = difflib.get_close_matches(target, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def build_centroids():
    print("🚀 Iniciando Motor Híbrido de Georreferenciación...")

    # ---------------------------------------------------------
    # PARTE 1: PERÚ (Procesamiento ultrarrápido con Shapefile Local)
    # ---------------------------------------------------------
    if not SHP_FILE.exists():
        print(f"❌ No se encontró el shapefile en {SHP_FILE}")
        return

    print("🗺️ Cargando Shapefile del INEI para PERÚ...")
    gdf = gpd.read_file(SHP_FILE)
    if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    centroides = gdf.to_crs(epsg=3857).centroid.to_crs(epsg=4326)
    gdf['lon'] = centroides.x
    gdf['lat'] = centroides.y

    cols = [c.upper() for c in gdf.columns]
    col_dep = next((c for c in cols if 'DEP' in c), 'NOMBDEP')
    col_prov = next((c for c in cols if 'PROV' in c), 'NOMBPROV')
    col_dist = next((c for c in cols if 'DIST' in c), 'NOMBDIST')

    inei_lookup = {}
    for idx, row in gdf.iterrows():
        dep = normalize(row[col_dep])
        prov = normalize(row[col_prov])
        dist = normalize(row[col_dist])

        if dep not in inei_lookup: inei_lookup[dep] = {}
        if prov not in inei_lookup[dep]: inei_lookup[dep][prov] = {}
        inei_lookup[dep][prov][dist] = {"lat": row['lat'], "lon": row['lon']}

    print("🔄 Cruzando datos nacionales (Fuzzy Matching + Overrides)...")
    with open(DIC_ORIGEN, 'r', encoding='utf-8') as f:
        onpe_data = json.load(f)

    new_data = {"PERU": {}, "EXTRANJERO": {}}
    peru_matches = 0
    peru_misses = 0

    for region, provincias in onpe_data.get("PERU", {}).items():
        new_data["PERU"][region] = {}
        reg_norm = normalize(region)
        reg_inei = fuzzy_match(reg_norm, inei_lookup.keys(), 0.90)

        if not reg_inei: continue

        for provincia, distritos in provincias.items():
            new_data["PERU"][region][provincia] = {}
            prov_norm = normalize(provincia)
            prov_inei = fuzzy_match(prov_norm, inei_lookup[reg_inei].keys(), 0.80)

            if not prov_inei:
                for distrito in distritos:
                    new_data["PERU"][region][provincia][distrito] = {"lat": None, "lon": None}
                    peru_misses += 1
                continue

            for distrito in distritos:
                dist_norm = normalize(distrito)

                # APLICAR EXCEPCIONES MANUALES (Ej. Santa Rosa de Loreto -> Yavari)
                if dist_norm in OVERRIDES:
                    dist_norm = OVERRIDES[dist_norm]

                dist_inei = fuzzy_match(dist_norm, inei_lookup[reg_inei][prov_inei].keys(), 0.75)

                if dist_inei:
                    coords = inei_lookup[reg_inei][prov_inei][dist_inei]
                    new_data["PERU"][region][provincia][distrito] = coords
                    peru_matches += 1
                else:
                    new_data["PERU"][region][provincia][distrito] = {"lat": None, "lon": None}
                    peru_misses += 1
                    print(f"  ⚠️ Sin match: {region} > {provincia} > {distrito}")

    # ---------------------------------------------------------
    # PARTE 2: EXTRANJERO (Geocoding API con ArcGIS)
    # ---------------------------------------------------------
    if "EXTRANJERO" in onpe_data:
        print("\n🌍 Iniciando API ArcGIS para geolocalizar EXTRANJERO...")
        geolocator = ArcGIS(user_agent="elec_tracker_pe_bot")
        # ArcGIS es muy rápido y permisivo, 0.3s de pausa es suficiente
        geocode = RateLimiter(geolocator.geocode, min_delay_seconds=0.3)

        ext_matches = 0
        ext_misses = 0

        for cont, paises in onpe_data["EXTRANJERO"].items():
            new_data["EXTRANJERO"][cont] = {}
            for pais, ciudades in paises.items():
                new_data["EXTRANJERO"][cont][pais] = {}
                print(f"  📍 Buscando ciudades en {pais}...")

                for ciudad in ciudades:
                    # Construimos el query de búsqueda: "Ciudad, Pais"
                    query = f"{ciudad}, {pais}"
                    try:
                        loc = geocode(query)
                        if loc:
                            new_data["EXTRANJERO"][cont][pais][ciudad] = {
                                "lat": loc.latitude,
                                "lon": loc.longitude
                            }
                            ext_matches += 1
                        else:
                            new_data["EXTRANJERO"][cont][pais][ciudad] = {"lat": None, "lon": None}
                            ext_misses += 1
                            print(f"    ⚠️ No encontrado: {query}")
                    except Exception as e:
                        new_data["EXTRANJERO"][cont][pais][ciudad] = {"lat": None, "lon": None}
                        ext_misses += 1
                        print(f"    ❌ Error red en {query}: {e}")

    # ---------------------------------------------------------
    # GUARDADO FINAL
    # ---------------------------------------------------------
    with open(GEO_DESTINO, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=4)

    print(f"\n✅ PROCESO COMPLETADO EXITOSAMENTE.")
    print(f"🇵🇪 PERÚ: {peru_matches} aciertos | {peru_misses} fallos (0 esperado).")
    if "EXTRANJERO" in onpe_data:
        print(f"🌎 EXTRANJERO: {ext_matches} aciertos | {ext_misses} fallos.")
    print(f"💾 Base de datos maestra guardada en: {GEO_DESTINO}")

if __name__ == "__main__":
    build_centroids()