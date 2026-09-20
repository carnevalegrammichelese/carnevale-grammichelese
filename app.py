import sqlite3
import os
import csv
import io
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "carnevale.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "img", "galleria")
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CHIAVI_CONTENUTI_VALIDE = {
    "hero_eyebrow", "hero_titolo", "hero_sottotitolo",
    "num_1_valore", "num_1_label", "num_2_valore", "num_2_label",
    "num_3_valore", "num_3_label", "num_4_valore", "num_4_label",
    "iban", "intestatario_conto",
    "footer_indirizzo", "footer_email", "footer_facebook", "footer_instagram",
}

# ---------------------------------------------------------------------------
# Invio email (recupero password) — opzionale: va configurato con le
# credenziali di una vostra casella email tramite variabili d'ambiente.
# Se non configurato, il sito continua a funzionare ma il recupero
# password via email resta disattivato (l'utente viene indirizzato a
# contattare il comitato).
# ---------------------------------------------------------------------------
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)


def smtp_configurato():
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def invia_email_recupero(destinatario, nome, link):
    """Prova a inviare l'email di recupero password. Ritorna True se inviata."""
    if not smtp_configurato():
        return False
    import smtplib
    from email.mime.text import MIMEText

    corpo = (
        f"Ciao {nome},\n\n"
        f"Hai richiesto di reimpostare la password del tuo account sul sito del "
        f"Carnevale Grammichelese.\n\n"
        f"Clicca su questo link per scegliere una nuova password (valido 1 ora):\n"
        f"{link}\n\n"
        f"Se non hai richiesto tu questo cambio, ignora pure questa email: "
        f"la tua password attuale resterà invariata.\n\n"
        f"Comitato Carnevale Grammichelese"
    )
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = "Recupero password — Carnevale Grammichelese"
    msg["From"] = SMTP_FROM
    msg["To"] = destinatario

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [destinatario], msg.as_string())
        return True
    except Exception as e:
        app.logger.warning(f"Invio email di recupero fallito: {e}")
        return False

# ---------------------------------------------------------------------------
# Limite tentativi di login (protezione base contro brute-force)
# ---------------------------------------------------------------------------
MAX_TENTATIVI = 5
FINESTRA_SECONDI = 300  # 5 minuti
_tentativi_falliti = defaultdict(list)


def troppi_tentativi(chiave):
    now = time.time()
    _tentativi_falliti[chiave] = [t for t in _tentativi_falliti[chiave] if now - t < FINESTRA_SECONDI]
    return len(_tentativi_falliti[chiave]) >= MAX_TENTATIVI


def registra_tentativo_fallito(chiave):
    _tentativi_falliti[chiave].append(time.time())


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB max upload


# ---------------------------------------------------------------------------
# Protezione CSRF (obbligatoria su ogni form POST del sito)
# ---------------------------------------------------------------------------

def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def csrf_protect():
    if request.method == "POST" and not app.config.get("TESTING"):
        token_sessione = session.get("_csrf_token")
        token_form = request.form.get("_csrf_token")
        if not token_sessione or not token_form or not secrets.compare_digest(token_sessione, token_form):
            abort(400, description="Richiesta non valida (token di sicurezza mancante o scaduto). Ricarica la pagina e riprova.")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    first_time = not os.path.exists(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(BASE_DIR, "schema.sql")) as f:
        db.executescript(f.read())

    if first_time:
        db.execute(
            "INSERT INTO admin (username, password_hash) VALUES (?, ?)",
            ("admin", generate_password_hash("carnevale2027")),
        )

        categorie_default = [
            ("carro-allegorico", "Carro allegorico",
             "Per i gruppi che costruiscono un carro in cartapesta.",
             "Il carro deve rispettare le misure massime indicate dal regolamento comunale. "
             "Ogni gruppo è responsabile della sicurezza dei propri figuranti.",
             5.0, "Tema del carro / misure", "carro", 1),
            ("gruppo-in-maschera", "Gruppo in maschera",
             "Gruppi coreografici o mascherati senza carro.",
             "I gruppi devono presentarsi almeno 30 minuti prima della partenza della sfilata.",
             5.0, "Tema del costume", "gruppo", 2),
            ("maschera-singola", "Maschera singola",
             "Partecipazione individuale con costume personale.",
             "La partecipazione individuale è aperta a tutte le età.",
             5.0, "Descrizione del costume", "maschera", 3),
            ("scuole", "Scuole",
             "Classi e istituti che partecipano con un progetto.",
             "Ogni istituto deve indicare un referente docente responsabile del gruppo.",
             3.0, "Descrizione del progetto", "scuola", 4),
        ]
        db.executemany(
            "INSERT INTO categorie (slug, nome, descrizione, regolamento, prezzo_quota, dettagli_label, icona, ordine) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            categorie_default,
        )

        contenuti_default = {
            "hero_eyebrow": "Grammichele, la città esagonale",
            "hero_titolo": "Un paese a forma di esagono, in festa per il Carnevale",
            "hero_sottotitolo": "Carri allegorici in cartapesta, gruppi in maschera, scuole e maschere singole sfilano per le vie di Grammichele. Iscrivi il tuo gruppo e diventa parte della sfilata.",
            "num_1_valore": "40+", "num_1_label": "edizioni del Carnevale",
            "num_2_valore": "18", "num_2_label": "gruppi iscritti nel 2026",
            "num_3_valore": "6", "num_3_label": "strade della sfilata, una per lato dell'esagono",
            "num_4_valore": "3", "num_4_label": "giorni di festa",
            "iban": "IT00 X000 0000 0000 0000 0000 000",
            "intestatario_conto": "Comitato Carnevale Grammichelese",
            "footer_indirizzo": "Via Roma, Grammichele (CT)",
            "footer_email": "info@carnevalegrammichelese.com",
            "footer_facebook": "#",
            "footer_instagram": "#",
        }
        db.executemany(
            "INSERT INTO contenuti (chiave, valore) VALUES (?, ?)",
            list(contenuti_default.items()),
        )

        programma_default = [
            ("Giorno 1 · Sabato", 1, "16:30", "Apertura in Piazza Umberto",
             "Saluto del comitato e presentazione dei gruppi iscritti", 1),
            ("Giorno 1 · Sabato", 1, "18:00", "Prima sfilata dei carri",
             "Percorso lungo i sei assi principali dell'esagono", 2),
            ("Giorno 2 · Domenica", 2, "15:00", "Sfilata delle scuole",
             "Cortei degli istituti cittadini", 1),
            ("Giorno 3 · Martedì grasso", 3, "17:00", "Sfilata finale dei carri",
             "Percorso completo con giuria di premiazione", 1),
        ]
        db.executemany(
            "INSERT INTO programma (giorno_label, giorno_ordine, orario, titolo, descrizione, ordine) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            programma_default,
        )

        db.commit()
    db.close()


