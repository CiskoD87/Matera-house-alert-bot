import requests
import json
import re
from bs4 import BeautifulSoup
from dedup import extract_agency_ref, generate_fingerprint

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.google.it/"
}

def scrape_immobiliare(search_url):
    """
    Scraper per Immobiliare.it Matera.
    Estrae gli annunci analizzando lo stato strutturato o le card dell'elenco.
    """
    results = []
    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[Immobiliare] HTTP Status: {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        next_data_script = soup.find("script", id="__NEXT_DATA__")

        if next_data_script:
            data = json.loads(next_data_script.string)
            props = data.get("props", {}).get("pageProps", {})
            real_estates = props.get("dehydratedState", {}).get("queries", [{}])[0].get("state", {}).get("data", {}).get("results", [])
            if not real_estates:
                real_estates = props.get("results", [])

            for re_item in real_estates:
                item = re_item.get("realEstate", re_item)
                if not item:
                    continue

                ad_id = str(item.get("id", ""))
                ad_url = item.get("seo", {}).get("url") or item.get("canonicalUrl")
                if not ad_url:
                    continue

                title = item.get("title", "")
                price = item.get("price", {}).get("value", 0)
                properties = item.get("properties", [{}])[0]

                desc = properties.get("description", "")
                full_text = f"{title} {desc}"

                mq = properties.get("surfaceValue", 0)
                rooms = properties.get("rooms", 0)
                bed = properties.get("bedRooms", 0)
                bath = properties.get("bathrooms", 0)
                floor = properties.get("floor", {}).get("value", "")
                has_elev = properties.get("hasElevator")

                # Features / Spazi
                has_terr = 1 if "terrazz" in full_text.lower() else 0
                has_gard = 1 if "giardin" in full_text.lower() else 0
                has_balc = 1 if "balcon" in full_text.lower() else 0
                has_gar = 1 if properties.get("gaType") or "garage" in full_text.lower() or "posto auto" in full_text.lower() else 0

                # Immagine
                photos = properties.get("photos", [])
                img_url = photos[0].get("urls", {}).get("medium") if photos else ""

                zone_str = properties.get("location", {}).get("macrozone", "") or properties.get("location", {}).get("microzone", "")

                agency_ref = extract_agency_ref(full_text)
                fingerprint = generate_fingerprint(price, mq, floor, zone_str, bath)

                results.append({
                    "external_id": ad_id,
                    "url": ad_url,
                    "title": title,
                    "description": desc,
                    "price": float(price or 0),
                    "mq": float(mq or 0),
                    "rooms": int(rooms or 0),
                    "bedrooms": int(bed or 0),
                    "bathrooms": int(bath or 0),
                    "floor": str(floor),
                    "floor_number": int(re.search(r'\d+', str(floor)).group()) if re.search(r'\d+', str(floor)) else 0,
                    "has_elevator": has_elev,
                    "has_terrace": has_terr,
                    "terrace_mq": 0,
                    "has_garden": has_gard,
                    "garden_mq": 0,
                    "has_balcony": has_balc,
                    "has_garage": has_gar,
                    "is_renovated": 1 if "ristrutturato" in full_text.lower() else 0,
                    "is_to_renovate": 1 if "da ristrutturare" in full_text.lower() else 0,
                    "is_furnished": 1 if "arredato" in full_text.lower() else 0,
                    "zone_name": zone_str,
                    "image_url": img_url,
                    "agency_ref": agency_ref,
                    "fingerprint": fingerprint
                })

    except Exception as e:
        print(f"[Immobiliare Scraper Error] {e}")

    return results

