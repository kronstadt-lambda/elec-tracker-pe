import json
import asyncio
import time
import argparse
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
from .config import ONPE_PRE_URL, ONPE_PC_URL, DATA_DIR
from .utils import clean_onpe_date, extract_number, calculate_absolute_voters

class ONPEMasterScraper:
    def __init__(self, target="all"):
        self.url_pre = ONPE_PRE_URL
        self.url_pc = ONPE_PC_URL
        self.geo_file = DATA_DIR.parent / "ubigeo_georeferenciado.json"
        self.geo_data = self._load_geo_data()
        self.last_known_date = None
        self.current_extraction_date = None
        self.total_tasks = 0
        self.completed_tasks = 0
        self.target = target # 'peru', 'extranjero', o 'all'

    def _load_geo_data(self):
        if self.geo_file.exists():
            with open(self.geo_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"PERU": {}, "EXTRANJERO": {}}

    async def _select_option(self, page, dropdown_name, option_text):
        try:
            dropdown = page.locator(f'mat-select[formcontrolname="{dropdown_name}"]')
            await dropdown.click()
            await asyncio.sleep(0.5)
            await page.get_by_role("option", name=option_text, exact=True).click(timeout=10000)
            await asyncio.sleep(1.5)
            return True
        except Exception as e:
            await page.keyboard.press("Escape")
            return False

    async def check_for_updates(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            try:
                await page.goto(self.url_pre, timeout=60000)
                await page.wait_for_selector('.infoprincipal-detalle', timeout=60000)
                date_text = await page.locator('.actualizado b').inner_text()
                current_date = clean_onpe_date(date_text)

                if current_date != self.last_known_date:
                    print(f"\n🚨 [{self.target.upper()}] NUEVA ACTUALIZACIÓN MAESTRA: {current_date}", flush=True)
                    self.last_known_date = current_date
                    await browser.close()
                    return True
            except Exception as e:
                print(f"⚠️ Error al revisar web maestra: {e}", flush=True)
            await browser.close()
        return False

    async def _scrape_target_task(self, browser, semaphore, tipo="TODOS", nivel1=None, nivel2=None):
        """Tarea individual protegida por un semáforo inyectado dinámicamente."""
        async with semaphore:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page_pre = await context.new_page()
            page_pc = await context.new_page()

            # Ajuste clave: Si no hay nivel2 (como en los continentes), usamos el nivel1
            folder_name = nivel2 if nivel2 else (nivel1 if nivel1 else "todos")
            carpeta_limpia = folder_name.lower().replace(" ", "_")

            try:
                await page_pre.goto(self.url_pre, timeout=60000)
                await page_pc.goto(self.url_pc, timeout=60000)

                for p in [page_pre, page_pc]:
                    if tipo == "TODOS":
                        await self._select_option(p, "region", "TODOS")
                    elif tipo == "PERÚ":
                        await self._select_option(p, "region", "PERÚ")
                        await self._select_option(p, "department", nivel1)
                        await self._select_option(p, "province", nivel2)
                    elif tipo == "EXTRANJERO":
                        await self._select_option(p, "region", "EXTRANJERO")
                        if nivel1:
                            # CORRECCIÓN: El formcontrolname correcto para continentes es 'continent'
                            await self._select_option(p, "continent", nivel1)

                date_pre = clean_onpe_date(await page_pre.locator('.actualizado b').inner_text())

                # ==========================================
                # FASE 1: Extracción Presidencial
                # ==========================================
                actas_pct = extract_number(await page_pre.locator('.infoprincipal-detalle', has_text="Actas contabilizadas").locator('b').inner_text())

                leyenda_pre = page_pre.locator('ul.leyenda.vertical li')
                votos_data = {}
                count = await leyenda_pre.count()
                for i in range(count):
                    texto_li = await leyenda_pre.nth(i).inner_text()
                    valor_b = await leyenda_pre.nth(i).locator('b').inner_text()
                    if "Contabilizadas" in texto_li: votos_data['contabilizadas'] = extract_number(valor_b)
                    elif "JEE" in texto_li: votos_data['envio_jee'] = extract_number(valor_b)
                    elif "Pendientes" in texto_li: votos_data['pendientes'] = extract_number(valor_b)

                rows = []
                filas = await page_pre.locator('article.candidato').all()
                for fila in filas:
                    if not await fila.is_visible() or await page_pre.locator('.nombre h3').count() == 0: continue
                    clases = await fila.get_attribute('class') or ""

                    try:
                        nombre = (await fila.locator('.nombre h3').first.text_content()).strip()
                        agrupacion = ""
                        pct_valido, pct_emitido, votos_totales = "-", "0", "0"

                        if 'sincandidato' not in clases:
                            agrupacion = (await fila.locator('.nombre p').first.text_content()).strip()
                            pct_valido = (await fila.locator('.cant.cant-pc').nth(0).locator('b').first.text_content()).strip()
                            pct_emitido = (await fila.locator('.cant.cant-pc').nth(1).locator('b').first.text_content()).strip()
                            votos_totales = (await fila.locator('.titulo_votos_totales__num2').first.text_content()).strip()
                        else:
                            if "total de votos" in nombre.lower():
                                pct_valido, pct_emitido = "100", "100"
                                votos_totales = (await fila.locator('.titulo_votos_totales__num2').nth(1).text_content()).strip()
                            else:
                                pct_valido = "-"
                                pct_emitido = (await fila.locator('.cant.cant-pc b').first.text_content()).strip()
                                votos_totales = (await fila.locator('.titulo_votos_totales__num2').first.text_content()).strip()

                        # Identificador para la fila
                        ubicacion_str = nivel2 if nivel2 else (nivel1 if nivel1 else "TODOS")

                        row = {
                            "ubicacion": ubicacion_str,
                            "actualizado_dt": date_pre,
                            "actas_contabilizadas_pct": actas_pct,
                            "global_contabilizadas": votos_data.get('contabilizadas', 0),
                            "global_jee": votos_data.get('envio_jee', 0),
                            "global_pendientes": votos_data.get('pendientes', 0),
                            "candidato_o_tipo": nombre,
                            "agrupacion": agrupacion,
                            "porcentaje_valido": extract_number(pct_valido),
                            "porcentaje_emitido": extract_number(pct_emitido),
                            "cantidad_votos": extract_number(votos_totales)
                        }
                        rows.append(row)
                    except Exception as e:
                        continue

                # ==========================================
                # FASE 2: Extracción Participación
                # ==========================================
                electores_text = await page_pc.locator('.infoNumbers.txtClr_1 b').first.text_content()
                electores = int(extract_number(electores_text))

                lis_participacion = await page_pc.locator('.col_dato_participacion ul.leyenda.vertical li').all()
                pct_asist, pct_aus, pct_pend = "0", "0", "0"
                for li in lis_participacion:
                    txt = (await li.text_content()).lower()
                    val = await li.locator('b').first.text_content()
                    if 'asistentes' in txt: pct_asist = val
                    elif 'ausentes' in txt: pct_aus = val
                    elif 'pendientes' in txt: pct_pend = val

                for r in rows:
                    r.update({
                        "electores_habiles": electores,
                        "asistentes_totales": calculate_absolute_voters(pct_asist, electores),
                        "ausentes_totales": calculate_absolute_voters(pct_aus, electores),
                        "pendientes_totales": calculate_absolute_voters(pct_pend, electores)
                    })

                # GUARDADO INMEDIATO
                if rows:
                    self.save_to_csv(rows, carpeta_limpia)
                    self.completed_tasks += 1
                    print(f"  [{self.completed_tasks}/{self.total_tasks}] ✅ Extraído: {folder_name}", flush=True)

            except Exception as e:
                self.completed_tasks += 1
                print(f"  [{self.completed_tasks}/{self.total_tasks}] ❌ Error en {folder_name}: {e}", flush=True)
            finally:
                await context.close()

    async def run_full_extraction(self):
        self.current_extraction_date = self.last_known_date
        print(f"⚙️ Iniciando extracción para target: {self.target.upper()}", flush=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            self.completed_tasks = 0

            # CALCULAR TOTALES SEGÚN TARGET
            self.total_tasks = 0
            if self.target in ['peru', 'all']:
                self.total_tasks += 1 # MACRO
                self.total_tasks += sum(len(provs) for provs in self.geo_data.get("PERU", {}).values())
            if self.target in ['extranjero', 'all']:
                self.total_tasks += len(self.geo_data.get("EXTRANJERO", {}).keys())

            # ---------------------------------------------------------
            # BLOQUE 1: PERÚ (Concurrencia Dinámica por Región) + MACRO
            # ---------------------------------------------------------
            if self.target in ['peru', 'all']:
                print("  🌍 Extrayendo MACRO (Secuencial)...", flush=True)
                sem_single = asyncio.Semaphore(1)
                await self._scrape_target_task(browser, sem_single, tipo="TODOS")

                print("  🇵🇪 Iniciando PERÚ (Ráfagas dinámicas por Región)...", flush=True)
                for region, provincias in self.geo_data.get("PERU", {}).items():
                    num_provincias = len(provincias)
                    sem_dinamico = asyncio.Semaphore(num_provincias)
                    print(f"    -> Lanzando Región {region} ({num_provincias} provincias a la vez)...", flush=True)

                    region_tasks = []
                    for provincia in provincias.keys():
                        region_tasks.append(self._scrape_target_task(browser, sem_dinamico, tipo="PERÚ", nivel1=region, nivel2=provincia))

                    await asyncio.gather(*region_tasks)

            # ---------------------------------------------------------
            # BLOQUE 2: EXTRANJERO (Secuencial por Continente)
            # ---------------------------------------------------------
            if self.target in ['extranjero', 'all']:
                print("  ✈️ Iniciando EXTRANJERO (Secuencial por Continente)...", flush=True)
                sem_single = asyncio.Semaphore(1)

                for continente in self.geo_data.get("EXTRANJERO", {}).keys():
                    print(f"    -> Extrayendo Continente: {continente}...", flush=True)
                    await self._scrape_target_task(browser, sem_single, tipo="EXTRANJERO", nivel1=continente)

            await browser.close()
            print(f"✅ Extracción {self.target.upper()} finalizada.", flush=True)

    def save_to_csv(self, data, folder_name):
        target_dir = DATA_DIR / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        dt_str = self.current_extraction_date.replace("-", "").replace(":", "").replace(" ", "_")
        filename = target_dir / f"onpe_{folder_name}_{dt_str}.csv"

        pd.DataFrame(data).to_csv(filename, index=False, encoding='utf-8')

async def main():
    parser = argparse.ArgumentParser(description="ONPE Electoral Tracker")
    parser.add_argument('--target', type=str, choices=['peru', 'extranjero', 'all'], default='all', help="Define qué bloque descargar")
    args = parser.parse_args()

    scraper = ONPEMasterScraper(target=args.target)
    print(f"🛡️ Tracker Maestro Iniciado. Modo: {args.target.upper()}", flush=True)

    while True:
        try:
            if await scraper.check_for_updates():
                await scraper.run_full_extraction()
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Esperando actualización...", flush=True)
            await asyncio.sleep(30)
        except Exception as e:
            print(f"\n🔥 Error global: {e}", flush=True)
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())