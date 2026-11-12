import re
from database import get_rules, get_zones

def detect_zone(text_to_search, portal_zone=""):
    """
    Riconosce la zona e il Tier analizzando il testo dell'annuncio e la zona del portale.
    Restituisce (nome_zona, tier).
    """
    zones = get_zones()
    search_corpus = f"{portal_zone} {text_to_search}".lower()

    # Ordiniamo prima per Tier crescente (1 prima di 2, poi 3)
    sorted_zones = sorted(zones, key=lambda z: (z["tier"] == 0, z["tier"]))

    for z in sorted_zones:
        for alias in z["aliases"]:
            pattern = r'\b' + re.escape(alias.lower()) + r'\b'
            if re.search(pattern, search_corpus):
                return z["name"], z["tier"]

    # Se menziona Matera o provincia generica ma non il quartiere specifico
    return "Matera (Zona non specificata)", 0

def evaluate_listing(item):
    """
    Valutazione con Sistema Near-Match (Giardino escluso come richiesto):
    Parametri considerati (8 parametri):
    1. Zona (Tier 1, 2 o 3)
    2. Prezzo (200.000 € - 350.000 €; max 250k se da ristrutturare)
    3. Superficie (95 mq - 130 mq)
    4. Camere / Locali (almeno 3 camere da letto / 4 vani)
    5. Bagni (almeno 2 bagni)
    6. Ascensore (presente)
    7. Spazio Aperto (balcone o terrazzo) - Giardino escluso dai requisiti!
    8. Piano (esclusi piano terra e seminterrato; piano rialzato ammesso)
    9. Garage / Posto auto (richiesto in Tier 1, preferibile altrove)
    """
    rules = get_rules()
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    full_text = f"{title} {desc}"

    # ==========================================
    # 1. FILTRI DI SICUREZZA ASSOLUTI (Hard Exclusions)
    # ==========================================
    auction_keywords = ["asta", "giudiziaria", "tribunale fallimentare", "esecutivo", "custode"]
    if rules.get("exclude_auctions", True):
        for kw in auction_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', full_text):
                return "SCARTATO", 0, [f"Asta giudiziaria ({kw})"], None, 0

    if rules.get("exclude_bare_ownership", True):
        if "nuda proprietà" in full_text or "nuda proprieta" in full_text or "usufrutto" in full_text:
            return "SCARTATO", 0, ["Nuda proprietà / Usufrutto"], None, 0

    if rules.get("exclude_rent", True):
        rent_keywords = ["affittasi", "in affitto", "canone mensile", "locazione transitoria", "rent to buy"]
        for kw in rent_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', title):
                return "SCARTATO", 0, ["Annuncio di affitto/locazione"], None, 0

    # Escludi annunci palesemente non residenziali
    if any(k in title for k in ["locale commerciale", "ufficio", "capannone", "negozio", "deposito", "terreno agricolo", "box auto in vendita"]):
        return "SCARTATO", 0, ["Non residenziale (commerciale/ufficio/terreno/solo box)"], None, 0

    missing_params = []
    satisfied_count = 0
    total_params = 8 # 8 parametri essenziali

    # 1. ZONA & TIER
    zone_name, tier = detect_zone(full_text, item.get("zone_name", ""))
    item["zone_name"] = zone_name
    item["tier"] = tier

    if tier in [1, 2, 3]:
        satisfied_count += 1
    else:
        missing_params.append(f"Zona: '{zone_name}' (fuori dai Tier 1, 2 o 3)")

    # 2. PREZZO
    price = item.get("price") or 0
    price_min = rules.get("price_min", 200000)
    price_max = rules.get("price_max", 350000)
    price_max_renovate = rules.get("price_max_to_renovate", 250000)
    is_to_renovate = item.get("is_to_renovate", 0) or ("da ristrutturare" in full_text)
    mq = item.get("mq") or 0

    if price > 0 and (price < 70000 or price > 600000):
        return "SCARTATO", 0, [f"Prezzo totalmente fuori scala ({price:,.0f} €)"], zone_name, tier

    if price_min <= price <= price_max:
        if is_to_renovate and price > price_max_renovate and not (tier == 1 and mq >= 125):
            missing_params.append(f"Prezzo da ristrutturare: {price:,.0f} € (sopra il limite di {price_max_renovate:,.0f} €)")
        else:
            satisfied_count += 1
    else:
        if price < price_min:
            missing_params.append(f"Prezzo: {price:,.0f} € (inferiore al minimo di {price_min:,.0f} €)")
        else:
            missing_params.append(f"Prezzo: {price:,.0f} € (superiore al massimo di {price_max:,.0f} €)")

    # 3. SUPERFICIE (Mq)
    mq_min = rules.get("mq_min", 95)
    mq_max = rules.get("mq_max", 130)
    if mq > 0:
        if mq_min <= mq <= mq_max:
            satisfied_count += 1
        elif mq < mq_min:
            missing_params.append(f"Superficie: {mq:.0f} mq (inferiore a {mq_min} mq)")
        else:
            missing_params.append(f"Superficie: {mq:.0f} mq (superiore a {mq_max} mq)")
    else:
        missing_params.append("Superficie: non specificata")

    # 4. CAMERE DA LETTO / LOCALI
    bedrooms = item.get("bedrooms") or 0
    rooms = item.get("rooms") or 0
    if bedrooms >= 3 or rooms >= 4:
        satisfied_count += 1
    else:
        cam_desc = f"{bedrooms} camere" if bedrooms > 0 else (f"{rooms} vani" if rooms > 0 else "non specificate")
        missing_params.append(f"Camere da letto: {cam_desc} (richieste 3 camere / min 4 vani)")

    # 5. BAGNI
    bathrooms = item.get("bathrooms") or 0
    if bathrooms >= 2:
        satisfied_count += 1
    else:
        missing_params.append(f"Bagni: {bathrooms if bathrooms > 0 else 'non specificati'} (richiesti almeno 2 bagni)")

    # 6. ASCENSORE
    has_elevator = item.get("has_elevator")
    floor_num = item.get("floor_number", 0)
    if re.search(r'\b(?:senza|no|privo di)\s+ascensore\b', full_text):
        has_elevator = False
    elif has_elevator is None and re.search(r'\b(?:con|servito da|dotato di)\s+ascensore\b', full_text):
        has_elevator = True

    if has_elevator is True or (floor_num == 1 and has_elevator is not False):
        satisfied_count += 1
    else:
        missing_params.append("Ascensore: Assente o non specificato")

    # 7. PIANO (Escluso SOLO piano terra e seminterrato; piano rialzato AMMESSO!)
    floor_str = (item.get("floor") or "").lower()
    is_ground = "piano terra" in floor_str or "seminterrato" in floor_str or "piano s1" in full_text
    if is_ground:
        missing_params.append("Piano: Piano terra / Seminterrato escluso")
    else:
        satisfied_count += 1

    # 8. SPAZIO APERTO (Balcone o Terrazzo - GIARDINO NON RICHIESTO)
    has_terrace = item.get("has_terrace", 0) or ("terrazz" in full_text)
    has_balcony = item.get("has_balcony", 0) or ("balcon" in full_text)

    if has_terrace or has_balcony:
        satisfied_count += 1
    else:
        missing_params.append("Spazio Aperto: Nessun balcone o terrazzo specificato")

    # GARAGE / POSTO AUTO (Bonus o filtro condizionale)
    has_garage = item.get("has_garage", 0)
    if re.search(r'\b(?:senza|no|privo di)\s+(?:garage|box|posto auto)\b', full_text):
        has_garage = 0
    elif not has_garage and re.search(r'\b(?:con|dotato di|compreso|incluso)?\s*(?:garage|box auto|posto auto)\b', full_text):
        has_garage = 1

    if tier == 1 and not has_garage:
        missing_params.append("Garage/Posto Auto: Assente (previsto per Tier 1)")

    # ==========================================
    # CLASSIFICAZIONE
    # ==========================================
    score = (satisfied_count / total_params) * 100.0
    miss_count = len(missing_params)

    if miss_count == 0:
        category = "PRIMA_SCELTA"
    elif miss_count == 1:
        category = "QUASI_PERFETTO"
    elif miss_count == 2:
        category = "VALUTABILE"
    else:
        category = "SCARTATO"

    return category, score, missing_params, zone_name, tier
