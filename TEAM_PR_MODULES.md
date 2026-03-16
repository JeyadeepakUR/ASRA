# Team PR Modules

This file defines two small, parallelizable modules for teammates.

## Module A - Persistent Incident Store

- Owner: Teammate 1
- Base file: `incident_store.py`
- Goal: Add a persistent backend (SQLite first) while preserving the current API behavior.

### Scope

- Add `SQLiteIncidentStore` with the same public API as `InMemoryIncidentStore`:
  - `upsert(thread_id, incident)`
  - `remove(thread_id)`
  - `contains(thread_id)`
  - `count()`
  - `list_all()`
  - `clear()`
- Wire backend selection through env var, e.g. `INCIDENT_STORE_BACKEND=inmemory|sqlite`.
- Keep endpoint contracts unchanged.

### Acceptance Criteria

- All tests pass.
- API endpoints still return the same response shape.
- Restarting API with sqlite backend preserves pending incidents.

### Validation

```bash
pytest -q
uvicorn api:app --reload
curl http://localhost:8000/api/incidents/pending
```

## Module B - Production Simulation Profiles

- Owner: Teammate 2
- Base file: `simulate_prod.py`
- Goal: Add reusable profiles and richer report output for prod-like testing.

### Scope

- Add profile presets, e.g. `normal`, `peak`, `incident-storm`.
- Add optional CSV/JSON summary output for each run.
- Add latency/error counters from webhook responses.
- Keep CLI backward-compatible.

### Acceptance Criteria

- Existing simulator args continue to work.
- New profile flag works, e.g. `--profile incident-storm`.
- New tests added for profile selection and output serialization.

### Validation

```bash
python simulate_prod.py --duration 30 --rps 3
python simulate_prod.py --duration 30 --spike-mode --rps 5
pytest -q
```

## Suggested Branch Names

- `feat/sqlite-incident-store`
- `feat/simulation-profiles`
