import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from .config import DATA_DIR

class ElectionProjector:
    def __init__(self):
        self.raw_dir = DATA_DIR
        self.proy_dir = DATA_DIR.parent / "proyections"
        self.proy_dir.mkdir(parents=True, exist_ok=True)

        self.afinidad_file = DATA_DIR.parent / "afinidad_electoral.json"
        self.geo_file = DATA_DIR.parent / "ubigeo_georeferenciado.json"

        self.prov_to_region = {}
        self.afinidad_data = {"provincias": {}, "candidatos": {}}

        # Parámetros del Prior de Distorsión
        self.DISTORSION_MAX_PCT = 8.0

        # ARRAY DE PENALIDADES (Análisis de Sensibilidad)
        # 0.0 = El bolsón faltante es igual de rural que la provincia.
        # 0.6 = El bolsón faltante es extremadamente más rural que la provincia.
        self.RURAL_PENALTIES = [0.0, 0.1, 0.2]

        self._build_geo_maps()
        self._load_affinity_data()

    def _build_geo_maps(self):
        if self.geo_file.exists():
            with open(self.geo_file, 'r', encoding='utf-8') as f:
                geo_data = json.load(f)
            for region, provs in geo_data.get("PERU", {}).items():
                for prov in provs.keys():
                    carpeta_limpia = prov.lower().replace(" ", "_")
                    self.prov_to_region[carpeta_limpia] = region

    def _load_affinity_data(self):
        if self.afinidad_file.exists():
            with open(self.afinidad_file, 'r', encoding='utf-8') as f:
                self.afinidad_data = json.load(f)
        else:
            print(f"⚠️ CUIDADO: No se encontró {self.afinidad_file}. La proyección no tendrá distorsión de clústeres.")

    def _get_latest_csv(self, folder_path):
        csv_files = list(folder_path.glob("*.csv"))
        if not csv_files: return None
        return max(csv_files, key=lambda x: x.stat().st_mtime)

    def _safe_float(self, val):
        try: return float(str(val).replace(',', ''))
        except (ValueError, TypeError): return 0.0

    def _calcular_porcentajes_distorsionados(self, carpeta_limpia, df_candidatos, current_penalty):
        """Aplica el Prior Geográfico ajustado por la penalidad iterativa."""

        prov_data = self.afinidad_data.get("provincias_y_continentes", {}).get(carpeta_limpia, {})
        base_rurality = prov_data.get("ruralidad_score_proxy", 0.5)

        # F dinámico según la penalidad actual del bucle
        F = min(1.0, base_rurality + current_penalty)
        M = (F - 0.5) * 2

        candidatos_ajustados = []
        suma_nuevos_pct = 0.0

        for _, row in df_candidatos.iterrows():
            cand = row['candidato_o_tipo']
            pct_base = self._safe_float(row['porcentaje_valido'])

            cand_data = self.afinidad_data.get("candidatos", {}).get(cand, {})
            A_i = cand_data.get("afinidad_nacional", 0.0)

            ajuste = M * A_i * self.DISTORSION_MAX_PCT
            # --- GESTIÓN ASIMÉTRICA DE ZONAS URBANAS (M < 0) ---
            if M < 0:
                if A_i > 0:
                    # CASO A: Candidato Rural en Zona Urbana (Ajuste Negativo)
                    # Amortiguador para proteger el "Voto Duro" (caída suavizada)
                    ajuste = ajuste * 0.2

                elif A_i < 0:
                    # CASO B: Candidato Urbano en Zona Urbana (Ajuste Positivo)
                    # Factor de Canibalización para frenar el crecimiento excesivo
                    ajuste = ajuste * 0.50  # Retiene solo el 30% de la recompensa teórica
            # ---------------------------------------------------

            pct_nuevo = max(0.0, pct_base + ajuste)

            candidatos_ajustados.append({
                "cand": cand,
                "agrupacion": row.get('agrupacion', ''),
                "pct_base": pct_base,
                "pct_crudo": pct_nuevo
            })
            suma_nuevos_pct += pct_nuevo

        # Normalizar
        for item in candidatos_ajustados:
            if suma_nuevos_pct > 0:
                item["pct_proyectado"] = (item["pct_crudo"] / suma_nuevos_pct) * 100.0
            else:
                item["pct_proyectado"] = item["pct_base"]

        return candidatos_ajustados

    def generate_projections(self):
        print("📊 Generando matriz de proyecciones (Optimista/Pesimista x Múltiples Penalidades)...")

        # Diccionarios para agrupar proyecciones por nivel de penalidad
        projections_opt = {p: [] for p in self.RURAL_PENALTIES}
        projections_pes = {p: [] for p in self.RURAL_PENALTIES}

        needs_imputation = []
        regional_valid_pcts = {}

        for folder in [f for f in self.raw_dir.iterdir() if f.is_dir()]:
            folder_name = folder.name
            if folder_name == "todos": continue

            latest_csv = self._get_latest_csv(folder)
            if not latest_csv: continue

            df_raw = pd.read_csv(latest_csv)
            if df_raw.empty: continue

            unwanted_terms = ['VOTOS EN BLANCO', 'VOTOS NULOS', 'total de votos']
            df = df_raw[~df_raw['candidato_o_tipo'].str.contains('|'.join(unwanted_terms), case=False, na=False)].copy()

            row_base = df_raw.iloc[0]
            g_contab = self._safe_float(row_base.get('global_contabilizadas', 0))
            g_jee = self._safe_float(row_base.get('global_jee', 0))
            g_pend = self._safe_float(row_base.get('global_pendientes', 0))

            electores = self._safe_float(row_base.get('electores_habiles', 0))
            asistentes = self._safe_float(row_base.get('asistentes_totales', 0))
            ausentes = self._safe_float(row_base.get('ausentes_totales', 0))

            total_actas = g_contab + g_jee + g_pend
            if total_actas == 0 or electores == 0: continue

            ratio_electores_acta = electores / total_actas
            total_padron = ausentes + asistentes
            tasa_ausentismo = (ausentes / total_padron) if total_padron > 0 else 0

            votantes_validos_opt = ((g_jee + g_pend) * ratio_electores_acta) * (1 - tasa_ausentismo)
            votantes_validos_pes = ((g_pend) * ratio_electores_acta) * (1 - tasa_ausentismo)

            data_base = {
                "ubicacion": row_base['ubicacion'],
                "actualizado_dt": row_base['actualizado_dt'],
                "avance_actas_pct": round(g_contab / total_actas, 4) if total_actas > 0 else 0
            }

            if g_contab == 0:
                needs_imputation.append((folder_name, data_base, votantes_validos_opt, votantes_validos_pes, df))
            else:
                region = self.prov_to_region.get(folder_name, "EXTRANJERO")
                if region not in regional_valid_pcts: regional_valid_pcts[region] = {}

                # Guardamos los votos base para imputaciones futuras (solo una vez por provincia)
                for _, row in df.iterrows():
                    cand = row['candidato_o_tipo']
                    pct_base = self._safe_float(row['porcentaje_valido'])
                    if cand not in regional_valid_pcts[region]: regional_valid_pcts[region][cand] = []
                    regional_valid_pcts[region][cand].append(pct_base)

                # =======================================================
                # BUCLE DE SENSIBILIDAD: Calcular para cada penalidad
                # =======================================================
                for penalty in self.RURAL_PENALTIES:
                    candidatos_con_prior = self._calcular_porcentajes_distorsionados(folder_name, df, penalty)

                    d_opt = data_base.copy()
                    d_opt["votantes_validos_pendientes_est"] = round(votantes_validos_opt, 2)
                    d_opt["candidatos"] = []

                    d_pes = data_base.copy()
                    d_pes["votantes_validos_pendientes_est"] = round(votantes_validos_pes, 2)
                    d_pes["candidatos"] = []

                    for item in candidatos_con_prior:
                        cand = item["cand"]
                        pct_final = item["pct_proyectado"]

                        d_opt["candidatos"].append({
                            "candidato_o_tipo": cand, "agrupacion": item["agrupacion"],
                            "porcentaje_valido_base": item["pct_base"],
                            "porcentaje_valido_usado": round(pct_final, 3),
                            "votos_proyectados_faltantes": round(votantes_validos_opt * (pct_final / 100.0), 0)
                        })
                        d_pes["candidatos"].append({
                            "candidato_o_tipo": cand, "agrupacion": item["agrupacion"],
                            "porcentaje_valido_base": item["pct_base"],
                            "porcentaje_valido_usado": round(pct_final, 3),
                            "votos_proyectados_faltantes": round(votantes_validos_pes * (pct_final / 100.0), 0)
                        })

                    projections_opt[penalty].append(d_opt)
                    projections_pes[penalty].append(d_pes)

        # =======================================================
        # RESOLUCIÓN DE IMPUTACIONES (Zonas con 0%)
        # =======================================================
        for folder_name, data_base, votantes_validos_opt, votantes_validos_pes, df in needs_imputation:
            region = self.prov_to_region.get(folder_name, "EXTRANJERO")

            temp_rows = []
            for _, row in df.iterrows():
                cand = row['candidato_o_tipo']
                if region in regional_valid_pcts and cand in regional_valid_pcts[region]:
                    vals = regional_valid_pcts[region][cand]
                    pct_imputado = sum(vals) / len(vals)
                else: pct_imputado = 0.0

                temp_rows.append({
                    'candidato_o_tipo': cand, 'agrupacion': row.get('agrupacion', ''),
                    'porcentaje_valido': pct_imputado
                })

            df_imputado = pd.DataFrame(temp_rows)

            for penalty in self.RURAL_PENALTIES:
                candidatos_imputados = self._calcular_porcentajes_distorsionados(folder_name, df_imputado, penalty)

                d_opt = data_base.copy()
                d_opt["votantes_validos_pendientes_est"] = round(votantes_validos_opt, 2)
                d_opt["observacion"] = f"Imputado de {region} + Prior (P={penalty})"
                d_opt["candidatos"] = []

                d_pes = data_base.copy()
                d_pes["votantes_validos_pendientes_est"] = round(votantes_validos_pes, 2)
                d_pes["observacion"] = f"Imputado de {region} + Prior (P={penalty})"
                d_pes["candidatos"] = []

                for item in candidatos_imputados:
                    pct_final = item["pct_proyectado"]

                    d_opt["candidatos"].append({
                        "candidato_o_tipo": item["cand"], "agrupacion": item["agrupacion"],
                        "porcentaje_valido_base": round(item["pct_base"], 3),
                        "porcentaje_valido_usado": round(pct_final, 3),
                        "votos_proyectados_faltantes": round(votantes_validos_opt * (pct_final / 100.0), 0)
                    })
                    d_pes["candidatos"].append({
                        "candidato_o_tipo": item["cand"], "agrupacion": item["agrupacion"],
                        "porcentaje_valido_base": round(item["pct_base"], 3),
                        "porcentaje_valido_usado": round(pct_final, 3),
                        "votos_proyectados_faltantes": round(votantes_validos_pes * (pct_final / 100.0), 0)
                    })

                projections_opt[penalty].append(d_opt)
                projections_pes[penalty].append(d_pes)

        # =======================================================
        # GUARDADO DE TODOS LOS ESCENARIOS
        # =======================================================
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for penalty in self.RURAL_PENALTIES:
            # Los archivos llevarán el identificador de penalidad p0.0, p0.1, etc.
            self._flatten_and_save(projections_opt[penalty], f"proyeccion_optimista_p{penalty:.1f}", ts)
            self._flatten_and_save(projections_pes[penalty], f"proyeccion_pesimista_p{penalty:.1f}", ts)

    def _flatten_and_save(self, projections_list, prefijo_nombre, ts):
        flat_data = []
        for loc in projections_list:
            for cand in loc["candidatos"]:
                flat_data.append({
                    "ubicacion": loc["ubicacion"],
                    "actualizado_dt": loc["actualizado_dt"],
                    "avance_actas_pct": loc["avance_actas_pct"],
                    "votantes_validos_pendientes_est": loc["votantes_validos_pendientes_est"],
                    "candidato_o_tipo": cand["candidato_o_tipo"],
                    "agrupacion": cand["agrupacion"],
                    "porcentaje_valido_base": cand["porcentaje_valido_base"],
                    "porcentaje_valido_usado_prior": cand["porcentaje_valido_usado"],
                    "votos_proyectados_faltantes": cand["votos_proyectados_faltantes"],
                    "observacion": loc.get("observacion", "Data real")
                })

        if flat_data:
            df_final = pd.DataFrame(flat_data)
            output_file = self.proy_dir / f"{prefijo_nombre}_{ts}.csv"
            df_final.to_csv(output_file, index=False, encoding='utf-8')
            print(f"✅ Generado: {output_file.name}")

if __name__ == "__main__":
    ElectionProjector().generate_projections()