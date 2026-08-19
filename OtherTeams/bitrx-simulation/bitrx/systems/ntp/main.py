from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import os
import time

app = FastAPI(title="HappyTuna NTP - Simulation Time Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration from environment variables ---
# How many simulated seconds pass per real second
SPEED_MULTIPLIER = float(os.getenv("SPEED_MULTIPLIER", "60"))  # default: 1 real min = 1 sim hour

# The simulated world start date (ISO format)
SIM_START_ISO = os.getenv("SIM_START", "2024-06-10T08:00:00Z")

# Parse sim start
SIM_START_DT = datetime.fromisoformat(SIM_START_ISO.replace("Z", "+00:00"))

# Record when this server actually started (real time)
REAL_START_TS = time.time()

# Optional manual offset in simulated seconds (used by /time/advance)
_manual_offset_seconds: float = 0.0


def get_sim_time() -> datetime:
    real_elapsed = time.time() - REAL_START_TS
    sim_elapsed = real_elapsed * SPEED_MULTIPLIER + _manual_offset_seconds
    return SIM_START_DT + timedelta(seconds=sim_elapsed)


# --- Models ---
class AdvanceRequest(BaseModel):
    seconds: float


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "service": "ntp"}


@app.get("/time")
def get_time():
    sim = get_sim_time()
    real = datetime.now(timezone.utc)
    return {
        "sim_time": sim.isoformat(),
        "sim_time_human": sim.strftime("%A, %d %B %Y %H:%M:%S UTC"),
        "real_time": real.isoformat(),
        "day_of_week": sim.strftime("%A"),
        "speed_multiplier": SPEED_MULTIPLIER,
    }


@app.get("/time/info")
def get_info():
    sim = get_sim_time()
    real_elapsed = time.time() - REAL_START_TS
    return {
        "sim_start": SIM_START_DT.isoformat(),
        "sim_current": sim.isoformat(),
        "real_elapsed_seconds": round(real_elapsed, 2),
        "sim_elapsed_seconds": round(real_elapsed * SPEED_MULTIPLIER + _manual_offset_seconds, 2),
        "speed_multiplier": SPEED_MULTIPLIER,
        "manual_offset_seconds": _manual_offset_seconds,
        "description": f"1 real second = {SPEED_MULTIPLIER} simulated seconds",
    }


@app.post("/time/advance")
def advance_time(body: AdvanceRequest):
    global _manual_offset_seconds
    if body.seconds <= 0:
        raise HTTPException(status_code=400, detail="seconds must be positive")
    _manual_offset_seconds += body.seconds
    sim = get_sim_time()
    return {
        "message": f"Advanced simulation by {body.seconds} simulated seconds",
        "sim_time": sim.isoformat(),
        "sim_time_human": sim.strftime("%A, %d %B %Y %H:%M:%S UTC"),
        "total_manual_offset_seconds": _manual_offset_seconds,
    }
