import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import (
    LoginManager,
    login_user,
    login_required,
    logout_user,
    current_user,
    UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from datetime import datetime
from dotenv import load_dotenv
import requests

# -------------------------------------------------------------------
# APP CONFIGURATION
# -------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "your_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///planora.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

# Load environment variables
load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

# -------------------------------------------------------------------
# LOGIN SETUP
# -------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# -------------------------------------------------------------------
# MODELS
# -------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    location = db.Column(db.String(100))
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Trip(db.Model):
    __tablename__ = "trip"
    id = db.Column(db.Integer, primary_key=True)
    destination = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

# -------------------------------------------------------------------
# LOGIN MANAGER
# -------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("home.html", title="Welcome to Planora")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        location = request.form.get("location")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.", "danger")
            return redirect(url_for("login"))

        hashed_pw = generate_password_hash(password, method="pbkdf2:sha256")
        new_user = User(name=name, email=email, location=location, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            flash("Invalid email or password!", "danger")
            return redirect(url_for("login"))

        login_user(user)
        flash("Login successful!", "success")
        return redirect(url_for("dashboard"))
    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)

#------------- Edit Profile -----------------
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.username = request.form.get('username')
        current_user.email = request.form.get('email')
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('home'))
    return render_template('edit_profile.html', user=current_user)

