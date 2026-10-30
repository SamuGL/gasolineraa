import os
import sys
import time
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Faltan las variables de entorno de Supabase.")
    sys.exit(1)

# Códigos oficiales de todas las CCAA y Ciudades Autónomas de España
IDS_CCAA = [
    "01", "02", "03", "04", "05", "06", "07", "08", "09", 
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def parse_num(val):
    if not val:
        return None
    try:
        return float(val.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None

def parse_coord(val):
    if not val:
        return None
    try:
        return float(val.replace(",", "."))
    except (ValueError, AttributeError):
        return None

session = requests.Session()
session.headers.update(HEADERS)

todas_las_estaciones = []

print("Descargando gasolineras por Comunidades Autónomas...")
for ccaa in IDS_CCAA:
    url = f"https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/FiltroCCAA/{ccaa}"
    exito = False
    
    for intento in range(3):
        try:
            res = session.get(url, timeout=20)
            if res.status_code == 200:
                data = res.json()
                lista = data.get("ListaEESSPrecio", [])
                todas_las_estaciones.extend(lista)
                print(f"  ✓ CCAA {ccaa}: {len(lista)} estaciones obtenidas.")
                exito = True
                break
        except Exception as e:
            time.sleep(1.5)
            
    if not exito:
        print(f"  ⚠ Aviso: No se pudo obtener la CCAA {ccaa} tras varios intentos.")
    
    time.sleep(0.3)

print(f"\nTotal gasolineras recopiladas: {len(todas_las_estaciones)}")

records = []
vistos = set()

for st in todas_las_estaciones:
    id_est = str(st.get("IDEESS"))
    if id_est in vistos:
        continue
    vistos.add(id_est)

    lat = parse_coord(st.get("Latitud"))
    lon = parse_coord(st.get("Longitud (WGS84)"))
    if not lat or not lon:
        continue

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
        "id": id_est,
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

print(f"\nSubiendo {len(records)} gasolineras a Supabase en paquetes de 500...")

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
    res = session.post(url_upsert, headers=sb_headers, json=chunk, timeout=60)
    if res.status_code not in (200, 201):
        print(f"Error en bloque {i}: {res.status_code} - {res.text}")
    else:
        print(f"Bloque {i} a {i+len(chunk)} guardado con éxito.")

print("\n¡Base de datos completamente actualizada!")
