import asyncio
from database import (
    get_sources, is_url_seen, save_listing, get_rules
)
from dedup import check_and_deduplicate
from evaluator import evaluate_listing
from scrapers.subito_scraper import scrape_subito
from scrapers.immobiliare_scraper import scrape_immobiliare
from scrapers.agency_scraper import scrape_agency_site
from scrapers.facebook_scraper import scrape_facebook_group_or_marketplace

async def run_scan(bot_instance=None, chat_id=None):
    """
    Esegue una scansione completa di tutte le fonti attive (portali, agenzie, social).
    Filtra, deduplica e notifica i nuovi annunci idonei su Telegram.
    """
    sources = get_sources(active_only=True)
    new_approved = 0
    prime_count = 0
    quasi_count = 0
    val_count = 0
    new_duplicates = 0
    scartati = 0

    print(f"\n[Monitor] Inizio scansione su {len(sources)} fonti attive...")

    for src in sources:
        src_name = src["name"]
        src_type = src["type"]
        src_url = src["url"]

        items = []
        try:
            if "subito" in src_url.lower():
                items = scrape_subito(src_url)
            elif "immobiliare.it" in src_url.lower():
                items = scrape_immobiliare(src_url)
            elif src_type == "agency":
                items = scrape_agency_site(src_name, src_url)
            elif src_type == "facebook":
                items = await scrape_facebook_group_or_marketplace(src_url)
        except Exception as e:
            print(f"[Monitor] Errore scansione {src_name}: {e}")
            continue

        for item in items:
            url = item.get("url")
            if not url or is_url_seen(url):
                continue

            # Controllo Anti-Doppione Cross-Platform
            is_dup, primary_ad, match_type = check_and_deduplicate(item, src_name)
            if is_dup:
                new_duplicates += 1
                # Se è un doppione di un annuncio già inviato, possiamo aggiornarlo su Telegram
                if bot_instance and chat_id and primary_ad.get("telegram_message_id"):
                    try:
                        await bot_instance.send_message(
                            chat_id=chat_id,
                            text=f"ℹ️ *Aggiornamento:* L'immobile a *{primary_ad.get('zone_name')}* ({primary_ad.get('price'):,.0f} €) è presente anche su:\n🔗 [{src_name}]({url})",
                            parse_mode="Markdown"
                        )
                    except Exception as e:
                        print(f"[Telegram Dup Notify Error] {e}")
                continue

            # Valutazione di Pertinenza
            category, score, missing_params, zone_name, tier = evaluate_listing(item)
            item["category"] = category
            item["score"] = score
            item["missing_params"] = missing_params
            item["rejection_reason"] = "; ".join(missing_params) if isinstance(missing_params, list) else str(missing_params)
            item["source_id"] = src["id"]

            listing_id = save_listing(item)

            if category in ["PRIMA_SCELTA", "QUASI_PERFETTO", "VALUTABILE"]:
                new_approved += 1
                if category == "PRIMA_SCELTA":
                    prime_count += 1
                elif category == "QUASI_PERFETTO":
                    quasi_count += 1
                elif category == "VALUTABILE":
                    val_count += 1

                if bot_instance and chat_id:
                    await send_telegram_alert(bot_instance, chat_id, item, listing_id)
            else:
                scartati += 1

    print(f"[Monitor] Scansione terminata: {new_approved} idonei ({prime_count} perfetti, {quasi_count} quasi perfetti, {val_count} valutabili), {new_duplicates} doppioni unificati, {scartati} scartati.\n")
    return {
        "approved": new_approved,
        "approved_prime": prime_count,
        "approved_quasi": quasi_count,
        "approved_valutabili": val_count,
        "duplicates": new_duplicates,
        "rejected": scartati
    }

