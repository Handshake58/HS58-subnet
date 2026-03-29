# Subnet 58 Update — Yuma-Proof & Funktional

> Status: **PLAN** — Noch nicht gestartet
> Letzte Änderung: 2026-03-29

## Aktueller Zustand

- **Mining inaktiv** — alle Incentives werden verbrannt
- **Version**: 2.0.0 (spec_version 2000)
- **Architektur**: Probe-basiert (Miner pingen URLs, Validators messen Konsensus)
- **`tasks/todo.md`** beschreibt ein LLM-Benchmark-System das **nie implementiert wurde** — alle Items fälschlich als `[x]` markiert

## Root Causes: Warum Incentives verbrennen

### 1. KRITISCH — Validator-Weight-Divergenz (Yuma-Killer)

**Problem**: `random.sample(providers, PROBES_PER_ROUND)` — jeder Validator probt jede Epoche andere zufällige Provider.

```
Validator A probt Provider {1,3,5,7,9} → Miner-Scores X
Validator B probt Provider {2,4,6,8,10} → Miner-Scores Y
→ Weights divergieren → Yuma bestraft BEIDE als Outlier → Incentives verbrannt
```

**Fix**: Deterministisches Provider-Sampling basierend auf Block-Hash.
Alle Validators proben die gleichen Provider in der gleichen Epoche.

```python
import hashlib
block_hash = self.subtensor.get_block_hash(current_block)
seed = int(hashlib.sha256(block_hash.encode()).hexdigest(), 16)
rng = random.Random(seed)
selected = rng.sample(providers, min(PROBES_PER_ROUND, len(providers)))
```

### 2. KRITISCH — Geographische Latenz-Bias (30% der Score)

**Problem**: 30% der Miner-Score basiert auf Latenz-Nähe zum Median. Aber Latenz hängt vom Standort ab — verschiedene Validators messen verschiedene Medians → verschiedene Scores → Weight-Divergenz.

**Fix**: Scoring-Gewichte bei `0.4 / 0.3 / 0.3` lassen (konsistent mit Oracle-Seite), aber Latenz-Score von Median-basiert auf **binären Band-Check** umstellen:

```
Vorher:  latency_score = 1.0 - abs(latenz - median) / MAX_DEVIATION  (pro Validator unterschiedlich!)
Nachher: latency_score = 1.0 wenn latenz < MAX_LATENCY, sonst 0.0    (deterministisch, alle Validators gleich)
```

Die veröffentlichte Formel `0.4 × reachable + 0.3 × status + 0.3 × latency` bleibt gleich — nur die interne Latenz-Berechnung wird deterministisch. Oracle-Seite muss NICHT geändert werden.

### 3. MITTEL — EMA-Alpha Mismatch

**Problem**: `config.py` definiert `ACCURACY_EMA_ALPHA = 0.3`, aber der Code nutzt `self.config.neuron.moving_average_alpha` (default 0.1 aus `utils/config.py`). Score-Konvergenz dauert ~3x länger als erwartet.

**Fix**: `ACCURACY_EMA_ALPHA` tatsächlich im Code verwenden, oder den Default in `utils/config.py` auf 0.3 setzen.

### 4. MITTEL — Probes an Validators (nicht nur Miner)

**Problem**: `miner_uids = list(range(self.metagraph.n.item()))` — probt ALLE UIDs, inkl. Validators die kein Axon haben.

**Fix**: UIDs filtern auf tatsächlich erreichbare Miner-Axons:

```python
miner_uids = [
    uid for uid in range(self.metagraph.n.item())
    if self.metagraph.axons[uid].ip != "0.0.0.0"
    and uid != self.uid
]
```

### 5. MITTEL — Keine Weight-Bestätigung

**Problem**: `wait_for_finalization=False, wait_for_inclusion=False` — es gibt keinen Beweis dass Weights on-chain landen.

**Fix**: Mindestens `wait_for_inclusion=True` setzen und bei Fehler retry.

### 6. NIEDRIG — Auto-Update defekt

**Problem**: Exit-Code 42 wird signalisiert aber `entrypoint.sh` führt nie `git pull` durch.

**Fix**: In `entrypoint.sh` Exit-Code 42 erkennen und `git pull && pip install -e .` ausführen.

---

## Implementierungsplan

### Phase 1: Yuma-Sicherheit (höchste Priorität)

