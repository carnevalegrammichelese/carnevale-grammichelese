# Sito Carnevale Grammichelese — versione custom (locale)

Sito completo scritto in Python (Flask) con database proprio (SQLite) e dashboard di
amministrazione. Pensato per girare sul tuo computer.

## Come avviarlo la prima volta

1. **Installa Python** (se non ce l'hai già): scarica da https://www.python.org/downloads/
   durante l'installazione su Windows spunta "Add Python to PATH".

2. **Apri il terminale** (Prompt dei comandi su Windows, Terminale su Mac) dentro questa
   cartella (`carnevale-app`).

3. **Crea un ambiente virtuale e installa le dipendenze:**

   ```
   python -m venv venv
   ```

   Poi attivalo:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`

   Poi installa Flask:

   ```
   pip install -r requirements.txt
   ```

4. **Avvia il sito:**

   ```
   python app.py
   ```

5. Apri il browser su **http://localhost:5000** — è il sito pubblico.

6. Il pannello di amministrazione è su **http://localhost:5000/admin/login**
   - Username: `admin`
   - Password: `carnevale2027`
   - **Cambia subito la password** dal menu "Cambia password" appena entri.

## Come si arresta

Torna nel terminale dove hai lanciato `python app.py` e premi `CTRL+C`.
La prossima volta basta ripetere il punto 4 (dopo aver riattivato l'ambiente virtuale
al punto 3, se hai chiuso il terminale).

## Dove sono salvati i dati

- **Iscrizioni, contenuti, programma**: tutto nel file `carnevale.db` (creato al primo
  avvio). È un file unico: per fare un backup, basta copiarlo altrove.
- **Foto della galleria**: nella cartella `static/img/galleria/`.
- **Logo**: metti il file del logo (PNG con sfondo trasparente) dentro `static/img/`
  e chiamalo esattamente `logo.png` — comparirà automaticamente in header e hero.

## Cosa può fare chi si iscrive (utenti pubblici)

- Crea un proprio account (email + password) da `/registrati`.
- Sceglie una categoria, crea il "gruppo" con i primi dati (tema, primo partecipante).
- Dal proprio account (`/account`) vede tutti i suoi gruppi e partecipanti, il loro
  stato di pagamento, e può **aggiungere nuovi partecipanti in qualsiasi momento**
  semplicemente tornando a fare login — senza dover ricompilare tutto da capo.
- Ogni partecipante aggiunto genera un proprio codice di riferimento e una propria
  quota da versare via bonifico (le coordinate bancarie, modificabili dalla dashboard
  admin, sono sempre mostrate nella pagina account).

## Cosa puoi fare dalla dashboard (/admin)

- **Panoramica**: statistiche su iscrizioni e incassi.
- **Utenti**: elenco di tutti gli account creati, con quanti gruppi e partecipanti hanno.
- **Iscrizioni**: elenco completo (un versamento per riga, con l'elenco dei suoi partecipanti), filtri per categoria/stato/gruppo, colonne ridimensionabili trascinando i bordi, segna "pagato" quando
  arriva il bonifico, esporta tutto in un PDF pulito organizzato per categoria e gruppo, elimina iscrizioni.
- **Utenti**: oltre all'elenco, puoi generare una password temporanea per chi la dimentica
  (comunicala tu stesso, via telefono o email — non viene inviata automaticamente).
- **Contenuti sito**: modifica i testi dell'hero, i 4 numeri statistici, IBAN e
  intestatario per il bonifico, indirizzo/email/social nel footer, e per ogni categoria
  (carro, gruppo, maschera singola, scuole): nome, descrizione, regolamento, prezzo
  della quota, etichetta del campo "dettagli" nel modulo.
- **Programma**: aggiungi/elimina gli eventi di ogni giornata della festa.
- **Galleria**: carica ed elimina le foto mostrate nella Home.
- **Cambia password**: per il tuo account amministratore.

## Password dimenticata

- **Utenti** (chi si iscrive): ora hanno un vero recupero **da soli**, cliccando
  "Password dimenticata?" nella pagina di accesso — ma perché arrivi davvero
  l'email, va configurato l'invio (vedi sotto "Attivare l'invio email").
  Finché non lo configuri, il sito lo dice onestamente all'utente e lo
  indirizza a contattare il comitato — non finge di aver inviato nulla.
  In ogni caso, resta sempre disponibile anche la strada manuale: da
  Utenti > "Reimposta password" puoi generare tu una password temporanea
  e comunicarla direttamente a chi ne ha bisogno.
- **Amministratore**: se dimentichi la password admin, lancia da terminale
  (nella cartella del progetto, con l'ambiente virtuale attivo):

  ```
  python reset_admin_password.py
  ```

  Ti chiederà una nuova password e la imposta subito, senza bisogno di
  conoscere quella vecchia.

## Attivare l'invio email (per il recupero password degli utenti)

Il sito può inviare davvero l'email di recupero, ma serve collegarlo a una
casella email vera tramite 4 variabili d'ambiente, da impostare **prima** di
lanciare `python app.py`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=vostroindirizzo@gmail.com
SMTP_PASSWORD=xxxxxxxxxxxxxxxx
```

Con Gmail, `SMTP_PASSWORD` **non** è la password normale dell'account: va
creata una "Password per le app" da myaccount.google.com/apppasswords
(richiede la verifica in due passaggi attiva sull'account Google). Altri
provider email hanno un procedimento simile.

Su Windows, prima di lanciare `python app.py` nello stesso terminale:

```
set SMTP_HOST=smtp.gmail.com
set SMTP_PORT=587
set SMTP_USER=vostroindirizzo@gmail.com
set SMTP_PASSWORD=xxxxxxxxxxxxxxxx
python app.py
```

Se non le imposti, il sito funziona lo stesso: semplicemente il recupero
password via email resta disattivato, con il messaggio onesto di cui sopra.

## Nota importante sulla sicurezza

Questa versione è pensata per girare **in locale**, sul tuo computer, per lavorarci
con calma. Se un giorno deciderete di renderla raggiungibile pubblicamente da
internet, **non basta lasciarla così**: andrebbero rivisti hosting, chiave segreta
dell'app (`app.secret_key` in `app.py`, oggi generata a caso a ogni avvio — va resa
fissa e segreta), backup automatici e HTTPS. Parliamone insieme quando arriva quel
momento.
