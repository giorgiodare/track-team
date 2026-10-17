# Spec — Simulazione movimento giocatori (demo hackathon)

Stato: approvata dall'utente il 2026-10-17. Metodo: Spec-Driven Development
(spec → design → task → implementazione → verifica). Niente TDD: i test sono
evidenza di verifica scritta dopo/accanto al codice, non driver.

## 1. Outcome

Backend Python/FastAPI che simula 11 giocatori di una squadra. All'avvio sono
sparsi in posizioni sbagliate; si ricompongono in un **4-4-2 a rombo** corretto;
poi eseguono uno scenario di **attacco** e uno di **difesa**. Frontend e
triangolazione dai 4 sensori agli angoli arriveranno da altri branch: questo
componente espone la *ground truth* del movimento con un contratto stabile.

## 2. Scope / Non-goals

In scope: motore di movimento deterministico, macchina a fasi, metriche,
API REST + WebSocket, esempio di frame per gli altri branch.

Non-goals: solver di triangolazione/trilaterazione, avversari, fisica della
palla realistica, persistenza, autenticazione, UI.

## 3. Contratto dati

- Campo: 105 × 68 m. Origine `(0,0)` in un angolo, `x` = lunghezza
  (attacco verso `x` crescente), `y` = larghezza. Stesse coordinate dei
  4 sensori d'angolo: `(0,0)`, `(105,0)`, `(0,68)`, `(105,68)`.
- Unità: metri, m/s, secondi. Tick interno `dt = 0.1 s`, broadcast 10 Hz.
- Formazione 4-4-2 a rombo (11): GK; 4 difensori; rombo di centrocampo
  (mediano basso, 2 mezzali, trequartista); 2 punte. Slot in `formations.py`,
  modificabili senza toccare il motore.
- Frame WebSocket/REST (`Frame`): `t`, `phase`, `ball {x,y}`,
  `players[] {id, role, x, y, vx, vy, speed, distance_m}`,
  `metrics {formation_error_m, centroid {x,y}, team_length_m, team_width_m,
  line_gap_def_mid_m, line_gap_mid_att_m}`.
- `formation_error_m`: distanza media dei giocatori di movimento dal proprio
  slot. Deve partire alta (posizioni sbagliate) e scendere `< 1 m` a
  ricomposizione avvenuta: è la metrica centrale della demo.

## 4. Comportamento

