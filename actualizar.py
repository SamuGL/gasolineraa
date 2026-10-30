import os
import sys
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

SUPABASE_URL = os.environ.get("https://ppzjdckokrbegbpoztzk.supabase.co")
SUPABASE_KEY = os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBwempkY2tva3JiZWdicG96dHprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MzMwODMyNCwiZXhwIjoyMTA4ODg0MzI0fQ.SjqgtJmdwqIohbvrzeu2GUmwkRfp6EVylysW2J8MT0A")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Faltan las variables de entorno SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY.")
    sys.exit(1)

# Endpoint oficial del Ministerio
API_MINISTERIO = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"

# Cabeceras completas imitando a un navegador Chrome real
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

def parse_num(val):
    if not val:
        return None
    try:
        return float(val.replace(".", "").replace(",", "."))
    except ValueError:
        return None

def parse_coord(val):
    if not val:
        return None
    try:
        return float(val.replace(",", "."))
    except ValueError:
        return None

def descargar_con_reintentos():
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Estrategia de reintentos automáticos
    retry_strategy = Retry(
        total=5,
        backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Intentamos primero directo; si la sede del Ministerio bloquea el servidor de GitHub,
    # usamos un espejo / proxy transparente para descargar el JSON
    urls_fuente = [
        API_MINISTERIO,
        f"https://api.allorigins.win/raw?url={requests.utils.quote(API_MINISTERIO)}"
    ]

    for url in urls_fuente:
        try:
            print(f"Probando descarga desde: {url[:60]}...")
            res = session.get(url, timeout=45)
            if res.status_code == 200:
                data = res.json()
                if "ListaEESSPrecio" in data:
                    print("¡Descarga completada con éxito!")
                    return data
        except Exception as e:
            print(f"Aviso: Falló el intento con {url[:30]}... ({e})")
            time.sleep(2)
            
    raise RuntimeError("No se pudo descargar el catálogo de gasolineras desde ninguna fuente.")

print("Descargando datos del Ministerio...")
data = descargar_con_reintentos()

lista = data.get("ListaEESSPrecio", [])
print(f"Total estaciones recibidas: {len(lista)}")

records = []
for st in lista:
    lat = parse_coord(st.get("Latitud"))
    lon = parse_coord(st.get("Longitud (WGS84)"))
    
    if not lat or not lon:
        continue

    # Filtrar solo coordenadas válidas en territorio español
    if not (27.0 <= lat <= 44.5 and -19.0 <= lon <= 5.0):
        continue

    g95 = parse_num(st.get("Precio Gasolina 95 E5"))
    g98 = parse_num(st.get("Precio Gasolina 98 E5"))
    die = parse_num(st.get("Precio Gasoleo A"))
    die_p = parse_num(st.get("Precio Gasoleo Premium"))
    glp = parse_num(st.get("Precio Gases licuados del petroleo"))

    if not any([g95, g98, die, die_p, glp]):
        continue

    records.append({
        "id": str(st.get("IDEESS")),
        "rotulo": (st.get("Rótulo") or "GASOLINERA").strip(),
        "direccion": (st.get("Dirección") or "").strip(),
        "localidad": (st.get("Localidad") or "").strip(),
        "municipio": (st.get("Municipio") or "").strip(),
        "provincia": (st.get("Provincia") or "").strip(),
        "horario": (st.get("Horario") or "").strip(),
        "gasolina95": g95,
        "gasolina98": g98,
        "diesel": die,
        "diesel_premium": die_p,
        "glp": glp,
        "latitud": lat,
        "longitud": lon,
        "ubicacion": f"SRID=4326;POINT({lon} {lat})"
    })

print(f"Subiendo {len(records)} gasolineras a Supabase en bloques de 500...")

url_upsert = f"{SUPABASE_URL}/rest/v1/gasolineras?on_conflict=id"
sb_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

chunk_size = 500
for i in range(0, len(records), chunk_size):
    chunk = records[i:i + chunk_size]
    res = requests.post(url_upsert, headers=sb_headers, json=chunk, timeout=60)
    if res.status_code not in (200, 201):
        print(f"Error en bloque {i}: {res.status_code} - {res.text}")
    else:
        print(f"Bloque {i}-{i+len(chunk)} actualizado.")

print("¡Proceso completado con éxito!")
