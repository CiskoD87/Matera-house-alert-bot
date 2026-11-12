import os
import re
import json
import asyncio
from dedup import extract_agency_ref, generate_fingerprint

COOKIES_PATH = "data/fb_session.json"

async def init_facebook_login():
    """
    Apre un browser visibile per consentire all'utente di effettuare il login
    con l'account Facebook dedicato/secondario e salvare la sessione (cookies).
    Da eseguire una sola volta!
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[Facebook Scraper] Playwright non è installato. Esegui: pip install playwright && playwright install")
        return False

    os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("[Facebook Login] Apertura pagina di login di Facebook...")
        await page.goto("https://www.facebook.com/login")
        print("[Facebook Login] Effettua il login nel browser aperto. Hai 120 secondi...")

        # Attende che l'utente effettui il login
        for _ in range(24):
            await asyncio.sleep(5)
            cookies = await context.cookies()
            # Se trova il cookie 'c_user', il login è avvenuto con successo
            if any(c.get("name") == "c_user" for c in cookies):
                print("[Facebook Login] Login rilevato con successo!")
                await context.storage_state(path=COOKIES_PATH)
                print(f"[Facebook Login] Sessione salvata in {COOKIES_PATH}")
                await browser.close()
                return True

        await browser.close()
        print("[Facebook Login] Timeout login.")
        return False

async def scrape_facebook_group_or_marketplace(target_url):
    """
    Scraper per gruppi privati o Marketplace di Facebook utilizzando la sessione salvata.
    """
    results = []
    if not os.path.exists(COOKIES_PATH):
        print(f"[Facebook Scraper] File di sessione {COOKIES_PATH} non trovato. Effettua prima il login.")
        return results

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=COOKIES_PATH)
            page = await context.new_page()

            await page.goto(target_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)

            # Scroll verso il basso per caricare i post recenti
            await page.evaluate("window.scrollBy(0, 1500)")
            await asyncio.sleep(2)

            # Seleziona gli elementi dei post (feed post)
            posts = await page.query_selector_all("div[role='feed'] > div, div[role='article']")

            for post in posts[:15]:
                try:
                    text_content = await post.inner_text()
                    if not text_content or len(text_content) < 50:
                        continue

                    text_lower = text_content.lower()

                    # Controlla se parla di vendita / appartamento a Matera
                    if not any(k in text_lower for k in ["vend", "appartament", "casa", "quadrilocale", "trilocale"]):
                        continue

                    # Estrazione Prezzo
                    price_match = re.search(r'(?:€|euro)\s*([0-9]{1,3}(?:\.[0-9]{3})*)', text_content, re.IGNORECASE)
                    price = float(price_match.group(1).replace(".", "")) if price_match else 0

                    if price > 0 and (price < 180000 or price > 400000):
                        continue

                    # Mq
                    mq_match = re.search(r'(\d{2,3})\s*(?:mq|m²)', text_lower)
                    mq = float(mq_match.group(1)) if mq_match else 0

                    # Cerca link al post
                    link_el = await post.query_selector("a[href*='/posts/'], a[href*='/permalink/'], a[href*='/marketplace/item/']")
                    post_url = target_url
                    if link_el:
                        href = await link_el.get_attribute("href")
                        if href:
                            post_url = f"https://www.facebook.com{href}" if href.startswith("/") else href

                    # Immagine
                    img_el = await post.query_selector("img[src*='scontent']")
                    img_url = await img_el.get_attribute("src") if img_el else ""

                    agency_ref = extract_agency_ref(text_content)
                    fingerprint = generate_fingerprint(price, mq, "", "Facebook", 2)

                    results.append({
                        "external_id": f"fb_{abs(hash(post_url))}",
                        "url": post_url,
                        "title": f"[Facebook] {text_content[:60].strip()}...",
                        "description": text_content[:1000],
                        "price": price,
                        "mq": mq,
                        "rooms": 0,
                        "bedrooms": 3 if "3 camere" in text_lower or "tre camere" in text_lower else 0,
                        "bathrooms": 2 if "2 bagni" in text_lower or "doppi servizi" in text_lower else 1,
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
                        "zone_name": "Facebook",
                        "image_url": img_url,
                        "agency_ref": agency_ref,
                        "fingerprint": fingerprint
                    })
                except Exception as inner_e:
                    continue

            await browser.close()
    except Exception as e:
        print(f"[Facebook Scraper Error] {e}")

    return results

