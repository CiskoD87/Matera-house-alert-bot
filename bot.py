import os
import asyncio
import logging
from datetime import time
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

try:
    from zoneinfo import ZoneInfo
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters
)
from database import (
    init_db, get_rules, set_rule, get_zones, update_zone_tier,
    get_sources, add_source, toggle_source, save_feedback, get_favorites, get_stats
)
from monitor import run_scan
from keep_alive import start_keep_alive

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9269494568:AAH7iVb96yTjIALveW8LiKQPhIv_fJeH5KM")
TARGET_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "67966940")

# Tastiera persistente sempre visibile sotto la chat
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔍 Avvia Scansione Completa", "⭐ Preferiti"],
        ["⚙️ Regole & Filtri", "📍 Zone & Tier"],
        ["📡 Fonti Monitorate", "📊 Statistiche"]
    ],
    resize_keyboard=True
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando di benvenuto con pulsante di primo monitoraggio e tastiera fissa."""
    global TARGET_CHAT_ID
    chat_id = update.effective_chat.id
    TARGET_CHAT_ID = str(chat_id)

    # Salva in .env
    env_file = os.path.join(BASE_DIR, ".env")
    try:
        with open(env_file, "w") as f:
            f.write(f"TELEGRAM_BOT_TOKEN={TELEGRAM_BOT_TOKEN}\nTELEGRAM_CHAT_ID={chat_id}\n")
    except Exception as e:
        logger.error(f"Errore scrittura .env: {e}")

    inline_keyboard = [
        [InlineKeyboardButton("🚀 Avvia Primo Monitoraggio Subito", callback_data="cmd:scan_now")],
        [
            InlineKeyboardButton("⚙️ Regole", callback_data="cmd:rules"),
            InlineKeyboardButton("📍 Mappa Zone", callback_data="cmd:zones")
        ]
    ]

    msg = (
        "👋 *Benvenuto nel tuo Bot Immobiliare per Matera!*\n\n"
        f"✅ *Chat ID registrato:* `{chat_id}`\n\n"
        "⏰ *Scansioni automatiche programmate:*\n"
        "• ☀️ Mattina: **08:30**\n"
        "• 🌙 Sera: **20:30**\n\n"
        "Puoi avviare in qualsiasi momento una scansione manuale usando il pulsante qui sotto "
        "o la tastiera in basso!"
    )
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD
    )
    await update.message.reply_text(
        "👇 *Vuoi fare subito un primo controllo di tutti gli annunci?*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard)
    )

async def trigger_scan(chat_id, bot):
    """Esegue la scansione completa e notifica l'esito."""
    status_msg = await bot.send_message(
        chat_id=chat_id,
        text="⏳ *Avvio scansione completa di tutti i portali e le agenzie di Matera...*",
        parse_mode="Markdown"
    )

    res = await run_scan(bot_instance=bot, chat_id=chat_id)

    await status_msg.edit_text(
        f"✅ *Scansione completata!*\n\n"
        f"• 🌟 Annunci idonei trovati e notificati: *{res['approved']}*\n"
        f"• ♻️ Annunci duplicati unificati: *{res['duplicates']}*\n"
        f"• 🗑️ Annunci scartati (fuori dai tuoi filtri): *{res['rejected']}*\n\n"
        f"_I prossimi controlli automatici avverranno alle 08:30 e alle 20:30._",
        parse_mode="Markdown"
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /controlla."""
    chat_id = update.effective_chat.id
    await trigger_scan(chat_id, context.bot)

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Visualizza i parametri attivi con istruzioni di modifica."""
    rules = get_rules()
    msg = (
        "⚙️ *Parametri di Ricerca Attuali:*\n\n"
        f"• 💰 *Prezzo:* {rules.get('price_min'):,.0f} € - {rules.get('price_max'):,.0f} €\n"
        f"• 🛠️ *Max se Da Ristrutturare:* {rules.get('price_max_to_renovate'):,.0f} €\n"
        f"• 📐 *Superficie:* {rules.get('mq_min')} mq - {rules.get('mq_max')} mq\n"
        f"• 🚪 *Camere da letto:* Minimo {rules.get('bedrooms_min')}\n"
        f"• 🚿 *Bagni:* Minimo {rules.get('bathrooms_min')}\n"
        f"• ☀️ *Terrazzo min:* {rules.get('terrace_min_mq')} mq\n"
        f"• 🌳 *Giardino min:* {rules.get('garden_min_mq')} mq\n"
        f"• 🛗 *Ascensore:* {'Obbligatorio ✅' if rules.get('elevator_required') else 'Facoltativo'}\n"
        f"• 🅿️ *Garage:* Obbligatorio in Tier 1 ✅ (Preferibile in Tier 2/3)\n"
        f"• 🚫 *Piani esclusi:* Piano terra e Seminterrato (Rialzato solo con giardino $\\ge$ 25 mq)\n"
        f"• 🛑 *Sicurezza:* No Aste, No Nuda Proprietà, No Affitti\n\n"
        "_Per modificare un parametro invia ad esempio:_\n"
        "`/set_prezzo_max 380000`\n"
        "`/set_mq_min 100`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def zones_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elenco completo di tutti i quartieri suddivisi per Tier."""
    zones = get_zones()
    tier1 = [z["name"] for z in zones if z["tier"] == 1]
    tier2 = [z["name"] for z in zones if z["tier"] == 2]
    tier3 = [z["name"] for z in zones if z["tier"] == 3]
    excluded = [z["name"] for z in zones if z["tier"] == 0]

    msg = (
        "📍 *Mappatura Zone di Matera:*\n\n"
        "⭐ *TIER 1 (Massima priorità):*\n" + "\n".join([f"• {n}" for n in tier1]) + "\n\n"
        "🔹 *TIER 2 (Molto graditi):*\n" + "\n".join([f"• {n}" for n in tier2]) + "\n\n"
        "🔸 *TIER 3 (Valutabili se ottimo prezzo):*\n" + "\n".join([f"• {n}" for n in tier3]) + "\n\n"
        "❌ *ESCLUSE ATTUALMENTE:*\n" + "\n".join([f"• {n}" for n in excluded]) + "\n\n"
        "_Per spostare un quartiere in un altro Tier invia:_\n"
        "`/sposta_zona NomeQuartiere 1` (oppure 2, 3, 0 per escluderlo)"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def move_zone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sposta un quartiere da un Tier all'altro."""
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usa il formato: `/sposta_zona NomeQuartiere NuovoTier`\nEs: `/sposta_zona San Giacomo 2`", parse_mode="Markdown")
        return

    try:
        new_tier = int(args[-1])
        zone_name = " ".join(args[:-1])
        if update_zone_tier(zone_name, new_tier):
            await update.message.reply_text(f"✅ Quartiere *{zone_name}* spostato nel *Tier {new_tier}*!", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Quartiere '{zone_name}' non trovato. Verifica il nome esatto con /zone.")
    except ValueError:
        await update.message.reply_text("Il Tier deve essere un numero: 1, 2, 3 oppure 0 (per escluderlo).")

async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra le fonti attive con pulsanti inline per attivarle/disattivarle."""
    sources = get_sources(active_only=False)
    keyboard = []
    text_lines = ["📡 *Fonti e Siti Monitorati:*\n"]

    for src in sources[:18]:
        status_icon = "🟢" if src["active"] else "🔴"
        action_text = "Disattiva" if src["active"] else "Attiva"
        keyboard.append([
            InlineKeyboardButton(f"{status_icon} {src['name']}", callback_data="noop"),
            InlineKeyboardButton(action_text, callback_data=f"src:toggle:{src['id']}")
        ])

    text_lines.append(f"Totale fonti configurate: {len(sources)} (portali aggregatori, agenzie e social).")
    text_lines.append("\n_Per aggiungere una nuova fonte, incolla direttamente l'URL qui in chat!_")

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("\n".join(text_lines), parse_mode="Markdown", reply_markup=reply_markup)

async def favorites_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra gli annunci salvati nei preferiti."""
    favs = get_favorites()
    if not favs:
        await update.message.reply_text("Non hai ancora salvato nessun annuncio nei preferiti ⭐!")
        return

    msg_lines = ["⭐ *I tuoi Annunci Preferiti:*\n"]
    for f in favs:
        p_str = f"{f['price']:,.0f} €" if f['price'] else "N/D"
        msg_lines.append(f"• [{f['title']}]({f['url']}) - *{p_str}* ({f['zone_name']})")

    await update.message.reply_text("\n".join(msg_lines), parse_mode="Markdown", disable_web_page_preview=True)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra le statistiche del bot."""
    stats = get_stats()
    msg = (
        "📊 *Statistiche Monitoraggio:* \n\n"
        f"• Annunci totali esaminati: *{stats['total']}*\n"
        f"• 🌟 Prima Scelta approvati: *{stats['prima_scelta']}*\n"
        f"• 📌 Seconda Scelta approvati: *{stats['seconda_scelta']}*\n"
        f"• ♻️ Doppioni identificati e unificati: *{stats['duplicati']}*\n"
        f"• 🗑️ Annunci scartati (fuori parametri): *{stats['scartati']}*\n"
        f"• ⭐ Immobili salvati nei preferiti: *{stats['preferiti']}*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce i click sui pulsanti inline."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cmd:scan_now":
        chat_id = update.effective_chat.id
        await trigger_scan(chat_id, context.bot)

    elif data == "cmd:rules":
        await rules_command(update, context)

    elif data == "cmd:zones":
        await zones_command(update, context)

    elif data.startswith("fb:"):
        _, action, listing_id = data.split(":")
        user_id = query.from_user.id
        save_feedback(int(listing_id), user_id, action)

        if action == "like":
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Registrato: Pertinente 👍", callback_data="noop")]])
            )
        elif action == "dislike":
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Registrato: Non pertinente 👎", callback_data="noop")]])
            )
        elif action == "star":
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Aggiunto ai Preferiti!", callback_data="noop")]])
            )

    elif data.startswith("src:toggle:"):
        source_id = int(data.split(":")[2])
        sources = get_sources(active_only=False)
        src = next((s for s in sources if s["id"] == source_id), None)
        if src:
            new_state = not src["active"]
            toggle_source(source_id, new_state)
            await query.answer(f"Fonte {src['name']} {'attivata' if new_state else 'disattivata'}")
            await sources_command(update, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce pulsanti della tastiera fissa e messaggi liberi."""
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if text == "🔍 Avvia Scansione Completa":
        await trigger_scan(chat_id, context.bot)
    elif text == "⭐ Preferiti" or text == "⭐ I Miei Preferiti":
        await favorites_command(update, context)
    elif text == "⚙️ Regole & Filtri":
        await rules_command(update, context)
    elif text == "📍 Zone & Tier" or text == "📍 Mappa Zone":
        await zones_command(update, context)
    elif text == "📡 Fonti Monitorate":
        await sources_command(update, context)
    elif text == "📊 Statistiche":
        await stats_command(update, context)
    elif text.startswith("http://") or text.startswith("https://"):
        add_source(f"Fonte Custom {text[:30]}", text, "custom")
        await update.message.reply_text(
            f"✅ *Nuova fonte aggiunta al monitoraggio!*\n🔗 `{text}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "Usa i pulsanti in basso oppure invia /help per la lista comandi.",
            reply_markup=MAIN_KEYBOARD
        )

async def scheduled_scanner_job(context: ContextTypes.DEFAULT_TYPE):
    """Job periodico che esegue lo scraping alle 8:30 e alle 20:30."""
    chat_id = TARGET_CHAT_ID
    if chat_id:
        logger.info(f"[Scheduler] Esecuzione scansione programmata per chat {chat_id}...")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏰ *Scansione Programmata in corso...* Sto controllando i nuovi annunci su tutti i portali e le agenzie di Matera.",
                parse_mode="Markdown"
            )
            res = await run_scan(bot_instance=context.bot, chat_id=chat_id)
            if res["approved"] == 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"ℹ️ *Nessun nuovo annuncio idoneo* in questo momento ({res['rejected']} esaminati e scartati, {res['duplicates']} già noti).\nProssimo controllo alle 08:30 / 20:30.",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"[Scheduler Error] {e}")

def main():
    init_db()
    start_keep_alive()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers Comandi
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("regole", rules_command))
    application.add_handler(CommandHandler("zone", zones_command))
    application.add_handler(CommandHandler("sposta_zona", move_zone_command))
    application.add_handler(CommandHandler("fonti", sources_command))
    application.add_handler(CommandHandler("controlla", check_command))
    application.add_handler(CommandHandler("preferiti", favorites_command))
    application.add_handler(CommandHandler("stats", stats_command))

    # Handler Callback Pulsanti Inline
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Handler Messaggi di Testo (Pulsanti tastiera persistente e link)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Scheduler: 8:30 Mattina e 20:30 Sera (Fuso Orario Italiano)
    job_queue = application.job_queue
    if job_queue:
        time_morning = time(hour=8, minute=30, tzinfo=ROME_TZ)
        time_evening = time(hour=20, minute=30, tzinfo=ROME_TZ)
        job_queue.run_daily(scheduled_scanner_job, time=time_morning, name="morning_scan")
        job_queue.run_daily(scheduled_scanner_job, time=time_evening, name="evening_scan")
        logger.info(f"[Scheduler] Configurato per le 08:30 e le 20:30 (Europe/Rome).")

    print("[Matera House Bot] Bot riavviato e aggiornato. In ascolto...")
    application.run_polling()

if __name__ == "__main__":
    main()
