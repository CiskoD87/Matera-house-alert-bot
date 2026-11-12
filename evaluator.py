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

    return "Zona Matera (Non specificata)", 0

def evaluate_listing(item):
    """
    Valuta un immobile con il sistema di Near-Match (Parametri Mancanti):
    - 0 parametri mancanti -> PRIMA_SCELTA (🌟 Match Perfetto 9/9)
    - 1 parametro mancante  -> QUASI_PERFETTO (🟠 Rispetta 8 su 9)
    - 2 parametri mancanti  -> VALUTABILE (🟡 Rispetta 7 su 9)
    - >= 3 mancanti o filtri sicurezza violati -> SCARTATO
    """
    rules = get_rules()
    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    full_text = f"{title} {desc}"

    # ==========================================
    # 1. FILTRI DI SICUREZZA ASSOLUTI (Hard Exclusions)
    # ==========================================
    # Se fallisce uno di questi, l'annuncio viene cestinato subito (nessun near-match)
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

    # Escludi annunci palesemente non residenziali (es. negozi, locali commerciali, uffici, capannoni)
    if any(k in title for k in ["locale commerciale", "ufficio", "capannone", "negozio", "deposito", "terreno agricolo"]):
        return "SCARTATO", 0, ["Non residenziale (commerciale/ufficio/terreno)"], None, 0

    # ==========================================
    # 2. CONTEGGIO DEI 9 PARAMETRI DESIDERATI
    # ==========================================
    missing_params = []
    satisfied_count = 0
    total_params = 9

    # Parametro 1: ZONA & TIER
    zone_name, tier = detect_zone(full_text, item.get("zone_name", ""))
    item["zone_name"] = zone_name
    item["tier"] = tier

    if tier in [1, 2, 3]:
        satisfied_count += 1
    else:
        missing_params.append(f"Zona: '{zone_name}' (attualmente fuori dai tuoi Tier 1, 2 o 3)")

    # Parametro 2: PREZZO
    price = item.get("price") or 0
    price_min = rules.get("price_min", 200000)
    price_max = rules.get("price_max", 350000)
    price_max_renovate = rules.get("price_max_to_renovate", 250000)
    is_to_renovate = item.get("is_to_renovate", 0) or ("da ristrutturare" in full_text)
    mq = item.get("mq") or 0

    # Scarto immediato solo se prezzo assurdo (< 80k o > 550k)
    if price > 0 and (price < 80000 or price > 550000):
        return "SCARTATO", 0, [f"Prezzo fuori scala ({price:,.0f} €)"], zone_name, tier

    if price_min <= price <= price_max:
        if is_to_renovate and price > price_max_renovate and not (tier == 1 and mq >= 125):
            missing_params.append(f"Prezzo da ristrutturare: {price:,.0f} € (superiore al limite di {price_max_renovate:,.0f} €)")
        else:
            satisfied_count += 1
    else:
        if price < price_min:
            missing_params.append(f"Prezzo: {price:,.0f} € (inferiore al minimo di {price_min:,.0f} €)")
        else:
            missing_params.append(f"Prezzo: {price:,.0f} € (superiore al massimo di {price_max:,.0f} €)")

    # Parametro 3: SUPERFICIE (Mq)
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

    # Parametro 4: CAMERE DA LETTO / LOCALI
    bedrooms = item.get("bedrooms") or 0
    rooms = item.get("rooms") or 0
    if bedrooms >= 3 or rooms >= 4:
        satisfied_count += 1
    else:
        cam_desc = f"{bedrooms} camere" if bedrooms > 0 else (f"{rooms} vani" if rooms > 0 else "non specificate")
        missing_params.append(f"Camere da letto: {cam_desc} (richieste 3 camere / min 4 vani)")

    # Parametro 5: BAGNI
    bathrooms = item.get("bathrooms") or 0
    if bathrooms >= 2:
        satisfied_count += 1
    else:
        missing_params.append(f"Bagni: {bathrooms if bathrooms > 0 else 'non specificati'} (richiesti almeno 2 bagni)")

    # Parametro 6: ASCENSORE
    has_elevator = item.get("has_elevator")
    floor_num = item.get("floor_number", 0)
    if re.search(r'\b(?:senza|no|privo di)\s+ascensore\b', full_text):
        has_elevator = False
    elif has_elevator is None and re.search(r'\b(?:con|servito da|dotato di)\s+ascensore\b', full_text):
        has_elevator = True

    if has_elevator is True:
        satisfied_count += 1
    elif floor_num == 1 and not re.search(r'\b(?:senza|no)\s+ascensore\b', full_text):
        # Al 1° piano l'assenza può essere tollerata come piccolo warning
        satisfied_count += 1
    else:
        missing_params.append("Ascensore: Assente o non confermato")

    # Parametro 7: PIANO
    floor_str = (item.get("floor") or "").lower()
    is_ground = "terra" in floor_str or "seminterrato" in floor_str or "piano t" in full_text
    is_raised = "rialzato" in floor_str or "piano rialzato" in full_text
    has_garden = item.get("has_garden", 0) or ("giardino" in full_text)
    garden_mq = item.get("garden_mq") or 0

    if is_ground:
        missing_params.append("Piano: Piano terra / Seminterrato")
    elif is_raised:
        if has_garden and (garden_mq >= 25 or garden_mq == 0):
            satisfied_count += 1
        else:
            missing_params.append("Piano: Piano rialzato sprovvisto di giardino >= 25 mq")
    else:
        satisfied_count += 1

    # Parametro 8: SPAZI APERTI (Terrazzo >= 25 mq o Giardino >= 25 mq o Balconi Abitabili)
    has_terrace = item.get("has_terrace", 0) or ("terrazz" in full_text)
    terrace_mq = item.get("terrace_mq") or 0
    has_balcony = item.get("has_balcony", 0) or ("balcon" in full_text)

    large_terrace = has_terrace and (terrace_mq >= 25 or terrace_mq == 0)
    large_garden = has_garden and (garden_mq >= 25 or garden_mq == 0)

    if large_terrace or large_garden:
        satisfied_count += 1
    elif has_balcony:
        missing_params.append("Spazio Aperto: Solo balconi standard (manca terrazzo o giardino >= 25 mq)")
    else:
        missing_params.append("Spazio Aperto: Nessun terrazzo, giardino o balcone specificato")

    # Parametro 9: GARAGE / POSTO AUTO
    has_garage = item.get("has_garage", 0)
    if re.search(r'\b(?:senza|no|privo di)\s+(?:garage|box|posto auto)\b', full_text):
        has_garage = 0
    elif not has_garage and re.search(r'\b(?:con|dotato di|compreso|incluso)?\s*(?:garage|box auto|posto auto)\b', full_text):
        has_garage = 1

    if has_garage:
        satisfied_count += 1
    else:
        if tier == 1:
            missing_params.append("Garage/Posto Auto: Assente (imprescindibile in Tier 1)")
        else:
            missing_params.append("Garage/Posto Auto: Non presente o non specificato")

    # ==========================================
    # 3. CLASSIFICAZIONE FINALE
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
