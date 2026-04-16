import os
import shutil
import pandas as pd
from pathlib import Path

# Configuración de rutas
BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROY_DIR = BASE_DIR / "data" / "proyections"
STREAM_DIR = BASE_DIR / "data_stream"

def prepare_stream_folder():
    """Crea la carpeta de destino si no existe."""
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📂 Directorio de salida preparado: {STREAM_DIR}")

def build_todos_history():
    """Aglomera el histórico de 'todos' eliminando filas de control (Nulos/Blancos/Totales)."""
    print("⏳ Construyendo histórico consolidado Nacional (TODOS)...")
    todos_dir = RAW_DIR / "todos"

    if not todos_dir.exists():
        return

    csv_files = list(todos_dir.glob("*.csv"))
    if not csv_files:
        return

    # 1. Leer y concatenar todos los archivos
    df_consolidado = pd.concat([pd.read_csv(f) for f in csv_files], ignore_index=True)

    # 2. FILTRADO CRÍTICO: Eliminar filas que no son de candidatos específicos
    unwanted_terms = ['VOTOS EN BLANCO', 'VOTOS NULOS', 'total de votos']
    if 'candidato_o_tipo' in df_consolidado.columns:
        # Usamos regex para eliminar las coincidencias exactas o parciales de los términos no deseados
        df_consolidado = df_consolidado[~df_consolidado['candidato_o_tipo'].str.contains('|'.join(unwanted_terms), case=False, na=False)]

    # 3. Limpiar conversiones numéricas
    numeric_cols = ['actas_contabilizadas_pct', 'porcentaje_valido', 'cantidad_votos']
    for col in numeric_cols:
        if col in df_consolidado.columns:
            df_consolidado[col] = pd.to_numeric(df_consolidado[col], errors='coerce')

    # 4. Ordenar por avance y eliminar duplicados para asegurar una línea de tiempo limpia
    df_consolidado = df_consolidado.sort_values(by='actas_contabilizadas_pct')
    df_consolidado = df_consolidado.drop_duplicates()

    # 5. Guardar archivo único sobreescribible
    output_path = STREAM_DIR / "onpe_todos_latest.csv"
    df_consolidado.to_csv(output_path, index=False, encoding='utf-8')
    print(f"   ✅ Guardado: {output_path.name} (Datos de candidatos filtrados)")

def copy_latest_projection():
    """Copia la última proyección final generada."""
    print("⏳ Copiando proyección más reciente...")
    csv_files = list(PROY_DIR.glob("proyeccion_final_*.csv"))
    if not csv_files:
        return

    # Obtener el archivo más reciente por fecha de modificación
    latest_file = max(csv_files, key=os.path.getmtime)
    shutil.copy2(latest_file, STREAM_DIR / "proyeccion_final_latest.csv")
    print(f"   ✅ Copiado: {latest_file.name}")

def extract_jee_acts():
    """Genera el reporte sumario de actas JEE y pendientes por provincia."""
    print("⏳ Generando reporte consolidado de Actas JEE y Pendientes...")
    jee_data = []

    # Iterar sobre carpetas de provincias/continentes
    for folder in [f for f in RAW_DIR.iterdir() if f.is_dir() and f.name != 'todos']:
        csv_files = list(folder.glob("*.csv"))
        if not csv_files: continue

        latest_file = max(csv_files, key=os.path.getmtime)
        df_prov = pd.read_csv(latest_file)

        if not df_prov.empty:
            row = df_prov.iloc[0]
            jee_data.append({
                "ubicacion_clean": str(row.get('ubicacion', folder.name)).upper().replace('_', ' ').strip(),
                "actas_jee": int(row.get('global_jee', 0)) if pd.notna(row.get('global_jee')) else 0,
                "actas_pendientes": int(row.get('global_pendientes', 0)) if pd.notna(row.get('global_pendientes')) else 0
            })

    if jee_data:
        # Ordenamos primero por JEE (mayor a menor) y luego por Pendientes
        df_jee = pd.DataFrame(jee_data).sort_values(by=['actas_jee', 'actas_pendientes'], ascending=[False, False])
        output_path = STREAM_DIR / "actas.csv"
        df_jee.to_csv(output_path, index=False, encoding='utf-8')
        print(f"   ✅ Guardado: {output_path.name} (Reporte JEE y Pendientes generado)")

if __name__ == "__main__":
    prepare_stream_folder()
    build_todos_history()
    copy_latest_projection()
    extract_jee_acts()