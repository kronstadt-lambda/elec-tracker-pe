import pandas as pd
import requests
import json
import streamlit as st
from pathlib import Path

# ---------------------------------------------------------
# CONSTANTES Y CONFIGURACIÓN GLOBAL
# ---------------------------------------------------------
CANDIDATOS_TARGET = {
    "KEIKO SOFIA FUJIMORI HIGUCHI": "#fe8019",
    "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA": "#83a598",
    "JORGE NIETO MONTESINOS": "#fabd2f",
    "ROBERTO HELBERT SANCHEZ PALOMINO": "#b8bb26",
    "RICARDO PABLO BELMONT CASSINELLI": "#689d6a"
}

EMOJIS_CANDIDATOS = {
    "KEIKO SOFIA FUJIMORI HIGUCHI": "🍊",
    "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA": "🐷",
    "JORGE NIETO MONTESINOS": "☀️",
    "ROBERTO HELBERT SANCHEZ PALOMINO": "🤠",
    "RICARDO PABLO BELMONT CASSINELLI": "👴"
}

DATA_DIR = Path("data/raw/todos")
PROY_DIR = Path("data/proyections")
GEO_FILE = DATA_DIR.parent.parent / "ubigeo_estructura.json"

# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y DE DATOS
# ---------------------------------------------------------
def clean_name(x):
    """Limpia nombres eliminando guiones y tildes para asegurar cruces exactos."""
    return str(x).upper().replace('_', ' ').replace('Á','A').replace('É','E').replace('Í','I').replace('Ó','O').replace('Ú','U').strip()

@st.cache_data
def load_geojson(tipo):
    """Carga los polígonos GeoJSON de regiones o provincias."""
    if tipo == "regiones":
        url = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_departamental_simple.geojson"
    else:
        url = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_provincial_simple.geojson"
    try:
        r = requests.get(url, timeout=5)
        return r.json()
    except Exception as e:
        return None

@st.cache_data
def get_geo_mapping():
    """
    Construye y retorna el diccionario de mapeo Provincia -> Región y los sets
    necesarios para filtrar los continentes y auditorías.
    """
    province_to_region_map = {}
    region_set = set()
    province_set = set()
    continents_set = set()

    if GEO_FILE.exists():
        print("exists")
        with open(GEO_FILE, 'r', encoding='utf-8') as f:
            ubigeo_structure = json.load(f)

        # Mapeo inequívoco para Perú
        for region, provinces in ubigeo_structure.get("PERU", {}).items():
            region_clean = clean_name(region)
            region_set.add(region_clean)

            if isinstance(provinces, list):
                for province in provinces:
                    province_clean = clean_name(province)
                    province_set.add(province_clean)
                    province_to_region_map[province_clean] = region_clean

        # Mapeo para Extranjero (Continentes)
        continentes_list = ubigeo_structure.get("EXTRANJERO", [])
        continents = [clean_name(c) for c in continentes_list]
        for cont in continents:
            province_to_region_map[cont] = cont
            region_set.add(cont)
            continents_set.add(cont)

    return province_to_region_map, region_set, province_set, continents_set

def load_data():
    """Carga y consolida los cortes históricos de la ONPE."""
    if not DATA_DIR.exists(): return pd.DataFrame()
    archivos = list(DATA_DIR.glob("*.csv"))
    if not archivos: return pd.DataFrame()

    df = pd.concat([pd.read_csv(f) for f in archivos], ignore_index=True)
    numeric_cols = ['actas_contabilizadas_pct', 'porcentaje_valido', 'cantidad_votos', 'electores_habiles', 'asistentes_totales', 'ausentes_totales', 'pendientes_totales']

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df.sort_values('actas_contabilizadas_pct')

def load_latest_projection(tipo_jee, penalty):
    """Obtiene la última proyección según los hiperparámetros seleccionados."""
    if not PROY_DIR.exists(): return pd.DataFrame()
    prefix = f"proyeccion_{tipo_jee}_p{penalty:.1f}_*.csv"
    archivos = list(PROY_DIR.glob(prefix))
    if not archivos: return pd.DataFrame()

    latest_file = max(archivos, key=lambda x: x.stat().st_mtime)
    return pd.read_csv(latest_file)