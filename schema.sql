-- Schema del database — Sito Carnevale Grammichelese

CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS utenti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    telefono TEXT,
    password_hash TEXT NOT NULL,
    reset_token TEXT,
    reset_scadenza TEXT,
    data_creazione TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contenuti (
    chiave TEXT PRIMARY KEY,
    valore TEXT
);

CREATE TABLE IF NOT EXISTS categorie (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    nome TEXT NOT NULL,
    descrizione TEXT,
    regolamento TEXT,
    prezzo_quota REAL DEFAULT 0,
    dettagli_label TEXT DEFAULT 'Note aggiuntive',
    icona TEXT DEFAULT 'carro',
    ordine INTEGER DEFAULT 0
);

-- Un "gruppo": un utente può avere al massimo un'iscrizione per categoria
CREATE TABLE IF NOT EXISTS iscrizioni (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    utente_id INTEGER NOT NULL,
    categoria_id INTEGER NOT NULL,
    nome_gruppo TEXT,
    dettagli TEXT,
    data_creazione TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (utente_id) REFERENCES utenti(id),
    FOREIGN KEY (categoria_id) REFERENCES categorie(id),
    UNIQUE(utente_id, categoria_id)
);

-- Un "versamento": tutti i partecipanti aggiunti nella stessa operazione
-- condividono lo stesso codice e vengono pagati insieme.
CREATE TABLE IF NOT EXISTS versamenti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iscrizione_id INTEGER NOT NULL,
    codice_riferimento TEXT UNIQUE NOT NULL,
    stato_pagamento TEXT DEFAULT 'in_attesa',
    data_creazione TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (iscrizione_id) REFERENCES iscrizioni(id)
);

CREATE TABLE IF NOT EXISTS partecipanti (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    versamento_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    data_creazione TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (versamento_id) REFERENCES versamenti(id)
);

CREATE TABLE IF NOT EXISTS programma (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    giorno_label TEXT NOT NULL,
    giorno_ordine INTEGER DEFAULT 0,
    orario TEXT,
    titolo TEXT,
    descrizione TEXT,
    ordine INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS galleria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    immagine_filename TEXT NOT NULL,
    didascalia TEXT,
    ordine INTEGER DEFAULT 0
);
