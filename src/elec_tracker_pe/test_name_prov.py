import requests

def get_geojson_provinces():
    # URL definida en tu archivo utils_graphs.py para provincias
    url = "https://raw.githubusercontent.com/juaneladio/peru-geojson/master/peru_provincial_simple.geojson"

    print(f"--- Cargando GeoJSON desde: {url} ---")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extraer los nombres de la propiedad 'NOMBPROV' que usa tu dashboard
        provincias_geojson = []
        for feature in data['features']:
            nombre = feature['properties'].get('NOMBPROV')
            if nombre:
                provincias_geojson.append(nombre)

        # Ordenar alfabéticamente
        provincias_geojson.sort()

        print(f"Total de provincias encontradas en el GeoJSON: {len(provincias_geojson)}")
        print("\nLista de Provincias:")
        for i, prov in enumerate(provincias_geojson, 1):
            print(f"{i}. {prov}")

        return provincias_geojson

    except Exception as e:
        print(f"Error al obtener el archivo: {e}")
        return []

if __name__ == "__main__":
    lista_provincias = get_geojson_provinces()