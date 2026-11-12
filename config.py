# Configurazione Iniziale per Matera House Bot
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "matera_house.db")

# Parametri di Ricerca Default
DEFAULT_RULES = {
    "price_min": 200000,
    "price_max": 350000,
    "price_max_to_renovate": 250000,
    "mq_min": 95,
    "mq_max": 130,
    "bedrooms_min": 3,      # 3 camere (esclusi cucina, soggiorno, ripostigli)
    "bathrooms_min": 2,     # Minimo 2 bagni
    "terrace_min_mq": 25,   # Terrazzo minimo 25 mq
    "garden_min_mq": 25,    # Giardino minimo 25 mq
    "elevator_required": True,
    "garage_required_tier1": True,
    "garage_preferred_other_tiers": True,
    "exclude_ground_floor": True,
    "exclude_semi_basement": True,
    "exclude_raised_floor_without_garden": True, # Rialzato ammesso solo con giardino >= 25mq
    "exclude_first_floor_without_garden": False, # 1° piano ammesso con balconi/terrazzo, se con giardino è valutabile
    "exclude_auctions": True,      # No aste giudiziarie
    "exclude_bare_ownership": True,# No nuda proprietà
    "exclude_rent": True,          # No affitto/rent to buy
}

# Mappatura Zone Matera con relative parole chiave e Tier
DEFAULT_ZONES = {
    # TIER 1: Massima priorità
    "Centro Direzionale": {
        "tier": 1,
        "aliases": ["centro direzionale", "via parri", "via aldo moro", "via moro", "via timmari", "tribunale", "asl"]
    },
    "Piano / Centro città": {
        "tier": 1,
        "aliases": ["centro", "centro storico", "il piano", "piazza vittorio veneto", "via ridola", "via del corso", "via roma", "via lucana", "via xx settembre"]
    },
    "Via Castello": {
        "tier": 1,
        "aliases": ["via castello", "castello tramontano", "castello", "parco del castello"]
    },

    # TIER 2: Molto graditi
    "Zona Stadio / Asse Via Dante - Via Nazionale": {
        "tier": 2,
        "aliases": ["via dante", "via nazionale", "stadio", "zona stadio", "san pio x", "via manzoni", "via sturzo"]
    },
    "Lanera": {
        "tier": 2,
        "aliases": ["lanera", "via lanera", "università"]
    },

    # TIER 3: Valutabili (solo ottime condizioni/prezzo)
    "Agna / Agna Le Piane": {
        "tier": 3,
        "aliases": ["agna", "agna le piane", "borgo agna", "via agna"]
    },
    "Piccianello": {
        "tier": 3,
        "aliases": ["piccianello", "via cererie", "via annunziatella", "via la croce", "madonna della croce"]
    },
    "Rione Pini": {
        "tier": 3,
        "aliases": ["rione pini", "i pini", "via dei pini"]
    },
    "Rione Giustino Fortunato": {
        "tier": 3,
        "aliases": ["giustino fortunato", "rione fortunato", "via fortunato"]
    },
    "Spine Bianche": {
        "tier": 3,
        "aliases": ["spine bianche", "bottiglione", "rione spine bianche"]
    },

    # ZONE ESCLUSE DI DEFAULT (Attivabili a richiesta via bot)
    "Sassi (Barisano e Caveoso)": {
        "tier": 0,
        "aliases": ["sassi", "sasso barisano", "sasso caveoso", "civita"]
    },
    "Serra Rifusa": {
        "tier": 0,
        "aliases": ["serra rifusa", "via serra rifusa"]
    },
    "Serra Venerdì": {
        "tier": 0,
        "aliases": ["serra venerdì", "serra venerdi"]
    },
    "San Giacomo": {
        "tier": 0,
        "aliases": ["san giacomo"]
    },
    "Villa Longo": {
        "tier": 0,
        "aliases": ["villa longo", "villalongo", "olmi"]
    },
    "San Pardo": {
        "tier": 0,
        "aliases": ["san pardo"]
    },
    "Acquarium": {
        "tier": 0,
        "aliases": ["acquarium", "aquarium"]
    },
    "Matera 2000": {
        "tier": 0,
        "aliases": ["matera 2000", "via gravina"]
    },
    "Il Quadrifoglio": {
        "tier": 0,
        "aliases": ["il quadrifoglio", "quadrifoglio"]
    },
    "Giada / Giovanni Paolo II": {
        "tier": 0,
        "aliases": ["giada", "giovanni paolo ii", "zona giada"]
    },
    "Rione Cappuccini": {
        "tier": 0,
        "aliases": ["cappuccini", "rione cappuccini"]
    },
    "Borgo La Martella": {
        "tier": 0,
        "aliases": ["la martella", "borgo la martella"]
    },
    "Borgo Venusio": {
        "tier": 0,
        "aliases": ["venusio", "borgo venusio"]
    },
    "Borgo Picciano": {
        "tier": 0,
        "aliases": ["picciano", "borgo picciano"]
    },
    "Timmari": {
        "tier": 0,
        "aliases": ["timmari", "contrada timmari"]
    },
    "Contrade Esterne": {
        "tier": 0,
        "aliases": ["rondinelle", "pantano", "chiancalata", "guirro", "giardinelle"]
    }
}

