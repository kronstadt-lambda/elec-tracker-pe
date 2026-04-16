import json
import pandas as pd
import numpy as np
import unicodedata
from pathlib import Path
from .config import DATA_DIR

class AffinityCalculator:
    def __init__(self):
        self.raw_dir = DATA_DIR
        self.densidad_file = DATA_DIR.parent / "densidad_prov_poblacional.json"
        self.output_file = DATA_DIR.parent / "afinidad_electoral.json"

        # Parámetros Logarítmicos para Normalización (Distribución del Bolsón)
        self.MIN_DENSIDAD = 0.2
        self.MAX_DENSIDAD = 1000.0

        # Umbrales Estratégicos para Clústeres
        self.UMBRAL_URBANO = 100.0
        self.UMBRAL_RURAL = 20.0

        self.geo_proxy = {}

        # Contenedores para la ponderación real
        self.total_validos_cluster = {"URBANO": 0, "RURAL": 0, "MIXTO": 0}
        self.candidatos_votos_cluster = {}

    def _normalize_name(self, name):
        text = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
        return text.lower().replace(" ", "_")

    def _calculate_urban_score(self, densidad):
        d = max(self.MIN_DENSIDAD, min(densidad, self.MAX_DENSIDAD))
        score = (np.log(d) - np.log(self.MIN_DENSIDAD)) / (np.log(self.MAX_DENSIDAD) - np.log(self.MIN_DENSIDAD))
        return round(score, 4)

    def _determinar_cluster(self, densidad):
        if densidad >= self.UMBRAL_URBANO:
            return "URBANO"
        elif densidad <= self.UMBRAL_RURAL:
            return "RURAL"
        else:
            return "MIXTO"

    def _load_and_process_densities(self):
        if not self.densidad_file.exists():
            print(f"❌ No se encontró el archivo: {self.densidad_file}")
            return False

        with open(self.densidad_file, 'r', encoding='utf-8') as f:
            raw_densidades = json.load(f)

        for region, provs in raw_densidades.get("PERU", {}).items():
            for prov_name, data in provs.items():
                clean_name = self._normalize_name(prov_name)
                d = data["densidad_hab_km2"]
                urb_score = self._calculate_urban_score(d)

                self.geo_proxy[clean_name] = {
                    "densidad": d,
                    "cluster": self._determinar_cluster(d),
                    "urbanidad_pct": round(urb_score * 100, 2),
                    "ruralidad_pct": round((1 - urb_score) * 100, 2),
                    "ruralidad_score_proxy": round((1 - urb_score), 4)
                }

        for cont_name, data in raw_densidades.get("EXTRANJERO", {}).items():
            clean_name = self._normalize_name(cont_name)
            d = data["densidad_hab_km2"]
            urb_score = self._calculate_urban_score(d)

            self.geo_proxy[clean_name] = {
                "densidad": d,
                "cluster": self._determinar_cluster(d),
                "urbanidad_pct": round(urb_score * 100, 2),
                "ruralidad_pct": round((1 - urb_score) * 100, 2),
                "ruralidad_score_proxy": round((1 - urb_score), 4)
            }
        return True

    def _get_latest_csv(self, folder_path):
        csv_files = list(folder_path.glob("*.csv"))
        if not csv_files: return None
        return max(csv_files, key=lambda x: x.stat().st_mtime)

    def _safe_float(self, val):
        try: return float(str(val).replace(',', ''))
        except (ValueError, TypeError): return 0.0

    def calculate_affinities(self):
        print("🧠 Iniciando cálculo de Perfiles Geográficos por Clúster y Ponderación de Votos...")

        if not self._load_and_process_densities(): return

        unwanted_terms = ['VOTOS EN BLANCO', 'VOTOS NULOS', 'total de votos']

        # 1. Recolección y Agrupación Ponderada
        for folder in [f for f in self.raw_dir.iterdir() if f.is_dir()]:
            folder_name = folder.name
            if folder_name == "todos": continue
            if folder_name not in self.geo_proxy: continue

            latest_csv = self._get_latest_csv(folder)
            if not latest_csv: continue

            df = pd.read_csv(latest_csv)
            df = df[~df['candidato_o_tipo'].str.contains('|'.join(unwanted_terms), case=False, na=False)].copy()

            cluster = self.geo_proxy[folder_name]["cluster"]

            # Sumar total de votos válidos en esta provincia para el denominador del clúster
            df['cantidad_votos_num'] = df['cantidad_votos'].apply(self._safe_float)
            total_validos_prov = df['cantidad_votos_num'].sum()
            self.total_validos_cluster[cluster] += total_validos_prov

            # Sumar votos a cada candidato dentro del clúster
            for _, row in df.iterrows():
                cand = row['candidato_o_tipo']
                votos = row['cantidad_votos_num']

                if cand not in self.candidatos_votos_cluster:
                    self.candidatos_votos_cluster[cand] = {"URBANO": 0, "RURAL": 0, "MIXTO": 0}

                self.candidatos_votos_cluster[cand][cluster] += votos

        # 2. Calcular Índice de Contraste (Afinidad)
        resultados_afinidad = {}
        for cand, votos_por_cluster in self.candidatos_votos_cluster.items():

            # Cálculo de promedios ponderados exactos
            pct_urbano = (votos_por_cluster["URBANO"] / self.total_validos_cluster["URBANO"]) * 100 if self.total_validos_cluster["URBANO"] > 0 else 0
            pct_rural = (votos_por_cluster["RURAL"] / self.total_validos_cluster["RURAL"]) * 100 if self.total_validos_cluster["RURAL"] > 0 else 0
            pct_mixto = (votos_por_cluster["MIXTO"] / self.total_validos_cluster["MIXTO"]) * 100 if self.total_validos_cluster["MIXTO"] > 0 else 0

            # Índice de Contraste: (-1 a 1)
            denominador = pct_rural + pct_urbano
            if denominador > 0:
                afinidad = (pct_rural - pct_urbano) / denominador
            else:
                afinidad = 0.0

            afinidad_redondeada = round(afinidad, 4)

            # Categorización
            if afinidad_redondeada > 0.25: perfil = "Rural"
            elif afinidad_redondeada < -0.25: perfil = "Urbano"
            else: perfil = "Transversal"

            resultados_afinidad[cand] = {
                "afinidad_nacional": afinidad_redondeada,
                "perfil_estimado": perfil,
                "desglose_rendimiento": {
                    "rendimiento_urbano_pct": round(pct_urbano, 2),
                    "rendimiento_rural_pct": round(pct_rural, 2),
                    "rendimiento_mixto_pct": round(pct_mixto, 2)
                }
            }

        # 3. Ensamblar JSON
        output_data = {
            "metodologia": {
                "transformacion_distribucion": "Logarítmica Min-Max (0.2 a 1000 hab/km2)",
                "calculo_afinidad": "Rendimiento por Clústeres con Ponderación de Votos Absolutos",
                "umbrales_cluster": f"Urbano > {self.UMBRAL_URBANO} hab/km2 | Rural < {self.UMBRAL_RURAL} hab/km2",
                "escala_afinidad": "-1 (100% Urbano) a 1 (100% Rural)"
            },
            "provincias_y_continentes": self.geo_proxy,
            "candidatos": resultados_afinidad
        }

        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)

        print(f"✅ Archivo de afinidad (Modelo de Clústeres) generado en: {self.output_file}")

if __name__ == "__main__":
    AffinityCalculator().calculate_affinities()