# ---------------- PLAN TRIP (Main Logic) ----------------
@app.route("/plan_trip", methods=["GET", "POST"])
@login_required
def plan_trip():
    if request.method == "POST":
        from_location = request.form.get("from_location")
        destination = request.form.get("destination")
        budget = request.form.get("budget", "medium").lower()
        trip_type = request.form.get("trip_type")
        preferences = request.form.get("preferences")
        trip_days = int(request.form.get("days") or 1)

        # ---------------- Helper functions ----------------
        def safe_get_json(url):
            try:
                res = requests.get(url, headers={"User-Agent": "TripPlannerApp/1.0"}, timeout=10)
                res.raise_for_status()
                return res.json()
            except Exception as e:
                print("⚠️ Error fetching:", url, e)
                return {}

        def get_coords(place):
            url = f"https://nominatim.openstreetmap.org/search?format=json&q={place}"
            try:
                res = requests.get(url, headers={"User-Agent": "TripPlannerApp/1.0"}, timeout=10)
                res.raise_for_status()
                data = res.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
            except Exception as e:
                print("⚠️ Error fetching coords:", place, e)
            return None, None

        from_lat, from_lon = get_coords(from_location)
        dest_lat, dest_lon = get_coords(destination)

        # ---------------- Attractions ----------------
        BUDGET_PLACES = {
            "low": ["park", "market", "museum", "temple", "street food", "public garden"],
            "medium": ["restaurant", "art gallery", "shopping mall", "beach", "zoo", "lake"],
            "high": ["luxury hotel", "fine dining", "private tour", "cruise", "helicopter ride"]
        }

        attractions = []
        if GEOAPIFY_API_KEY and dest_lat and dest_lon:
            url = f"https://api.geoapify.com/v2/places?categories=tourism.attraction&filter=circle:{dest_lon},{dest_lat},8000&limit=20&apiKey={GEOAPIFY_API_KEY}"
            data = safe_get_json(url)
            if "features" in data:
                for f in data["features"]:
                    props = f["properties"]
                    attractions.append({
                        "name": props.get("name", "Unknown Place"),
                        "address": props.get("formatted", "No address"),
                        "lat": f["geometry"]["coordinates"][1],
                        "lon": f["geometry"]["coordinates"][0],
                        "image": None
                    })

        # ---------------- Images ----------------
        if UNSPLASH_ACCESS_KEY:
            for a in attractions:
                q = a["name"].replace(" ", "+")
                img_url = f"https://api.unsplash.com/search/photos?query={q}&per_page=1&client_id={UNSPLASH_ACCESS_KEY}"
                img_data = safe_get_json(img_url)
                if img_data.get("results"):
                    a["image"] = img_data["results"][0]["urls"]["regular"]

        # ---------------- Fallback if empty ----------------
        if not attractions:
            import random
            for place_type in BUDGET_PLACES.get(budget, BUDGET_PLACES["medium"]):
                q = f"{destination} {place_type} travel"
                unsplash_url = f"https://api.unsplash.com/search/photos?query={q}&per_page=1&client_id={UNSPLASH_ACCESS_KEY}"
                img_data = safe_get_json(unsplash_url)
                img = None
                if img_data.get("results"):
                    img = img_data["results"][0]["urls"]["regular"]
                attractions.append({
                    "name": place_type.title(),
                    "address": f"Popular spot for {budget}-budget travelers",
                    "image": img or "/static/placeholder.jpg",
                    "lat": dest_lat,
                    "lon": dest_lon
                })
            random.shuffle(attractions)

        # ---------------- Daily Plan ----------------
        daily_plan = []
        if attractions:
            per_day = max(1, len(attractions) // trip_days)
            for i in range(trip_days):
                start = i * per_day
                end = start + per_day
                selected = attractions[start:end]
                daily_plan.append({
                    "day": f"Day {i+1}",
                    "places": selected,
                    "budget_tip": f"Recommended {budget}-budget itinerary for Day {i+1} (Approx spend: ₹{int(1500 if budget=='low' else 3500 if budget=='medium' else 7000)})"
                })

            #-------Coordinate function-------------

        def get_coordinates(destination):
            """
            Convert a destination name into latitude and longitude
            using the Geoapify Geocoding API.
            """
            api_key = "b62963e3cfcf43a9a7f22ac117efdf36"  # Replace with your key
            
            url = (
                f"https://api.geoapify.com/v1/geocode/search?"
                f"text={destination}&apiKey={api_key}"
            )
            
            response = requests.get(url)
            data = response.json()
            
            if data.get("features"):
                coords = data["features"][0]["geometry"]["coordinates"]
                lon, lat = coords[0], coords[1]
                return lat, lon
            
            # If nothing found
            return None, None
       #----Nearby Services ------------------------

        def get_nearby_emergency_services(lat, lon):
            api_key = "b62963e3cfcf43a9a7f22ac117efdf36"  # your Geoapify key
            url = (
                f"https://api.geoapify.com/v2/places?categories=healthcare.hospital,"
                f"healthcare.clinic,police,fire_station&filter=circle:{lon},{lat},5000&limit=10&apiKey={api_key}"
            )

            try:
                response = requests.get(url)
                data = response.json()
                results = []

                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    name = props.get("name", "Unknown Location")
                    address = props.get("formatted", "No address available")
                    lat_ = feature["geometry"]["coordinates"][1]
                    lon_ = feature["geometry"]["coordinates"][0]
                    place_type = props.get("categories", ["Other"])[0].title()

                    # Try to extract phone number
                    contact = props.get("contact:phone") or props.get("phone")

                    # If contact number is missing, use default helplines based on type
                    if not contact:
                        if "police" in place_type.lower():
                            contact = "Dial 100"
                        elif "hospital" in place_type.lower() or "clinic" in place_type.lower():
                            contact = "Dial 108"
                        elif "fire" in place_type.lower():
                            contact = "Dial 101"
                        else:
                            contact = "Not available"

                    results.append({
                        "type": place_type,
                        "name": name,
                        "address": address,
                        "contact": contact,
                        "latitude": lat_,
                        "longitude": lon_,
                    })

                # ✅ Fallback if nothing found — add at least one default emergency entry
                if not any("Police" in s["type"] for s in results):
                    results.append({
                        "type": "Police Station",
                        "name": "Local Police Helpline",
                        "address": "India",
                        "contact": "Dial 100",
                        "latitude": lat,
                        "longitude": lon
                    })

                if not any("Hospital" in s["type"] for s in results):
                    results.append({
                        "type": "Hospital",
                        "name": "Nearest Medical Emergency",
                        "address": "India",
                        "contact": "Dial 108",
                        "latitude": lat,
                        "longitude": lon
                    })

                return results

            except Exception as e:
                print("Error fetching emergency data:", e)
                return []



        
        destination = request.form["destination"]
        lat, lon = get_coordinates(destination)
           # 🆘 Get emergency services data
        emergency_data = get_nearby_emergency_services(lat, lon) 
        nearby_services = emergency_data 


        # ---------------- Trip Info ----------------
        trip_info = {
            "from": from_location,
            "destination": destination,
            "budget": budget,
            "trip_type": trip_type,
            "preferences": preferences,
            "days": trip_days,
            "lat": dest_lat,
            "lon": dest_lon,
            "from_lat": from_lat,
            "from_lon": from_lon,
            "daily_plan": daily_plan,
            "nearby": nearby_services
        }

        return render_template("plan_result.html", trip_info=trip_info)

    return render_template("plan_trip.html")

# ---------------- GET SOS API ----------------
@app.route("/get_sos", methods=["POST"])
def get_sos():
    data = request.json
    lat = data.get("lat")
    lon = data.get("lon")

    if not lat or not lon:
        return jsonify({"error": "Latitude and longitude are required"}), 400

    def get_nearby_sos_services(lat, lon):
        url = f"https://api.geoapify.com/v2/places?categories=healthcare.hospital,public_service.police&filter=circle:{lon},{lat},5000&limit=10&apiKey={GEOAPIFY_API_KEY}"
        res = requests.get(url)
        data = res.json()
        services = []
        if "features" in data:
            for f in data["features"]:
                props = f["properties"]
                services.append({
                    "name": props.get("name", "Unknown"),
                    "type": props.get("categories", ["Service"])[0].split(".")[-1].title(),
                    "address": props.get("formatted", "No address available"),
                })
        return services

    sos_services = get_nearby_sos_services(lat, lon)
    return jsonify({"services": sos_services})

# -------------------------------------------------------------------
# MAIN
# -------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
