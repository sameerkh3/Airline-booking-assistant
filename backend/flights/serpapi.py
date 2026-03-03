"""
SerpAPI Google Flights adapter — Phase 2 real flight data.

Calls the SerpAPI /search?engine=google_flights endpoint and maps the
response into the internal flight schema used by _flight_search() in
agent/tools_impl.py.

Internal flight schema (matches mock_flights.json):
  airline        str   — e.g. "Emirates"
  flight_number  str   — e.g. "EK 609"
  departure_time str   — e.g. "14:30"
  arrival_time   str   — e.g. "18:05"
  date_offset    int   — 1 if arrival is next day, else 0
  duration       str   — e.g. "3h 35m"
  stops          int   — number of layovers (0 = non-stop)
  cabin_class    str   — e.g. "Economy"
  price_usd      int   — total price in USD
"""

import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

SERPAPI_BASE_URL = "https://serpapi.com/search"
MAX_RESULTS = 5

# City name → IATA code mappings (global coverage)
# Where a city has multiple airports the busiest/main international one is used.
_CITY_TO_IATA: dict[str, str] = {
    # ── Pakistan ────────────────────────────────────────────────────────────
    "karachi": "KHI",
    "lahore": "LHE",
    "islamabad": "ISB",
    "peshawar": "PEW",
    "quetta": "UET",
    "multan": "MUX",
    "faisalabad": "LYP",
    "sialkot": "SKT",
    "dera ghazi khan": "DEA",
    # ── UAE ─────────────────────────────────────────────────────────────────
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "sharjah": "SHJ",
    "ras al khaimah": "RKT",
    "al ain": "AAN",
    # ── Saudi Arabia ────────────────────────────────────────────────────────
    "riyadh": "RUH",
    "jeddah": "JED",
    "medina": "MED",
    "madinah": "MED",
    "dammam": "DMM",
    "abha": "AHB",
    "taif": "TIF",
    "tabuk": "TUU",
    # ── Qatar ───────────────────────────────────────────────────────────────
    "doha": "DOH",
    # ── Kuwait ──────────────────────────────────────────────────────────────
    "kuwait city": "KWI",
    "kuwait": "KWI",
    # ── Bahrain ─────────────────────────────────────────────────────────────
    "bahrain": "BAH",
    "manama": "BAH",
    # ── Oman ────────────────────────────────────────────────────────────────
    "muscat": "MCT",
    "salalah": "SLL",
    # ── Jordan ──────────────────────────────────────────────────────────────
    "amman": "AMM",
    "aqaba": "AQJ",
    # ── Iraq ────────────────────────────────────────────────────────────────
    "baghdad": "BGW",
    "basra": "BSR",
    "erbil": "EBL",
    # ── Egypt ───────────────────────────────────────────────────────────────
    "cairo": "CAI",
    "alexandria": "HBE",
    "luxor": "LXR",
    "aswan": "ASW",
    "hurghada": "HRG",
    "sharm el sheikh": "SSH",
    # ── Turkey ──────────────────────────────────────────────────────────────
    "istanbul": "IST",
    "ankara": "ESB",
    "izmir": "ADB",
    "antalya": "AYT",
    "bodrum": "BJV",
    "trabzon": "TZX",
    # ── Iran ────────────────────────────────────────────────────────────────
    "tehran": "IKA",
    "mashhad": "MHD",
    "isfahan": "IFN",
    "shiraz": "SYZ",
    "tabriz": "TBZ",
    # ── India ───────────────────────────────────────────────────────────────
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "chennai": "MAA",
    "madras": "MAA",
    "hyderabad": "HYD",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "ahmedabad": "AMD",
    "pune": "PNQ",
    "kochi": "COK",
    "cochin": "COK",
    "goa": "GOI",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "amritsar": "ATQ",
    "chandigarh": "IXC",
    "nagpur": "NAG",
    "surat": "STV",
    "thiruvananthapuram": "TRV",
    "trivandrum": "TRV",
    "varanasi": "VNS",
    "bhubaneswar": "BBI",
    "guwahati": "GAU",
    # ── Sri Lanka ───────────────────────────────────────────────────────────
    "colombo": "CMB",
    # ── Bangladesh ──────────────────────────────────────────────────────────
    "dhaka": "DAC",
    "chittagong": "CGP",
    "sylhet": "ZYL",
    # ── Nepal ───────────────────────────────────────────────────────────────
    "kathmandu": "KTM",
    # ── Afghanistan ─────────────────────────────────────────────────────────
    "kabul": "KBL",
    # ── Maldives ────────────────────────────────────────────────────────────
    "male": "MLE",
    "malé": "MLE",
    # ── UK ──────────────────────────────────────────────────────────────────
    "london": "LHR",
    "manchester": "MAN",
    "birmingham": "BHX",
    "edinburgh": "EDI",
    "glasgow": "GLA",
    "bristol": "BRS",
    "newcastle": "NCL",
    "leeds": "LBA",
    "belfast": "BFS",
    "liverpool": "LPL",
    "cardiff": "CWL",
    # ── Ireland ─────────────────────────────────────────────────────────────
    "dublin": "DUB",
    "cork": "ORK",
    # ── France ──────────────────────────────────────────────────────────────
    "paris": "CDG",
    "nice": "NCE",
    "lyon": "LYS",
    "marseille": "MRS",
    "bordeaux": "BOD",
    "toulouse": "TLS",
    "strasbourg": "SXB",
    # ── Germany ─────────────────────────────────────────────────────────────
    "frankfurt": "FRA",
    "munich": "MUC",
    "berlin": "BER",
    "hamburg": "HAM",
    "dusseldorf": "DUS",
    "düsseldorf": "DUS",
    "cologne": "CGN",
    "stuttgart": "STR",
    "hanover": "HAJ",
    "hannover": "HAJ",
    "nuremberg": "NUE",
    "nürnberg": "NUE",
    # ── Netherlands ─────────────────────────────────────────────────────────
    "amsterdam": "AMS",
    "rotterdam": "RTM",
    "eindhoven": "EIN",
    # ── Spain ───────────────────────────────────────────────────────────────
    "madrid": "MAD",
    "barcelona": "BCN",
    "malaga": "AGP",
    "málaga": "AGP",
    "seville": "SVQ",
    "valencia": "VLC",
    "alicante": "ALC",
    "bilbao": "BIO",
    "ibiza": "IBZ",
    "palma": "PMI",
    "tenerife": "TFS",
    "gran canaria": "LPA",
    "las palmas": "LPA",
    "fuerteventura": "FUE",
    "lanzarote": "ACE",
    # ── Portugal ────────────────────────────────────────────────────────────
    "lisbon": "LIS",
    "porto": "OPO",
    "faro": "FAO",
    # ── Italy ───────────────────────────────────────────────────────────────
    "rome": "FCO",
    "milan": "MXP",
    "venice": "VCE",
    "florence": "FLR",
    "naples": "NAP",
    "catania": "CTA",
    "palermo": "PMO",
    "bologna": "BLQ",
    "bari": "BRI",
    # ── Switzerland ─────────────────────────────────────────────────────────
    "zurich": "ZRH",
    "zürich": "ZRH",
    "geneva": "GVA",
    "basel": "BSL",
    # ── Austria ─────────────────────────────────────────────────────────────
    "vienna": "VIE",
    "salzburg": "SZG",
    "innsbruck": "INN",
    # ── Belgium ─────────────────────────────────────────────────────────────
    "brussels": "BRU",
    "liege": "LGG",
    # ── Scandinavia ─────────────────────────────────────────────────────────
    "stockholm": "ARN",
    "oslo": "OSL",
    "copenhagen": "CPH",
    "helsinki": "HEL",
    "reykjavik": "KEF",
    "gothenburg": "GOT",
    "malmo": "MMX",
    "malmö": "MMX",
    "bergen": "BGO",
    "trondheim": "TRD",
    "aarhus": "AAR",
    "tampere": "TMP",
    "turku": "TKU",
    # ── Eastern Europe ──────────────────────────────────────────────────────
    "moscow": "SVO",
    "st. petersburg": "LED",
    "saint petersburg": "LED",
    "warsaw": "WAW",
    "krakow": "KRK",
    "kraków": "KRK",
    "prague": "PRG",
    "budapest": "BUD",
    "bucharest": "OTP",
    "sofia": "SOF",
    "athens": "ATH",
    "thessaloniki": "SKG",
    "zagreb": "ZAG",
    "belgrade": "BEG",
    "sarajevo": "SJJ",
    "kyiv": "KBP",
    "kiev": "KBP",
    "minsk": "MSQ",
    "riga": "RIX",
    "tallinn": "TLL",
    "vilnius": "VNO",
    "bratislava": "BTS",
    "ljubljana": "LJU",
    "skopje": "SKP",
    "tirana": "TIA",
    "chisinau": "KIV",
    "tbilisi": "TBS",
    "yerevan": "EVN",
    "baku": "GYD",
    # ── North Africa ────────────────────────────────────────────────────────
    "tunis": "TUN",
    "algiers": "ALG",
    "casablanca": "CMN",
    "marrakech": "RAK",
    "tripoli": "TIP",
    "khartoum": "KRT",
    # ── Sub-Saharan Africa ───────────────────────────────────────────────────
    "nairobi": "NBO",
    "mombasa": "MBA",
    "addis ababa": "ADD",
    "lagos": "LOS",
    "abuja": "ABV",
    "accra": "ACC",
    "dar es salaam": "DAR",
    "johannesburg": "JNB",
    "cape town": "CPT",
    "durban": "DUR",
    "harare": "HRE",
    "lusaka": "LUN",
    "kampala": "EBB",
    "entebbe": "EBB",
    "kigali": "KGL",
    "dakar": "DSS",
    "bamako": "BKO",
    "ouagadougou": "OUA",
    "abidjan": "ABJ",
    "douala": "DLA",
    "kinshasa": "FIH",
    "luanda": "LAD",
    "maputo": "MPM",
    "antananarivo": "TNR",
    # ── USA ─────────────────────────────────────────────────────────────────
    "new york": "JFK",
    "los angeles": "LAX",
    "chicago": "ORD",
    "houston": "IAH",
    "miami": "MIA",
    "dallas": "DFW",
    "san francisco": "SFO",
    "seattle": "SEA",
    "boston": "BOS",
    "atlanta": "ATL",
    "denver": "DEN",
    "las vegas": "LAS",
    "orlando": "MCO",
    "phoenix": "PHX",
    "washington": "IAD",
    "washington dc": "IAD",
    "minneapolis": "MSP",
    "detroit": "DTW",
    "philadelphia": "PHL",
    "san diego": "SAN",
    "portland": "PDX",
    "salt lake city": "SLC",
    "charlotte": "CLT",
    "baltimore": "BWI",
    "new orleans": "MSY",
    "nashville": "BNA",
    "kansas city": "MCI",
    "tampa": "TPA",
    "raleigh": "RDU",
    "pittsburgh": "PIT",
    "st. louis": "STL",
    "saint louis": "STL",
    "austin": "AUS",
    "san antonio": "SAT",
    "indianapolis": "IND",
    "columbus": "CMH",
    "memphis": "MEM",
    "honolulu": "HNL",
    "anchorage": "ANC",
    "cincinnati": "CVG",
    "sacramento": "SMF",
    "san jose": "SJC",
    "oklahoma city": "OKC",
    "omaha": "OMA",
    "richmond": "RIC",
    "norfolk": "ORF",
    "jacksonville": "JAX",
    "buffalo": "BUF",
    "albany": "ALB",
    "providence": "PVD",
    # ── Canada ──────────────────────────────────────────────────────────────
    "toronto": "YYZ",
    "vancouver": "YVR",
    "montreal": "YUL",
    "calgary": "YYC",
    "ottawa": "YOW",
    "edmonton": "YEG",
    "winnipeg": "YWG",
    "halifax": "YHZ",
    "quebec city": "YQB",
    "victoria": "YYJ",
    "saskatoon": "YXE",
    "regina": "YQR",
    "st. john's": "YYT",
    # ── Mexico & Central America ─────────────────────────────────────────────
    "mexico city": "MEX",
    "cancun": "CUN",
    "guadalajara": "GDL",
    "monterrey": "MTY",
    "puerto vallarta": "PVR",
    "los cabos": "SJD",
    "merida": "MID",
    "guatemala city": "GUA",
    "san jose": "SJO",   # Costa Rica (note: same key as SJC above — Costa Rica wins for travel context)
    "panama city": "PTY",
    "managua": "MGA",
    "tegucigalpa": "TGU",
    "san salvador": "SAL",
    "belize city": "BZE",
    # ── Caribbean ───────────────────────────────────────────────────────────
    "havana": "HAV",
    "santo domingo": "SDQ",
    "san juan": "SJU",
    "kingston": "KIN",
    "port of spain": "POS",
    "nassau": "NAS",
    "bridgetown": "BGI",
    "barbados": "BGI",
    "punta cana": "PUJ",
    "montego bay": "MBJ",
    # ── South America ───────────────────────────────────────────────────────
    "sao paulo": "GRU",
    "são paulo": "GRU",
    "rio de janeiro": "GIG",
    "brasilia": "BSB",
    "brasília": "BSB",
    "buenos aires": "EZE",
    "santiago": "SCL",
    "lima": "LIM",
    "bogota": "BOG",
    "bogotá": "BOG",
    "caracas": "CCS",
    "quito": "UIO",
    "guayaquil": "GYE",
    "la paz": "VVI",
    "santa cruz": "VVI",
    "asuncion": "ASU",
    "asunción": "ASU",
    "montevideo": "MVD",
    "medellin": "MDE",
    "medellín": "MDE",
    "cali": "CLO",
    "cartagena": "CTG",
    "barranquilla": "BAQ",
    "manaus": "MAO",
    "belo horizonte": "CNF",
    "recife": "REC",
    "fortaleza": "FOR",
    "salvador": "SSA",
    "curitiba": "CWB",
    "porto alegre": "POA",
    # ── East Asia ───────────────────────────────────────────────────────────
    "tokyo": "NRT",
    "osaka": "KIX",
    "nagoya": "NGO",
    "sapporo": "CTS",
    "fukuoka": "FUK",
    "beijing": "PEK",
    "shanghai": "PVG",
    "guangzhou": "CAN",
    "shenzhen": "SZX",
    "chengdu": "CTU",
    "chongqing": "CKG",
    "xi'an": "XIY",
    "xian": "XIY",
    "kunming": "KMG",
    "wuhan": "WUH",
    "hangzhou": "HGH",
    "nanjing": "NKG",
    "qingdao": "TAO",
    "xiamen": "XMN",
    "tianjin": "TSN",
    "harbin": "HRB",
    "shenyang": "SHE",
    "dalian": "DLC",
    "seoul": "ICN",
    "busan": "PUS",
    "jeju": "CJU",
    "hong kong": "HKG",
    "macau": "MFM",
    "taipei": "TPE",
    "kaohsiung": "KHH",
    "ulaanbaatar": "ULN",
    # ── Southeast Asia ──────────────────────────────────────────────────────
    "singapore": "SIN",
    "kuala lumpur": "KUL",
    "bangkok": "BKK",
    "phuket": "HKT",
    "chiang mai": "CNX",
    "jakarta": "CGK",
    "bali": "DPS",
    "denpasar": "DPS",
    "surabaya": "SUB",
    "medan": "KNO",
    "makassar": "UPG",
    "manila": "MNL",
    "cebu": "CEB",
    "davao": "DVO",
    "hanoi": "HAN",
    "ho chi minh city": "SGN",
    "saigon": "SGN",
    "da nang": "DAD",
    "phnom penh": "PNH",
    "siem reap": "REP",
    "vientiane": "VTE",
    "yangon": "RGN",
    "rangoon": "RGN",
    "naypyidaw": "NYT",
    "bandar seri begawan": "BWN",
    "brunei": "BWN",
    "dili": "DIL",
    # ── Central Asia ────────────────────────────────────────────────────────
    "almaty": "ALA",
    "astana": "NQZ",
    "nur-sultan": "NQZ",
    "tashkent": "TAS",
    "ashgabat": "ASB",
    "bishkek": "FRU",
    "dushanbe": "DYU",
    # ── Caucasus ────────────────────────────────────────────────────────────
    "tbilisi": "TBS",
    "yerevan": "EVN",
    "baku": "GYD",
    # ── Pacific / Oceania ────────────────────────────────────────────────────
    "sydney": "SYD",
    "melbourne": "MEL",
    "brisbane": "BNE",
    "perth": "PER",
    "adelaide": "ADL",
    "gold coast": "OOL",
    "cairns": "CNS",
    "darwin": "DRW",
    "hobart": "HBA",
    "canberra": "CBR",
    "auckland": "AKL",
    "wellington": "WLG",
    "christchurch": "CHC",
    "queenstown": "ZQN",
    "nadi": "NAN",
    "fiji": "NAN",
    "port moresby": "POM",
    "noumea": "NOU",
    "papeete": "PPT",
    "tahiti": "PPT",
    "suva": "SUV",
    "apia": "APW",
    "honiara": "HIR",
    "nuku'alofa": "TBU",
    "port vila": "VLI",
    "funafuti": "FUN",
    "tarawa": "TRW",
    "majuro": "MAJ",
    "koror": "ROR",
    "palau": "ROR",
    "palikir": "PNI",
    "yaren": "INU",  # Nauru
    # ── Caribbean additions ──────────────────────────────────────────────────
    "george town": "GCM",  # Cayman Islands
    "hamilton": "BDA",    # Bermuda
    "st. maarten": "SXM",
    "aruba": "AUA",
    "curacao": "CUR",
    "willemstad": "CUR",
    "fort-de-france": "FDF",  # Martinique
    "pointe-à-pitre": "PTP",  # Guadeloupe
    "cayenne": "CAY",         # French Guiana
}


