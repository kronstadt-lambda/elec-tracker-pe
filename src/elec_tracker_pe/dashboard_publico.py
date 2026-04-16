import streamlit as st
import pandas as pd
import plotly.graph_objects as from_plotly
import plotly.express as px
import numpy as np

# Importamos las herramientas, datos y configuraciones desde utils_graphs.py
from utils_graphs import (
    CANDIDATOS_TARGET, NOMBRES_CORTOS, EMOJIS_CANDIDATOS,
    clean_name, load_geojson, get_geo_mapping,
    load_data, load_latest_projection, load_actas
)

# ---------------------------------------------------------
# CONFIGURACIÓN Y ESTILOS
# ---------------------------------------------------------
st.set_page_config(page_title="ONPE Tracker Radar (Público)", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'VT323', monospace !important;
        font-size: 1.2rem;
        background-color: #282828;
        color: #ebdbb2;
    }
    .stApp { background-color: #282828; }
    h1, h2, h3 { color: #fe8019 !important; font-weight: bold; }
    div[data-testid="metric-container"] {
        background-color: #3c3836;
        border: 2px solid #504945;
        padding: 10px;
        border-radius: 5px;
    }
    div[data-testid="stMetricValue"] { color: #fe8019; }
    div[data-testid="stMetricLabel"] { color: #ebdbb2; }
    
    .winner-box {
        padding: 15px;
        border-radius: 5px;
        margin-top: 10px;
        margin-bottom: 15px;
        font-family: 'Arial', sans-serif;
    }
    .warning-box {
        background-color: #d7992120;
        border-left: 5px solid #d79921;
        padding: 15px;
        margin-top: 25px;
        margin-bottom: 25px;
        border-radius: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# CACHÉ DE LECTURA DE DISCO (Optimización Crítica)
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_cached_data():
    df = load_data()
    df_proy = load_latest_projection()
    df_actas = load_actas()
    return df, df_proy, df_actas

# ---------------------------------------------------------
# MÓDULOS DE VISUALIZACIÓN Y TEXTO
# ---------------------------------------------------------
def render_header(df_latest):
    st.markdown(f"### 📡 RADAR ELECTORAL · ACTUALIZADO: {df_latest['actualizado_dt'].iloc[0]} · CORTE ONPE: {df_latest['actas_contabilizadas_pct'].iloc[0]}%")

def render_bar_and_versus(df_latest):
    col_bar, col_vs = st.columns([1.2, 1])

    df_chart = df_latest[df_latest['candidato_o_tipo'].isin(CANDIDATOS_TARGET.keys())][['candidato_o_tipo', 'cantidad_votos', 'porcentaje_valido']].copy()
    df_chart['nombre_corto'] = df_chart['candidato_o_tipo'].map(NOMBRES_CORTOS)
    df_chart = df_chart.sort_values('cantidad_votos', ascending=True)

    with col_bar:
        st.markdown("#### Votación por Candidato (Último Corte)")
        fig_bar = from_plotly.Figure()
        colores = [CANDIDATOS_TARGET[cand] for cand in df_chart['candidato_o_tipo']]

        fig_bar.add_trace(from_plotly.Bar(
            y=df_chart['nombre_corto'], x=df_chart['cantidad_votos'],
            orientation='h', marker_color=colores,
            text=[f"{v:,.0f} votos ({p}%)" for v, p in zip(df_chart['cantidad_votos'], df_chart['porcentaje_valido'])],
            textposition='auto', insidetextanchor='end'
        ))
        fig_bar.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="VT323", size=16, color="#3c3836"),
            height=350, margin=dict(l=0, r=0, t=0, b=0), xaxis=dict(showgrid=True, gridcolor="#d5c4a1")
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_vs:
        st.markdown("#### Comparador para el 2do Puesto")

        cand1 = "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA"
        cand2 = "ROBERTO HELBERT SANCHEZ PALOMINO"

        df_vs = df_chart[df_chart['candidato_o_tipo'].isin([cand1, cand2])]

        if len(df_vs) == 2:
            votos1 = float(df_vs[df_vs['candidato_o_tipo'] == cand1]['cantidad_votos'].iloc[0])
            pct1 = float(df_vs[df_vs['candidato_o_tipo'] == cand1]['porcentaje_valido'].iloc[0])
            votos2 = float(df_vs[df_vs['candidato_o_tipo'] == cand2]['cantidad_votos'].iloc[0])
            pct2 = float(df_vs[df_vs['candidato_o_tipo'] == cand2]['porcentaje_valido'].iloc[0])

            diff_votos = votos1 - votos2
            diff_pct = pct1 - pct2
            lider = cand1 if diff_votos > 0 else cand2
            lider_color = CANDIDATOS_TARGET[lider]

            lider_nombre_corto = NOMBRES_CORTOS.get(lider, lider)

            st.markdown(f"""
            <div style='background-color: {lider_color}20; border-left: 5px solid {lider_color}; padding: 15px; margin-top: 15px;'>
                <h3 style='margin:0; color:{lider_color} !important;'>{lider_nombre_corto} Lidera el 2do puesto por:</h3>
                <h1 style='margin:0; font-size: 3rem;'>{abs(diff_votos):,.0f} <span style='font-size: 1.5rem;'>votos</span></h1>
                <p style='margin:0; font-size: 1.5rem;'>Margen: <b>{abs(diff_pct):.2f} pp</b></p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Esperando datos de ambos candidatos para la comparación.")

def render_projection_warning():
    st.markdown("""
    <div class="warning-box">
        <h3 style="margin-top:0; color: #d79921 !important;">⚠️ ZONA DE PROYECCIÓN ESTADÍSTICA</h3>
        <p style="font-family: 'Arial', sans-serif; font-size: 1rem; color: #ebdbb2;">
            A partir de este punto, los gráficos y mapas <strong>NO representan resultados oficiales consolidados</strong>. Muestran estimaciones matemáticas generadas por el <b>Modelo de Proyección Espacial Asimétrica (PEA)</b>, el cual integra proactivamente tanto las actas pendientes de procesamiento como aquellas observadas y enviadas al <b>JEE</b>. Se asume que, bajo el comportamiento histórico de estas instancias electorales, las observaciones suelen ser desestimadas en su casi totalidad, por lo que se consideran íntegramente dentro del conteo final proyectado al 100%.<br><br>
            <strong>Escenario Estructural:</strong> Esta proyección aplica factores de corrección que compensan el procesamiento tardío de actas. Por diseño, este escenario asume condiciones que <b>favorecen estadísticamente a un candidato de perfil rural frente a uno urbano</b>, ajustando el peso de los votos faltantes según la profundidad geográfica de las provincias por procesar.<br><br>
            <a href="#metodologia-de-proyeccion" style="color: #fe8019; font-weight: bold; text-decoration: underline;">[ Leer Metodología Técnica Detallada ↓ ]</a>
        </p>
        <hr style="border-color: #504945; margin: 10px 0;">
        <p style="font-family: 'Arial', sans-serif; font-size: 0.85rem; color: #a89984; margin-bottom: 0;">
            <em><b>Aviso Legal y de Fuente:</b> Esta metodología utiliza como insumo exclusivo los datos crudos extraídos mediante scraping directo de la plataforma pública de la ONPE en tiempo real. Cualquier recategorización oficial de actas, modificacion de datos, anulación de mesas por el JEE o caída temporal del sistema oficial alterará la base de datos e impactará automáticamente en la sensibilidad y resultados de esta proyección.</em>
        </p>
    </div>
    """, unsafe_allow_html=True)

def render_spatial_module(df_proy):
    st.markdown("#### 🗺️ Caudal de votos válidos faltantes proyectados por provincia y continente")

    if df_proy.empty:
        st.info("Esperando proyecciones territoriales...")
        return

    df_map = df_proy[(df_proy['candidato_o_tipo'].isin(CANDIDATOS_TARGET.keys())) & (df_proy['ubicacion'] != 'TODOS')][['ubicacion', 'candidato_o_tipo', 'votos_proyectados_faltantes']].copy()
    df_map['ubicacion_clean'] = df_map['ubicacion'].apply(clean_name)

    province_to_region_map, region_set, province_set, continents_set = get_geo_mapping()

    if not province_to_region_map:
        st.error(f"Error: No se encontró el archivo crítico `data_stream/ubigeo_estructura.json`.")
        return

    df_map['Parent_Region'] = df_map['ubicacion_clean'].map(province_to_region_map).replace({"CUZCO": "CUSCO"})
    df_map_provincial_audit = df_map.copy()

    tipo_mapa = st.radio("Alternar Vista:", ["🇵🇪 PERÚ (Regiones)", "🏙️ LIMA Y CALLAO", "🌍 EXTRANJERO"], horizontal=True, key="spatial_vista")

    sel_target = None
    df_det = pd.DataFrame()

    if "PERÚ" in tipo_mapa:
        df_peru_base = df_map[~df_map['Parent_Region'].isin(continents_set)]
        df_peru_base = df_peru_base[~df_peru_base['ubicacion_clean'].isin(['LIMA', 'CALLAO'])]

        df_peru = df_peru_base.groupby(['Parent_Region', 'candidato_o_tipo'])['votos_proyectados_faltantes'].sum().reset_index()
        idx_winners = df_peru.groupby('Parent_Region')['votos_proyectados_faltantes'].idxmax()
        df_winners = df_peru.loc[idx_winners].copy()
        df_winners.rename(columns={'candidato_o_tipo': 'Ganador'}, inplace=True)

        geojson_peru = load_geojson("regiones")

        if geojson_peru:
            fig_map = px.choropleth_mapbox(
                df_winners, geojson=geojson_peru, locations='Parent_Region', featureidkey="properties.NOMBDEP_CLEAN",
                color='Ganador', color_discrete_map=CANDIDATOS_TARGET,
                mapbox_style="carto-darkmatter", center={"lat": -9.18, "lon": -75.01}, zoom=4.2,
                hover_name='Parent_Region'
            )
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=500, showlegend=False)

            map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", selection_mode="points", key="mapa_peru")
            reg_list = sorted(df_peru['Parent_Region'].dropna().unique())
            sel_target = map_event.selection.points[0]["location"] if map_event and len(map_event.selection.points) > 0 else (reg_list[0] if reg_list else None)

            if sel_target:
                df_det = df_peru[df_peru['Parent_Region'] == sel_target]

    elif "LIMA Y CALLAO" in tipo_mapa:
        df_lima = df_map[df_map['ubicacion_clean'].isin(['LIMA', 'CALLAO'])].copy()
        df_reg = df_lima.groupby(['ubicacion_clean', 'candidato_o_tipo'])['votos_proyectados_faltantes'].sum().reset_index()

        idx_winners = df_reg.groupby('ubicacion_clean')['votos_proyectados_faltantes'].idxmax()
        df_winners = df_reg.loc[idx_winners].copy()
        df_winners.rename(columns={'candidato_o_tipo': 'Ganador'}, inplace=True)

        geojson_prov = load_geojson("provincias")
        if geojson_prov:
            fig_map = px.choropleth_mapbox(
                df_winners, geojson=geojson_prov, locations='ubicacion_clean', featureidkey="properties.NOMBPROV_CLEAN",
                color='Ganador', color_discrete_map=CANDIDATOS_TARGET,
                mapbox_style="carto-darkmatter", center={"lat": -12.05, "lon": -77.05}, zoom=8.5,
                hover_name='ubicacion_clean'
            )
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=500, showlegend=False)

            map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", selection_mode="points", key="mapa_lima")
            reg_list = sorted(df_reg['ubicacion_clean'].unique())
            sel_target = map_event.selection.points[0]["location"] if map_event and len(map_event.selection.points) > 0 else (reg_list[0] if reg_list else None)

            if sel_target:
                df_det = df_reg[df_reg['ubicacion_clean'] == sel_target]

    else:
        df_ext = df_map[df_map['Parent_Region'].isin(continents_set)].copy()
        df_reg = df_ext.groupby(['Parent_Region', 'candidato_o_tipo'])['votos_proyectados_faltantes'].sum().reset_index()

        idx_winners = df_reg.groupby('Parent_Region')['votos_proyectados_faltantes'].idxmax()
        df_winners = df_reg.loc[idx_winners].copy()
        df_winners.rename(columns={'candidato_o_tipo': 'Ganador'}, inplace=True)

        coords = {"AFRICA": (0, 20), "AMERICA": (15, -85), "ASIA": (40, 100), "EUROPA": (50, 15), "OCEANIA": (-25, 135)}
        df_winners['lat'] = df_winners['Parent_Region'].map(lambda x: coords.get(x, (0,0))[0])
        df_winners['lon'] = df_winners['Parent_Region'].map(lambda x: coords.get(x, (0,0))[1])

        fig_map = px.scatter_geo(
            df_winners, lat='lat', lon='lon', color='Ganador',
            color_discrete_map=CANDIDATOS_TARGET, size='votos_proyectados_faltantes',
            size_max=50, text='Parent_Region', projection="natural earth",
            hover_name='Parent_Region', custom_data=['Parent_Region']
        )
        fig_map.update_geos(showcoastlines=True, coastlinecolor="#504945", showland=True, landcolor="#3c3836", showocean=True, oceancolor="#282828", bgcolor="rgba(0,0,0,0)")
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=500, showlegend=False)

        map_event = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun", selection_mode="points", key="mapa_extranjero")
        reg_list = sorted(df_reg['Parent_Region'].unique())
        if map_event and len(map_event.selection.points) > 0:
            pt = map_event.selection.points[0]
            sel_target = pt.get("customdata", [pt.get("text", reg_list[0])])[0]
        else:
            sel_target = reg_list[0] if len(reg_list) > 0 else None

        if sel_target:
            df_det = df_reg[df_reg['Parent_Region'] == sel_target]

    if sel_target and not df_det.empty:
        df_det = df_det.sort_values('votos_proyectados_faltantes', ascending=False)
        total_votos_region = df_det['votos_proyectados_faltantes'].sum()

        ganador = df_det.iloc[0]
        nombre_ganador_corto = NOMBRES_CORTOS.get(ganador['candidato_o_tipo'], ganador['candidato_o_tipo'])

        st.markdown(f"""
        <div class="winner-box" style="background-color: #e2d3ba; border: 2px solid #a89984; color: #000000;">
            <h3 style="margin:0; color: #000000 !important; font-weight:bold;">
                📍 ZONA AGREGADA: {sel_target} | LÍDER: {nombre_ganador_corto.upper()}
            </h3>
            <h4 style="margin:0; color: #000000 !important;">
                👥 Votantes Faltantes Proyectados (Total): {total_votos_region:,.0f} votos
            </h4>
        </div>
        """, unsafe_allow_html=True)

        df_det['nombre_corto'] = df_det['candidato_o_tipo'].map(NOMBRES_CORTOS)
        df_det['porcentaje'] = (df_det['votos_proyectados_faltantes'] / total_votos_region) * 100

        colores_candidatos_cortos = {NOMBRES_CORTOS[k]: v for k, v in CANDIDATOS_TARGET.items() if k in NOMBRES_CORTOS}

        fig_tree = px.treemap(
            df_det, path=[px.Constant("Proporción Regional proyectada de votos válidos"), 'nombre_corto'],
            values='votos_proyectados_faltantes', color='nombre_corto',
            color_discrete_map=colores_candidatos_cortos, custom_data=['porcentaje', 'votos_proyectados_faltantes', 'nombre_corto']
        )
        fig_tree.update_traces(
            textinfo="label+text+value", texttemplate="<b>%{customdata[2]}</b><br>%{customdata[0]:.1f}%<br>%{value:,.0f} votos",
            hovertemplate="<b>%{customdata[2]}</b><br>Votos: %{value:,.0f}<br>Proporción: %{customdata[0]:.1f}%<extra></extra>",
            marker=dict(line=dict(color='#282828', width=2))
        )
        fig_tree.update_layout(margin=dict(t=10, l=10, r=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=380, font=dict(family="VT323", size=16, color="#282828"))
        st.plotly_chart(fig_tree, use_container_width=True)

        if sel_target in region_set and not df_map_provincial_audit.empty:
            st.markdown(f"#### 📊 Desglose de Votos Faltantes Proyectados por Provincia en {sel_target}")

            df_provs = df_map_provincial_audit[df_map_provincial_audit['Parent_Region'] == sel_target]

            if "PERÚ" in tipo_mapa:
                df_provs = df_provs[~df_provs['ubicacion_clean'].isin(['LIMA', 'CALLAO'])]

            if not df_provs.empty:
                pivot_provs = df_provs.pivot_table(
                    index='ubicacion_clean',
                    columns='candidato_o_tipo',
                    values='votos_proyectados_faltantes',
                    aggfunc='sum'
                ).fillna(0)

                cols = [c for c in CANDIDATOS_TARGET.keys() if c in pivot_provs.columns]
                pivot_provs = pivot_provs[cols]

                pivot_provs.rename(columns=NOMBRES_CORTOS, inplace=True)
                pivot_provs['TOTAL PROVINCIA'] = pivot_provs.sum(axis=1)
                pivot_provs = pivot_provs.sort_values('TOTAL PROVINCIA', ascending=False)
                pivot_provs.rename_axis('Provincia', inplace=True)

                for col in pivot_provs.columns:
                    pivot_provs[col] = pivot_provs[col].apply(lambda x: f"{int(x):,}")

                st.dataframe(pivot_provs, use_container_width=True)

def render_projections_and_layout(df_filtrado, min_x, dict_proy_abs, dict_proy_pct, df_proy, margin_of_error):
    fig_pct = from_plotly.Figure()
    fig_abs = from_plotly.Figure()

    ultimo_corte_x = 0

    cand_last_vals = []
    for cand in CANDIDATOS_TARGET.keys():
        df_c = df_filtrado[df_filtrado['candidato_o_tipo'] == cand]
        if not df_c.empty:
            cand_last_vals.append((cand, df_c['porcentaje_valido'].values[-1]))
    cand_last_vals.sort(key=lambda x: x[1], reverse=True)
    sorted_cands = [x[0] for x in cand_last_vals]

    ax_start_opts = [-40, -75, -40, -75, -40]
    ax_end_opts = [40, 75, 40, 75, 40]
    ay_opts = [-60, -30, 0, 30, 60]

    for fig in [fig_pct, fig_abs]:
        fig.add_vline(x=100, line_width=2, line_dash="dash", line_color="#a89984", opacity=0.8)

    for i, candidato in enumerate(sorted_cands):
        color = CANDIDATOS_TARGET[candidato]
        df_cand = df_filtrado[df_filtrado['candidato_o_tipo'] == candidato]

        x_data = df_cand['actas_contabilizadas_pct'].values
        y_pct = df_cand['porcentaje_valido'].values
        y_abs = df_cand['cantidad_votos'].values

        nombre_corto = NOMBRES_CORTOS.get(candidato, candidato)
        ultimo_corte_x = max(ultimo_corte_x, x_data[-1] if len(x_data) > 0 else 0)

        fig_pct.add_trace(from_plotly.Scatter(x=x_data, y=y_pct, mode='lines+markers', name=nombre_corto, line=dict(color=color, width=3), connectgaps=True))
        fig_abs.add_trace(from_plotly.Scatter(x=x_data, y=y_abs, mode='lines+markers', name=nombre_corto, line=dict(color=color, width=3), connectgaps=True))

        if candidato in dict_proy_abs and len(x_data) > 0:
            last_x = x_data[-1]
            last_y_pct = y_pct[-1]
            last_y_abs = y_abs[-1]

            p_pct = dict_proy_pct[candidato]
            p_abs = dict_proy_abs[candidato]

            moe_pct = margin_of_error.get(candidato, {}).get('pct', 0.0)
            moe_abs = margin_of_error.get(candidato, {}).get('abs', 0.0)

            ay_offset = ay_opts[i % len(ay_opts)]
            ax_start = ax_start_opts[i % len(ax_start_opts)]
            ax_end = ax_end_opts[i % len(ax_end_opts)]
            icono = EMOJIS_CANDIDATOS.get(candidato, "👤")

            for fig, y_val in [(fig_pct, last_y_pct), (fig_abs, last_y_abs)]:
                fig.add_annotation(
                    x=last_x, y=y_val, text=f"<span style='font-size:20px'>{icono}</span>",
                    showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1,
                    arrowcolor="black", ax=ax_start, ay=ay_offset,
                    bgcolor="rgba(255,255,255,0.9)", bordercolor="black", borderwidth=1, borderpad=2
                )

            steps_x = np.linspace(last_x, 100, 11)
            steps_y_pct = np.linspace(last_y_pct, p_pct, 11)
            steps_y_abs = np.linspace(last_y_abs, p_abs, 11)

            fig_pct.add_trace(from_plotly.Scatter(x=steps_x, y=steps_y_pct, mode='lines+markers', line=dict(color=color, width=2.5, dash='dot'), marker=dict(size=5, opacity=0.8), showlegend=False))
            fig_abs.add_trace(from_plotly.Scatter(x=steps_x, y=steps_y_abs, mode='lines+markers', line=dict(color=color, width=2.5, dash='dot'), marker=dict(size=5, opacity=0.8), showlegend=False))

            fig_pct.add_trace(from_plotly.Scatter(
                x=[100], y=[p_pct], mode='markers',
                marker=dict(size=14, symbol='star', color=color),
                error_y=dict(type='data', array=[moe_pct], visible=True, color=color, thickness=2, width=5),
                showlegend=False
            ))
            fig_abs.add_trace(from_plotly.Scatter(
                x=[100], y=[p_abs], mode='markers',
                marker=dict(size=14, symbol='star', color=color),
                error_y=dict(type='data', array=[moe_abs], visible=True, color=color, thickness=2, width=5),
                showlegend=False
            ))

            fig_pct.add_annotation(
                x=100, y=p_pct, text=f"<b>{p_pct:.2f}%</b>",
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="black", ax=ax_end, ay=ay_offset,
                font=dict(size=18, color=color), bgcolor="rgba(255,255,255,0.9)", bordercolor=color, borderwidth=1
            )

            txt_abs = f'{p_abs/1000000:.2f}M' if p_abs >= 1000000 else f'{p_abs:,.0f}'
            moe_abs_txt = f"{moe_abs/1000:.1f}K" if moe_abs > 1000 else f"{moe_abs:.0f}"
            fig_abs.add_annotation(
                x=100, y=p_abs, text=f"<b>{txt_abs} ±{moe_abs_txt}</b>",
                showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1, arrowcolor="black", ax=ax_end, ay=ay_offset,
                font=dict(size=18, color=color), bgcolor="rgba(255,255,255,0.9)", bordercolor=color, borderwidth=1
            )

    for fig in [fig_pct, fig_abs]:
        fig.add_annotation(
            xref="paper", yref="paper", x=0.01, y=0.98,
            text=f"<b>ONPE<br><span style='font-size:24px'>{ultimo_corte_x:.3f}%</span></b>",
            showarrow=False, font=dict(family="Arial", size=18, color="black"),
            bgcolor="rgba(255,255,255,0.95)", bordercolor="black", borderwidth=2, borderpad=6, align="center"
        )

    layout_base = dict(
        plot_bgcolor="#ffffff", paper_bgcolor="rgba(0,0,0,0)", font=dict(family="VT323", size=14, color="#3c3836"),
        xaxis=dict(
            title="% Actas Contabilizadas",
            range=[83, 103],
            gridcolor="#e0e0e0",
            tickmode='array',
            tickvals=list(range(83, 101))
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(t=30, b=30), height=500
    )

    fig_pct.update_layout(**layout_base, title="Votos Válidos (%) - Proy. Final", yaxis=dict(gridcolor="#e0e0e0", range=[9, 18]))
    fig_abs.update_layout(**layout_base, title="Cantidad de Votos - Proy. Final", yaxis=dict(gridcolor="#e0e0e0"))

    if dict_proy_pct and dict_proy_abs:
        datos_finales = []
        for cand in dict_proy_pct.keys():
            datos_finales.append({
                'Candidato': cand,
                'Nombre': NOMBRES_CORTOS.get(cand, cand),
                'Porcentaje': dict_proy_pct[cand],
                'Votos': dict_proy_abs[cand],
                'Error_Pct': margin_of_error.get(cand, {}).get('pct', 0.0),
                'Error_Abs': margin_of_error.get(cand, {}).get('abs', 0.0)
            })
        df_final = pd.DataFrame(datos_finales)
        df_final = df_final.sort_values('Porcentaje', ascending=True).reset_index(drop=True)

        n = len(df_final)
        etiquetas = []
        for i, row in df_final.iterrows():
            cand = row['Candidato']
            icono = EMOJIS_CANDIDATOS.get(cand, "👤")
            nombre_base = f"{icono} {row['Nombre']}"
            if i == n - 1:
                etiquetas.append(f"🥇 {nombre_base}")
            elif i == n - 2:
                etiquetas.append(f"🥈 {nombre_base}")
            else:
                etiquetas.append(nombre_base)

        df_final['Etiqueta'] = etiquetas
        df_final['Texto_Barra'] = df_final.apply(lambda r: f"<b>{r['Porcentaje']:.2f}% ±{r['Error_Pct']:.2f}%</b> ({r['Votos']:,.0f} ±{r['Error_Abs']:,.0f})", axis=1)

        fig_bar_final = px.bar(
            df_final, x='Porcentaje', y='Etiqueta', orientation='h',
            color='Candidato', color_discrete_map=CANDIDATOS_TARGET,
            text='Texto_Barra',
            error_x='Error_Pct'
        )

        opacidades = [0.6 if i < n-2 else 1.0 for i in range(n)]
        fig_bar_final.update_traces(
            textposition='outside',
            insidetextanchor='end',
            textfont=dict(size=15, color="#ebdbb2"),
            marker=dict(line=dict(color='#282828', width=1)),
            marker_opacity=opacidades,
            error_x=dict(thickness=2)
        )

        max_x = (df_final['Porcentaje'] + df_final['Error_Pct']).max() * 1.35
        fig_bar_final.update_layout(
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="VT323", size=18, color="#ebdbb2"),
            xaxis=dict(showgrid=True, gridcolor="#504945", range=[0, max_x], title=""),
            yaxis=dict(title=""),
            showlegend=False,
            height=400,
            margin=dict(t=10, b=0, l=0, r=0)
        )
    else:
        fig_bar_final = None

    col_graficas, col_mapas = st.columns(2)
    with col_graficas:
        st.plotly_chart(fig_pct, use_container_width=True)
        st.plotly_chart(fig_abs, use_container_width=True)
        if fig_bar_final:
            st.markdown(f"<h4 style='color:#ebdbb2;'>🏁 Resumen de Posiciones al 100% (Proyección con Margen de Error al 95%)</h4>", unsafe_allow_html=True)
            st.plotly_chart(fig_bar_final, use_container_width=True)
    with col_mapas:
        render_spatial_module(df_proy)

def render_bottom_totals(df_proy):
    st.markdown("---")
    st.markdown("### 🧮 Total del Bolsón Nacional + Extranjero (Votos Válidos en Disputa proyectados)")
    if df_proy.empty: return

    unwanted_terms = ['VOTOS EN BLANCO', 'VOTOS NULOS', 'total de votos']
    df_map = df_proy[(df_proy['candidato_o_tipo'].isin(CANDIDATOS_TARGET.keys())) &
                     (df_proy['ubicacion'] != 'TODOS') &
                     (~df_proy['candidato_o_tipo'].str.contains('|'.join(unwanted_terms), case=False, na=False))].copy()

    df_map['ubicacion_clean'] = df_map['ubicacion'].apply(clean_name)
    province_to_region_map, _, _, continents_set = get_geo_mapping()
    df_map['Parent_Region'] = df_map['ubicacion_clean'].map(province_to_region_map)

    def classificar_vertiente(row):
        if row['Parent_Region'] in continents_set:
            return 'Extranjero'
        elif row['ubicacion_clean'] in ['LIMA', 'CALLAO']:
            return 'Lima y Callao'
        else:
            return 'Interior del País'

    df_map['Vertiente'] = df_map.apply(classificar_vertiente, axis=1)

    df_totals = df_map.groupby(['candidato_o_tipo', 'Vertiente'])['votos_proyectados_faltantes'].sum().reset_index()

    df_totals['nombre_corto'] = df_totals['candidato_o_tipo'].map(NOMBRES_CORTOS)
    colores_candidatos_cortos = {NOMBRES_CORTOS[k]: v for k, v in CANDIDATOS_TARGET.items() if k in NOMBRES_CORTOS}

    orden_total = df_totals.groupby('nombre_corto')['votos_proyectados_faltantes'].sum().sort_values(ascending=True)

    colores_vertientes = {
        'Interior del País': '#83a598',
        'Lima y Callao': '#fabd2f',
        'Extranjero': '#d3869b'
    }

    fig1 = px.bar(
        df_totals, x='votos_proyectados_faltantes', y='nombre_corto', color='Vertiente',
        orientation='h', text_auto='.0f',
        category_orders={
            'nombre_corto': list(orden_total.index),
            'Vertiente': ['Interior del País', 'Lima y Callao', 'Extranjero']
        },
        color_discrete_map=colores_vertientes
    )

    fig1.update_layout(
        xaxis=dict(title="Cantidad Total de Votos Aspirados", gridcolor="#504945"), yaxis=dict(title=""),
        legend=dict(title="Flujo Geográfico", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="VT323", size=18, color="#ebdbb2"),
        barmode='stack'
    )

    for cand, total_val in orden_total.items():
        fig1.add_annotation(
            x=total_val, y=cand,
            text=f"<b>Total: {total_val:,.0f}</b>",
            showarrow=False, xanchor='left', xshift=5,
            font=dict(color="#ebdbb2", size=16)
        )

    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("### 🌎 Composición del Bolsón por Vertiente Geográfica (Votos Válidos en Disputa proyectados)")

    fig2 = px.bar(
        df_totals, x='Vertiente', y='votos_proyectados_faltantes', color='nombre_corto',
        text_auto='.0f',
        category_orders={
            'Vertiente': ['Interior del País', 'Lima y Callao', 'Extranjero']
        },
        color_discrete_map=colores_candidatos_cortos
    )

    fig2.update_layout(
        yaxis=dict(title="Cantidad de Votos", gridcolor="#504945"), xaxis=dict(title=""),
        legend=dict(title="", orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=550, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="VT323", size=16, color="#ebdbb2"),
        barmode='stack'
    )

    totales_vertiente = df_totals.groupby('Vertiente')['votos_proyectados_faltantes'].sum()
    for vert, total_val in totales_vertiente.items():
        fig2.add_annotation(
            x=vert, y=total_val,
            text=f"<b>Total: {total_val:,.0f}</b>",
            showarrow=False, yanchor='bottom', yshift=10,
            font=dict(color="#ebdbb2", size=18)
        )

    st.plotly_chart(fig2, use_container_width=True)

def render_legal_strategy_map(df_proy, df_actas):
    st.markdown("---")
    st.markdown("### ⚖️ Mapa de Estrategia Legal y Defensa del Voto")
    st.markdown("Identifica las zonas de batalla legal (Actas JEE/Pendientes) coloreadas por el candidato que lidera la **base de votación validada** por provincia y continente, ideal para asignar recursos y priorizar nulidad de actas.")
    st.markdown("Se prioriza el enfoque entre Rafael Lopez Aliaga y Roberto Sanchez dado que pelean por el segundo puesto.")

    if df_proy.empty or df_actas.empty:
        st.info("Esperando datos de proyecciones y actas JEE...")
        return

    cand1 = "RAFAEL BERNARDO LÓPEZ ALIAGA CAZORLA"
    cand2 = "ROBERTO HELBERT SANCHEZ PALOMINO"

    df_disputa = df_proy[df_proy['candidato_o_tipo'].isin([cand1, cand2])].copy()
    df_disputa['ubicacion_clean'] = df_disputa['ubicacion'].apply(clean_name)

    idx_lider = df_disputa.groupby('ubicacion_clean')['porcentaje_valido_base'].idxmax()
    df_lideres = df_disputa.loc[idx_lider][['ubicacion_clean', 'candidato_o_tipo']]
    df_lideres = df_lideres.rename(columns={'candidato_o_tipo': 'Lider_Base'})

    df_actas['ubicacion_clean'] = df_actas['ubicacion_clean'].apply(clean_name)
    df_mapa = pd.merge(df_actas, df_lideres, on='ubicacion_clean', how='left')

    col_ctrl1, col_ctrl2 = st.columns(2)
    with col_ctrl1:
        metrica_sel = st.radio("Foco Legal a Visualizar:", ["⚖️ Actas en JEE (Observadas)", "🕒 Actas Pendientes (Por Procesar)"], horizontal=True)
    with col_ctrl2:
        vista_sel = st.radio("Escenario Geográfico:", ["🇵🇪 PERÚ (Provincias)", "🏙️ LIMA Y CALLAO", "🌍 EXTRANJERO"], horizontal=True, key="legal_vista")

    col_metrica = 'actas_jee' if 'JEE' in metrica_sel else 'actas_pendientes'

    df_mapa['Lider_Corto'] = df_mapa['Lider_Base'].map(NOMBRES_CORTOS).fillna('Sin Datos')
    cand1_corto = NOMBRES_CORTOS[cand1]
    cand2_corto = NOMBRES_CORTOS[cand2]

    df_mapa['Estrategia'] = df_mapa.apply(
        lambda r: r['Lider_Corto'] if r[col_metrica] > 0 else 'Sin Actas en Disputa', axis=1
    )

    color_map = {
        cand1_corto: CANDIDATOS_TARGET[cand1],
        cand2_corto: CANDIDATOS_TARGET[cand2],
        'Sin Actas en Disputa': '#ffffff'
    }

    province_to_region_map, region_set, province_set, continents_set = get_geo_mapping()
    df_mapa['Parent_Region'] = df_mapa['ubicacion_clean'].map(province_to_region_map).replace({"CUZCO": "CUSCO"})

    fig_map = None

    if "PERÚ" in vista_sel:
        df_plot = df_mapa[~df_mapa['ubicacion_clean'].isin(['LIMA', 'CALLAO']) & ~df_mapa['Parent_Region'].isin(continents_set)].copy()
        geojson_prov = load_geojson("provincias")

        if geojson_prov:
            fig_map = px.choropleth_mapbox(
                df_plot, geojson=geojson_prov, locations='ubicacion_clean', featureidkey="properties.NOMBPROV_CLEAN",
                color='Estrategia', color_discrete_map=color_map,
                mapbox_style="carto-darkmatter", center={"lat": -9.18, "lon": -75.01}, zoom=4.5,
                hover_name='ubicacion_clean', hover_data={col_metrica: True, 'Estrategia': False, 'ubicacion_clean': False}
            )
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=550)

    elif "LIMA" in vista_sel:
        df_plot = df_mapa[df_mapa['ubicacion_clean'].isin(['LIMA', 'CALLAO'])].copy()
        geojson_prov = load_geojson("provincias")

        if geojson_prov:
            fig_map = px.choropleth_mapbox(
                df_plot, geojson=geojson_prov, locations='ubicacion_clean', featureidkey="properties.NOMBPROV_CLEAN",
                color='Estrategia', color_discrete_map=color_map,
                mapbox_style="carto-darkmatter", center={"lat": -12.05, "lon": -77.05}, zoom=8.5,
                hover_name='ubicacion_clean', hover_data={col_metrica: True, 'Estrategia': False, 'ubicacion_clean': False}
            )
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=550)

    else:
        df_plot = df_mapa[df_mapa['Parent_Region'].isin(continents_set)].copy()
        coords = {"AFRICA": (0, 20), "AMERICA": (15, -85), "ASIA": (40, 100), "EUROPA": (50, 15), "OCEANIA": (-25, 135)}
        df_plot['lat'] = df_plot['ubicacion_clean'].map(lambda x: coords.get(x, (0,0))[0])
        df_plot['lon'] = df_plot['ubicacion_clean'].map(lambda x: coords.get(x, (0,0))[1])

        df_plot['Bubble_Size'] = df_plot[col_metrica].apply(lambda x: x if x > 0 else 1)

        fig_map = px.scatter_geo(
            df_plot, lat='lat', lon='lon', color='Estrategia',
            color_discrete_map=color_map, size='Bubble_Size',
            size_max=40, text='ubicacion_clean', projection="natural earth",
            hover_name='ubicacion_clean', hover_data={col_metrica: True, 'Estrategia': False, 'lat': False, 'lon': False, 'Bubble_Size': False}
        )
        fig_map.update_geos(showcoastlines=True, coastlinecolor="#504945", showland=True, landcolor="#3c3836", showocean=True, oceancolor="#282828", bgcolor="rgba(0,0,0,0)")
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=550)

    if fig_map is not None:
        col_map, col_bars = st.columns([1.2, 1])

        with col_map:
            st.plotly_chart(fig_map, use_container_width=True)

        with col_bars:
            st.markdown(f"#### 📊 Balance de Actas Totales en el mapa seleccionado")

            df_summary_raw = df_plot[df_plot['Lider_Corto'].isin([cand1_corto, cand2_corto])].groupby('Lider_Corto')[['actas_jee', 'actas_pendientes']].sum().reset_index()

            res = []
            for c in [cand1_corto, cand2_corto]:
                row = df_summary_raw[df_summary_raw['Lider_Corto'] == c]
                if not row.empty:
                    res.append({'Lider_Corto': c, 'actas_jee': row['actas_jee'].values[0], 'actas_pendientes': row['actas_pendientes'].values[0]})
                else:
                    res.append({'Lider_Corto': c, 'actas_jee': 0, 'actas_pendientes': 0})

            df_summary = pd.DataFrame(res)

            df_jee_sorted = df_summary.sort_values('actas_jee', ascending=True)
            fig_jee = px.bar(
                df_jee_sorted, x='actas_jee', y='Lider_Corto', color='Lider_Corto',
                orientation='h', text_auto='.0f', color_discrete_map=color_map,
                title="⚖️ Actas en JEE (Impugnadas)"
            )
            fig_jee.update_layout(
                xaxis=dict(title="Total Actas", gridcolor="#504945"), yaxis=dict(title=""),
                showlegend=False, height=200, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="VT323", size=16, color="#ebdbb2"), margin=dict(t=40, b=0, l=0, r=0)
            )
            fig_jee.update_traces(textposition='outside', textfont=dict(color="#ebdbb2"))
            st.plotly_chart(fig_jee, use_container_width=True)

            st.markdown("<br>", unsafe_allow_html=True)

            df_pend_sorted = df_summary.sort_values('actas_pendientes', ascending=True)
            fig_pend = px.bar(
                df_pend_sorted, x='actas_pendientes', y='Lider_Corto', color='Lider_Corto',
                orientation='h', text_auto='.0f', color_discrete_map=color_map,
                title="🕒 Actas Pendientes (Por Procesar)"
            )
            fig_pend.update_layout(
                xaxis=dict(title="Total Actas", gridcolor="#504945"), yaxis=dict(title=""),
                showlegend=False, height=200, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="VT323", size=16, color="#ebdbb2"), margin=dict(t=40, b=0, l=0, r=0)
            )
            fig_pend.update_traces(textposition='outside', textfont=dict(color="#ebdbb2"))
            st.plotly_chart(fig_pend, use_container_width=True)

def render_methodology_section():
    st.markdown("<a id='metodologia-de-proyeccion'></a>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("## 🔍 Metodología: Modelo de Proyección Espacial Asimétrica (PEA)")
    st.markdown("""
    Esta herramienta utiliza un enfoque determinista con *priors* sociodemográficos para proyectar el resultado final de la elección a partir de los datos crudos e incompletos de la ONPE.
    
    ### 1. Procesamiento del Bolsón de Votos Faltantes
    Para calcular cuántos votos quedan realmente en juego (el "Bolsón"), el modelo no asume una asistencia perfecta. En cambio, realiza un ajuste dinámico por provincia:
    * Extrae la cantidad total de actas pendientes y las actas enviadas al JEE (asumiendo un escenario optimista donde el 100% son recuperables).
    * Multiplica estas actas por el promedio histórico de electores por acta en dicha zona.
    * Aplica un descuento utilizando la **Tasa de Ausentismo** específica de esa provincia.
    
    $$ \text{Votos Faltantes} = (\text{Actas}_{JEE} + \text{Actas}_{Pend}) \\times \\left( \\frac{\text{Electores Totales}}{\text{Actas Totales}} \\right) \\times (1 - \text{Tasa Ausentismo}) $$
    
    ### 2. Algoritmo de Proyección Estructural (Corrección de Sesgos)
    El modelo reconoce que las actas que tardan más en llegar al centro de cómputo provienen de zonas geográficamente más profundas y aisladas. Por ende, no proyecta linealmente, sino que inyecta variables de distorsión:
    * **Penalidad por Ruralidad:** Asume estadísticamente que las zonas restantes dentro de una provincia tienen mayor ruralidad que las zonas urbanas ya procesadas, favoreciendo a los candidatos con fuerza en el "Perú profundo".
    * **Amortiguador de Voto Duro:** Suaviza la caída de los candidatos rurales cuando el modelo proyecta zonas puramente urbanas, respetando su núcleo duro de votantes. Este ajuste se sustenta en la hipótesis sociodemográfica de que es significativamente más probable que votantes de origen provincial migren y residan en núcleos urbanos (conservando su identidad de voto) a que ocurra el fenómeno inverso.
    * **Factor de Canibalización:** Frena matemáticamente el crecimiento irreal en las ciudades, simulando la fragmentación del voto entre candidatos de perfil urbano que compiten por el mismo electorado.
    
    ### 3. Cuantificación del Margen de Error
    Para calcular el error estadístico a nivel nacional, se emplea la fórmula de **Propagación de Varianza de Proporciones Multinomiales**. Debido a que el volumen de votos faltantes ($N_i$) y la probabilidad del candidato ($p_i$) varían por cada provincia, la varianza se calcula localmente y luego se acumula para extraer la desviación estándar nacional.
    
    $$ E_{nac} = 1.96 \\times \\frac{\\sqrt{\\sum_{i=1}^{n} [N_{i} \\times p_{i}(1 - p_{i})]}}{N_{total}} $$
    
    *Donde $E_{nac}$ representa el margen de error para un nivel de confianza del 95%. Este margen representa estrictamente la volatilidad estadística (error de muestreo) bajo la suposición de que los parámetros del modelo son exactos.*
    """)

# ---------------------------------------------------------
# ORQUESTADOR PRINCIPAL (ENVUELTO EN FRAGMENTO DE RECARGA AUTOMÁTICA)
# ---------------------------------------------------------
@st.fragment(run_every=60)
def auto_refresh_dashboard():
    df, df_proy, df_actas = fetch_cached_data()

    if df.empty:
        st.warning("📡 Esperando datos consolidados en data_stream/onpe_todos_latest.csv...")
        return

    ultima_fecha = df['actualizado_dt'].max()
    df_latest = df[df['actualizado_dt'] == ultima_fecha]
    df_filtrado = df[df['candidato_o_tipo'].isin(CANDIDATOS_TARGET.keys())]

    render_header(df_latest)
    render_bar_and_versus(df_latest)

    # <-- NUEVO: Alerta visual de separación y metodología
    render_projection_warning()

    proy_100_abs = {}
    proy_100_pct = {}
    margin_of_error = {}

    if not df_proy.empty:
        unwanted_terms = ['VOTOS EN BLANCO', 'VOTOS NULOS', 'total de votos']
        df_latest_validos = df_latest[~df_latest['candidato_o_tipo'].str.contains('|'.join(unwanted_terms), case=False, na=False)]

        total_validos_actual = df_latest_validos['cantidad_votos'].sum()
        total_validos_proyectados_faltantes = df_proy[~df_proy['candidato_o_tipo'].str.contains('|'.join(unwanted_terms), case=False, na=False)]['votos_proyectados_faltantes'].sum()

        total_nacional_proyectado_100 = total_validos_actual + total_validos_proyectados_faltantes

        if total_nacional_proyectado_100 > 0:
            for cand in CANDIDATOS_TARGET.keys():
                votos_actuales_cand = df_latest[df_latest['candidato_o_tipo'] == cand]['cantidad_votos'].sum()
                votos_proyectados_cand = df_proy[df_proy['candidato_o_tipo'] == cand]['votos_proyectados_faltantes'].sum()

                votos_finales_cand = votos_actuales_cand + votos_proyectados_cand
                pct_final_cand = (votos_finales_cand / total_nacional_proyectado_100) * 100

                proy_100_abs[cand] = votos_finales_cand
                proy_100_pct[cand] = pct_final_cand

                # --- CÁLCULO ESTADÍSTICO DE INCERTIDUMBRE (Propagación de Varianza) ---
                df_cand_proy = df_proy[df_proy['candidato_o_tipo'] == cand]
                var_sum = 0.0

                for _, row in df_cand_proy.iterrows():
                    n_i = float(row.get('votantes_validos_pendientes_est', 0))
                    p_i = float(row.get('porcentaje_valido_usado_prior', 0)) / 100.0
                    if n_i > 0 and pd.notna(p_i):
                        var_sum += n_i * p_i * (1.0 - p_i)

                moe_abs = 1.96 * np.sqrt(var_sum) if var_sum > 0 else 0
                moe_pct = (moe_abs / total_nacional_proyectado_100) * 100.0 if total_nacional_proyectado_100 > 0 else 0

                margin_of_error[cand] = {'abs': moe_abs, 'pct': moe_pct}

    render_projections_and_layout(df_filtrado, df_filtrado['actas_contabilizadas_pct'].min(), proy_100_abs, proy_100_pct, df_proy, margin_of_error)
    render_bottom_totals(df_proy)
    render_legal_strategy_map(df_proy, df_actas)

    # <-- NUEVO: Bloque de texto con la metodología matemática
    render_methodology_section()

# Llamada principal a la aplicación
auto_refresh_dashboard()