def get_contenuti(db):
    rows = db.execute("SELECT chiave, valore FROM contenuti").fetchall()
    return {r["chiave"]: r["valore"] for r in rows}


def get_programma_raggruppato(db):
    rows = db.execute("SELECT * FROM programma ORDER BY giorno_ordine, ordine").fetchall()
    giorni = {}
    for r in rows:
        giorni.setdefault(r["giorno_label"], []).append(r)
    return giorni


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def nuovo_codice(prefisso):
    return f"{prefisso[:3].upper()}-{secrets.token_hex(3).upper()}"


@app.context_processor
def inject_globals():
    db = get_db()
    categorie = db.execute("SELECT * FROM categorie ORDER BY ordine").fetchall()
    utente_corrente = None
    if session.get("utente_id"):
        utente_corrente = db.execute(
            "SELECT * FROM utenti WHERE id = ?", (session["utente_id"],)
        ).fetchone()
    contenuti_globali = get_contenuti(db)
    return dict(categorie=categorie, utente_corrente=utente_corrente, c=contenuti_globali)


# ---------------------------------------------------------------------------
# Autenticazione — utenti (area iscrizioni) e admin (dashboard comitato)
# ---------------------------------------------------------------------------

def utente_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("utente_id"):
            return redirect(url_for("accedi", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Pagine pubbliche
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    db = get_db()
    contenuti = get_contenuti(db)
    categorie = db.execute("SELECT * FROM categorie ORDER BY ordine").fetchall()
    galleria = db.execute("SELECT * FROM galleria ORDER BY ordine").fetchall()
    programma = get_programma_raggruppato(db)
    return render_template(
        "index.html", c=contenuti, categorie=categorie, galleria=galleria, programma=programma
    )


# ---------------------------------------------------------------------------
# Account utente: registrazione, login, logout
# ---------------------------------------------------------------------------

@app.route("/registrati", methods=["GET", "POST"])
def registrati():
    if session.get("utente_id"):
        return redirect(url_for("account"))

    next_url = request.args.get("next") or request.form.get("next") or url_for("account")

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefono = request.form.get("telefono", "").strip()
        password = request.form.get("password", "")
        conferma = request.form.get("conferma", "")

        errori = []
        if not nome:
            errori.append("Il nome è obbligatorio.")
        if not EMAIL_RE.match(email):
            errori.append("Inserisci un'email valida.")
        if len(password) < 8:
            errori.append("La password deve avere almeno 8 caratteri.")
        if password != conferma:
            errori.append("Le due password non coincidono.")

        db = get_db()
        if not errori and db.execute("SELECT 1 FROM utenti WHERE email = ?", (email,)).fetchone():
            errori.append("Esiste già un account con questa email. Prova ad accedere.")

        if errori:
            for e in errori:
                flash(e, "errore")
            return render_template("registrati.html", form=request.form, next=next_url)

        cur = db.execute(
            "INSERT INTO utenti (nome, email, telefono, password_hash) VALUES (?, ?, ?, ?)",
            (nome, email, telefono, generate_password_hash(password)),
        )
        db.commit()
        session["utente_id"] = cur.lastrowid
        flash("Account creato! Benvenuto/a.", "successo")
        return redirect(next_url)

    return render_template("registrati.html", form={}, next=next_url)


@app.route("/accedi", methods=["GET", "POST"])
def accedi():
    if session.get("utente_id"):
        return redirect(url_for("account"))

    next_url = request.args.get("next") or request.form.get("next") or url_for("account")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        chiave_tentativi = f"utente:{request.remote_addr}:{email}"
        if troppi_tentativi(chiave_tentativi):
            flash("Troppi tentativi falliti. Riprova tra qualche minuto.", "errore")
            return render_template("accedi.html", next=next_url)
        db = get_db()
        utente = db.execute("SELECT * FROM utenti WHERE email = ?", (email,)).fetchone()
        if utente and check_password_hash(utente["password_hash"], password):
            session["utente_id"] = utente["id"]
            return redirect(next_url)
        registra_tentativo_fallito(chiave_tentativi)
        flash("Email o password errati.", "errore")

    return render_template("accedi.html", next=next_url)


@app.route("/password-dimenticata", methods=["GET", "POST"])
def password_dimenticata():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        chiave_tentativi = f"recupero:{email}"
        if troppi_tentativi(chiave_tentativi):
            flash(
                "Hai già richiesto il recupero password troppe volte di recente. Riprova tra qualche minuto.",
                "errore",
            )
            return render_template("password_dimenticata.html")
        registra_tentativo_fallito(chiave_tentativi)

        db = get_db()
        utente = db.execute("SELECT * FROM utenti WHERE email = ?", (email,)).fetchone()

        # Messaggio sempre uguale, esista o no l'account: evita di far capire
        # a chi prova a indovinare quali email sono registrate sul sito.
        messaggio_generico = (
            "Se l'indirizzo è registrato, riceverai a breve un'email con le "
            "istruzioni per reimpostare la password."
        )

        if utente:
            token = secrets.token_urlsafe(32)
            scadenza = (datetime.now().timestamp() + 3600)  # 1 ora
            db.execute(
                "UPDATE utenti SET reset_token = ?, reset_scadenza = ? WHERE id = ?",
                (token, scadenza, utente["id"]),
            )
            db.commit()
            link = url_for("reimposta_password", token=token, _external=True)
            inviata = invia_email_recupero(utente["email"], utente["nome"], link)
            if not inviata:
                # SMTP non configurato (o invio fallito): il sito resta onesto
                # e non finge che l'email sia partita.
                contenuti = get_contenuti(db)
                flash(
                    "Il recupero automatico via email non è ancora attivo su questo sito. "
                    f"Scrivi al comitato ({contenuti.get('footer_email','')}) per farti reimpostare la password.",
                    "errore",
                )
                return render_template("password_dimenticata.html")

        flash(messaggio_generico, "successo")
        return render_template("password_dimenticata.html")

    return render_template("password_dimenticata.html")


@app.route("/reimposta-password/<token>", methods=["GET", "POST"])
def reimposta_password(token):
    db = get_db()
    utente = db.execute(
        "SELECT * FROM utenti WHERE reset_token = ?", (token,)
    ).fetchone()

    token_valido = (
        utente is not None
        and utente["reset_scadenza"] is not None
        and float(utente["reset_scadenza"]) > datetime.now().timestamp()
    )

    if not token_valido:
        flash("Questo link non è valido o è scaduto. Richiedine uno nuovo.", "errore")
        return redirect(url_for("password_dimenticata"))

    if request.method == "POST":
        nuova = request.form.get("nuova", "")
        conferma = request.form.get("conferma", "")
        if len(nuova) < 8:
            flash("La password deve avere almeno 8 caratteri.", "errore")
        elif nuova != conferma:
            flash("Le due password non coincidono.", "errore")
        else:
            db.execute(
                "UPDATE utenti SET password_hash = ?, reset_token = NULL, reset_scadenza = NULL WHERE id = ?",
                (generate_password_hash(nuova), utente["id"]),
            )
            db.commit()
            session["utente_id"] = utente["id"]
            flash("Password aggiornata! Sei stato/a autenticato/a automaticamente.", "successo")
            return redirect(url_for("account"))

    return render_template("reimposta_password.html", token=token)


@app.route("/esci")
def esci():
    session.pop("utente_id", None)
    return redirect(url_for("home"))


# ---------------------------------------------------------------------------
# Area riservata utente: i propri gruppi e partecipanti
# ---------------------------------------------------------------------------

@app.route("/account")
@utente_login_required
def account():
    db = get_db()
    gruppi = db.execute(
        "SELECT i.*, c.nome as categoria_nome, c.slug as categoria_slug, "
        "c.prezzo_quota, c.dettagli_label "
        "FROM iscrizioni i JOIN categorie c ON i.categoria_id = c.id "
        "WHERE i.utente_id = ? ORDER BY i.data_creazione",
        (session["utente_id"],),
    ).fetchall()

    gruppi_completi = []
    for gr in gruppi:
        versamenti = db.execute(
            "SELECT * FROM versamenti WHERE iscrizione_id = ? ORDER BY data_creazione",
            (gr["id"],),
        ).fetchall()
        versamenti_con_partecipanti = []
        for versamento in versamenti:
            partecipanti = db.execute(
                "SELECT * FROM partecipanti WHERE versamento_id = ? ORDER BY data_creazione",
                (versamento["id"],),
            ).fetchall()
            versamenti_con_partecipanti.append({"versamento": versamento, "partecipanti": partecipanti})
        gruppi_completi.append({"gruppo": gr, "versamenti": versamenti_con_partecipanti})

    categorie_disponibili = db.execute(
        "SELECT * FROM categorie WHERE id NOT IN "
        "(SELECT categoria_id FROM iscrizioni WHERE utente_id = ?) ORDER BY ordine",
        (session["utente_id"],),
    ).fetchall()

    contenuti = get_contenuti(db)
    return render_template(
        "account.html",
        gruppi=gruppi_completi,
        categorie_disponibili=categorie_disponibili,
        c=contenuti,
    )


@app.route("/account/nuovo-gruppo/<slug>", methods=["GET", "POST"])
@utente_login_required
def account_nuovo_gruppo(slug):
    db = get_db()
    categoria = db.execute("SELECT * FROM categorie WHERE slug = ?", (slug,)).fetchone()
    if categoria is None:
        abort(404)

    esistente = db.execute(
        "SELECT * FROM iscrizioni WHERE utente_id = ? AND categoria_id = ?",
        (session["utente_id"], categoria["id"]),
    ).fetchone()
    if esistente:
        flash("Hai già un'iscrizione in questa categoria: aggiungi lì i partecipanti.", "successo")
        return redirect(url_for("account"))

    if request.method == "POST":
        nome_gruppo = request.form.get("nome_gruppo", "").strip()
        dettagli = request.form.get("dettagli", "").strip()
        elenco_nomi = request.form.get("elenco_nomi", "")
        nomi = [n.strip() for n in elenco_nomi.splitlines() if n.strip()]

        if not nome_gruppo:
            flash("Il nome del gruppo è obbligatorio.", "errore")
            contenuti = get_contenuti(db)
            return render_template("nuovo_gruppo.html", categoria=categoria, c=contenuti, form=request.form)

        if not nomi:
            flash("Inserisci almeno un nome di partecipante.", "errore")
            contenuti = get_contenuti(db)
            return render_template("nuovo_gruppo.html", categoria=categoria, c=contenuti, form=request.form)

        cur = db.execute(
            "INSERT INTO iscrizioni (utente_id, categoria_id, nome_gruppo, dettagli) "
            "VALUES (?, ?, ?, ?)",
            (session["utente_id"], categoria["id"], nome_gruppo, dettagli),
        )
        iscrizione_id = cur.lastrowid

        codice = nuovo_codice(slug)
        cur2 = db.execute(
            "INSERT INTO versamenti (iscrizione_id, codice_riferimento) VALUES (?, ?)",
            (iscrizione_id, codice),
        )
        versamento_id = cur2.lastrowid
        db.executemany(
            "INSERT INTO partecipanti (versamento_id, nome) VALUES (?, ?)",
            [(versamento_id, n) for n in nomi],
        )
        db.commit()
        flash(
            f"Iscrizione creata per {categoria['nome']} — {len(nomi)} partecipant"
            f"{'e' if len(nomi)==1 else 'i'}. Il codice per il bonifico è {codice}.",
            "successo",
        )
        return redirect(url_for("account"))

    contenuti = get_contenuti(db)
    return render_template("nuovo_gruppo.html", categoria=categoria, c=contenuti, form={})


@app.route("/account/gruppo/<int:iscrizione_id>/aggiungi", methods=["POST"])
@utente_login_required
def account_aggiungi_partecipante(iscrizione_id):
    db = get_db()
    gruppo = db.execute(
        "SELECT i.*, c.slug, c.nome as categoria_nome FROM iscrizioni i "
        "JOIN categorie c ON i.categoria_id = c.id WHERE i.id = ?",
        (iscrizione_id,),
    ).fetchone()
    if gruppo is None or gruppo["utente_id"] != session["utente_id"]:
        abort(403)

    nomi_raw = request.form.get("nomi", "")
    nomi = [n.strip() for n in nomi_raw.splitlines() if n.strip()]
    if not nomi:
        flash("Inserisci almeno un nome (uno per riga).", "errore")
        return redirect(url_for("account"))

    codice = nuovo_codice(gruppo["slug"])
    cur = db.execute(
        "INSERT INTO versamenti (iscrizione_id, codice_riferimento) VALUES (?, ?)",
        (iscrizione_id, codice),
    )
    versamento_id = cur.lastrowid
    db.executemany(
        "INSERT INTO partecipanti (versamento_id, nome) VALUES (?, ?)",
        [(versamento_id, n) for n in nomi],
    )
    db.commit()
    flash(
        f"{len(nomi)} partecipant{'e' if len(nomi)==1 else 'i'} aggiunt{'o' if len(nomi)==1 else 'i'} "
        f"a {gruppo['categoria_nome']}. Il codice da scrivere nella causale del bonifico è: {codice}",
        "successo",
    )
    return redirect(url_for("account"))


@app.route("/account/versamento/<int:versamento_id>/elimina", methods=["POST"])
@utente_login_required
def account_elimina_versamento(versamento_id):
    db = get_db()
    versamento = db.execute(
        "SELECT l.*, i.utente_id FROM versamenti l "
        "JOIN iscrizioni i ON l.iscrizione_id = i.id WHERE l.id = ?",
        (versamento_id,),
    ).fetchone()
    if versamento is None or versamento["utente_id"] != session["utente_id"]:
        abort(403)
    if versamento["stato_pagamento"] == "pagato":
        flash("Non puoi rimuovere un versamento già segnato come pagato: contatta il comitato.", "errore")
        return redirect(url_for("account"))
    db.execute("DELETE FROM partecipanti WHERE versamento_id = ?", (versamento_id,))
    db.execute("DELETE FROM versamenti WHERE id = ?", (versamento_id,))
    db.commit()
    flash("Versamento rimosso.", "successo")
    return redirect(url_for("account"))


@app.route("/account/elimina", methods=["GET", "POST"])
@utente_login_required
def account_elimina():
    db = get_db()
    utente = db.execute("SELECT * FROM utenti WHERE id = ?", (session["utente_id"],)).fetchone()

    if request.method == "POST":
        password = request.form.get("password", "")
        conferma_testo = request.form.get("conferma_testo", "").strip().upper()

        if conferma_testo != "ELIMINA":
            flash('Scrivi ELIMINA (tutto maiuscolo) per confermare.', "errore")
            return render_template("account_elimina.html")
        if not check_password_hash(utente["password_hash"], password):
            flash("Password errata.", "errore")
            return render_template("account_elimina.html")

        elimina_utente_e_dati(db, session["utente_id"])
        session.clear()
        flash("Il tuo account e tutte le tue iscrizioni sono stati eliminati definitivamente.", "successo")
        return redirect(url_for("home"))

    return render_template("account_elimina.html")


# ---------------------------------------------------------------------------
# Admin — autenticazione
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        chiave_tentativi = f"admin:{request.remote_addr}:{username}"
        if troppi_tentativi(chiave_tentativi):
            flash("Troppi tentativi falliti. Riprova tra qualche minuto.", "errore")
            return render_template("admin/login.html")
        db = get_db()
        user = db.execute("SELECT * FROM admin WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["admin_id"] = user["id"]
            session["admin_username"] = user["username"]
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        registra_tentativo_fallito(chiave_tentativi)
        flash("Username o password errati.", "errore")
    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    return redirect(url_for("admin_login"))


# ---------------------------------------------------------------------------
# Admin — dashboard
# ---------------------------------------------------------------------------

@app.route("/admin/")
@admin_login_required
def admin_dashboard():
    db = get_db()
    totale_iscrizioni = db.execute("SELECT COUNT(*) n FROM partecipanti").fetchone()["n"]
    totale_pagati = db.execute(
        "SELECT COUNT(*) n FROM partecipanti p JOIN versamenti l ON p.versamento_id = l.id "
        "WHERE l.stato_pagamento = 'pagato'"
    ).fetchone()["n"]
    totale_utenti = db.execute("SELECT COUNT(*) n FROM utenti").fetchone()["n"]
    per_categoria = db.execute(
        "SELECT c.nome, COUNT(DISTINCT i.id) gruppi, COUNT(p.id) partecipanti "
        "FROM categorie c "
        "LEFT JOIN iscrizioni i ON i.categoria_id = c.id "
        "LEFT JOIN versamenti l ON l.iscrizione_id = i.id "
        "LEFT JOIN partecipanti p ON p.versamento_id = l.id "
        "GROUP BY c.id ORDER BY c.ordine"
    ).fetchall()
    incasso_atteso = db.execute(
        "SELECT COALESCE(SUM(c.prezzo_quota),0) tot FROM partecipanti p "
        "JOIN versamenti l ON p.versamento_id = l.id "
        "JOIN iscrizioni i ON l.iscrizione_id = i.id "
        "JOIN categorie c ON i.categoria_id = c.id"
    ).fetchone()["tot"]
    incasso_incassato = db.execute(
        "SELECT COALESCE(SUM(c.prezzo_quota),0) tot FROM partecipanti p "
        "JOIN versamenti l ON p.versamento_id = l.id "
        "JOIN iscrizioni i ON l.iscrizione_id = i.id "
        "JOIN categorie c ON i.categoria_id = c.id "
        "WHERE l.stato_pagamento = 'pagato'"
    ).fetchone()["tot"]
    return render_template(
        "admin/dashboard.html",
        totale_iscrizioni=totale_iscrizioni,
        totale_pagati=totale_pagati,
        totale_utenti=totale_utenti,
        per_categoria=per_categoria,
        incasso_atteso=incasso_atteso,
        incasso_incassato=incasso_incassato,
    )


@app.route("/admin/iscrizioni")
@admin_login_required
def admin_iscrizioni():
    db = get_db()
    filtro_categoria = request.args.get("categoria", "")
    filtro_stato = request.args.get("stato", "")
    filtro_gruppo = request.args.get("gruppo", "")

    query = (
        "SELECT l.id as versamento_id, l.codice_riferimento, l.stato_pagamento, l.data_creazione, "
        "i.id as iscrizione_id, i.nome_gruppo, i.dettagli, "
        "u.nome as utente_nome, u.email as utente_email, u.telefono as utente_telefono, "
        "c.nome as categoria_nome, c.slug as categoria_slug, c.prezzo_quota, "
        "(SELECT GROUP_CONCAT(p2.nome, char(10)) FROM partecipanti p2 "
        " WHERE p2.versamento_id = l.id ORDER BY p2.data_creazione, p2.id) as nomi_partecipanti, "
        "(SELECT COUNT(*) FROM partecipanti p2 WHERE p2.versamento_id = l.id) as num_partecipanti "
        "FROM versamenti l "
        "JOIN iscrizioni i ON l.iscrizione_id = i.id "
        "JOIN utenti u ON i.utente_id = u.id "
        "JOIN categorie c ON i.categoria_id = c.id "
        "WHERE 1=1"
    )
    params = []
    if filtro_categoria:
        query += " AND c.slug = ?"
        params.append(filtro_categoria)
    if filtro_stato:
        query += " AND l.stato_pagamento = ?"
        params.append(filtro_stato)
    if filtro_gruppo:
        query += " AND i.id = ?"
        params.append(filtro_gruppo)
    query += " ORDER BY l.data_creazione DESC"

    versamenti = db.execute(query, params).fetchall()
    categorie = db.execute("SELECT * FROM categorie ORDER BY ordine").fetchall()
    gruppi_disponibili = db.execute(
        "SELECT i.id, i.nome_gruppo, u.nome as utente_nome, c.nome as categoria_nome "
        "FROM iscrizioni i JOIN utenti u ON i.utente_id = u.id "
        "JOIN categorie c ON i.categoria_id = c.id ORDER BY c.ordine, u.nome"
    ).fetchall()
    return render_template(
        "admin/iscrizioni.html",
        versamenti=versamenti,
        categorie=categorie,
        gruppi_disponibili=gruppi_disponibili,
        filtro_categoria=filtro_categoria,
        filtro_stato=filtro_stato,
        filtro_gruppo=filtro_gruppo,
    )


@app.route("/admin/versamento/<int:versamento_id>/stato", methods=["POST"])
@admin_login_required
def admin_cambia_stato(versamento_id):
    nuovo_stato = request.form.get("stato")
    if nuovo_stato not in ("in_attesa", "pagato"):
        abort(400)
    db = get_db()
    db.execute(
        "UPDATE versamenti SET stato_pagamento = ? WHERE id = ?",
        (nuovo_stato, versamento_id),
    )
    db.commit()
    flash("Stato aggiornato.", "successo")
    return redirect(request.referrer or url_for("admin_iscrizioni"))


@app.route("/admin/versamento/<int:versamento_id>/elimina", methods=["POST"])
@admin_login_required
def admin_elimina_versamento(versamento_id):
    db = get_db()
    db.execute("DELETE FROM partecipanti WHERE versamento_id = ?", (versamento_id,))
    db.execute("DELETE FROM versamenti WHERE id = ?", (versamento_id,))
    db.commit()
    flash("Versamento eliminato.", "successo")
    return redirect(url_for("admin_iscrizioni"))


@app.route("/admin/iscrizioni/export.pdf")
@admin_login_required
def admin_export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    )

    db = get_db()
    categorie = db.execute("SELECT * FROM categorie ORDER BY ordine").fetchall()

    ROSSO = colors.HexColor("#C1392B")
    ORO = colors.HexColor("#E7A93C")
    GRIGIO_TESTO = colors.HexColor("#3a332a")
    GRIGIO_CHIARO = colors.HexColor("#f2ece0")

    styles = getSampleStyleSheet()
    stile_titolo = ParagraphStyle("TitoloDoc", parent=styles["Title"], textColor=ROSSO, fontSize=20, spaceAfter=2)
    stile_sottotitolo = ParagraphStyle("Sottotitolo", parent=styles["Normal"], textColor=GRIGIO_TESTO, fontSize=9, spaceAfter=16)
    stile_categoria = ParagraphStyle("Categoria", parent=styles["Heading2"], textColor=ROSSO, fontSize=14,
                                      spaceBefore=18, spaceAfter=8, borderPadding=0)
    stile_gruppo = ParagraphStyle("Gruppo", parent=styles["Heading3"], textColor=GRIGIO_TESTO, fontSize=11,
                                   spaceBefore=10, spaceAfter=4)
    stile_meta = ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.HexColor("#7a6f58"), fontSize=8.5, spaceAfter=6)
    stile_vuoto = ParagraphStyle("Vuoto", parent=styles["Normal"], textColor=colors.HexColor("#7a6f58"), fontSize=9, spaceAfter=10)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=16 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )

    elementi = []
    elementi.append(Paragraph("Carnevale Grammichelese — Elenco iscrizioni", stile_titolo))
    elementi.append(Paragraph(
        f"Esportato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}", stile_sottotitolo
    ))

    totale_generale_partecipanti = 0
    totale_generale_pagati = 0

    for cat in categorie:
        gruppi = db.execute(
            "SELECT i.*, u.nome as utente_nome, u.email as utente_email, u.telefono as utente_telefono "
            "FROM iscrizioni i JOIN utenti u ON i.utente_id = u.id "
            "WHERE i.categoria_id = ? ORDER BY i.data_creazione",
            (cat["id"],),
        ).fetchall()

        if not gruppi:
            continue

        elementi.append(Paragraph(cat["nome"], stile_categoria))

        for gr in gruppi:
            partecipanti = db.execute(
                "SELECT p.nome, p.data_creazione, v.stato_pagamento, v.codice_riferimento "
                "FROM partecipanti p JOIN versamenti v ON p.versamento_id = v.id "
                "WHERE v.iscrizione_id = ? ORDER BY p.data_creazione",
                (gr["id"],),
            ).fetchall()
            if not partecipanti:
                continue

            n_tot = len(partecipanti)
            n_pagati = sum(1 for p in partecipanti if p["stato_pagamento"] == "pagato")
            totale_generale_partecipanti += n_tot
            totale_generale_pagati += n_pagati

            blocco = []
            titolo_gruppo = gr["nome_gruppo"] or gr["utente_nome"]
            blocco.append(Paragraph(titolo_gruppo, stile_gruppo))
            blocco.append(Paragraph(
                f"Referente: {gr['utente_nome']} — {gr['utente_email']}"
                + (f" — {gr['utente_telefono']}" if gr["utente_telefono"] else "")
                + f" &nbsp;|&nbsp; {n_pagati}/{n_tot} pagati",
                stile_meta,
            ))

            dati_tabella = [["Partecipante", "Stato", "Codice versamento"]]
            for p in partecipanti:
                stato_testo = "Pagato" if p["stato_pagamento"] == "pagato" else "In attesa"
                dati_tabella.append([p["nome"], stato_testo, p["codice_riferimento"]])

            tabella = Table(dati_tabella, colWidths=[70 * mm, 30 * mm, 60 * mm])
            stile_tabella = TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GRIGIO_CHIARO),
                ("TEXTCOLOR", (0, 0), (-1, 0), GRIGIO_TESTO),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#d8cfb8")),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#ece4d0")),
                ("TEXTCOLOR", (0, 1), (-1, -1), GRIGIO_TESTO),
            ])
            for idx, p in enumerate(partecipanti, start=1):
                if p["stato_pagamento"] == "pagato":
                    stile_tabella.add("TEXTCOLOR", (1, idx), (1, idx), colors.HexColor("#1f6e68"))
                else:
                    stile_tabella.add("TEXTCOLOR", (1, idx), (1, idx), ORO)
            tabella.setStyle(stile_tabella)
            blocco.append(tabella)
            blocco.append(Spacer(1, 4))

            elementi.append(KeepTogether(blocco))

    if totale_generale_partecipanti == 0:
        elementi.append(Paragraph("Nessuna iscrizione ricevuta ancora.", stile_vuoto))
    else:
        elementi.append(Spacer(1, 14))
        elementi.append(Paragraph(
            f"Totale generale: {totale_generale_partecipanti} partecipanti — "
            f"{totale_generale_pagati} pagati, {totale_generale_partecipanti - totale_generale_pagati} in attesa.",
            ParagraphStyle("Totale", parent=styles["Normal"], fontSize=10, textColor=GRIGIO_TESTO),
        ))

    doc.build(elementi)
    buffer.seek(0)
    return send_file(
        buffer, mimetype="application/pdf", as_attachment=True,
        download_name=f"iscrizioni_carnevale_{datetime.now().strftime('%Y%m%d')}.pdf",
    )


