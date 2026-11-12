import asyncio
from scrapers.facebook_scraper import init_facebook_login

if __name__ == "__main__":
    print("=" * 60)
    print("AUTENTICAZIONE FACEBOOK PER MATERA HOUSE BOT")
    print("=" * 60)
    print("Si aprirà una finestra del browser.")
    print("Accedi al tuo account Facebook secondario/dedicato.")
    print("Una volta effettuato l'accesso, la sessione verrà salvata")
    print("automaticamente in data/fb_session.json.")
    print("=" * 60)
    asyncio.run(init_facebook_login())

