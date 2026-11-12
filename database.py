import sqlite3
import os
import json
from datetime import datetime
from config import DB_PATH, DEFAULT_RULES, DEFAULT_ZONES, AGGREGATOR_SOURCES, AGENCY_SOURCES

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Tabella Regole (parametri editabili dal bot)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT
        )
    """)

    # Tabella Zone e Quartieri (Tier 1, 2, 3 o 0 = escluso)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            tier INTEGER NOT NULL,
            aliases TEXT NOT NULL
        )
    """)

    # Tabella Fonti (Aggregatori, Siti Agenzie, Gruppi FB)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            url TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            last_checked TIMESTAMP
        )
    """)

    # Tabella Annunci
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            external_id TEXT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            price REAL,
            mq REAL,
            rooms INTEGER,
            bedrooms INTEGER,
            bathrooms INTEGER,
            floor TEXT,
            floor_number INTEGER,
            has_elevator INTEGER,
            has_terrace INTEGER,
            terrace_mq REAL,
            has_garden INTEGER,
            garden_mq REAL,
            has_balcony INTEGER,
            has_garage INTEGER,
            is_renovated INTEGER,
            is_to_renovate INTEGER,
            is_furnished INTEGER,
            zone_name TEXT,
            tier INTEGER,
            category TEXT, -- 'PRIMA_SCELTA', 'SECONDA_SCELTA', 'SCARTATO'
            score REAL,
            rejection_reason TEXT,
            image_url TEXT,
            description TEXT,
            agency_ref TEXT,
            fingerprint TEXT,
            telegram_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES sources (id)
        )
    """)

    # Tabella per tracciare i doppioni (Cross-Platform)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duplicates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_listing_id INTEGER NOT NULL,
            duplicate_url TEXT NOT NULL,
            source_name TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            match_type TEXT, -- 'REF_CODE', 'FINGERPRINT', 'PHASH'
            FOREIGN KEY (primary_listing_id) REFERENCES listings (id)
        )
    """)

    # Tabella Feedback Utente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            user_id INTEGER,
            rating TEXT NOT NULL, -- 'like', 'dislike', 'star'
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (listing_id) REFERENCES listings (id)
        )
    """)

    conn.commit()

    # Popola regole iniziali se vuoto
    cursor.execute("SELECT COUNT(*) FROM rules")
    if cursor.fetchone()[0] == 0:
        for k, v in DEFAULT_RULES.items():
            cursor.execute("INSERT INTO rules (key, value) VALUES (?, ?)", (k, json.dumps(v)))
        conn.commit()

    # Popola zone se vuoto
    cursor.execute("SELECT COUNT(*) FROM zones")
    if cursor.fetchone()[0] == 0:
        for name, data in DEFAULT_ZONES.items():
            cursor.execute(
                "INSERT INTO zones (name, tier, aliases) VALUES (?, ?, ?)",
                (name, data["tier"], json.dumps(data["aliases"]))
            )
        conn.commit()

    # Popola fonti se vuoto
    cursor.execute("SELECT COUNT(*) FROM sources")
    if cursor.fetchone()[0] == 0:
        for src in AGGREGATOR_SOURCES + AGENCY_SOURCES:
            cursor.execute(
                "INSERT OR IGNORE INTO sources (name, type, url, active) VALUES (?, ?, ?, ?)",
                (src["name"], src["type"], src["url"], 1 if src.get("active", True) else 0)
            )
        conn.commit()

    conn.close()

# Helper Regole
def get_rules():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM rules")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: json.loads(row["value"]) for row in rows}

def set_rule(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO rules (key, value) VALUES (?, ?)", (key, json.dumps(value)))
    conn.commit()
    conn.close()

# Helper Zone
def get_zones():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, tier, aliases FROM zones ORDER BY tier ASC, name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {"name": row["name"], "tier": row["tier"], "aliases": json.loads(row["aliases"])}
        for row in rows
    ]

def update_zone_tier(zone_name, new_tier):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE zones SET tier = ? WHERE name = ?", (new_tier, zone_name))
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated

# Helper Fonti
def get_sources(active_only=True):
    conn = get_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM sources WHERE active = 1")
    else:
        cursor.execute("SELECT * FROM sources")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_source(name, url, source_type="custom"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO sources (name, type, url, active) VALUES (?, ?, ?, 1)",
        (name, source_type, url)
    )
    conn.commit()
    conn.close()