# Portali Aggregatori Principali
AGGREGATOR_SOURCES = [
    {
        "name": "Subito.it (Matera Immobili)",
        "type": "aggregator",
        "url": "https://www.subito.it/annunci-basilicata/vendita/immobili/matera/matera/?ps=200000&pe=350000",
        "active": True
    },
    {
        "name": "Immobiliare.it (Matera Vendita)",
        "type": "aggregator",
        "url": "https://www.immobiliare.it/vendita-case/matera/?prezzoMinimo=200000&prezzoMassimo=350000&superficieMinima=90&superficieMassima=135",
        "active": True
    },
    {
        "name": "Idealista.it (Matera Vendita)",
        "type": "aggregator",
        "url": "https://www.idealista.it/vendita-case/matera-matera/?prezzo-min=200000&prezzo-max=350000&dimensione-min=90&dimensione-max=135",
        "active": True
    },
    {
        "name": "Casa.it (Matera Vendita)",
        "type": "aggregator",
        "url": "https://www.casa.it/vendita/residenziale/matera/?priceMin=200000&priceMax=350000",
        "active": True
    }
]

# Siti Agenzie Immobiliari Locali di Matera
AGENCY_SOURCES = [
    {"name": "3D Immobiliare", "type": "agency", "url": "https://www.3dimmobiliare.com/", "active": True},
    {"name": "Immobiliare Aesse", "type": "agency", "url": "https://www.immobiliareaesse.it/", "active": True},
    {"name": "Barone Immobiliare", "type": "agency", "url": "https://baroneimmobiliare.com/", "active": True},
    {"name": "Casa Innova", "type": "agency", "url": "https://www.casainnova.it/", "active": True},
    {"name": "Gabetti Matera", "type": "agency", "url": "https://www.gabetti.it/agenzia/matera-centro", "active": True},
    {"name": "Iconacasa Matera", "type": "agency", "url": "https://www.iconacasa.com/index.php/agenzie/companyproperties/86-iconacasa-matera", "active": True},
    {"name": "Idea Casa Matera", "type": "agency", "url": "https://www.ideacasamatera.it/", "active": True},
    {"name": "Ifim Casa", "type": "agency", "url": "https://www.ifimcasa.it/", "active": True},
    {"name": "Infinity Immobiliare", "type": "agency", "url": "https://www.infinityimmobiliare.it/", "active": True},
    {"name": "Immobiliare Matera SAS", "type": "agency", "url": "https://immobiliarematera.com/it", "active": True},
    {"name": "Agenzia Immobilrete", "type": "agency", "url": "https://www.agenziaimmobilrete.it/", "active": True},
    {"name": "Lunalbi", "type": "agency", "url": "https://www.lunalbi.it/", "active": True},
    {"name": "Materhouse Immobiliare", "type": "agency", "url": "https://materhouseimmobiliare.it/", "active": True},
    {"name": "Pianeta Casa Facile", "type": "agency", "url": "https://www.pianetacasafacile.it/", "active": True},
    {"name": "Giuseppe Incampo Immobiliare", "type": "agency", "url": "https://www.immobiliare.it/agenzie-immobiliari/435593/giuseppe-incampo/?criterio=rilevanza", "active": True},
    {"name": "Agenzia Reale", "type": "agency", "url": "https://www.agenziareale.it/", "active": True},
    {"name": "Remax Sprint Matera", "type": "agency", "url": "https://www.remax.it/vendita-case/matera", "active": True},
    {"name": "Sefim Matera", "type": "agency", "url": "https://www.sefimmatera.com/", "active": True},
    {"name": "Sassi Immobiliare Matera", "type": "agency", "url": "https://www.idealista.it/pro/sassi-immobiliare-matera/", "active": True},
    {"name": "Sio Immobiliare", "type": "agency", "url": "https://sioimmobiliare.it/inserzioni/grid-map/", "active": True},
    {"name": "Tuttocasa Matera", "type": "agency", "url": "https://www.tuttocasamatera.it/", "active": True},
    {"name": "Stella Case", "type": "agency", "url": "https://stellacase.it/", "active": True},
    # Aggiunte da verifica sul territorio:
    {"name": "Tecnocasa Matera", "type": "agency", "url": "https://matera1.tecnocasa.it/matera/matera/", "active": True},
    {"name": "Tecnorete Matera", "type": "agency", "url": "https://matera1.tecnorete.it/", "active": True}
]

