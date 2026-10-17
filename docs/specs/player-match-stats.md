# Spec — Statistiche giocatori per partita

Stato: bozza del 2026-10-17, allineata al commit `d547df5` (replay da
PostgreSQL). Metodo: Spec-Driven Development, come
`docs/specs/player-simulation.md`. Dipende dal formato di export (§7bis) e
dallo storage PostgreSQL (§9) di quella spec.

## 1. Outcome

Nuova pagina della web app, **Statistiche partita**: scelgo una partita e
vedo una tabella con gli 11 giocatori e, per ciascuno:

- distanza percorsa;
- velocità media;
- numero di passaggi;
- numero di gol fatti;
- numero di parate (solo portiere).

Una partita corrisponde a **un JSON** nel formato di
`track_team.export.write_trace`, salvato in PostgreSQL come **run**
(`scripts/seed_db.py`). Le metriche sono calcolate nel **backend Python**
e la pagina si limita a mostrarle.

## 2. Scope / Non-goals

In scope: modulo di calcolo puro, modelli Pydantic, endpoint REST, pagina
`stats.html`.

Non-goals: modifiche al formato del JSON, al motore o allo schema DB
esistente, squadra avversaria, confronto tra più partite, grafici
temporali, cache/tabelle di statistiche precalcolate, autenticazione.

## 3. Input

- Una partita = un trace `{meta, slots, frames}` nel formato di
  `write_trace` (`src/track_team/export.py`). Due sorgenti, stessa forma:
  - **run in PostgreSQL** (sorgente principale): `meta`/`slots` da
    `db.get_run`, frame da `db.get_frames` (`src/track_team/db.py`), che
    ricostruisce già i frame nella forma dell'export;
  - **JSON caricato** dall'utente (upload), per partite non ancora nel DB.
- Campi usati: `meta.dt_s`, `meta.field_m`, `frames[].t`, `frames[].phase`,
  `frames[].ball {x, y}`, `frames[].players[] {id, role, group, x, y, speed,
  distance_m}`.
- Il JSON **non contiene eventi**: passaggi, gol e parate si ricavano
  dalle posizioni di palla e giocatori, frame per frame (§4).
- Id partita = `runs.id` (intero); nome = `runs.name` (es. `demo-65s`).
- Per le statistiche servono **tutti** i frame del run: si leggono in
  backend con `db.get_frames(conn, run_id, from_idx=0, limit=frame_count)`,
  senza il cap a 500 dell'endpoint di replay. I dati non passano dal
  browser.
- Frame ordinati per `t` crescente prima del calcolo.

## 4. Definizioni delle metriche

Parametri, tutti costanti in testa a `match_stats.py`:

| Costante | Valore | Significato |
|---|---|---|
| `POSSESSION_RADIUS_M` | 1.5 | distanza max palla–giocatore per avere palla |
| `POSSESSION_DEBOUNCE_FRAMES` | 3 | frame consecutivi per confermare il possesso |
| `GOAL_LINE_X_M` | 103.5 | palla oltre questa x = dentro la porta avversaria |
| `GOAL_HALF_WIDTH_M` | 3.66 | metà luce della porta (7.32 m), centrata a `y = 34` |
| `SHOT_MIN_SPEED_MPS` | 12.0 | velocità palla minima per considerarla un tiro |

### 4.1 Distanza percorsa

`distance_m` dell'ultimo frame − `distance_m` del primo frame del giocatore.
Fallback se il campo manca: somma di `hypot(Δx, Δy)` tra frame consecutivi.
Unità: metri, 1 decimale in pagina.

### 4.2 Velocità media

`distanza / (t_ultimo − t_primo)`, in m/s; in pagina anche in km/h (× 3.6).
Calcolata su tutta la durata della partita, fermi inclusi. Come colonna
secondaria si mostra anche la **velocità massima** (max di `speed`), che
costa zero.

### 4.3 Possesso (base per passaggi e gol)

In ogni frame **al più un giocatore ha la palla**:

1. Possessore candidato = giocatore più vicino alla palla, se entro
   `POSSESSION_RADIUS_M`; altrimenti nessuno (palla in volo o libera).
2. Possesso **confermato** quando lo stesso candidato resta tale per
   `POSSESSION_DEBOUNCE_FRAMES` frame consecutivi (0.3 s). Serve perché
   un passaggio viaggia a 18 m/s (1.8 m/frame) e può sfiorare un compagno
   per 1–2 frame senza che lui la tocchi.
