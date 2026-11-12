import re
import hashlib
from database import find_duplicate, record_duplicate

def extract_agency_ref(text):
    """Estrae codici di riferimento annuncio tipici delle agenzie (es. Rif. MT-102, Cod. 4501)."""
    if not text:
        return None
    patterns = [
        r'(?:rif|riferimento|cod|codice)[\.\:\s]+([a-zA-Z0-9\-\_\/]+)',
        r'\b(mt[\-\_\s]?[0-9]{2,6})\b',
        r'\b(rif[\-\_\s]?[0-9]{3,6})\b'
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            ref = m.group(1).strip().upper()
            if len(ref) >= 3 and not ref.isdigit() or (ref.isdigit() and len(ref) >= 4):
                return ref
    return None

def generate_fingerprint(price, mq, floor, zone_name, bathrooms=2):
    """
    Crea un'impronta normalizzata dell'immobile per intercettare lo stesso annuncio
    pubblicato su siti diversi con testi o foto leggermente differenti.
    """
    # Prezzo arrotondato a scaglioni di 5.000 €
    norm_price = round((price or 0) / 5000) * 5000 if price else 0
    # Mq arrotondati a scaglioni di 5 mq
    norm_mq = round((mq or 0) / 5) * 5 if mq else 0
    # Normalizza piano
    norm_floor = str(floor or "").lower().strip()
    # Normalizza zona
    norm_zone = str(zone_name or "").lower().strip()

    raw_signature = f"{norm_price}_{norm_mq}_{norm_floor}_{norm_zone}_{bathrooms}"
    return hashlib.md5(raw_signature.encode('utf-8')).hexdigest()

def check_and_deduplicate(listing_data, source_name):
    """
    Verifica se l'annuncio è un duplicato.
    Restituisce (is_duplicate, primary_listing, match_type).
    """
    agency_ref = listing_data.get("agency_ref")
    fingerprint = listing_data.get("fingerprint")

    duplicate_match = find_duplicate(fingerprint=fingerprint, agency_ref=agency_ref)
    if duplicate_match:
        primary_listing, match_type = duplicate_match
        # Registra il nuovo URL associandolo all'annuncio originale
        record_duplicate(
            primary_id=primary_listing["id"],
            duplicate_url=listing_data["url"],
            source_name=source_name,
            match_type=match_type
        )
        return True, primary_listing, match_type

    return False, None, None

