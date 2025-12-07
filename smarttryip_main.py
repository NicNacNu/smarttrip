from flask import Flask, render_template, request, send_file
import requests
import os
from dotenv import load_dotenv
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4 

load_dotenv()

app = Flask(__name__)

# Access Token holen
def get_access_token():
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": os.getenv("AMADEUS_API_KEY"),
        "client_secret": os.getenv("AMADEUS_API_SECRET")
    }
    response = requests.post(url, data=payload)
    return response.json()["access_token"]

@app.route("/", methods=["GET"])
def index():
    action = ''
    action = request.form.get("action")
    match action:
        case "flight":
            # Flugsuche ausführen
            return flight_list()
        case "hotel":
            # Hotelsuche ausführen
            return hotel_list()
        case _:
            return render_template(
            "index.html",
            flights=[],
            hotels=[],
            angebote_pro_hotel={},
            search_done=False
        )


def price():
    import json

    flight_offer_raw = request.form.get("flight_offer")
    adults = int(request.form.get("adults", 1))
    bags = int(request.form.get("bags", 1))

    flight_offer = json.loads(flight_offer_raw)

    # Ergänze fareDetailsBySegment für jeden Reisenden
    traveler_pricings = []
    for i in range(adults):
        fare_details = []
        for itinerary in flight_offer.get("itineraries", []):
            for segment in itinerary.get("segments", []):
                fare_details.append({
                    "segmentId": segment["id"],
                    "cabin": "ECONOMY",
                    "fareBasis": "Y",
                    "class": "Y",
                    "includedCheckedBags": {
                        "quantity": bags
                    }
                })
        traveler_pricings.append({
            "travelerId": str(i + 1),
            "fareOption": "STANDARD",
            "travelerType": "ADULT",
            "fareDetailsBySegment": fare_details
        })

    flight_offer["travelerPricings"] = traveler_pricings

    # Anfrage an Pricing-API
    token = get_access_token()
    url = "https://test.api.amadeus.com/v1/shopping/flight-offers/pricing"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "data": {
            "type": "flight-offers-pricing",
            "flightOffers": [flight_offer]
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    pricing_data = response.json()

    return render_template("price.html", pricing=pricing_data)

def get_city_iata_code(city_name):
    token = get_access_token()
    url = "https://test.api.amadeus.com/v1/reference-data/locations/cities"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"keyword": city_name, "max": 1}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]["iataCode"]
    else:
        return None

def fetch_hotel_offers(hotels, anzahl, checkIn, checkOut, raumAnzahl):
    token = get_access_token()
    url = "https://test.api.amadeus.com/v3/shopping/hotel-offers"
    headers = {"Authorization": f"Bearer {token}"}
    hotel_ids = [hotel["hotelId"] for hotel in hotels][:20]
    params = {
        "hotelIds": hotel_ids,
        "adults": anzahl,
        "checkInDate": checkIn,
        "checkOutDate": checkOut,
        "roomQuantity": raumAnzahl,
        "currency": "EUR",
        "lang": "de-DE",
        "bestRateOnly": "false"
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])

@app.route("/hotel_list", methods=["GET"])
def hotel_list():
    city_name = request.args.get("hotelCity")
    radius = request.args.get("radius")
    rating = request.args.get("rating", 5)
    anzahl = request.args.get("hotelGuests", 1)
    checkIn = request.args.get("hotelCheckIn")
    checkOut = request.args.get("hotelCheckOut")
    raumAnzahl = request.args.get("hotelRoom", 1)

    
    if not city_name:
        city_code = get_city_iata_code("Berlin")
    else:
        city_code = get_city_iata_code(city_name)
        

    token = get_access_token()
    url = "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"cityCode": city_code, "radius": radius, "ratings": rating}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    hotels_all = data.get("data", [])

    hotelsOffer = fetch_hotel_offers(hotels_all, anzahl, checkIn, checkOut, raumAnzahl)

    # Angebote nach Hotel-ID gruppieren
    angebote_pro_hotel = {}
    for offer in hotelsOffer:
        hotel_id = offer['hotel']['hotelId']
        angebote_pro_hotel.setdefault(hotel_id, []).append(offer)
    
    # Nur Hotels mit mindestens einem Zimmerangebot behalten
    hotels_mit_zimmer = []
    for hotel in hotels_all:
        hotel_id = hotel["hotelId"]
        angebote = angebote_pro_hotel.get(hotel_id, [])
        if any(o.get("offers") for o in angebote):
            hotels_mit_zimmer.append(hotel)

    return render_template(
        "index.html",
        flights=[],  # keine Flüge hier
        hotels=hotels_mit_zimmer,
        angebote_pro_hotel=angebote_pro_hotel,
        search_done=True
    )

@app.route("/flight_list", methods=["GET"])
def flight_list():
    flights = []
    search_done = False

    if request.method == "GET":
        search_done = True
        origin = get_city_iata_code(request.args.get("origin"))
        destination = get_city_iata_code(request.args.get("destination"))
        departure_date = request.args.get("departureDate")
        return_date = request.args.get("returnDate")
        one_way = request.args.get("oneWay")

        try:
            token = get_access_token()
            url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": departure_date,
                "adults": 1,
                "max": 5
            }
            if not one_way and return_date:
                params["returnDate"] = return_date

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            flights = data.get("data", [])

        except Exception as e:
            print("Fehler bei der API-Abfrage:", e)

    return render_template(
        "index.html",
        flights=flights,
        hotels=[],
        angebote_pro_hotel={},
        search_done=search_done
    )



@app.post("/download_pdf")
def download_pdf():
    data = request.get_json()

    filename = "reise_details.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    content = []

    def add(title, text):
        content.append(Paragraph(f"<b>{title}</b><br/>{text}<br/><br/>", styles["Normal"]))

    add("Hinflug – Datum", data["hinflug"]["datum"])
    add("Hinflug – Preis", data["hinflug"]["preis"])
    add("Hinflug – Segmente", data["hinflug"]["segmente"])

    add("Rückflug – Datum", data["rueckflug"]["datum"])
    add("Rückflug – Preis", data["rueckflug"]["preis"])
    add("Rückflug – Segmente", data["rueckflug"]["segmente"])

    add("Hotel – Name", data["hotel"]["name"])
    add("Hotel – Adresse", data["hotel"]["adresse"])
    add("Hotel – CheckIn", data["hotel"]["checkin"])
    add("Hotel – CheckOut", data["hotel"]["checkout"])
    add("Hotel – Zimmer", data["hotel"]["zimmer"])
    add("Hotel – Beschreibung", data["hotel"]["beschreibung"])
    add("Hotel – Betten", data["hotel"]["betten"])
    add("Hotel – Preis", data["hotel"]["preis"])
    add("Hotel – Board", data["hotel"]["board"])
    add("Hotel – Storno", data["hotel"]["refund"])

    doc.build(content)

    return send_file(filename, as_attachment=True)



if __name__ == "__main__":
    app.run(debug=True)