3. Il possesso vale solo nella fase `attack`. In `defense` la palla è
   avversaria; in `scattered`/`forming` è ferma al centro (spec
   simulazione §4bis). Fuori da `attack` il possessore viene azzerato.

### 4.4 Passaggi

Dalla sequenza dei possessori confermati: ogni volta che il possesso passa
da A a B (B ≠ A) conta **1 passaggio effettuato da A** e **1 ricevuto da B**.
I frame senza possessore (palla in volo) non spezzano la catena.

La catena si azzera, e quindi il cambio successivo **non** conta come
passaggio, quando:

- cambia la fase;
- viene segnato un gol (§4.5): dopo il gol il simulatore riassegna la palla
  al mediano, e quella non è una giocata.

In pagina: colonna "Passaggi" = effettuati; "Ricevuti" come secondaria.

### 4.5 Gol fatti

Gol = la palla entra nella porta avversaria: `ball.x ≥ GOAL_LINE_X_M` e
`|ball.y − 34| ≤ GOAL_HALF_WIDTH_M`. Va al **marcatore**, cioè l'ultimo
possessore confermato prima del tiro. Un gol si conta una sola volta
finché la palla non esce dalla zona porta. Un ingresso in porta senza
possessore noto conta come gol di squadra ma non viene attribuito a nessun
giocatore.

### 4.6 Parate (solo portiere)

- Tiro avversario: nella fase `defense`, palla che va verso `x = 0` (`vx < 0`)
  a velocità ≥ `SHOT_MIN_SPEED_MPS`, con velocità ricavata da posizioni di
  frame consecutivi (`Δpos / dt`).
- Parata: durante un tiro avversario la palla arriva entro
  `POSSESSION_RADIUS_M` dal portiere (`group == "GK"`) prima di superare
  `x = 105 − GOAL_LINE_X_M` tra i pali. Un tiro vale al massimo una parata.
- Per i giocatori non portieri `saves = null` e in pagina si vede "—".
- **Nota:** il simulatore attuale non produce tiri avversari (in `defense`
  la palla resta a `x ≥ 55`), quindi oggi le parate sono sempre 0. La regola
  è già definita così da funzionare quando ci saranno tiri.

## 5. Contratto dati

Nuovi modelli Pydantic in `src/track_team/models.py`:

```python
class PlayerMatchStats(BaseModel):
    id: str
    role: str
    group: str
    distance_m: float
    avg_speed_mps: float
    max_speed_mps: float
    passes: int
    passes_received: int
    goals: int
    saves: int | None        # None per i non portieri

class TeamMatchStats(BaseModel):
    distance_m: float
    passes: int
    goals: int               # include i gol non attribuiti

class MatchStats(BaseModel):
    run_id: int | None       # None per un JSON caricato
    name: str                # runs.name, oppure "upload"
    duration_s: float        # t_ultimo − t_primo
    frames: int
    players: list[PlayerMatchStats]   # ordinati per numero (P1…P11)
    team: TeamMatchStats
```

Valori arrotondati a 2 decimali nel backend.

## 6. Backend

- Modulo puro `src/track_team/match_stats.py`:
  `compute_match_stats(trace: dict, *, run_id: int | None, name: str) -> MatchStats`.
  Niente I/O, come `engine.py` (INV-4 della spec simulazione), quindi
  testabile senza FastAPI. Usa `FIELD_LENGTH_M`/`FIELD_WIDTH_M` da `models.py`.
- La lettura dal DB sta in `app.py`, che riusa `db.connect`, `db.get_run`
  e `db.get_frames`. Nessuna modifica allo schema.

| Metodo | Path | Effetto |
|---|---|---|
| GET | `/runs` | **esistente**: elenco partite (id, name, duration_s, frame_count) |
| GET | `/runs/{run_id}/stats` | `MatchStats` del run |
| POST | `/stats` | body = JSON partita (upload) → `MatchStats` con `run_id = null`, `name = "upload"` |

- Errori: `404 run not found` (stesso messaggio degli altri `/runs/{id}`);
  `422` se il JSON caricato non ha `frames` o i frame non hanno `players`;
  `503` se PostgreSQL non è raggiungibile.
- CORS: già abilitato in `app.py` (`allow_origins=["*"]`), niente da
  aggiungere.

## 7. Pagina `stats.html`

Pagina statica alla radice del repo, stile coerente con `index.html`
(stessi token colore, tema chiaro/scuro, layout leggibile anche su telefono).

