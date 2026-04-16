import pandas as pd
import requests
import json
import streamlit as st
from pathlib import Path
import os

# ---------------------------------------------------------
# CONSTANTES Y CONFIGURACIÓN GLOBAL (VERSIÓN DEPLOY)
# ---------------------------------------------------------
CANDIDATOS_TARGET = {
    "KEIKO SOFIA FUJIMORI HIGUCHI": "#fe8019",
    "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA": "#83a598",
    "JORGE NIETO MONTESINOS": "#fabd2f",
    "ROBERTO HELBERT SANCHEZ PALOMINO": "#b8bb26",
    "RICARDO PABLO BELMONT CASSINELLI": "#689d6a"
}

NOMBRES_CORTOS = {
    "KEIKO SOFIA FUJIMORI HIGUCHI": "Keiko Fujimori",
    "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA": "Rafael Lopez Aliaga",
    "JORGE NIETO MONTESINOS": "Jorge Nieto",
    "ROBERTO HELBERT SANCHEZ PALOMINO": "Roberto Sanchez",
    "RICARDO PABLO BELMONT CASSINELLI": "Ricardo Belmont"
}

EMOJIS_CANDIDATOS = {
    "KEIKO SOFIA FUJIMORI HIGUCHI": "🍊",
    "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA": "🐷",
    "JORGE NIETO MONTESINOS": "☀️",
    "ROBERTO HELBERT SANCHEZ PALOMINO": "🤠",
    "RICARDO PABLO BELMONT CASSINELLI": "👴"
}

# Diccionario forzado para errores tipográficos de la ONPE que no se arreglan quitando tildes
PROVINCIA_NORM = {
    "ANTONIO RAYMONDI": "ANTONIO RAIMONDI",
    "NAZCA": "NASCA",
    "VICTOR FAFARDO": "VICTOR FAJARDO",
}

# ---------------------------------------------------------
# RUTAS CENTRALIZADAS (DIRECTORIO data_stream)
# ---------------------------------------------------------
STREAM_DIR = Path("data_stream")

GEO_FILE = STREAM_DIR / "ubigeo_estructura.json"
TODOS_FILE = STREAM_DIR / "onpe_todos_latest.csv"
PROY_FILE = STREAM_DIR / "proyeccion_final_latest.csv"
ACTAS_FILE = STREAM_DIR / "actas.csv" # CORRECCIÓN: Apunta a actas_jee.csv según tu stream_builder.py

# ---------------------------------------------------------
# FUNCIONES AUXILIARES Y DE DATOS
# ---------------------------------------------------------
def clean_name(x):
    """Limpia nombres, elimina tildes y normaliza discrepancias."""
    if not x: return ""
    name = str(x).upper().replace('_', ' ').strip()

    # Eliminación agresiva de tildes
    replacements = (
        ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
    )
    for a, b in replacements:
        name = name.replace(a, b)

    # Aplicar mapeo de normalización directo
    return PROVINCIA_NORM.get(name, name)

@st.cache_data
def load_geojson(tipo):
    if tipo == "regiones":
        url = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_departamental_simple.geojson"
    else:
        url = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_provincial_simple.geojson"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        # NORMALIZACIÓN CRÍTICA: Limpiar nombres dentro del GeoJSON para que coincidan con los datos
        for feature in data['features']:
            prop = 'NOMBDEP' if tipo == "regiones" else 'NOMBPROV'
            if prop in feature['properties']:
                # Creamos una nueva propiedad limpia para el match de Plotly
                feature['properties'][f'{prop}_CLEAN'] = clean_name(feature['properties'][prop])

        return data
    except Exception as e:
        return None

@st.cache_data
def get_geo_mapping():
    province_to_region_map = {}
    region_set = set()
    province_set = set()
    continents_set = set()

    if GEO_FILE.exists():
        with open(GEO_FILE, 'r', encoding='utf-8') as f:
            ubigeo_structure = json.load(f)

        for region, provinces in ubigeo_structure.get("PERU", {}).items():
            region_clean = clean_name(region)
            region_set.add(region_clean)

            # Soporta tanto si provinces es una Lista o un Diccionario
            if isinstance(provinces, list):
                for province in provinces:
                    province_clean = clean_name(province)
                    province_set.add(province_clean)
                    province_to_region_map[province_clean] = region_clean
            elif isinstance(provinces, dict):
                for province in provinces.keys():
                    province_clean = clean_name(province)
                    province_set.add(province_clean)
                    province_to_region_map[province_clean] = region_clean

        continentes_list = ubigeo_structure.get("EXTRANJERO", [])
        continents = [clean_name(c) for c in continentes_list]
        for cont in continents:
            province_to_region_map[cont] = cont
            region_set.add(cont)
            continents_set.add(cont)

    return province_to_region_map, region_set, province_set, continents_set

def load_data():
    if not TODOS_FILE.exists(): return pd.DataFrame()
    df = pd.read_csv(TODOS_FILE)
    numeric_cols = ['actas_contabilizadas_pct', 'porcentaje_valido', 'cantidad_votos', 'electores_habiles', 'asistentes_totales', 'ausentes_totales', 'pendientes_totales']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.sort_values('actas_contabilizadas_pct')

def load_latest_projection():
    if not PROY_FILE.exists(): return pd.DataFrame()
    return pd.read_csv(PROY_FILE)

def load_actas():
    if not ACTAS_FILE.exists(): return pd.DataFrame()
    return pd.read_csv(ACTAS_FILE)