@app.route("/admin/contenuti", methods=["GET", "POST"])
@admin_login_required
def admin_contenuti():
    db = get_db()
    if request.method == "POST":
        for chiave, valore in request.form.items():
            if chiave not in CHIAVI_CONTENUTI_VALIDE:
                continue
            db.execute(
                "INSERT INTO contenuti (chiave, valore) VALUES (?, ?) "
                "ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore",
                (chiave, valore),
            )
        db.commit()
        flash("Contenuti aggiornati.", "successo")
        return redirect(url_for("admin_contenuti"))

    contenuti = get_contenuti(db)
    categorie = db.execute("SELECT * FROM categorie ORDER BY ordine").fetchall()
    return render_template("admin/contenuti.html", c=contenuti, categorie=categorie)


@app.route("/admin/categorie/<int:categoria_id>", methods=["POST"])
@admin_login_required
def admin_modifica_categoria(categoria_id):
    db = get_db()
    db.execute(
        "UPDATE categorie SET nome=?, descrizione=?, regolamento=?, prezzo_quota=?, dettagli_label=? "
        "WHERE id=?",
        (
            request.form.get("nome"),
            request.form.get("descrizione"),
            request.form.get("regolamento"),
            float(request.form.get("prezzo_quota") or 0),
            request.form.get("dettagli_label"),
            categoria_id,
        ),
    )
    db.commit()
    flash("Categoria aggiornata.", "successo")
    return redirect(url_for("admin_contenuti"))