- [ ] **1.1** Deterministisches Provider-Sampling mit Block-Hash als Seed
  - `neurons/validator.py` → `forward()` Methode
  - Alle Validators proben garantiert die gleichen Provider
  
- [ ] **1.2** Latenz-Scoring vereinfachen → Binärer Latenz-Band statt Median-Vergleich
  - `neurons/validator.py` → `_probe_accuracy()` und `_compute_consensus()`
  - Gewichte bleiben 0.4/0.3/0.3 (konsistent mit Oracle-Seite)
  - Nur interne Latenz-Berechnung wird deterministisch (< MAX_LATENCY = 1.0, sonst 0.0)

- [ ] **1.3** EMA-Alpha-Fix — Konstante aus `config.py` tatsächlich verwenden
  - `subnet58/base/validator.py` → `update_scores()`

### Phase 2: Funktionalität & Robustheit

- [ ] **2.1** Miner-UID-Filterung — nur aktive Axons proben
  - `neurons/validator.py` → `forward()`
  
- [ ] **2.2** Weight-Bestätigung aktivieren
  - `subnet58/base/validator.py` → `set_weights()`
  - `wait_for_inclusion=True`

- [ ] **2.3** Auto-Update reparieren
  - `entrypoint.sh` → Exit-Code 42 handling

- [ ] **2.4** `dendrite.query()` → async machen (optional, nice-to-have)

### Phase 3: Aufräumen & Version

- [ ] **3.1** `tasks/todo.md` aktualisieren (falsche [x]-Markierungen entfernen)
- [ ] **3.2** `config.py` aufräumen — ungenutzte Konstanten entfernen oder verlinken
- [ ] **3.3** `min_compute.yml` aktualisieren (sagt noch "DRAIN provider" für Miner)
- [ ] **3.4** Version bumpen → 2.1.0 (spec_version 2100)
- [ ] **3.5** README aktualisieren (EMA-Alpha, Scoring-Gewichte)

---

## Risikobewertung

| Fix | Risiko | Auswirkung |
|-----|--------|------------|
| Deterministisches Sampling | Niedrig | **Höchste** — eliminiert Yuma-Divergenz |
| Latenz-Band | Niedrig | **Hoch** — entfernt geographische Bias |
| EMA-Alpha Fix | Niedrig | Mittel — schnellere Score-Konvergenz |
| UID-Filterung | Niedrig | Mittel — sauberer, effizienter |
| Weight-Bestätigung | Niedrig | Mittel — zuverlässigere Weight-Setzung |
| Auto-Update | Niedrig | Niedrig — Convenience-Feature |

---

## Abgleich mit Oracle-Seite (handshake58.com/oracle)

Die Oracle-Seite beschreibt das gewünschte V1-Verhalten. Nach Phase 1 wird der Code
diese Versprechen tatsächlich einhalten:

| Oracle-Behauptung | Aktueller Code | Nach Phase 1 |
|---|---|---|
| "All miners probe the same targets" | FALSCH (random.sample) | KORREKT (Block-Hash Seed) |
| "deterministic and reproducible" | FALSCH (Latenz-Median) | KORREKT (binärer Band-Check) |
| Scoring 0.4/0.3/0.3 | Stimmt | Unverändert |
| Multiple Registries | Nur HS58 Default | + MPP.dev als 2. Default |

V2 (Anomaly Detection mit LLM) ist auf der Seite als "next_phase" markiert — wird hier nicht behandelt.

## Entscheidungen offen

1. **MPP.dev als zweite Default-Registry?**
   - Oracle-Seite zeigt `mpp.dev/api/services` als Quelle
   - Aktueller Code hat nur HS58 als Default
   - Soll MPP.dev in `DEFAULT_REGISTRIES` aufgenommen werden?

2. **Probes-per-Round erhöhen?**
   - Aktuell 5 — bei 50+ Providern dauert es viele Epochen bis alle geprobt sind
   - Mehr Probes = schnellere Konvergenz, aber mehr Netzwerk-Last

3. **Immunity-Period-Handling?**
   - Neue Miner starten bei Score 0.0 und brauchen ~10+ Runden zum Aufbauen
   - Soll es einen Initial-Score oder schnelleres Alpha für neue Miner geben?

4. **Provider-Kategorie-Weights?**
   - Sollen verschiedene Provider-Typen (LLM, Tools, Data) unterschiedlich gewichtet werden?
   - Oder bleiben alle gleich?
