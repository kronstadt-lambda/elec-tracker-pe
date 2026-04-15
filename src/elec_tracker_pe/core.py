from playwright.sync_api import sync_playwright
import pandas as pd
from pathlib import Path
from .config import ONPE_PRE_URL, ONPE_PC_URL, DATA_DIR
from .utils import clean_onpe_date, extract_number, calculate_absolute_voters

class ONPEScraper:
    def __init__(self):
        self.url_pre = ONPE_PRE_URL
        self.url_pc = ONPE_PC_URL

    def fetch_results(self, nivel_carpeta="todos"):
        """
        Extrae datos de Presidenciales y Participación Ciudadana.
        nivel_carpeta define en qué subcarpeta se guardará (ej: 'todos', 'region').
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, slow_mo=50)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # ==========================================
            # FASE 1: DATOS PRESIDENCIALES (url_pre)
            # ==========================================
            print(f"[{nivel_carpeta.upper()}] Cargando página de resultados presidenciales...")
            page.goto(self.url_pre, timeout=60000)

            try:
                page.wait_for_selector('.infoprincipal-detalle', timeout=60000)
            except Exception as e:
                print(f"Error cargando url_pre: {e}")
                browser.close()
                return [], nivel_carpeta, False

            # Extracción de fecha principal para el MATCH
            fecha_iso_pre = clean_onpe_date(page.locator('.actualizado b').inner_text())
            ubicacion = page.locator('mat-select-trigger').first.inner_text().strip()
            actas_pct = extract_number(page.locator('.infoprincipal-detalle', has_text="Actas contabilizadas").locator('b').inner_text())

            # Leyenda Vertical PRE
            leyenda_pre = page.locator('ul.leyenda.vertical li')
            votos_data = {}
            for i in range(leyenda_pre.count()):
                texto_li = leyenda_pre.nth(i).inner_text()
                valor_b = leyenda_pre.nth(i).locator('b').inner_text()
                if "Contabilizadas" in texto_li: votos_data['contabilizadas'] = extract_number(valor_b)
                elif "JEE" in texto_li: votos_data['envio_jee'] = extract_number(valor_b)
                elif "Pendientes" in texto_li: votos_data['pendientes'] = extract_number(valor_b)

            data_final = []
            filas = page.locator('article.candidato').all()

            for fila in filas:
                if not fila.is_visible():
                    continue
                if fila.locator('.nombre h3').count() == 0:
                    continue

                clases = fila.get_attribute('class') or ""

                try:
                    nombre = fila.locator('.nombre h3').first.text_content(timeout=500).strip()
                    agrupacion = ""

                    if 'sincandidato' not in clases:
                        agrupacion = fila.locator('.nombre p').first.text_content(timeout=500).strip()
                        pct_valido = fila.locator('.cant.cant-pc').nth(0).locator('b').first.text_content(timeout=500).strip()
                        pct_emitido = fila.locator('.cant.cant-pc').nth(1).locator('b').first.text_content(timeout=500).strip()
                        votos_totales = fila.locator('.titulo_votos_totales__num2').first.text_content(timeout=500).strip()
                    else:
                        if "total de votos" in nombre.lower():
                            pct_valido = "100"
                            pct_emitido = "100"
                            votos_totales = fila.locator('.titulo_votos_totales__num2').nth(1).text_content(timeout=500).strip()
                        else:
                            pct_valido = "-"
                            pct_emitido = fila.locator('.cant.cant-pc b').first.text_content(timeout=500).strip()
                            votos_totales = fila.locator('.titulo_votos_totales__num2').first.text_content(timeout=500).strip()

                    data_final.append({
                        "ubicacion": ubicacion,
                        "actualizado_dt": fecha_iso_pre,
                        "actas_contabilizadas_pct": actas_pct,
                        "global_contabilizadas": votos_data.get('contabilizadas', 0),
                        "global_jee": votos_data.get('envio_jee', 0),
                        "global_pendientes": votos_data.get('pendientes', 0),
                        "candidato_o_tipo": nombre,
                        "agrupacion": agrupacion,
                        "porcentaje_valido": extract_number(pct_valido),
                        "porcentaje_emitido": extract_number(pct_emitido),
                        "cantidad_votos": extract_number(votos_totales)
                    })
                except Exception as e:
                    print(f"Fila ignorada por formato inesperado: {e}")
                    continue

            # ==========================================
            # FASE 2: PARTICIPACIÓN CIUDADANA (url_pc)
            # ==========================================
            print("Navegando a Participación Ciudadana para cruce de datos...")
            page.goto(self.url_pc, timeout=60000)

            try:
                page.wait_for_selector('.infoNumbers.txtClr_1 b', timeout=30000)
            except Exception as e:
                print("Error: No cargó la página de Participación.")
                browser.close()
                return [], nivel_carpeta, False

            fecha_iso_pc = clean_onpe_date(page.locator('.actualizado b').inner_text())
            if fecha_iso_pre != fecha_iso_pc:
                print(f"❌ ALERTA DE DESFASE: La web 1 ({fecha_iso_pre}) no coincide con la web 2 ({fecha_iso_pc}).")
                print("Se aborta la extracción para mantener la integridad de los datos.")
                browser.close()
                return [], nivel_carpeta, False

            electores_text = page.locator('.infoNumbers.txtClr_1 b').first.text_content()
            electores_habiles = int(extract_number(electores_text))

            lis_participacion = page.locator('.col_dato_participacion ul.leyenda.vertical li').all()

            pct_asistentes, pct_ausentes, pct_pendientes = "0", "0", "0"
            for li in lis_participacion:
                txt = li.text_content().lower()
                val = li.locator('b').first.text_content()
                if 'asistentes' in txt: pct_asistentes = val
                elif 'ausentes' in txt: pct_ausentes = val
                elif 'pendientes' in txt: pct_pendientes = val

            abs_asistentes = calculate_absolute_voters(pct_asistentes, electores_habiles)
            abs_ausentes = calculate_absolute_voters(pct_ausentes, electores_habiles)
            abs_pendientes = calculate_absolute_voters(pct_pendientes, electores_habiles)

            for row in data_final:
                row['electores_habiles'] = electores_habiles
                row['asistentes_totales'] = abs_asistentes
                row['ausentes_totales'] = abs_ausentes
                row['pendientes_totales'] = abs_pendientes

            browser.close()
            print("✅ Extracción y cruce exitosos.")
            return data_final, nivel_carpeta, True

    def save_to_csv(self, data, nivel_carpeta, success):
        """Guarda la data solo si fue exitosa y si no es un duplicado."""
        if not success or not data:
            print("No se guardará el archivo debido a un error o desfase previo.")
            return

        target_dir = DATA_DIR / nivel_carpeta.lower()
        target_dir.mkdir(parents=True, exist_ok=True)

        # Convertimos '2026-04-14 17:04:16' a '20260414_170416'
        dt_str = data[0]['actualizado_dt'].replace("-", "").replace(":", "").replace(" ", "_")
        filename = target_dir / f"onpe_{nivel_carpeta.lower()}_{dt_str}.csv"

        if filename.exists():
            print(f"⚠️ El archivo {filename.name} ya existe. La ONPE no ha liberado nueva data. Saltando...")
            return

        df = pd.DataFrame(data)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"💾 Archivo nuevo guardado en: {filename}")

if __name__ == "__main__":
    scraper = ONPEScraper()
    res, nivel, success = scraper.fetch_results(nivel_carpeta="todos")
    scraper.save_to_csv(res, nivel, success)