# BRYT — TODO / Backlog

Da implementare dopo aver completato lo Step 5 (5.3 → 5.6).

---

## 1. Sonno e benessere quotidiano (priorità alta)

### Problema
Oggi il sonno arriva solo dai tag dichiarati **dopo una corsa**:
- nei giorni di riposo non si raccoglie nulla (proprio quelli che dicono se l'atleta recupera);
- chi corre la sera ricorda peggio la notte precedente;
- molti atleti (es. Andrea) indossano lo smartwatch solo durante la corsa: nessun dato notturno.

Le misure soggettive di benessere sono valide e usate nello sport d'élite (Saw, Main & Gastin,
BJSM 2016: le misure auto-riferite riflettono il carico meglio di molte misure oggettive):
il dato dichiarato resta la base, l'automatico è un complemento.

### 1a. Check-in mattutino ✅ (16/11/2026)
- Fatto in versione minima per decisione dell'utente (impatto minimo sulla vita dell'atleta):
  solo **ore dormite** (fasce ≤5…9+) e **come ti senti** (emoji 1-5). Niente gambe, qualità
  del sonno o stress separati. Tabella `daily_wellness`, trend 7 vs 28 giorni agli agent,
  pre-compilazione del sonno nella modale dei tag.
- Da aggiungere con l'import 1b: colonna `source` (CHECKIN / INTERVALS) per distinguere il dato
  del dispositivo da quello dichiarato.

### 1b. Import automatico da Intervals.icu (chi ha un dispositivo notturno)
- Intervals.icu raccoglie i dati Wellness (sonno, HRV, FC a riposo, ecc.) dai dispositivi collegati.
- Endpoint indicato: `GET /api/v1/athlete/{id}/wellness` (range di date).
  **Da verificare sulla documentazione ufficiale prima di implementare**: path esatto, parametri,
  nomi dei campi (es. durata/punteggio del sonno, HRV, FC a riposo) e quali fonti sono davvero
  supportate (Garmin, Oura, Whoop, Polar, Apple Health?).
- Import nella stessa `daily_wellness` con `source = INTERVALS`; l'utente conferma o corregge.
- Valore aggiunto per gli agent: **HRV e FC a riposo** (trend) come indicatori oggettivi di
  prontezza, più utili del "punteggio sonno" proprietario dei dispositivi.
- Non sostituisce il check-in: per chi non porta il dispositivo di notte resta l'unica fonte.

### Fuori portata
Lettura del sonno da Apple Salute / Google Health Connect: richiede un'app nativa.

---

## 2. Altri punti emersi durante lo sviluppo

- **Sync periodica Intervals.icu**: con API key personale i webhook non sono disponibili (solo app
  OAuth registrate) → job periodico (es. ogni 30') oltre al pulsante manuale.
- **Fasce orarie multiple** nel profilo (es. mattina + a volte sera): oggi `preferred_slot` è singolo.
- **Stima automatica di FC max / FC soglia** dai file caricati (gare, test di ricalibrazione),
  invece di lasciarle vuote.
- **Pagina impostazioni/profilo** (`/settings`), al posto del wizard (oggi `/onboarding` è bloccato
  per chi ha un piano attivo e il link "Profilo e obiettivi" è stato rimosso):
  - sezioni (profilo, settimana, allenamento, Intervals.icu) ciascuna con il proprio "Salva",
    via `PATCH /me/profile` (esiste già);
  - cambio di gara/obiettivo: salvare non rigenera nulla; avviso "il piano è costruito sulla gara
    precedente" + pulsante "Rigenera il piano" con conferma esplicita e costo indicato.
- **Dislivello inaffidabile** (altitudine GPS): eventuale correzione con modello altimetrico (DEM).
- **Pianificazione pre-gara all'estero**: giorni di viaggio/fuso → protocollo intestino e sonno.
- **Piano senza gara che si rinnova da solo** (permanenza): a 2-3 settimane dalla fine del piano
  di 12 settimane il sistema propone il blocco successivo (una sola chiamata di blocco, costo
  contenuto) usando il risultato del test finale per ricalibrare le zone. Nello stesso momento
  chiede "Hai trovato una gara?": se sì, genera il piano verso la gara. Obiettivo: il piano non
  finisce mai, così la fine del piano non diventa il momento in cui l'utente abbandona.
- **Modello più economico per la chat del coach**: oggi tutti gli agent usano `ANTHROPIC_MODEL`
  (Opus). Per la chat (domande frequenti, effort `low`) valutare un modello più economico (es.
  Sonnet 5.5) con un setting dedicato per agent (es. `COACH_CHAT_MODEL`), confrontando qualità
  delle risposte e costo sugli stessi messaggi prima di cambiarlo.
- **Servizio email esterno per Supabase Auth** (SMTP personalizzato, es. Resend/Postmark): quello
  incluso ha limiti di invio molto bassi, ok solo per i primi alpha tester. Serve anche per il
  reset della password (oggi assente).
- **Skill Supabase (`supabase/agent-skills`)**: leggerne il contenuto e valutarle al passaggio in
  produzione (database Supabase, RLS, migrazioni, storage dei `.fit`).
- **Riferimento 28 giorni più intelligente** ✅ (16/11/2026): copertura giudicata sulle 8 settimane,
  volume abituale + km settimanali + gare recenti con finestra di recupero passati agli agent.
- **Webhook Intervals.icu (produzione)**: registrare BRYT come app OAuth su Intervals.icu
  ("Accedi con Intervals" al posto della API key) → webhook `ACTIVITY_UPLOADED` in tempo reale;
  il poll ogni 15' resta come rete di sicurezza.
- **Superficie dal tracciato GPS**: incrociare il percorso con OpenStreetMap (`surface`/
  `highway` delle strade) per distinguere asfalto e sterrato anche nelle "Corsa" generiche;
  renderebbe quasi superflua la superficie abituale (`PROFILE_DEFAULT`).