@app.route("/admin/programma", methods=["GET", "POST"])
@admin_login_required
def admin_programma():
    db = get_db()
    if request.method == "POST":
        db.execute(
            "INSERT INTO programma (giorno_label, giorno_ordine, orario, titolo, descrizione, ordine) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                request.form.get("giorno_label"),
                int(request.form.get("giorno_ordine") or 0),
                request.form.get("orario"),
                request.form.get("titolo"),
                request.form.get("descrizione"),
                int(request.form.get("ordine") or 0),
            ),
        )
        db.commit()
        flash("Evento aggiunto al programma.", "successo")
        return redirect(url_for("admin_programma"))

    eventi = db.execute("SELECT * FROM programma ORDER BY giorno_ordine, ordine").fetchall()
    return render_template("admin/programma.html", eventi=eventi)


@app.route("/admin/programma/<int:evento_id>/elimina", methods=["POST"])
@admin_login_required
def admin_elimina_evento(evento_id):
    db = get_db()
    db.execute("DELETE FROM programma WHERE id = ?", (evento_id,))
    db.commit()
    flash("Evento eliminato.", "successo")
    return redirect(url_for("admin_programma"))


@app.route("/admin/galleria", methods=["GET", "POST"])
@admin_login_required
def admin_galleria():
    db = get_db()
    if request.method == "POST":
        file = request.files.get("immagine")
        didascalia = request.form.get("didascalia", "")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(f"{secrets.token_hex(4)}_{file.filename}")
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            db.execute(
                "INSERT INTO galleria (immagine_filename, didascalia) VALUES (?, ?)",
                (filename, didascalia),
            )
            db.commit()
            flash("Immagine caricata.", "successo")
        else:
            flash("File non valido. Usa PNG, JPG o WEBP.", "errore")
        return redirect(url_for("admin_galleria"))

    immagini = db.execute("SELECT * FROM galleria ORDER BY ordine, id").fetchall()
    return render_template("admin/galleria.html", immagini=immagini)


