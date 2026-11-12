import requests
import json
import re
from bs4 import BeautifulSoup
from dedup import extract_agency_ref, generate_fingerprint

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
}

def scrape_subito(search_url):
    """
    Scraper per Subito.it Matera Immobili.
    Estrae gli annunci analizzando sia il JSON __NEXT_DATA__ sia il markup HTML.
    """
    results = []
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[Subito] Errore richiesta HTTP: {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        next_data_script = soup.find("script", id="__NEXT_DATA__")

        if next_data_script:
            data = json.loads(next_data_script.string)
            state = data.get("props", {}).get("pageProps", {}).get("state", {})
            items = state.get("items", {}).get("list", [])

            for item in items:
                ad = item.get("item", {})
                if not ad:
                    continue

                url = ad.get("urls", {}).get("default")
                title = ad.get("subject", "")
                desc = ad.get("body", "")
                full_text = f"{title} {desc}"

                # Estrazione prezzo
                price = 0
                for f in ad.get("features", []):
                    if f.get("uri") == "/price":
                        val = f.get("values", [{}])[0].get("key")
                        try:
                            price = float(val)
                        except:
                            pass

                # Parametri (mq, locali, bagni, piano, ecc.)
                mq = 0
                rooms = 0
                bathrooms = 0
                floor = ""
                floor_num = 0
                has_elevator = None
                has_garage = 0
                has_terrace = 0
                terrace_mq = 0
                has_garden = 0
                garden_mq = 0
                has_balcony = 0
                is_renovated = 0
                is_to_renovate = 0
                is_furnished = 0

                for param in ad.get("parameters", []):
                    label = (param.get("label") or "").lower()
                    val = param.get("value", "")
                    val_lower = str(val).lower()

                    if "superficie" in label or "mq" in label:
                        match = re.search(r'(\d+)', str(val))
                        if match:
                            mq = float(match.group(1))
                    elif "locali" in label or "stanze" in label:
                        match = re.search(r'(\d+)', str(val))
                        if match:
                            rooms = int(match.group(1))
                    elif "bagni" in label:
                        match = re.search(r'(\d+)', str(val))
                        if match:
                            bathrooms = int(match.group(1))
                    elif "piano" in label:
                        floor = val
                        num_m = re.search(r'(\d+)', str(val))
                        if num_m:
                            floor_num = int(num_m.group(1))
                    elif "ascensore" in label:
                        has_elevator = (val_lower == "sì" or val_lower == "si" or "presente" in val_lower)
                    elif "garage" in label or "box" in label or "posto auto" in label:
                        has_garage = 1 if (val_lower == "sì" or val_lower == "si") else 0
                    elif "stato" in label:
                        if "ristrutturato" in val_lower or "ottimo" in val_lower or "nuovo" in val_lower:
                            is_renovated = 1
                        elif "da ristrutturare" in val_lower or "buono" in val_lower:
                            is_to_renovate = 1 if "da ristrutturare" in val_lower else 0

                # Analisi euristica dal testo della descrizione
                if not bathrooms:
                    b_match = re.search(r'(\d+)\s*(?:bagni|bagno|servizi)', full_text, re.IGNORECASE)
                    if b_match:
                        bathrooms = int(b_match.group(1))
                    elif "doppio servizio" in full_text or "doppi servizi" in full_text or "due bagni" in full_text:
                        bathrooms = 2

                if not mq:
                    mq_match = re.search(r'(\d{2,3})\s*(?:mq|metri quadri|m²)', full_text, re.IGNORECASE)
                    if mq_match:
                        mq = float(mq_match.group(1))

                # Riconoscimento terrazza e giardino con mq
                t_match = re.search(r'terrazz[oa]\s*(?:di|da)?\s*(\d{2,3})\s*mq', full_text, re.IGNORECASE)
                if t_match:
                    has_terrace = 1
                    terrace_mq = float(t_match.group(1))
                elif "terrazzo" in full_text or "terrazza" in full_text:
                    has_terrace = 1

                g_match = re.search(r'giardino\s*(?:di|da)?\s*(\d{2,3})\s*mq', full_text, re.IGNORECASE)
                if g_match:
                    has_garden = 1
                    garden_mq = float(g_match.group(1))
                elif "giardino" in full_text:
                    has_garden = 1

                if "balcone" in full_text or "balconi" in full_text:
                    has_balcony = 1

                if "garage" in full_text or "box auto" in full_text or "posto auto" in full_text:
                    has_garage = 1

                if has_elevator is None:
                    if "con ascensore" in full_text or "servito da ascensore" in full_text:
                        has_elevator = True
                    elif "senza ascensore" in full_text or "no ascensore" in full_text:
                        has_elevator = False

                if "arredato" in full_text or "ammobiliato" in full_text:
                    is_furnished = 1

                # Immagine di copertina
                images = ad.get("images", [])
                img_url = images[0].get("cdn_base_url") if images else ""

                # Zona dal portale
                geo = ad.get("geo", {})
                portal_zone = geo.get("town", {}).get("value", "")

                agency_ref = extract_agency_ref(full_text)
                fingerprint = generate_fingerprint(price, mq, floor_num or floor, portal_zone, bathrooms)

                results.append({
                    "external_id": str(ad.get("urn", "")),
                    "url": url,
                    "title": title,
                    "description": desc,
                    "price": price,
                    "mq": mq,
                    "rooms": rooms,
                    "bedrooms": max(rooms - 2, 0) if rooms >= 3 else 0, # stima camere da vani totali se non esplicitata
                    "bathrooms": bathrooms,
                    "floor": floor,
                    "floor_number": floor_num,
                    "has_elevator": has_elevator,
                    "has_terrace": has_terrace,
                    "terrace_mq": terrace_mq,
                    "has_garden": has_garden,
                    "garden_mq": garden_mq,
                    "has_balcony": has_balcony,
                    "has_garage": has_garage,
                    "is_renovated": is_renovated,
                    "is_to_renovate": is_to_renovate,
                    "is_furnished": is_furnished,
                    "zone_name": portal_zone,
                    "image_url": img_url,
                    "agency_ref": agency_ref,
                    "fingerprint": fingerprint
                })

    except Exception as e:
        print(f"[Subito Scraper Error] {e}")

    return results