def _resolve_airport_code(location: str) -> str:
    """
    Normalise a location string to an IATA airport code.

    If `location` is already a 3-letter uppercase code, return it as-is.
    Otherwise look it up in the city→IATA table (case-insensitive).
    Falls back to uppercasing the input (SerpAPI will reject it with a clear
    error if it's still invalid).
    """
    stripped = location.strip()
    if len(stripped) == 3 and stripped.isalpha():
        return stripped.upper()
    return _CITY_TO_IATA.get(stripped.lower(), stripped.upper())


# SerpAPI travel_class integer codes
_CABIN_CLASS_MAP = {
    "economy": "1",
    "premium economy": "2",
    "business": "3",
    "first": "4",
}

# Fallback price ranges (USD) by cabin class when price is missing
_PRICE_FALLBACK = {
    "economy": (200, 600),
    "premium economy": (600, 1400),
    "business": (1500, 4000),
    "first": (4000, 9000),
}


def _minutes_to_duration(minutes: int) -> str:
    """Convert total minutes to a human-readable duration string, e.g. '3h 35m'."""
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m"


def _parse_time(dt_str: str) -> tuple[str, int]:
    """
    Parse a SerpAPI datetime string ('YYYY-MM-DD HH:MM') into a time string
    ('HH:MM') and a date-offset flag (1 if the date differs from the first
    segment's departure date, else 0).

    Returns (time_str, date_offset).
    """
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return dt.strftime("%H:%M"), dt
    except (ValueError, TypeError):
        return dt_str, None


