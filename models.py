from extensions import db

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True)
    location = db.Column(db.String(150))
    password = db.Column(db.String(150))

class TripSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    destination = db.Column(db.String(150))
    culture = db.Column(db.String(100))
    budget = db.Column(db.String(50))
    trip_type = db.Column(db.String(50))
    description = db.Column(db.Text)

# -------------------------------------------------------------------
# SOS SERVICES (Hospitals, Police, Fire Stations)
# -------------------------------------------------------------------
def get_nearby_sos_services(lat, lon, radius=3000):
    """
    Get nearby hospitals, police, and fire stations using Overpass API (OpenStreetMap data)
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["amenity"="hospital"](around:{radius},{lat},{lon});
      node["amenity"="police"](around:{radius},{lat},{lon});
      node["amenity"="fire_station"](around:{radius},{lat},{lon});
    );
    out center;
    """

    response = requests.get(overpass_url, params={'data': query})
    data = response.json()

    results = []
    for element in data.get("elements", []):
        name = element["tags"].get("name", "Unnamed")
        amenity = element["tags"].get("amenity", "Unknown")
        lat = element["lat"]
        lon = element["lon"]
        results.append({
            "name": name,
            "type": amenity,
            "latitude": lat,
            "longitude": lon
        })

    return results