@app.route("/admin/galleria/<int:img_id>/elimina", methods=["POST"])
@admin_login_required
def admin_elimina_immagine(img_id):
    db = get_db()
    img = db.execute("SELECT * FROM galleria WHERE id = ?", (img_id,)).fetchone()
    if img:
        path = os.path.join(app.config["UPLOAD_FOLDER"], img["immagine_filename"])
        if os.path.exists(path):
            os.remove(path)
        db.execute("DELETE FROM galleria WHERE id = ?", (img_id,))
        db.commit()
        flash("Immagine eliminata.", "successo")
    return redirect(url_for("admin_galleria"))


@app.route("/admin/utenti")
@admin_login_required
def admin_utenti():
    db = get_db()
    utenti = db.execute(
        "SELECT u.*, COUNT(DISTINCT i.id) n_gruppi, COUNT(p.id) n_partecipanti "
        "FROM utenti u "
        "LEFT JOIN iscrizioni i ON i.utente_id = u.id "
        "LEFT JOIN versamenti l ON l.iscrizione_id = i.id "
        "LEFT JOIN partecipanti p ON p.versamento_id = l.id "
        "GROUP BY u.id ORDER BY u.data_creazione DESC"
    ).fetchall()
    return render_template("admin/utenti.html", utenti=utenti)


