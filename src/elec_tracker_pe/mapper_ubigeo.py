import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from .config import ONPE_PRE_URL, DATA_DIR

class ONPEUbigeoMapper:
    def __init__(self):
        self.url = ONPE_PRE_URL
        self.output_file = DATA_DIR.parent / "ubigeo_diccionario.json"

    def _get_dropdown_options(self, page, selector):
        """Abre un dropdown, extrae todas sus opciones válidas y lo cierra."""
        try:
            # 1. Hacemos clic para abrir el menú
            dropdown = page.locator(selector)
            dropdown.click(timeout=5000)

            # 2. Esperamos a que el panel CDK de Angular dibuje las opciones
            page.wait_for_selector('mat-option', timeout=5000)

            # 3. Extraemos todos los textos
            opciones_raw = page.locator('mat-option').all_inner_texts()

            # 4. FILTRO ESTRICTO: Ignoramos opciones vacías y los encabezados/placeholders
            palabras_ignoradas = [
                "TODOS", "SELECCIONE", "-- TODOS --",
                "REGIÓN", "PROVINCIA", "DISTRITO",
                "CONTINENTE", "PAÍS", "CIUDAD"
            ]

            opciones_limpias = []
            for opt in opciones_raw:
                texto = opt.strip()
                if texto and texto.upper() not in palabras_ignoradas:
                    opciones_limpias.append(texto)

            # 5. Cerramos el menú presionando Escape
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            return opciones_limpias
        except Exception as e:
            print(f"    [!] Error leyendo opciones de {selector}: {e}")
            page.keyboard.press("Escape")
            return []

    def _select_option(self, page, selector, opcion_texto):
        """Abre el dropdown y selecciona una opción específica."""
        dropdown = page.locator(selector)
        dropdown.click()
        page.wait_for_timeout(500)

        # Ignorar espacios en blanco iniciales/finales de Angular
        opcion = page.get_by_role("option", name=opcion_texto, exact=True)
        opcion.click()

        # Dar tiempo al servidor para cargar el siguiente dropdown
        page.wait_for_timeout(1500)

    def build_map(self):
        """Orquesta la iteración por todos los niveles geográficos."""

        # Cargar progreso previo si existe para reanudar o actualizar
        mapa_global = {"PERU": {}, "EXTRANJERO": {}}
        if self.output_file.exists():
            with open(self.output_file, 'r', encoding='utf-8') as f:
                mapa_global = json.load(f)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True) # Headless=False recomendado para monitorear bloqueos
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            print("🚀 Iniciando Mapeo de UBIGEOs ONPE...")
            page.goto(self.url, timeout=60000)
            page.wait_for_selector('mat-select[formcontrolname="region"]', timeout=30000)

            # ==========================================
            # ÁRBOL 1: PERÚ (Región -> Provincia -> Distrito)
            # ==========================================
            print("\n🌎 Explorando: PERÚ")
            self._select_option(page, 'mat-select[formcontrolname="region"]', "PERÚ")

            regiones = self._get_dropdown_options(page, 'mat-select[formcontrolname="department"]')
            print(f"Encontradas {len(regiones)} regiones.")

            for region in regiones:
                # Si ya mapeamos la región en una corrida anterior, la saltamos para ahorrar tiempo
                if region in mapa_global["PERU"] and mapa_global["PERU"][region]:
                    print(f"  ⏭️ Saltando {region} (ya existe en caché).")
                    continue

                print(f"  📍 Mapeando Región: {region}")
                self._select_option(page, 'mat-select[formcontrolname="department"]', region)
                mapa_global["PERU"][region] = {}

                provincias = self._get_dropdown_options(page, 'mat-select[formcontrolname="province"]')

                for provincia in provincias:
                    self._select_option(page, 'mat-select[formcontrolname="province"]', provincia)
                    distritos = self._get_dropdown_options(page, 'mat-select[formcontrolname="district"]')
                    mapa_global["PERU"][region][provincia] = distritos

                # Autoguardado tras cada región
                self.save_progress(mapa_global)


            # ==========================================
            # ÁRBOL 2: EXTRANJERO (Continente -> País -> Ciudad/Estado)
            # ==========================================
            print("\n✈️ Explorando: EXTRANJERO")
            # Refrescamos la web para resetear el DOM a su estado inicial
            page.goto(self.url)
            page.wait_for_selector('mat-select[formcontrolname="region"]')
            self._select_option(page, 'mat-select[formcontrolname="region"]', "EXTRANJERO")

            continentes = self._get_dropdown_options(page, 'mat-select[formcontrolname="continent"]')
            print(f"Encontrados {len(continentes)} continentes.")

            for continente in continentes:
                if continente in mapa_global["EXTRANJERO"] and mapa_global["EXTRANJERO"][continente]:
                    print(f"  ⏭️ Saltando {continente} (ya existe en caché).")
                    continue

                print(f"  🗺️ Mapeando Continente: {continente}")
                self._select_option(page, 'mat-select[formcontrolname="continent"]', continente)
                mapa_global["EXTRANJERO"][continente] = {}

                paises = self._get_dropdown_options(page, 'mat-select[formcontrolname="country"]')

                for pais in paises:
                    self._select_option(page, 'mat-select[formcontrolname="country"]', pais)
                    # La variable DOM de la ONPE se llama 'state' aunque visualmente dice 'CIUDAD'
                    ciudades = self._get_dropdown_options(page, 'mat-select[formcontrolname="state"]')
                    mapa_global["EXTRANJERO"][continente][pais] = ciudades

                # Autoguardado tras cada continente
                self.save_progress(mapa_global)

            browser.close()
            print("\n✅ MAPEO UBIGEO COMPLETADO EXITOSAMENTE.")

    def save_progress(self, data):
        """Guarda el estado actual del diccionario en el disco."""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"      💾 Autoguardado actualizado en {self.output_file.name}")

if __name__ == "__main__":
    mapper = ONPEUbigeoMapper()
    mapper.build_map()