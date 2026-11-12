import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dedup import extract_agency_ref, generate_fingerprint

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def scrape_agency_site(agency_name, base_url):
    """
    Parser versatile per siti di agenzie immobiliari locali di Matera.
    Estrae le schede immobile identificando i pattern comuni dei gestionali immobiliari.
    """
    results = []
    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        # Cerca contenitori di annunci comuni
        cards = soup.select(".immobile, .property, .card-immobile, .annuncio, .listing, article, .item-immobile")
        if not cards:
            # Fallback generico: cerca blocchi contenenti il simbolo € e mq
            cards = [elem for elem in soup.find_all(["div", "article", "li"]) if "€" in elem.text and ("mq" in elem.text.lower() or "m²" in elem.text.lower())]

        seen_links = set()
        for card in cards:
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue

            url = urljoin(base_url, link_tag["href"])
            if url in seen_links or url == base_url or len(url) < 15:
                continue
            seen_links.add(url)

            text = card.get_text(separator=" ", strip=True)
            text_lower = text.lower()

            # Estrazione prezzo
            price_match = re.search(r'(?:€|euro)\s*([0-9]{1,3}(?:\.[0-9]{3})*)', text, re.IGNORECASE)
            if not price_match:
                price_match = re.search(r'([0-9]{1,3}(?:\.[0-9]{3})*)\s*(?:€|euro)', text, re.IGNORECASE)
            
            price = 0
            if price_match:
                price = float(price_match.group(1).replace(".", ""))

            # Filtro rapido: solo immobili nel range o con prezzo da verificare
            if price > 0 and (price < 180000 or price > 400000):
                continue

            # Mq
            mq_match = re.search(r'(\d{2,3})\s*(?:mq|m²)', text_lower)
            mq = float(mq_match.group(1)) if mq_match else 0

            # Vani / Camere
            rooms_match = re.search(r'(\d+)\s*(?:locali|vani|camere)', text_lower)
            rooms = int(rooms_match.group(1)) if rooms_match else 0

            # Bagni
            bath_match = re.search(r'(\d+)\s*(?:bagni|bagno|servizi)', text_lower)
            bathrooms = int(bath_match.group(1)) if bath_match else (2 if "doppi servizi" in text_lower else 0)

            # Immagine
            img_tag = card.find("img")
            img_url = ""
            if img_tag:
                img_url = img_tag.get("src") or img_tag.get("data-src") or ""
                img_url = urljoin(base_url, img_url)

            # Titolo
            title_tag = card.find(["h2", "h3", "h4", "strong"])
            title = title_tag.get_text(strip=True) if title_tag else f"Immobile {agency_name}"

            agency_ref = extract_agency_ref(text)
            fingerprint = generate_fingerprint(price, mq, "", agency_name, bathrooms)

            results.append({
                "external_id": f"{agency_name}_{len(results)}",
                "url": url,
                "title": f"[{agency_name}] {title}",
                "description": text[:800],
                "price": price,
                "mq": mq,
                "rooms": rooms,
                "bedrooms": max(rooms - 2, 0) if rooms >= 3 else 0,
                "bathrooms": bathrooms,
                "floor": "",
                "floor_number": 0,
                "has_elevator": True if "ascensore" in text_lower and "senza" not in text_lower else None,
                "has_terrace": 1 if "terrazz" in text_lower else 0,
                "terrace_mq": 0,
                "has_garden": 1 if "giardin" in text_lower else 0,
                "garden_mq": 0,
                "has_balcony": 1 if "balcon" in text_lower else 0,
                "has_garage": 1 if "garage" in text_lower or "box" in text_lower or "posto auto" in text_lower else 0,
                "is_renovated": 1 if "ristrutturato" in text_lower else 0,
                "is_to_renovate": 1 if "da ristrutturare" in text_lower else 0,
                "is_furnished": 1 if "arredato" in text_lower else 0,
                "zone_name": agency_name,
                "image_url": img_url,
                "agency_ref": agency_ref,
                "fingerprint": fingerprint
            })
    except Exception as e:
        print(f"[{agency_name} Scraper Error] {e}")

    return results

