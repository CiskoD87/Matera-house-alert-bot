import subprocess
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

def fetch_html(url):
    """Tenta prima con requests; se bloccato (403), usa curl di sistema."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass

    # Fallback con curl
    try:
        cmd = [
            "curl", "-s", "-L",
            "-A", HEADERS["User-Agent"],
            "-H", f"Accept: {HEADERS['Accept']}",
            "-H", f"Accept-Language: {HEADERS['Accept-Language']}",
            url
        ]
        out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore", timeout=20)
        if len(out) > 1000:
            return out
    except Exception as e:
        print(f"[Subito fetch_html curl fallback error] {e}")

    return None

def scrape_subito(search_url):
    """
    Scraper per Subito.it Matera Immobili.
    Estrae gli annunci analizzando lo stato strutturato Next.js (__NEXT_DATA__).
    """
    results = []
    html = fetch_html(search_url)
    if not html:
        print("[Subito] Impossibile recuperare l'HTML della pagina di ricerca.")
        return results

    try:
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
        if not m:
            print("[Subito] Tag __NEXT_DATA__ non trovato nell'HTML.")
            return results

        data = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})
        init_state = page_props.get("initialState", {}) or page_props.get("state", {})
        
        # Può trovarsi in originalList oppure list
        items = init_state.get("items", {}).get("originalList", [])
        if not items:
            items = init_state.get("items", {}).get("list", [])

        for it in items:
            ad = it.get("item", it)
            if not ad:
                continue

            # Escludi uffici/negozi/commerciali/terreni se presenti in categoria
            cat_name = ad.get("category", {}).get("friendly_name", "").lower()
            if any(k in cat_name for k in ["uffici", "commerciali", "terreni", "garage"]):
                continue

            url = ad.get("urls", {}).get("default") or ad.get("urls", {}).get("mobile")
            title = ad.get("subject", "")
            desc = ad.get("body", "")
            full_text = f"{title} {desc}".lower()

            features = ad.get("features", {})
            # Se features è una lista la convertiamo in dict per chiave uri
            if isinstance(features, list):
                feat_dict = {f.get("uri"): f for f in features if f.get("uri")}
            elif isinstance(features, dict):
                feat_dict = features
            else:
                feat_dict = {}

            # Estrazione prezzo
            price = 0
            price_feat = feat_dict.get("/price")
            if price_feat:
                try:
                    price_val = price_feat.get("values", [{}])[0].get("key")
                    price = float(price_val)
                except Exception:
                    pass

            # Parametri
            mq = 0
            size_feat = feat_dict.get("/size")
            if size_feat:
                try:
                    mq = float(size_feat.get("values", [{}])[0].get("key"))
                except Exception:
                    pass

            rooms = 0
            room_feat = feat_dict.get("/room")
            if room_feat:
                try:
                    rooms = int(room_feat.get("values", [{}])[0].get("key"))
                except Exception:
                    pass

            bathrooms = 0
            bath_feat = feat_dict.get("/bathrooms")
            if bath_feat:
                try:
                    bathrooms = int(bath_feat.get("values", [{}])[0].get("key"))
                except Exception:
                    pass

            floor = ""
            floor_num = 0
            floor_feat = feat_dict.get("/floor")
            if floor_feat:
                try:
                    floor_val = floor_feat.get("values", [{}])[0].get("value")
                    floor = str(floor_val)
                    m_f = re.search(r'\d+', floor)
                    if m_f:
                        floor_num = int(m_f.group())
                except Exception:
                    pass

            has_elevator = None
            elev_feat = feat_dict.get("/elevator")
            if elev_feat:
                elev_val = elev_feat.get("values", [{}])[0].get("key")
                has_elevator = (elev_val == "1" or elev_val == "true")

            has_garage = 0
            parking_feat = feat_dict.get("/parking")
            if parking_feat:
                for pv in parking_feat.get("values", []):
                    pv_lbl = (pv.get("value") or "").lower()
                    if "box" in pv_lbl or "garage" in pv_lbl or "posto auto" in pv_lbl:
                        has_garage = 1

            has_balcony = 1 if feat_dict.get("/balcony") else 0

            # Stato immobile
            is_renovated = 0
            is_to_renovate = 0
            cond_feat = feat_dict.get("/building_condition")
            if cond_feat:
                cond_val = (cond_feat.get("values", [{}])[0].get("value") or "").lower()
                if "ristrutturato" in cond_val or "nuovo" in cond_val or "ottimo" in cond_val:
                    is_renovated = 1
                elif "da ristrutturare" in cond_val:
                    is_to_renovate = 1

            # Fallback e arricchimento da testo
            if not mq:
                mq_m = re.search(r'(\d{2,3})\s*(?:mq|m²)', full_text)
                if mq_m:
                    mq = float(mq_m.group(1))

            if not bathrooms:
                b_m = re.search(r'(\d+)\s*(?:bagni|bagno|servizi)', full_text)
                if b_m:
                    bathrooms = int(b_m.group(1))
                elif "doppio servizio" in full_text or "doppi servizi" in full_text:
                    bathrooms = 2

            has_terrace = 0
            terrace_mq = 0
            t_m = re.search(r'terrazz[oa]\s*(?:di|da)?\s*(\d{2,3})\s*mq', full_text)
            if t_m:
                has_terrace = 1
                terrace_mq = float(t_m.group(1))
            elif "terrazzo" in full_text or "terrazza" in full_text:
                has_terrace = 1

            has_garden = 0
            garden_mq = 0
            g_m = re.search(r'giardino\s*(?:di|da)?\s*(\d{2,3})\s*mq', full_text)
            if g_m:
                has_garden = 1
                garden_mq = float(g_m.group(1))
            elif "giardino" in full_text:
                has_garden = 1

            if "balcon" in full_text:
                has_balcony = 1

            if "garage" in full_text or "box auto" in full_text or "posto auto" in full_text:
                if not re.search(r'\b(?:senza|no)\s+(?:garage|box|posto auto)\b', full_text):
                    has_garage = 1

            if has_elevator is None:
                if re.search(r'\b(?:con|servito da|dotato di)\s+ascensore\b', full_text):
                    has_elevator = True
                elif re.search(r'\b(?:senza|no)\s+ascensore\b', full_text):
                    has_elevator = False

            is_furnished = 1 if "arredato" in full_text or "ammobiliato" in full_text else 0

            # Immagine di copertina
            images = ad.get("images", [])
            img_url = images[0].get("cdn_base_url") if images else ""

            # Geo town
            geo = ad.get("geo", {})
            town = geo.get("town", {}).get("value", "")

            agency_ref = extract_agency_ref(full_text)
            fingerprint = generate_fingerprint(price, mq, floor_num or floor, town, bathrooms)

            results.append({
                "external_id": str(ad.get("urn", "")),
                "url": url,
                "title": title,
                "description": desc,
                "price": price,
                "mq": mq,
                "rooms": rooms,
                "bedrooms": max(rooms - 2, 0) if rooms >= 3 else 0,
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
                "zone_name": town,
                "image_url": img_url,
                "agency_ref": agency_ref,
                "fingerprint": fingerprint
            })

    except Exception as e:
        print(f"[Subito Scraper Parsing Error] {e}")

    return results
