import os, uuid, json
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import requests
# from dotenv import load_dotenv
import psycopg2

# load_dotenv()

app = Flask(__name__)
CORS(app)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def initialize_supabase_table():
    try:
        conn = psycopg2.connect(os.getenv("DB_CONNECTION_STRING"))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS destinatii (
                id TEXT PRIMARY KEY,
                oras TEXT,
                oras_afisat TEXT,
                tara TEXT,
                lat FLOAT8,
                lon FLOAT8,
                vreme JSONB,
                obiective JSONB,
                restaurante JSONB,
                vreme_favorabila BOOLEAN,
                nota_utilizator TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS locatii_custom (
                id TEXT PRIMARY KEY,
                nume TEXT,
                lat FLOAT8,
                lon FLOAT8
            );
        """)
        conn.commit()
        print("Tabelele sunt pregătite.")
    except Exception as e:
        print(f"Eroare la inițializare: {e}")
    finally:
        if conn:
            conn.close()


def get_coordinates(city):
    url = f"http://api.positionstack.com/v1/forward?access_key={os.getenv('POSITIONSTACK_KEY')}&query={city}"
    r = requests.get(url).json()
    if r.get("data"):
        d = r["data"][0]
        return d["latitude"], d["longitude"], d.get("country", "")
    return None, None, None


def get_weather(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    r = requests.get(url).json()
    return r.get("current_weather", {})


def get_places(lat, lon):
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=geosearch&gscoord={lat}%7C{lon}&gsradius=10000&gslimit=5&format=json"
    r = requests.get(url).json()
    return [{"nume": p["title"], "lat": p["lat"], "lon": p["lon"]} for p in r.get("query", {}).get("geosearch", [])]


def get_restaurants(lat, lon):
    headers = {"Authorization": os.getenv("FOURSQUARE_KEY")}
    url = f"https://api.foursquare.com/v3/places/search?ll={lat},{lon}&radius=10000&categories=13065&limit=5"
    r = requests.get(url, headers=headers).json()
    return [
        {
            "nume": x["name"],
            "lat": x["geocodes"]["main"]["latitude"],
            "lon": x["geocodes"]["main"]["longitude"]
        }
        for x in r.get("results", [])
    ]


@app.route("/destinatii", methods=["GET"])
def get_destinatii():
    data = supabase.table("destinatii").select("*").execute()
    return jsonify(data.data), 200


@app.route("/destinatii/<string:dest_id>", methods=["GET"])
def get_dest(dest_id):
    data = supabase.table("destinatii").select("*").eq("id", dest_id).execute()
    if not data.data:
        return jsonify({"error": "Destinație inexistentă"}), 404
    return jsonify(data.data[0]), 200


@app.route("/destinatii/<string:dest_id>/<string:tip>/<int:index>", methods=["GET"])
def get_item(dest_id, tip, index):
    data = supabase.table("destinatii").select("*").eq("id", dest_id).execute()
    if not data.data:
        return jsonify({"error": "Destinație inexistentă"}), 404
    items = data.data[0].get(tip, [])
    if index >= len(items):
        return jsonify({"error": "Index invalid"}), 404
    return jsonify({"item": items[index]}), 200


@app.route("/destinatii", methods=["POST"])
def add_dest():
    data = request.get_json()
    city = data.get("oras")
    if not city:
        return jsonify({"error": "Orașul este necesar"}), 400

    lat, lon, tara = get_coordinates(city)
    if lat is None:
        return jsonify({"error": "Locația nu a putut fi găsită"}), 404

    vreme = get_weather(lat, lon)
    obiective = get_places(lat, lon)
    restaurante = get_restaurants(lat, lon)
    favorabil = 15 <= vreme.get("temperature", 0) <= 30 and vreme.get("windspeed", 0) < 30

    item = {
        "id": f"{city.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}",
        "oras": city,
        "oras_afisat": city,
        "tara": tara,
        "lat": lat,
        "lon": lon,
        "vreme": vreme,
        "obiective": obiective,
        "restaurante": restaurante,
        "vreme_favorabila": favorabil,
        "nota_utilizator": ""
    }
    supabase.table("destinatii").insert(item).execute()
    return jsonify(item), 201


@app.route("/destinatii/<string:dest_id>", methods=["PUT"])
def update_dest(dest_id):
    data = request.get_json()
    update_fields = {}
    if "oras_afisat" in data:
        d = supabase.table("destinatii").select("*").eq("id", dest_id).execute()
        if not d.data:
            return jsonify({"error": "Destinație inexistentă"}), 404
        original = d.data[0]["oras"]
        update_fields["oras_afisat"] = f"{data['oras_afisat']} ({original})"

    for field in ["nota_utilizator", "obiective", "restaurante"]:
        if field in data:
            update_fields[field] = data[field]

    supabase.table("destinatii").update(update_fields).eq("id", dest_id).execute()
    return jsonify({"message": "Actualizat"}), 200


@app.route("/destinatii/<string:dest_id>/<string:tip>/<int:index>", methods=["DELETE"])
def delete_item(dest_id, tip, index):
    d = supabase.table("destinatii").select("*").eq("id", dest_id).execute()
    if not d.data:
        return jsonify({"error": "Destinație inexistentă"}), 404
    lst = d.data[0].get(tip, [])
    if index >= len(lst):
        return jsonify({"error": "Index invalid"}), 404
    lst.pop(index)
    supabase.table("destinatii").update({tip: lst}).eq("id", dest_id).execute()
    return jsonify({"message": "Șters"}), 200


@app.route("/destinatii/<string:dest_id>", methods=["DELETE"])
def delete_dest(dest_id):
    supabase.table("destinatii").delete().eq("id", dest_id).execute()
    return jsonify({"message": "Șters"}), 200


@app.route("/locatii-custom", methods=["GET"])
def get_custom():
    data = supabase.table("locatii_custom").select("*").execute()
    return jsonify(data.data), 200


@app.route("/locatii-custom/<string:cid>", methods=["GET"])
def get_custom_item(cid):
    data = supabase.table("locatii_custom").select("*").eq("id", cid).execute()
    if not data.data:
        return jsonify({"error": "Inexistent"}), 404
    return jsonify(data.data[0]), 200


@app.route("/locatii-custom", methods=["POST"])
def add_custom():
    data = request.get_json()
    if not all(k in data for k in ("nume", "lat", "lon")):
        return jsonify({"error": "Date incomplete"}), 400
    item = {"id": uuid.uuid4().hex, **data}
    supabase.table("locatii_custom").insert(item).execute()
    return jsonify(item), 201


@app.route("/locatii-custom/<string:cid>", methods=["PUT"])
def update_custom(cid):
    data = request.get_json()
    supabase.table("locatii_custom").update(data).eq("id", cid).execute()
    return jsonify({"message": "Actualizat"}), 200


@app.route("/locatii-custom/<string:cid>", methods=["DELETE"])
def delete_custom(cid):
    supabase.table("locatii_custom").delete().eq("id", cid).execute()
    return jsonify({"message": "Șters"}), 200


if __name__ == "__main__":
    initialize_supabase_table()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