def elimina_utente_e_dati(db, utente_id):
    """Elimina un utente e a cascata tutte le sue iscrizioni, versamenti e partecipanti."""
    iscrizioni_ids = [
        r["id"] for r in db.execute(
            "SELECT id FROM iscrizioni WHERE utente_id = ?", (utente_id,)
        ).fetchall()
    ]
    for iscrizione_id in iscrizioni_ids:
        versamenti_ids = [
            r["id"] for r in db.execute(
                "SELECT id FROM versamenti WHERE iscrizione_id = ?", (iscrizione_id,)
            ).fetchall()
        ]
        for versamento_id in versamenti_ids:
            db.execute("DELETE FROM partecipanti WHERE versamento_id = ?", (versamento_id,))
        db.execute("DELETE FROM versamenti WHERE iscrizione_id = ?", (iscrizione_id,))
    db.execute("DELETE FROM iscrizioni WHERE utente_id = ?", (utente_id,))
    db.execute("DELETE FROM utenti WHERE id = ?", (utente_id,))
    db.commit()


@app.route("/admin/utenti/<int:utente_id>/reset-password", methods=["POST"])
@admin_login_required
def admin_reset_password_utente(utente_id):
    db = get_db()
    utente = db.execute("SELECT * FROM utenti WHERE id = ?", (utente_id,)).fetchone()
    if utente is None:
        abort(404)
    nuova_password = secrets.token_urlsafe(6)  # facile da leggere e comunicare a voce/telefono
    db.execute(
        "UPDATE utenti SET password_hash = ? WHERE id = ?",
        (generate_password_hash(nuova_password), utente_id),
    )
    db.commit()
    flash(
        f"Nuova password temporanea per {utente['nome']} ({utente['email']}): {nuova_password} "
        f"— comunicagliela tu (telefono/email), non è stata inviata automaticamente.",
        "successo",
    )
    return redirect(url_for("admin_utenti"))