- **Header:** titolo "Statistiche partita", selettore partita popolato da
  `GET /runs` (name · durata), pulsante "Carica JSON" per un file locale
  (`POST /stats`), link "Apri replay" a `index.html`.
- **Riepilogo squadra:** 3 card, cioè distanza totale (km), passaggi totali,
  gol.
- **Tabella giocatori:** colonne `#`, Ruolo, Distanza (m), Vel. media
  (km/h), Vel. max (km/h), Passaggi, Ricevuti, Gol, Parate. Ordinabile
  cliccando l'intestazione (default per id). Il valore più alto di ogni
  colonna numerica è evidenziato. Parate "—" per i non portieri.
- **Stati:** caricamento; backend non raggiungibile (messaggio con il
  comando `uvicorn` per avviarlo); DB vuoto (messaggio con
  `scripts/seed_db.py`); file non valido (testo dal `detail` del 422).
- URL backend: query param `?api=`, default `http://127.0.0.1:8765`, come
  `index.html`. Partita preselezionata con `?run=<id>`.

## 8. Invarianti

- INV-1: stesso JSON → stesse statistiche (calcolo deterministico).
- INV-2: Σ `passes` = Σ `passes_received` = `team.passes`.
- INV-3: `distance_m ≥ 0`, `avg_speed_mps ≤ max_speed_mps`.
- INV-4: `saves` è non nullo solo per `group == "GK"`.
- INV-5: Σ `goals` dei giocatori ≤ `team.goals`.
- INV-6: `match_stats.py` non fa I/O.

## 9. Acceptance criteria

Sul run `demo-65s` creato da `scripts/seed_db.py` e, identico, su
`examples/simulation_trace.json`: stesso seed 7 e 65 s, quindi stessi
650 frame (INV-3 della spec simulazione).

- AC-01: 11 giocatori, `duration_s ≈ 64.9`, `frames = 650`.
- AC-02: `distance_m` di ogni giocatore = `distance_m` dell'ultimo frame
  (± 0.01).
- AC-03: per ogni giocatore `max_speed_mps ≤ v_max` del ruolo (GK 5, DIF 7.5,
  CEN 8, ATT 9) e `avg_speed_mps > 0`.
- AC-04: tutti i passaggi avvengono in `attack` e seguono la sequenza palla
  di §4ter (mediano → mezzala → trequartista → terzino → punta). Sul trace
  di esempio sono 8: P6→P8, P8→P9, P9→P5, P5→P11, ×2 cicli. Il riposizionamento
  della palla dopo il gol (P11→P6) **non** è un passaggio.
- AC-05: `team.goals = 2`, entrambi attribuiti a P11 (punta sul primo palo).
- AC-06: parate P1 = 0; `saves = null` per gli altri 10.
- AC-07: JSON sintetico con possesso A (5 frame) → palla in volo (2 frame)
  → B (5 frame) → A (5 frame) dà esattamente 2 passaggi (A→B, B→A);
  un compagno sfiorato per 2 frame durante il volo non riceve nulla.
- AC-08: JSON sintetico con un tiro avversario fermato dal GK dà
  `saves = 1`; lo stesso tiro che entra in porta dà `saves = 0`.
- AC-09: API: `GET /runs/{id}/stats` di `demo-65s` restituisce i valori
  di AC-01…AC-06; `GET /runs/999999/stats` → 404; `POST /stats` con
  `{}` → 422; `POST /stats` con `examples/simulation_trace.json` dà le
  stesse statistiche del run. Come in `tests/test_db_replay.py`, i test
  che usano il DB si saltano se PostgreSQL non è raggiungibile.
- AC-10: la pagina mostra la tabella per `demo-65s` con i valori
  di AC-02…AC-06 e l'ordinamento per colonna funziona.

I valori di AC-04/AC-05 sono stati verificati con un probe sul trace
attuale. Se si rigenera il trace con un altro seed o un'altra durata vanno
riallineati.

## 10. Verifica pianificata

`uv run pytest` (unit su `compute_match_stats` con trace di esempio e JSON
sintetici, più test API con `TestClient`), `uv run ruff check`,
`uv run mypy src/`. Prova live, come nel README:

```bash
docker compose up -d
uv run python scripts/seed_db.py
uv run uvicorn track_team.app:app --app-dir src --port 8765
python3 -m http.server 5500
# apri http://127.0.0.1:5500/stats.html
```
