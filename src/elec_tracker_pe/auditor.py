import os
import pandas as pd
from pathlib import Path

# ==========================================
# 1. CONFIGURACIÓN DE RUTAS Y CANDIDATOS
# ==========================================
# Ajusta BASE_DIR dependiendo de dónde coloques este script
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data/raw")

# Carpetas de salida para auditoría
AUDIT_DIR = BASE_DIR / "data"
SYNC_DIR = AUDIT_DIR / "snapshots_sincronizados"
SYNC_DIR.mkdir(parents=True, exist_ok=True)

# Lista de candidatos objetivo (usamos palabras clave para evitar problemas con nombres completos)
CANDIDATOS_TARGET = [
    "FUJIMORI HIGUCHI",
    "LÓPEZ ALIAGA",
    "SANCHEZ PALOMINO",
    "NIETO",
    "BELMONT CASSINELLI"
]

def consolidar_y_sincronizar():
    print("🔍 [AUDITORÍA] Iniciando escaneo de archivos crudos en data/raw...")

    # 1. Recopilar todos los CSVs
    df_list = []
    archivos_csv = list(DATA_DIR.rglob("*.csv"))

    if not archivos_csv:
        print("⚠️ No se encontraron archivos CSV en data/raw.")
        return

    # Leer las columnas esenciales de todos los archivos
    columnas_requeridas = ['ubicacion', 'actualizado_dt', 'candidato_o_tipo', 'cantidad_votos']

    for archivo in archivos_csv:
        try:
            df_temp = pd.read_csv(archivo, usecols=columnas_requeridas)
            df_list.append(df_temp)
        except Exception as e:
            print(f"⚠️ Error leyendo {archivo.name}: {e}")

    # 2. Unir todo en un megabloque en memoria
    df_crudo = pd.concat(df_list, ignore_index=True)
    print(f"📊 Total de registros crudos cargados: {len(df_crudo):,}")

    # 3. Limpieza y Filtrado
    # Convertir fecha a datetime real de Pandas
    df_crudo['actualizado_dt'] = pd.to_datetime(df_crudo['actualizado_dt'], errors='coerce')
    df_crudo = df_crudo.dropna(subset=['actualizado_dt'])

    # Limpiar votos (quitar comas si las hay) y pasar a numérico
    df_crudo['cantidad_votos'] = pd.to_numeric(
        df_crudo['cantidad_votos'].astype(str).str.replace(',', '').str.replace("'", ''),
        errors='coerce'
    ).fillna(0)

    # Filtrar solo a los candidatos de interés usando Regex
    patron_candidatos = '|'.join(CANDIDATOS_TARGET)
    df_filtrado = df_crudo[df_crudo['candidato_o_tipo'].str.contains(patron_candidatos, case=False, na=False)].copy()

    # Normalizar nombres de candidatos para que queden limpios
    def limpiar_nombre(nombre):
        for c in CANDIDATOS_TARGET:
            if c.lower() in nombre.lower(): return c
        return nombre

    df_filtrado['candidato'] = df_filtrado['candidato_o_tipo'].apply(limpiar_nombre)
    df_filtrado = df_filtrado[['ubicacion', 'candidato', 'actualizado_dt', 'cantidad_votos']]

    print("⏳ [AUDITORÍA] Sincronizando e interpolando tiempos (Intervalos de 30 min)...")

    # 4. Magia de Pandas: Interpolación y Resampling por Grupo (Ubicación + Candidato)
    dfs_sincronizados = []
    grupos = df_filtrado.groupby(['ubicacion', 'candidato'])

    for (ubicacion, candidato), grupo in grupos:
        # Ordenar por tiempo y quitar duplicados exactos
        grupo = grupo.sort_values('actualizado_dt').drop_duplicates(subset=['actualizado_dt'], keep='last')

        # Poner el tiempo como índice (Requisito para Resampling)
        grupo.set_index('actualizado_dt', inplace=True)

        # Interpolar en ventanas de 30 minutos ('30min')
        # .mean() promedia si hay varios scapes en la misma media hora
        # .interpolate('linear') traza la línea matemática para los vacíos
        serie_resampleada = grupo[['cantidad_votos']].resample('30min').mean()
        serie_interpolada = serie_resampleada.interpolate(method='linear')

        # Extender hacia adelante y atrás para que no queden nulos en los extremos
        serie_interpolada = serie_interpolada.ffill().bfill()

        # Volver a formato de columnas
        df_res = serie_interpolada.reset_index()
        df_res['ubicacion'] = ubicacion
        df_res['candidato'] = candidato

        dfs_sincronizados.append(df_res)

    # 5. Ensamblar y Exportar el Master Parquet
    df_master = pd.concat(dfs_sincronizados, ignore_index=True)

    # Renombrar columna para claridad
    df_master.rename(columns={'actualizado_dt': 'timestamp_30m', 'cantidad_votos': 'votos_interpolados'}, inplace=True)

    # Redondear votos a entero (no existen medios votos)
    df_master['votos_interpolados'] = df_master['votos_interpolados'].round().astype(int)

    # Reordenar columnas
    df_master = df_master[['timestamp_30m', 'ubicacion', 'candidato', 'votos_interpolados']]

    # Guardar en formato PARQUET
    archivo_salida = SYNC_DIR / "master_series_30m.parquet"
    df_master.to_parquet(archivo_salida, index=False, engine='pyarrow')

    print(f"✅ [ÉXITO] Base de datos temporal creada: {archivo_salida}")
    print(f"💡 El archivo ocupa apenas unos Kilobytes, pero contiene la matriz sincronizada de todas las provincias y candidatos.")

if __name__ == "__main__":
    # Necesitas tener instalada la librería pyarrow (pip install pyarrow fastparquet)
    consolidar_y_sincronizar()