Fasi (`Phase`): `scattered → forming → attack ⇄ defense` (`idle` prima dell'avvio).

- `scattered`: posizioni iniziali = slot + jitter deterministico da seed,
  alcuni giocatori fuori linea. Nessun movimento.
- `forming`: ogni giocatore raggiunge il proprio slot con steering limitato
  da velocità/accelerazione per ruolo, separazione anti-collisione (~0.8 m),
  smorzamento in arrivo.
- `attack`: la squadra avanza, si allarga e fa corse scriptate a waypoint
  (sovrapposizione terzino, inserimento mezzala, punte che attaccano l'area);
  palla che progredisce verso `x ≈ 95`.
- `defense`: la squadra arretra, si compatta (~25–35 m di lunghezza), scivola
  lateralmente verso il lato palla; la punta più vicina pressa e rientra.
- Transizioni sempre morbide: cambiano i target, mai teleport dei giocatori.
- `run-demo`: sequenza automatica da palco
  `scattered (3 s) → forming → attack (18 s) → defense (18 s) → attack …`.

## 4ter. Pattern d'attacco (dal video di riferimento)

Schema estratto dal video "Attacking Patterns in a 4-4-2"
(youtube.com/watch?v=m4IYapfmCv4, animazione tattica 20 s): costruzione
centrale, palla larga sulla fascia, terzino che sovrappone fino al fondo,
cross per le due punte su primo/secondo palo, conclusione, recupero e
ripartenza sull'altra fascia. Il video usa un 4-4-2 piatto; qui è tradotto
nei ruoli del rombo: la fascia la creano mezzala + terzino.

Ciclo d'attacco di 16 s, fascia alternata a ogni ciclo:

1. Costruzione (0–5 s): palla al mediano P6, squadra che sale compatta.
2. Uscita larga (5–9 s): palla alla mezzala di fascia, il terzino dello
   stesso lato sovrappone fino alla linea di fondo (x ≥ 85).
3. Cross e conclusione (9–12 s): cross del terzino, punta vicina sul primo
   palo e lontana sul secondo (x ≥ 90), trequartista al limite; tiro in
   porta (palla a x ≥ 100).
4. Recupero (12–16 s): rientro verso le posizioni d'attacco; ciclo
   successivo sulla fascia opposta.

Sequenza palla sincronizzata: P6 → mezzala di fascia → trequartista →
terzino in sovrapposizione → punta primo palo → porta.

- AC-12: in 32 s di `attack` entrambi i terzini superano x = 85 m (uno
  per fascia), almeno una punta supera x = 90 m e la palla supera
  x = 100 m (conclusione).

## 4bis. Palla coerente con i giocatori

La palla non segue un percorso indipendente: dipende dai giocatori.

- `scattered`/`forming`: palla ferma al centro (52.5, 34).
- `attack`: possesso a catena P6→P7→P9→P10→P9→P8→P11→P6. Chi ha palla la
  tiene a ~0.8 m davanti a sé e la segue; dopo ~1.6 s passa al compagno
  successivo: la palla viaggia verso la posizione *attuale* del ricevente
  (che si muove) a 18 m/s, e al ricevimento il possesso cambia.
- `defense`: palla avversaria che si muove (≤ 6 m/s) tra waypoint davanti
  al blocco (x ≥ 60); il blocco scivola verso il lato palla e P10 pressa.
- Al cambio scenario la palla può essere riposizionata (nuovo possesso);
  i giocatori non si teletrasportano mai.

- AC-10: in `attack`, in almeno metà dei frame la palla è entro 2.5 m da
  un giocatore, e in 12 s percorre più di 30 m.
- AC-11: in `defense`, la palla resta sempre a x ≥ 55 m (metà avversaria
  davanti al blocco) e dentro il campo.

## 5. Invarianti

- INV-1: `0 ≤ x ≤ 105`, `0 ≤ y ≤ 68` per giocatori e palla, sempre.
- INV-2: velocità ≤ `v_max` del ruolo (GK 5, DIF 7.5, CEN 8, ATT 9 m/s).
- INV-3: a parità di `seed` e sequenza di comandi, traiettorie identiche.
- INV-4: il motore (`engine.py`) non fa I/O: è testabile senza FastAPI.

## 6. API

| Metodo | Path | Effetto |
|---|---|---|
| GET | `/health` | `{status: "ok"}` |
| POST | `/simulation/start` | avvia da `scattered` |
| POST | `/simulation/pause` / `/simulation/resume` | congela/riprende |
| POST | `/simulation/reset?seed=7` | torna a `scattered` |
| POST | `/simulation/scenario/{forming,attack,defense}` | cambia fase |
| POST | `/simulation/run-demo` | sequenza automatica |
| GET | `/simulation/state` | ultimo `Frame` |
| WS | `/ws/positions` | primo frame immediato, poi ~10 Hz |

## 7. Acceptance criteria

- AC-01: `start` → frame in `scattered` con `formation_error_m ≥ 5 m`.
- AC-02: `scenario/forming` → entro 20 s simulati `formation_error_m < 1 m`.
- AC-03: `scenario/attack` → baricentro `x` medio > baricentro in `forming` + 10 m.
- AC-04: `scenario/defense` → baricentro `x` medio < baricentro in `attack`,
  e `team_length_m` in difesa < `team_length_m` in attacco.
- AC-05: INV-1/INV-2 valgono in ogni frame campionato per 60 s simulati.
- AC-06: stesso seed → stessi primi 50 frame (determinismo, INV-3).
- AC-07: WS invia il primo frame subito e poi frame con `t` crescente.
- AC-08: `examples/frame.json` è un `Frame` valido secondo i modelli Pydantic.

## 7bis. Export JSON

`track_team.export.write_trace(path, seed=7, seconds=65)` esegue `run-demo`
in-process e scrive un JSON con: metadati (campo, angoli sensori, seed, dt),
slot formazione, e tutti i frame (posizioni/velocità giocatori, palla,
metriche). Da posizioni e slot si possono ricalcolare le statistiche.
Wrapper: `uv run python scripts/export_trace.py [path] [seconds]`.
Default: `examples/simulation_trace.json`.

- AC-09: il JSON generato è valido, contiene frame di tutte le fasi
  (`scattered`, `forming`, `attack`, `defense`) e 11 giocatori per frame.

## 9. Replay da PostgreSQL (anti-lag)

Il frontend replay non scarica più l'intero JSON: i frame stanno in
PostgreSQL e arrivano a chunk da 100 frame (10 s). I dati restano a
10 fps nativi; il browser interpola a schermo (niente frame inventati).

Schema: `runs(id, name, seed, created_at, meta jsonb, slots jsonb)`,
`frames(run_id, idx, t, phase, ball_x, ball_y, metrics jsonb)`,
`player_positions(run_id, frame_idx, player_id, role, group, x, y, vx,
vy, speed, distance_m)` con PK `(run_id, frame_idx, player_id)`.
Connessione da `DATABASE_URL`; Postgres locale via `compose.yaml`.

API: `GET /runs`, `GET /runs/{id}` (meta/slot/durata/conteggio),
`GET /runs/{id}/frames?from_idx=0&limit=100`. Seed idempotente per nome:
`uv run python scripts/seed_db.py [nome] [secondi]`.

- AC-13: dopo il seed, DB contiene 650 frame e 650×11 posizioni per 65 s.
- AC-14: un chunk da 100 frame risponde in < 200 ms in locale e il primo
  frame del replay è servito senza scaricare l'intero trace.
- AC-15: il frontend carica da API a chunk con prefetch, mantiene il
  fallback da file JSON, e con `?fps=1` mostra il contatore fps.

## 8. Verifica pianificata

`uv run pytest` (smoke/accettazione su motore + API, non TDD),
`uv run ruff check`, `uv run mypy src/`, più prova live:
server uvicorn + `scripts/demo_probe.py` che stampa errore di formazione e
baricentro durante `run-demo`.
