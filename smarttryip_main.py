import certifi
from flask import Flask, render_template, request, jsonify
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

response = requests.get("https://test.api.amadeus.com", verify=certifi.where())
print(response.status_code)


def get_access_token():
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("AMADEUS_API_KEY"),
        "client_secret": os.getenv("AMADEUS_API_SECRET")
    }

    response = requests.post(url, data=payload, verify=certifi.where())
    response.raise_for_status()  # wirft Fehler bei HTTP 4xx/5xx
    return response.json()["access_token"]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/search", methods=["POST"])
def search():
    origin = request.form["origin"]
    destination = request.form["destination"]
    date = request.form["date"]
    token = get_access_token()

    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": origin,
        "destinationLocationCode": destination,
        "departureDate": date,
        "adults": 1,
        "max": 5
    }

    response = requests.get(url, headers=headers, params=params)
    return jsonify(response.json())

if __name__ == "__main__":
    app.run(debug=True)
