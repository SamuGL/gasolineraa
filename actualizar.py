import os
import requests

SUPABASE_URL = os.environ.get("https://ppzjdckokrbegbpoztzk.supabase.co")
SUPABASE_KEY = os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBwempkY2tva3JiZWdicG96dHprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MzMwODMyNCwiZXhwIjoyMTA4ODg0MzI0fQ.SjqgtJmdwqIohbvrzeu2GUmwkRfp6EVylysW2J8MT0A")

API_MINISTERIO = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"

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

print("Descargando datos del Ministerio...")
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(API_MINISTERIO, headers=headers, timeout=60)
data = resp.json()

lista = data.get("ListaEESSPrecio", [])
print(f"Total estaciones recibidas: {len(lista)}")

records = []
for st in lista:
    lat = parse_coord(st.get("Latitud"))
    lon = parse_coord(st.get("Longitud (WGS84)"))
    
    if not lat or not lon:
        continue

    # Solo coordenadas válidas de España
    if not (27.0 <= lat <= 44.0 and -19.0 <= lon <= 5.0):
        continue

    g95 = parse_num(st.get("Precio Gasolina 95 E5"))
    g98 = parse_num(st.get("Precio Gasolina 98 E5"))
    die = parse_num(st.get("Precio Gasoleo A"))
    die_p = parse_num(st.get("Precio Gasoleo Premium"))
    glp = parse_num(st.get("Precio Gases licuados del petroleo"))

    # Omitir si no tiene precios informados
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

print("Actualización completada con éxito.")
