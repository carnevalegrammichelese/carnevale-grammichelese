"""
Reimposta la password dell'account amministratore, in caso te la dimentichi.

USO: lancia questo script dalla stessa cartella di app.py, con l'ambiente
virtuale attivato:

    python reset_admin_password.py

Ti chiederà la nuova password e la salva direttamente nel database.
Non serve conoscere la password attuale: è pensato apposta per quando l'hai
dimenticata. Va lanciato da chi ha accesso al computer dove gira il sito,
quindi tienilo al sicuro.
"""

import sqlite3
import os
import getpass
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "carnevale.db")


def main():
    if not os.path.exists(DB_PATH):
        print("Non trovo il file carnevale.db: avvia prima il sito almeno una volta con 'python app.py'.")
        return

    conn = sqlite3.connect(DB_PATH)
    admin = conn.execute("SELECT * FROM admin LIMIT 1").fetchone()
    if admin is None:
        print("Nessun account amministratore trovato nel database.")
        conn.close()
        return

    print(f"Account amministratore trovato: {admin[1]}")
    nuova = getpass.getpass("Nuova password (almeno 8 caratteri): ")
    conferma = getpass.getpass("Ripeti la nuova password: ")

    if len(nuova) < 8:
        print("La password deve avere almeno 8 caratteri. Riprova.")
        conn.close()
        return
    if nuova != conferma:
        print("Le due password non coincidono. Riprova.")
        conn.close()
        return

    conn.execute(
        "UPDATE admin SET password_hash = ? WHERE id = ?",
        (generate_password_hash(nuova), admin[0]),
    )
    conn.commit()
    conn.close()
    print("Fatto! La password dell'amministratore è stata aggiornata.")


if __name__ == "__main__":
    main()
