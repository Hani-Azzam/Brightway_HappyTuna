# BitriX NTP — Simulation Time Service

A shared clock for the BitriX simulation world. All agents and systems query this service instead of using real system time, so the simulation can run faster than real life.

## Default time model

| Setting | Value |
|---|---|
| Speed multiplier | 60× (1 real minute = 1 simulated hour) |
| Simulation start | Monday, 10 June 2024, 08:00 UTC |
| Port | 8001 |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SPEED_MULTIPLIER` | `60` | Simulated seconds per real second |
| `SIM_START` | `2024-06-10T08:00:00Z` | When the simulation world begins |

## Running locally

```bash
# With Docker Compose (recommended)
docker compose up ntp

# Without Docker
pip install -r requirements.txt
uvicorn main:app --port 8001
```

## API reference

### GET /time
Returns the current simulated timestamp.

```json
{
  "sim_time": "2024-06-10T09:23:00+00:00",
  "sim_time_human": "Monday, 10 June 2024 09:23:00 UTC",
  "real_time": "2026-06-28T10:01:00+00:00",
  "day_of_week": "Monday",
  "speed_multiplier": 60.0
}
```

### GET /time/info
Returns full simulation metadata.

### POST /time/advance
Manually jump the simulation clock forward.

```bash
curl -X POST http://localhost:8001/time/advance \
  -H "Content-Type: application/json" \
  -d '{"seconds": 3600}'
```

### GET /health
Returns `{"status": "ok"}` when running.

## How agents should use this

```python
import httpx

def get_sim_time() -> str:
    r = httpx.get("http://ntp:8001/time")
    return r.json()["sim_time"]
```
