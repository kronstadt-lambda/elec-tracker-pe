import asyncio
import time
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
from .config import ONPE_PRE_URL, ONPE_PC_URL, DATA_DIR
from .utils import clean_onpe_date, extract_number, calculate_absolute_voters

class ONPETodosScraper:
    def __init__(self):
        self.url_pre = ONPE_PRE_URL
        self.url_pc = ONPE_PC_URL
        self.last_known_date = None
        self.current_extraction_date = None

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
                    print(f"\n🚨 [MACRO] NUEVA ACTUALIZACIÓN ONPE: {current_date}", flush=True)
                    self.last_known_date = current_date
                    await browser.close()
                    return True
            except Exception as e:
                print(f"⚠️ Error al revisar web maestra: {e}", flush=True)
            await browser.close()
        return False

    async def _scrape_todos_task(self, browser):
        """Extrae únicamente el consolidado nacional (TODOS)."""
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        )
        page_pre = await context.new_page()
        page_pc = await context.new_page()
        folder_name = "todos"

        try:
            await page_pre.goto(self.url_pre, timeout=60000)
            await page_pc.goto(self.url_pc, timeout=60000)

            for p in [page_pre, page_pc]:
                await self._select_option(p, "region", "TODOS")

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

                    row = {
                        "ubicacion": "TODOS",
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
                except Exception:
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

            if rows:
                self.save_to_csv(rows, folder_name)
                print(f"  ✅ Extraído Exitosamente: CONSOLIDADO NACIONAL (TODOS)", flush=True)

        except Exception as e:
            print(f"  ❌ Error en extracción MACRO: {e}", flush=True)
        finally:
            await context.close()

    async def run_full_extraction(self):
        self.current_extraction_date = self.last_known_date
        print("⚙️ Iniciando extracción ultra-rápida (MACRO NACIONAL)...", flush=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            await self._scrape_todos_task(browser)
            await browser.close()
            print("✅ Extracción MACRO finalizada.", flush=True)

    def save_to_csv(self, data, folder_name):
        target_dir = DATA_DIR / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        dt_str = self.current_extraction_date.replace("-", "").replace(":", "").replace(" ", "_")
        filename = target_dir / f"onpe_{folder_name}_{dt_str}.csv"
        pd.DataFrame(data).to_csv(filename, index=False, encoding='utf-8')

async def main():
    scraper = ONPETodosScraper()
    print("⚡ Tracker FAST (Nacional) Iniciado.", flush=True)

    while True:
        try:
            if await scraper.check_for_updates():
                await scraper.run_full_extraction()
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Fast-Tracker esperando...", flush=True)
            # Puedes bajar este sleep a 10 o 15 segundos si quieres que detecte cambios casi de inmediato
            await asyncio.sleep(30)
        except Exception as e:
            print(f"\n🔥 Error global en Fast-Tracker: {e}", flush=True)
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())