@app.route("/admin/utenti/<int:utente_id>/elimina", methods=["POST"])
@admin_login_required
def admin_elimina_utente(utente_id):
    db = get_db()
    utente = db.execute("SELECT * FROM utenti WHERE id = ?", (utente_id,)).fetchone()
    if utente is None:
        abort(404)
    elimina_utente_e_dati(db, utente_id)
    flash(
        f"Account di {utente['nome']} ({utente['email']}) eliminato, insieme a tutte le sue "
        f"iscrizioni e versamenti.",
        "successo",
    )
    return redirect(url_for("admin_utenti"))


@app.route("/admin/password", methods=["GET", "POST"])
@admin_login_required
def admin_password():
    if request.method == "POST":
        attuale = request.form.get("attuale", "")
        nuova = request.form.get("nuova", "")
        conferma = request.form.get("conferma", "")
        db = get_db()
        user = db.execute("SELECT * FROM admin WHERE id = ?", (session["admin_id"],)).fetchone()
        if not check_password_hash(user["password_hash"], attuale):
            flash("Password attuale errata.", "errore")
        elif len(nuova) < 8:
            flash("La nuova password deve avere almeno 8 caratteri.", "errore")
        elif nuova != conferma:
            flash("Le due password non coincidono.", "errore")
        else:
            db.execute(
                "UPDATE admin SET password_hash = ? WHERE id = ?",
                (generate_password_hash(nuova), user["id"]),
            )
            db.commit()
            flash("Password cambiata con successo.", "successo")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin/password.html")


init_db()  # va eseguito sempre: sia con "python app.py" sia con gunicorn

if __name__ == "__main__":
    # In locale, mentre sviluppiamo, il debug resta attivo di default (comodo: si
    # riavvia da solo a ogni modifica). Se un giorno questo sito girerà raggiungibile
    # da internet, avvia con la variabile d'ambiente FLASK_DEBUG=0 per disattivarlo.
    debug_mode = os.environ.get("FLASK_DEBUG", "1") != "0"
    app.run(debug=debug_mode, port=5000)
