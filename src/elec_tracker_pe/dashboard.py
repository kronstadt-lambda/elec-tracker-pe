import streamlit as st
import pandas as pd
import plotly.graph_objects as from_plotly
import numpy as np
from pathlib import Path
import time

# ---------------------------------------------------------
# CONFIGURACIÓN Y ESTILOS
# ---------------------------------------------------------
st.set_page_config(page_title="ONPE Tracker Radar", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
    
    /* Fondo oscuro para el lienzo/página */
    html, body, [class*="css"] {
        font-family: 'VT323', monospace !important;
        font-size: 1.2rem;
        background-color: #282828; /* Gruvbox Dark central */
        color: #ebdbb2; /* Texto claro Gruvbox */
    }
    
    /* Asegura que el contenedor de Streamlit sea oscuro */
    .stApp { background-color: #282828; }
    
    /* Títulos en naranja retro */
    h1, h2, h3 { color: #fe8019 !important; font-weight: bold; }
    
    /* Ajuste de métricas superiores para fondo oscuro */
    div[data-testid="metric-container"] {
        background-color: #3c3836; /* Un gris un poco más claro que el fondo */
        border: 2px solid #504945;
        padding: 10px;
        border-radius: 5px;
    }
    div[data-testid="stMetricValue"] { color: #fe8019; }
    div[data-testid="stMetricLabel"] { color: #ebdbb2; }
    </style>
""", unsafe_allow_html=True)

CANDIDATOS_TARGET = {
    "KEIKO SOFIA FUJIMORI HIGUCHI": "#fe8019",        # Naranja
    "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA": "#83a598", # Celeste
    "JORGE NIETO MONTESINOS": "#fabd2f",               # Amarillo
    "ROBERTO HELBERT SANCHEZ PALOMINO": "#b8bb26",     # Verde Claro
    "RICARDO PABLO BELMONT CASSINELLI": "#689d6a"      # Verde Oscuro
}

DATA_DIR = Path("data/raw/todos")

# ---------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------
def load_data():
    if not DATA_DIR.exists(): return pd.DataFrame()
    archivos = list(DATA_DIR.glob("*.csv"))
    if not archivos: return pd.DataFrame()

    df = pd.concat([pd.read_csv(f) for f in archivos], ignore_index=True)
    for col in ['actas_contabilizadas_pct', 'porcentaje_valido', 'cantidad_votos', 'electores_habiles', 'asistentes_totales', 'ausentes_totales', 'pendientes_totales']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

    return df.sort_values('actas_contabilizadas_pct')

# ---------------------------------------------------------
# COMPONENTES VISUALES
# ---------------------------------------------------------
def render_header(df_latest):
    """Renderiza el encabezado estilo periódico con métricas clave."""
    st.markdown(f"### 📡 RADAR ELECTORAL · ACTUALIZADO: {df_latest['actualizado_dt'].iloc[0]} · CORTE ONPE: {df_latest['actas_contabilizadas_pct'].iloc[0]}%")

    if 'electores_habiles' in df_latest.columns:
        c1, c2, c3, c4 = st.columns(4)
        habiles = df_latest['electores_habiles'].iloc[0]
        asistentes = df_latest['asistentes_totales'].iloc[0]
        ausentes = df_latest['ausentes_totales'].iloc[0]
        pendientes = df_latest['pendientes_totales'].iloc[0]

        c1.metric("Electores Hábiles", f"{habiles:,.0f}")
        c2.metric("Asistentes (Procesados)", f"{asistentes:,.0f}", f"{(asistentes/habiles)*100:.1f}%")
        c3.metric("Ausentes Estimados", f"{ausentes:,.0f}", f"{(ausentes/habiles)*100:.1f}%", delta_color="inverse")
        c4.metric("Pendientes (Rural/Ext)", f"{pendientes:,.0f}", f"{(pendientes/habiles)*100:.1f}%")

    st.markdown("---")

def render_bar_and_versus(df_latest):
    """Renderiza el gráfico de barras horizontales y el comparador Versus."""
    col_bar, col_vs = st.columns([1.2, 1])

    df_chart = df_latest[df_latest['candidato_o_tipo'].isin(CANDIDATOS_TARGET.keys())].copy()
    df_chart['nombre_corto'] = df_chart['candidato_o_tipo'].apply(lambda x: x.split()[0] + " " + x.split()[1] if len(x.split())>1 else x)
    df_chart = df_chart.sort_values('cantidad_votos', ascending=True)

    with col_bar:
        st.markdown("#### Votación por Candidato (Último Corte)")
        fig_bar = from_plotly.Figure()

        colores = [CANDIDATOS_TARGET[cand] for cand in df_chart['candidato_o_tipo']]

        fig_bar.add_trace(from_plotly.Bar(
            y=df_chart['nombre_corto'],
            x=df_chart['cantidad_votos'],
            orientation='h',
            marker_color=colores,
            text=[f"{v:,.0f} votos ({p}%)" for v, p in zip(df_chart['cantidad_votos'], df_chart['porcentaje_valido'])],
            textposition='auto',
            insidetextanchor='end'
        ))

        fig_bar.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="VT323", size=16, color="#3c3836"),
            height=350, margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(showgrid=True, gridcolor="#d5c4a1")
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_vs:
        st.markdown("#### Comparador Directo (Versus)")
        nombres_disponibles = df_chart['candidato_o_tipo'].tolist()

        c1, c2 = st.columns(2)
        cand1 = c1.selectbox("Candidato A:", nombres_disponibles, index=0)
        opciones_cand2 = [n for n in nombres_disponibles if n != cand1]
        cand2 = c2.selectbox("Candidato B:", opciones_cand2, index=0)

        votos1 = df_chart[df_chart['candidato_o_tipo'] == cand1]['cantidad_votos'].values[0]
        pct1 = df_chart[df_chart['candidato_o_tipo'] == cand1]['porcentaje_valido'].values[0]

        votos2 = df_chart[df_chart['candidato_o_tipo'] == cand2]['cantidad_votos'].values[0]
        pct2 = df_chart[df_chart['candidato_o_tipo'] == cand2]['porcentaje_valido'].values[0]

        diff_votos = votos1 - votos2
        diff_pct = pct1 - pct2

        lider = cand1 if diff_votos > 0 else cand2
        lider_color = CANDIDATOS_TARGET[lider]

        st.markdown(f"""
        <div style='background-color: {lider_color}20; border-left: 5px solid {lider_color}; padding: 15px; margin-top: 15px;'>
            <h3 style='margin:0; color:{lider_color} !important;'>{lider.split()[0]} Lidera por:</h3>
            <h1 style='margin:0; font-size: 3rem;'>{abs(diff_votos):,.0f} <span style='font-size: 1.5rem;'>votos</span></h1>
            <p style='margin:0; font-size: 1.5rem;'>Margen: <b>{abs(diff_pct):.2f} pp</b></p>
        </div>
        """, unsafe_allow_html=True)

def render_projections(df_filtrado, min_x):
    """Renderiza las dos gráficas de series de tiempo separadas."""
    st.markdown("---")
    st.markdown("#### Evolución y Tendencias")

    fig_pct = from_plotly.Figure()
    fig_abs = from_plotly.Figure()

    for candidato, color in CANDIDATOS_TARGET.items():
        df_cand = df_filtrado[df_filtrado['candidato_o_tipo'] == candidato]
        if df_cand.empty: continue

        x_data = df_cand['actas_contabilizadas_pct'].values
        y_pct = df_cand['porcentaje_valido'].values
        y_abs = df_cand['cantidad_votos'].values
        nombre_corto = candidato.split()[0]

        fig_pct.add_trace(from_plotly.Scatter(x=x_data, y=y_pct, mode='lines+markers', name=nombre_corto, line=dict(color=color, width=3)))
        fig_abs.add_trace(from_plotly.Scatter(x=x_data, y=y_abs, mode='lines+markers', name=nombre_corto, line=dict(color=color, width=3)))

        # Regresión Lineal
        if len(x_data) > 1:
            x_proj = np.linspace(min_x, 100, 50)

            p_pct = np.poly1d(np.polyfit(x_data, y_pct, 1))
            fig_pct.add_trace(from_plotly.Scatter(x=x_proj, y=p_pct(x_proj), mode='lines', line=dict(color=color, width=1.5, dash='dot'), showlegend=False, opacity=0.6))

            p_abs = np.poly1d(np.polyfit(x_data, y_abs, 1))
            fig_abs.add_trace(from_plotly.Scatter(x=x_proj, y=p_abs(x_proj), mode='lines', line=dict(color=color, width=1.5, dash='dot'), showlegend=False, opacity=0.6))

    layout_base = dict(
        plot_bgcolor="#ebdbb2", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="VT323", size=14, color="#3c3836"),
        xaxis=dict(title="% Actas Contabilizadas", range=[min_x - 0.5, 100], gridcolor="#d5c4a1"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=30, b=30)
    )

    fig_pct.update_layout(**layout_base, title="Votos Válidos (%)", yaxis=dict(range=[9, 20], gridcolor="#d5c4a1"))
    fig_abs.update_layout(**layout_base, title="Cantidad de Votos (Absolutos)", yaxis=dict(range=[1000000, 2500000], gridcolor="#d5c4a1"))

    st.plotly_chart(fig_pct, use_container_width=True)
    st.plotly_chart(fig_abs, use_container_width=True)


# ---------------------------------------------------------
# ORQUESTADOR PRINCIPAL
# ---------------------------------------------------------
df = load_data()

if df.empty:
    st.warning("📡 Esperando datos en data/raw/todos/...")
else:
    ultima_fecha = df['actualizado_dt'].max()
    df_latest = df[df['actualizado_dt'] == ultima_fecha]
    df_filtrado = df[df['candidato_o_tipo'].isin(CANDIDATOS_TARGET.keys())]

    render_header(df_latest)
    render_bar_and_versus(df_latest)
    render_projections(df_filtrado, df_filtrado['actas_contabilizadas_pct'].min())

time.sleep(60)
st.rerun()