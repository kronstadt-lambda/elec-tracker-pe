import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import matplotlib.dates as mdates

# ==========================================
# CONFIGURACIÓN DE RUTAS LOCALES
# ==========================================
DATA_DIR = Path("/home/klambda/My_Projects/elec-tracker-pe/data")
PARQUET_FILE = DATA_DIR / "snapshots_sincronizados/master_series_30m.parquet"
IMAGES_DIR = DATA_DIR / "images/anomalias"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Candidatos a contrastar (Asegúrate de que coincidan con los nombres limpios de tu parquet)
CAND1 = "SANCHEZ PALOMINO"
CAND2 = "LÓPEZ ALIAGA"
UMBRAL_ANOMALIA = 1000

def encontrar_y_plotear_anomalias():
    print(f"🔍 Cargando matriz temporal desde {PARQUET_FILE.name}...")
    df = pd.read_parquet(PARQUET_FILE)

    # Filtrar a los dos candidatos en disputa
    df = df[df['candidato'].isin([CAND1, CAND2])]

    # Separar Total Nacional ("TODOS") de las Provincias
    df_nacional = df[df['ubicacion'] == 'TODOS'].copy()
    df_provincial = df[df['ubicacion'] != 'TODOS'].copy()

    # Sumar todas las provincias por Timestamp y Candidato
    df_suma_prov = df_provincial.groupby(['timestamp_30m', 'candidato'])['votos_interpolados'].sum().reset_index()
    df_suma_prov.rename(columns={'votos_interpolados': 'suma_provincias'}, inplace=True)

    # Preparar el Nacional para el cruce
    df_nacional = df_nacional[['timestamp_30m', 'candidato', 'votos_interpolados']]
    df_nacional.rename(columns={'votos_interpolados': 'total_nacional'}, inplace=True)

    # Unir ambas tablas
    df_cruce = pd.merge(df_nacional, df_suma_prov, on=['timestamp_30m', 'candidato'], how='inner')

    # Calcular la brecha (Gap)
    df_cruce['brecha_fantasma'] = df_cruce['total_nacional'] - df_cruce['suma_provincias']

    # Identificar Tiempos donde el Gap de algún candidato supera el umbral
    tiempos_anomalos = df_cruce[df_cruce['brecha_fantasma'] > UMBRAL_ANOMALIA]['timestamp_30m'].unique()

    if len(tiempos_anomalos) == 0:
        print("✅ No se detectaron anomalías por encima de los 1,000 votos en el historial.")
        return

    print(f"🚨 ¡ALERTA! Se detectaron {len(tiempos_anomalos)} momentos con anomalías > {UMBRAL_ANOMALIA} votos.")

    # Para no generar 50 imágenes iguales, agrupamos toda la serie de tiempo en un solo análisis global
    # (Si el proyecto crece a meses de datos, aquí se cortaría por días)

    _generar_grafico_evidencia(df_cruce, "Reporte_Global_Anomalias")

def _generar_grafico_evidencia(df_plot, nombre_archivo):
    # Configurar estilo visual oscuro (tipo dashboard / terminal)
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle('AUDITORÍA DE VOTOS: NACIONAL VS. SUMA DE REGIONES', fontsize=18, color='#fe8019', fontweight='bold')

    colores = {CAND1: '#d3869b', CAND2: '#83a598'} # Colores contrastantes

    # =======================================================
    # PANEL 1: La Divergencia (Solo para el candidato anómalo)
    # =======================================================
    # Para simplificar el gráfico 1, buscamos al candidato con mayor brecha
    max_gap_row = df_plot.loc[df_plot['brecha_fantasma'].idxmax()]
    cand_anomalo = max_gap_row['candidato']

    df_anomalo = df_plot[df_plot['candidato'] == cand_anomalo].sort_values('timestamp_30m')

    ax1.plot(df_anomalo['timestamp_30m'], df_anomalo['total_nacional'], color='#fe8019', linewidth=3, label=f'API Nacional ({cand_anomalo})')
    ax1.plot(df_anomalo['timestamp_30m'], df_anomalo['suma_provincias'], color='#fabd2f', linewidth=2, linestyle='--', label=f'Suma 26 Regiones ({cand_anomalo})')

    ax1.fill_between(df_anomalo['timestamp_30m'], df_anomalo['suma_provincias'], df_anomalo['total_nacional'], color='#fe8019', alpha=0.2)

    ax1.set_title(f"Comportamiento del Total de Votos: {cand_anomalo}", color='white', fontsize=14)
    ax1.set_ylabel("Cantidad de Votos")
    ax1.grid(color='#504945', linestyle=':', alpha=0.6)
    ax1.legend(loc='upper left', frameon=False)

    # =======================================================
    # PANEL 2: Contraste de "Votos Fantasma" (CAND1 vs CAND2)
    # =======================================================
    for cand in [CAND1, CAND2]:
        df_c = df_plot[df_plot['candidato'] == cand].sort_values('timestamp_30m')
        ax2.plot(df_c['timestamp_30m'], df_c['brecha_fantasma'], color=colores[cand], linewidth=2.5, marker='o', label=f'Brecha {cand}')

        # Anotar el punto máximo de la brecha
        if df_c['brecha_fantasma'].max() > 100:
            max_p = df_c.loc[df_c['brecha_fantasma'].idxmax()]
            ax2.annotate(f"+{int(max_p['brecha_fantasma']):,}",
                         xy=(max_p['timestamp_30m'], max_p['brecha_fantasma']),
                         xytext=(0, 10), textcoords='offset points', color=colores[cand], fontweight='bold')

    ax2.axhline(0, color='white', linewidth=1)
    ax2.set_title("Volumen de 'Votos Fantasma' (Nacional - Sumatoria Regional)", color='white', fontsize=14)
    ax2.set_ylabel("Diferencia de Votos")
    ax2.grid(color='#504945', linestyle=':', alpha=0.6)
    ax2.legend(loc='upper left', frameon=False)

    # Formatear Eje X para que se vean bien las fechas/horas
    for ax in [ax1, ax2]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=0)

    plt.tight_layout()

    # Guardar Imagen
    output_path = IMAGES_DIR / f"{nombre_archivo}.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f"📸 Imagen de evidencia guardada en: {output_path}")
    plt.close()

if __name__ == "__main__":
    encontrar_y_plotear_anomalias()