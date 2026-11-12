import re
from database import get_rules, get_zones

def detect_zone(text_to_search, portal_zone=""):
    """
    Riconosce la zona e il Tier analizzando il testo dell'annuncio e la zona del portale.
    Restituisce (nome_zona, tier).
    """
    zones = get_zones()
    search_corpus = f"{portal_zone} {text_to_search}".lower()

    # Cerca prima corrispondenze esatte con gli alias (priorità a Tier 1, poi Tier 2, poi Tier 3)
    # Ordiniamo prima per Tier crescente (1 prima di 2, ecc.)
    sorted_zones = sorted(zones, key=lambda z: (z["tier"] == 0, z["tier"]))

    for z in sorted_zones:
        for alias in z["aliases"]:
            # Usiamo regex con word boundary per evitare falsi positivi
            pattern = r'\b' + re.escape(alias.lower()) + r'\b'
            if re.search(pattern, search_corpus):
                return z["name"], z["tier"]

    # Se non trova corrispondenze specifiche ma è a Matera, zona sconosciuta/non censita
    return "Zona non specificata / Altra", 0

def evaluate_listing(item):
    """
    Valuta un immobile estratto rispetto alle regole attive.
    Restituisce:
    - category: 'PRIMA_SCELTA', 'SECONDA_SCELTA', 'SCARTATO'
    - score: punteggio numerico (0-100)
    - reason: motivo dell'eventuale scarto o note di classificazione
    - detected_zone: nome quartiere
    - tier: tier quartiere
    """
    rules = get_rules()
    reasons = []

    title = (item.get("title") or "").lower()
    desc = (item.get("description") or "").lower()
    full_text = f"{title} {desc}"

    # 1. Filtro Sicurezza: Aste, Nuda Proprietà, Affitti
    auction_keywords = ["asta", "giudiziaria", "tribunale fallimentare", "esecutivo", "custode"]
    if rules.get("exclude_auctions", True):
        for kw in auction_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', full_text):
                return "SCARTATO", 0, f"Asta giudiziaria ({kw})", None, 0

    if rules.get("exclude_bare_ownership", True):
        if "nuda proprietà" in full_text or "nuda proprieta" in full_text or "usufrutto" in full_text:
            return "SCARTATO", 0, "Nuda proprietà / Usufrutto", None, 0

    if rules.get("exclude_rent", True):
        rent_keywords = ["affittasi", "in affitto", "canone mensile", "locazione transitoria", "rent to buy"]
        for kw in rent_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', title):
                return "SCARTATO", 0, "Annuncio di affitto/locazione", None, 0

    # 2. Riconoscimento Zona e Tier
    zone_name, tier = detect_zone(full_text, item.get("zone_name", ""))
    item["zone_name"] = zone_name
    item["tier"] = tier

    if tier == 0:
        return "SCARTATO", 0, f"Zona esclusa o non idonea ({zone_name})", zone_name, tier

    # 3. Filtro Prezzo
    price = item.get("price") or 0
    price_min = rules.get("price_min", 200000)
    price_max = rules.get("price_max", 350000)
    price_max_renovate = rules.get("price_max_to_renovate", 250000)

    is_to_renovate = item.get("is_to_renovate", 0) or ("da ristrutturare" in full_text)
    mq = item.get("mq") or 0

    if price < price_min:
        return "SCARTATO", 0, f"Prezzo inferiore al minimo ({price:,.0f} € < {price_min:,.0f} €)", zone_name, tier
    if price > price_max:
        return "SCARTATO", 0, f"Prezzo superiore al massimo ({price:,.0f} € > {price_max:,.0f} €)", zone_name, tier

    # Regola speciale: da ristrutturare max 250.000 € (salvo eccezione: straordinariamente grande in Tier 1)
    if is_to_renovate and price > price_max_renovate:
        is_extraordinary = (tier == 1 and mq >= 125)
        if not is_extraordinary:
            return "SCARTATO", 0, f"Da ristrutturare ma con prezzo troppo alto ({price:,.0f} € > {price_max_renovate:,.0f} €)", zone_name, tier

    # 4. Filtro Superficie (Mq)
    mq_min = rules.get("mq_min", 95)
    mq_max = rules.get("mq_max", 130)
    if mq > 0:
        if mq < mq_min:
            return "SCARTATO", 0, f"Superficie insufficiente ({mq} mq < {mq_min} mq)", zone_name, tier
        if mq > mq_max:
            return "SCARTATO", 0, f"Superficie eccessiva ({mq} mq > {mq_max} mq)", zone_name, tier

    # 5. Filtro Camere da letto / Locali
    # Desiderio utente: 3 camere (esclusi cucina, soggiorno, ripostigli)
    bedrooms = item.get("bedrooms") or 0
    rooms = item.get("rooms") or 0
    if bedrooms > 0 and bedrooms < rules.get("bedrooms_min", 3):
        return "SCARTATO", 0, f"Camere da letto insufficienti ({bedrooms} < 3)", zone_name, tier
    elif bedrooms == 0 and rooms > 0 and rooms < 4:
        # Se non specifica camere, ma ha meno di 4 vani totali (es. bilocale/trilocale)
        return "SCARTATO", 0, f"Numero locali insufficiente ({rooms} vani, minimo 4)", zone_name, tier

    # 6. Filtro Bagni (minimo 2)
    bathrooms = item.get("bathrooms") or 0
    if bathrooms > 0 and bathrooms < rules.get("bathrooms_min", 2):
        return "SCARTATO", 0, f"Numero bagni insufficiente ({bathrooms} < 2)", zone_name, tier

    # 7. Filtro Ascensore (IMPRESCINDIBILE)
    has_elevator = item.get("has_elevator")
    floor_num = item.get("floor_number", 0)
    
    # Rileva assenza esplicita o presenza di ascensore nel testo
    if re.search(r'\b(?:senza|no|privo di)\s+ascensore\b', full_text):
        has_elevator = False
    elif has_elevator is None and re.search(r'\b(?:con|servito da|dotato di)\s+ascensore\b', full_text):
        has_elevator = True

    if rules.get("elevator_required", True) and has_elevator is False:
        return "SCARTATO", 0, "Assenza di ascensore (imprescindibile)", zone_name, tier

    # 8. Filtro Piani
    # Escludere Piano terra e Seminterrato
    floor_str = (item.get("floor") or "").lower()
    if "seminterrato" in floor_str or "seminterrato" in full_text or "piano s1" in full_text:
        return "SCARTATO", 0, "Seminterrato escluso", zone_name, tier
    if "piano terra" in floor_str or "terra" in floor_str or "piano t" in full_text:
        return "SCARTATO", 0, "Piano terra escluso", zone_name, tier

    # Piani rialzati o 1° piano: ammessi SOLO se hanno giardino >= 25mq
    has_garden = item.get("has_garden", 0)
    if not has_garden and re.search(r'\b(?:con|dotato di|ampio)?\s*giardino\b', full_text) and not re.search(r'\b(?:senza|no)\s+giardino\b', full_text):
        has_garden = 1
    garden_mq = item.get("garden_mq") or 0

    is_raised_floor = "rialzato" in floor_str or "piano rialzato" in full_text
    is_first_floor = floor_num == 1 or "primo piano" in floor_str or "1° piano" in full_text

    # Se piano rialzato senza giardino degno -> scarta
    if is_raised_floor:
        if not has_garden or (garden_mq > 0 and garden_mq < rules.get("garden_min_mq", 25)):
            return "SCARTATO", 0, "Piano rialzato senza giardino adeguato (min 25 mq)", zone_name, tier

    # 9. Garage / Posto Auto
    has_garage = item.get("has_garage", 0)
    # Se presente nel testo ma con negazione (es. "senza garage")
    if re.search(r'\b(?:senza|no|privo di)\s+(?:garage|box|posto auto)\b', full_text):
        has_garage = 0
    elif not has_garage and re.search(r'\b(?:con|dotato di|compreso|incluso)?\s*(?:garage|box auto|posto auto)\b', full_text):
        has_garage = 1

    if tier == 1 and rules.get("garage_required_tier1", True):
        if not has_garage:
            return "SCARTATO", 0, "Tier 1: Garage o Posto auto assente (imprescindibile in Tier 1)", zone_name, tier

    # 10. Terrazzo, Giardino e Balconi Abitabili
    has_terrace = item.get("has_terrace", 0)
    if re.search(r'\b(?:senza|no)\s+terrazz', full_text):
        has_terrace = 0
    elif not has_terrace and re.search(r'\bterrazz', full_text):
        has_terrace = 1
    terrace_mq = item.get("terrace_mq") or 0
    has_balcony = item.get("has_balcony", 0) or ("balcon" in full_text)
    has_big_balcony = "balcone abitabile" in full_text or "ampi balconi" in full_text or "grandi balconi" in full_text

    # Verifica condizione Prima Scelta vs Seconda Scelta
    # Prima Scelta richiede Terrazzo >= 25 mq OPPURE Giardino >= 25 mq (e piano non rialzato)
    has_large_terrace = has_terrace and (terrace_mq >= rules.get("terrace_min_mq", 25) or terrace_mq == 0)
    has_large_garden = has_garden and (garden_mq >= rules.get("garden_min_mq", 25) or garden_mq == 0)

    category = "SECONDA_SCELTA"
    score = 60.0

    # Calcolo Score e Categoria
    if (has_large_terrace or has_large_garden) and not is_raised_floor:
        category = "PRIMA_SCELTA"
        score = 85.0
    elif has_big_balcony or has_balcony or is_raised_floor:
        category = "SECONDA_SCELTA"
        score = 65.0
    else:
        # Nessun terrazzo, nessun giardino, nessun balcone
        return "SCARTATO", 0, "Spazi aperti assenti (nessun terrazzo, giardino o balcone)", zone_name, tier

    # Bonus Punteggio
    if tier == 1:
        score += 15.0
    elif tier == 2:
        score += 8.0

    if has_garage:
        score += 5.0

    if has_large_terrace:
        score += 5.0

    # Penalità lieve se piano rialzato (anche con giardino)
    if is_raised_floor:
        category = "SECONDA_SCELTA"
        score -= 10.0
        reasons.append("Piano rialzato con giardino (un gradino sotto attici/piani alti)")

    if is_to_renovate:
        score -= 5.0
        reasons.append("Da ristrutturare (prezzo idoneo)")

    return category, min(score, 100.0), "; ".join(reasons) if reasons else "Idoneo", zone_name, tier