async def send_telegram_alert(bot, chat_id, item, listing_id):
    """Invia una notifica formattata con pulsanti interattivi e banner dei parametri mancanti."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    cat = item.get("category", "")
    missing_list = item.get("missing_params") or []
    if isinstance(missing_list, str):
        missing_list = [m.strip() for m in missing_list.split(";") if m.strip()]

    if cat == "PRIMA_SCELTA":
        badge = "🌟 *PRIMA SCELTA (Match Perfetto: 9/9)*"
        missing_section = "✨ *Rispetta TUTTI i parametri richiesti!*\n"
    elif cat == "QUASI_PERFETTO":
        badge = "🟠 *QUASI PERFETTO (Rispetta 8 su 9 parametri)*"
        lines = [f"• ❌ {m}" for m in missing_list]
        missing_section = "⚠️ *PARAMETRO NON RISPETTATO:*\n" + "\n".join(lines) + "\n"
    elif cat == "VALUTABILE":
        badge = "🟡 *SECONDA SCELTA (Rispetta 7 su 9 parametri)*"
        lines = [f"• ❌ {m}" for m in missing_list]
        missing_section = f"⚠️ *PARAMETRI NON RISPETTATI ({len(missing_list)}):*\n" + "\n".join(lines) + "\n"
    else:
        badge = "📌 *ANNUNCIO SEGNALATO*"
        missing_section = ""

    tier_label = f"Tier {item.get('tier', 1)}" if item.get('tier') else "Zona Esterna"

    # Preparazione campi
    price_str = f"{item.get('price'):,.0f} €".replace(",", ".") if item.get('price') else "Trattativa riservata"
    mq_str = f"{item.get('mq'):.0f} mq" if item.get('mq') else "N/D"
    rooms_str = f"{item.get('bedrooms', 0)} camere ({item.get('rooms', 0)} vani)" if item.get('rooms') else "N/D"
    bath_str = f"{item.get('bathrooms', 0)} bagni"
    piano_str = item.get("floor") or "N/D"
    ascensore_str = "Sì ✅" if item.get("has_elevator") else ("No ❌" if item.get("has_elevator") is False else "Da verificare")
    garage_str = "Sì 🚗" if item.get("has_garage") else "Non specificato"
    arredo_str = "Arredato 🛋️" if item.get("is_furnished") else "Non arredato"

    spazi_aperti = []
    if item.get("has_terrace"):
        t_mq = f" ({item.get('terrace_mq'):.0f} mq)" if item.get('terrace_mq') else ""
        spazi_aperti.append(f"Terrazzo{t_mq} ☀️")
    if item.get("has_garden"):
        g_mq = f" ({item.get('garden_mq'):.0f} mq)" if item.get('garden_mq') else ""
        spazi_aperti.append(f"Giardino{g_mq} 🌳")
    if item.get("has_balcony"):
        spazi_aperti.append("Balconi")

    spazi_str = ", ".join(spazi_aperti) if spazi_aperti else "Nessuno specificato"

    caption = (
        f"{badge} (Score: {item.get('score', 0):.0f}%)\n\n"
        f"{missing_section}\n"
        f"🏠 *{item.get('title')}*\n"
        f"📍 *Zona:* {item.get('zone_name')} ({tier_label})\n"
        f"💰 *Prezzo:* {price_str}\n"
        f"📐 *Superficie:* {mq_str}\n"
        f"🚪 *Spazi:* {rooms_str} | {bath_str}\n"
        f"🏢 *Piano:* {piano_str} | *Ascensore:* {ascensore_str}\n"
        f"🌿 *Spazi Aperti:* {spazi_str}\n"
        f"🅿️ *Garage/Posto Auto:* {garage_str}\n"
        f"🛋️ *Arredo:* {arredo_str}\n\n"
        f"🔗 [Apri Annuncio Originale]({item.get('url')})"
    )

    # Pulsanti Interattivi
    keyboard = [
        [
            InlineKeyboardButton("👍 Pertinente", callback_data=f"fb:like:{listing_id}"),
            InlineKeyboardButton("👎 Non Pertinente", callback_data=f"fb:dislike:{listing_id}"),
        ],
        [
            InlineKeyboardButton("⭐ Salva nei Preferiti", callback_data=f"fb:star:{listing_id}"),
            InlineKeyboardButton("🔗 Vedi Annuncio", url=item.get("url"))
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if item.get("image_url") and item.get("image_url").startswith("http"):
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=item["image_url"],
                caption=caption[:1024],
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup,
                disable_web_page_preview=False
            )

        # Salva telegram_message_id nel DB
        from database import get_connection
        conn = get_connection()
        conn.cursor().execute("UPDATE listings SET telegram_message_id = ? WHERE id = ?", (msg.message_id, listing_id))
        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[Telegram Alert Send Error] {e}")