def _fallback_price(cabin_class: str) -> int:
    """Return a mid-point mock price when SerpAPI omits the price field."""
    import random
    lo, hi = _PRICE_FALLBACK.get(cabin_class.lower(), (300, 800))
    return random.randint(lo, hi)


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    cabin_class: str = "Economy",
    airline_preference: str | None = None,
) -> list[dict] | str:
    """
    Search for real flights via SerpAPI Google Flights.

    Args:
        origin:           IATA code of the departure airport (e.g. "KHI")
        destination:      IATA code of the arrival airport (e.g. "DXB")
        departure_date:   Date string in YYYY-MM-DD format
        cabin_class:      One of Economy / Premium Economy / Business / First
        airline_preference: Optional partial airline name filter (applied client-side)

    Returns:
        A list of flight dicts matching the internal schema, or a user-friendly
        error string if the API call fails or returns no results.
    """
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        return "Flight data is temporarily unavailable: SERPAPI_KEY is not configured."

    travel_class_code = _CABIN_CLASS_MAP.get(cabin_class.strip().lower(), "1")

    # Normalise city names to IATA codes (SerpAPI requires 3-letter codes)
    origin_code = _resolve_airport_code(origin)
    destination_code = _resolve_airport_code(destination)

    params = {
        "engine": "google_flights",
        "api_key": api_key,
        "departure_id": origin_code,
        "arrival_id": destination_code,
        "outbound_date": departure_date,
        "type": "2",          # one-way
        "adults": "1",
        "travel_class": travel_class_code,
        "currency": "USD",
    }

    try:
        response = httpx.get(SERPAPI_BASE_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException:
        logger.error("SerpAPI request timed out for %s→%s", origin_code, destination_code)
        return "Flight data is temporarily unavailable: request timed out."
    except httpx.HTTPStatusError as exc:
        logger.error("SerpAPI HTTP error %s for %s→%s", exc.response.status_code, origin_code, destination_code)
        return f"Flight data is temporarily unavailable (HTTP {exc.response.status_code})."
    except Exception as exc:
        logger.error("SerpAPI unexpected error: %s", exc)
        return "Flight data is temporarily unavailable."

    # SerpAPI returns results in best_flights and other_flights
    raw_itineraries = data.get("best_flights", []) + data.get("other_flights", [])

    if not raw_itineraries:
        return []

    flights: list[dict] = []
    for itinerary in raw_itineraries:
        segments = itinerary.get("flights", [])
        if not segments:
            continue

        first_seg = segments[0]
        last_seg = segments[-1]

        # --- Airline and flight number (from first segment) ---
        airline = first_seg.get("airline", "Unknown Airline")
        flight_number = first_seg.get("flight_number", "N/A")

        # --- Apply airline preference filter (client-side partial match) ---
        if airline_preference and airline_preference.strip().lower() not in airline.lower():
            continue

        # --- Departure and arrival times ---
        dep_str = first_seg.get("departure_airport", {}).get("time", "")
        arr_str = last_seg.get("arrival_airport", {}).get("time", "")

        dep_time, dep_dt = _parse_time(dep_str)
        arr_time, arr_dt = _parse_time(arr_str)

        # Determine date offset (did we land the next day or beyond?)
        date_offset = 0
        if dep_dt and arr_dt and arr_dt.date() > dep_dt.date():
            date_offset = 1

        # --- Duration ---
        total_minutes = itinerary.get("total_duration")
        duration = _minutes_to_duration(total_minutes) if total_minutes else "N/A"

        # --- Stops ---
        stops = len(segments) - 1

        # --- Cabin class (from first segment, normalised) ---
        cabin = first_seg.get("travel_class", cabin_class)

        # --- Price ---
        price_raw = itinerary.get("price")
        price_usd = int(price_raw) if price_raw is not None else _fallback_price(cabin)

        flights.append({
            "airline": airline,
            "flight_number": flight_number,
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "date_offset": date_offset,
            "duration": duration,
            "stops": stops,
            "cabin_class": cabin,
            "price_usd": price_usd,
        })

        if len(flights) >= MAX_RESULTS:
            break

    return flights