def toggle_source(source_id, active_state):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sources SET active = ? WHERE id = ?", (1 if active_state else 0, source_id))
    conn.commit()
    conn.close()

# Helper Annunci e Deduplicazione
def is_url_seen(url):
    """
    Ritorna True SOLO se l'annuncio è già stato notificato su Telegram.
    Se era stato precedentemente scartato, permette la rivalutazione con i nuovi filtri!
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, telegram_message_id FROM listings WHERE url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False
    # Se è già stato inviato su Telegram, non inviarlo due volte
    return row["telegram_message_id"] is not None

def find_duplicate(fingerprint=None, agency_ref=None):
    """Verifica se l'annuncio esiste già per impronta o riferimento agenzia."""
    conn = get_connection()
    cursor = conn.cursor()
    match = None

    if agency_ref:
        cursor.execute("SELECT * FROM listings WHERE agency_ref = ? AND agency_ref != ''", (agency_ref,))
        row = cursor.fetchone()
        if row:
            match = (dict(row), 'REF_CODE')

    if not match and fingerprint:
        cursor.execute("SELECT * FROM listings WHERE fingerprint = ? AND fingerprint != ''", (fingerprint,))
        row = cursor.fetchone()
        if row:
            match = (dict(row), 'FINGERPRINT')

    conn.close()
    return match

def save_listing(listing_data):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM listings WHERE url = :url", listing_data)
    row = cursor.fetchone()
    if row:
        listing_id = row["id"]
        cursor.execute("""
            UPDATE listings SET
                category = :category, score = :score, rejection_reason = :rejection_reason,
                zone_name = :zone_name, tier = :tier, price = :price, mq = :mq
            WHERE id = :id
        """, {**listing_data, "id": listing_id})
    else:
        cursor.execute("""
            INSERT INTO listings (
                source_id, external_id, url, title, price, mq, rooms, bedrooms,
                bathrooms, floor, floor_number, has_elevator, has_terrace, terrace_mq,
                has_garden, garden_mq, has_balcony, has_garage, is_renovated,
                is_to_renovate, is_furnished, zone_name, tier, category, score,
                rejection_reason, image_url, description, agency_ref, fingerprint
            ) VALUES (
                :source_id, :external_id, :url, :title, :price, :mq, :rooms, :bedrooms,
                :bathrooms, :floor, :floor_number, :has_elevator, :has_terrace, :terrace_mq,
                :has_garden, :garden_mq, :has_balcony, :has_garage, :is_renovated,
                :is_to_renovate, :is_furnished, :zone_name, :tier, :category, :score,
                :rejection_reason, :image_url, :description, :agency_ref, :fingerprint
            )
        """, listing_data)
        listing_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return listing_id

def record_duplicate(primary_id, duplicate_url, source_name, match_type):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO duplicates (primary_listing_id, duplicate_url, source_name, match_type)
        VALUES (?, ?, ?, ?)
    """, (primary_id, duplicate_url, source_name, match_type))
    conn.commit()
    conn.close()

def save_feedback(listing_id, user_id, rating, notes=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback (listing_id, user_id, rating, notes)
        VALUES (?, ?, ?, ?)
    """, (listing_id, user_id, rating, notes))
    conn.commit()
    conn.close()

def get_favorites():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.* FROM listings l
        JOIN feedback f ON l.id = f.listing_id
        WHERE f.rating = 'star'
        ORDER BY f.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM listings")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM listings WHERE category = 'PRIMA_SCELTA'")
    prime = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM listings WHERE category = 'QUASI_PERFETTO'")
    quasi = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM listings WHERE category = 'VALUTABILE'")
    valutabili = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM listings WHERE category = 'SCARTATO'")
    scartati = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM duplicates")
    duplicati = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM feedback WHERE rating = 'star'")
    preferiti = cursor.fetchone()[0]
    conn.close()
    return {
        "total": total,
        "prima_scelta": prime,
        "quasi_perfetto": quasi,
        "valutabile": valutabili,
        "scartati": scartati,
        "duplicati": duplicati,
        "preferiti": preferiti
    }

