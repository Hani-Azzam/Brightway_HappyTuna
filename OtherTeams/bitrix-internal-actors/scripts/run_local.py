"""Run the internal chat + employee together, with one command.

Two modes:

  # FULL STACK — PostgreSQL + Redis + Kafka (needs Docker)
  python scripts/run_local.py --full

  # QUICK — SQLite, no cache, no bus (needs only Python; good for a fast look)
  python scripts/run_local.py

Both then seed the incident channel and launch the employee worker pointed at the
chat. Ctrl+C stops everything (and `docker compose stop` in --full mode).

Flags:
  --full          use the Docker stack (Postgres/Redis/Kafka) instead of SQLite
  --no-employee   chat + seed only (no Anthropic key needed)
  --port          host port for the SQLite chat (default 8085; --full uses 8080)

Env:
  EMPLOYEE_ANTHROPIC_API_KEY   required unless --no-employee (the employee's LLM)
  CHAT_DB_PATH              SQLite path in quick mode (default ./data/chat.db)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CORRELATION = "HT-2026-001"


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file (KEY=VALUE lines) without overriding
    values already set in the shell. Stdlib-only so run_local stays dependency-free.
    Lets you keep EMPLOYEE_ANTHROPIC_API_KEY in .env instead of pasting it each run."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_json(url: str, headers: dict) -> dict | None:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def _post_json(url: str, headers: dict, body: dict) -> dict | None:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={**headers, "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def _wait_health(url: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _get_json(url, {}) == {"status": "ok"}:
            return True
        time.sleep(1.0)
    return False


def _seed_via_rest(base: str) -> str | None:
    """Create the HT-2026-001 incident room over REST — backend-agnostic, so it
    works identically against SQLite or Postgres. Idempotent."""
    hdr = {"Authorization": "Bearer COO-1"}
    listing = _get_json(f"{base}/api/channels", hdr) or {}
    for c in listing.get("data", {}).get("channels", []):
        if c.get("correlation_id") == _CORRELATION:
            print(f"[run_local] world already seeded (channel {c['channel']}).")
            return c["channel"]
    res = _post_json(f"{base}/api/channels", hdr, {
        "type": "incident", "members": ["EMP-QA-17", "CEO-1"],
        "name": "ht-crisis", "correlation_id": _CORRELATION,
    })
    cid = (res or {}).get("data", {}).get("channel")
    print(f"[run_local] created incident channel {cid}")
    return cid


def _shutdown(procs: list[subprocess.Popen], full: bool) -> None:
    for p in reversed(procs):
        if p.poll() is None:
            p.terminate()
    for p in reversed(procs):
        try:
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            p.kill()
    if full:
        print("[run_local] stopping the docker stack ...")
        subprocess.run(["docker", "compose", "stop"], cwd=str(ROOT), check=False)


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)   # show progress live, not on exit
    except Exception:  # noqa: BLE001
        pass

    _load_dotenv(ROOT / ".env")   # so EMPLOYEE_ANTHROPIC_API_KEY can live in .env, not the shell

    ap = argparse.ArgumentParser(description="Run internal chat + employee locally.")
    ap.add_argument("--full", action="store_true", help="Docker stack: Postgres + Redis + Kafka")
    ap.add_argument("--no-employee", action="store_true", help="chat + seed only")
    ap.add_argument("--port", type=int, default=8085, help="host port for SQLite (quick) mode")
    ap.add_argument("--db", default=os.environ.get("CHAT_DB_PATH", str(ROOT / "data" / "chat.db")))
    args = ap.parse_args()

    env = dict(os.environ)
    py = sys.executable
    procs: list[subprocess.Popen] = []

    if args.full:
        # The chat + its Postgres/Redis/Kafka run in Docker; the container publishes 8080.
        base = "http://localhost:8080"
        print("[run_local] bringing up the full stack (Postgres + Redis + Kafka) via docker compose ...")
        up = subprocess.run(["docker", "compose", "up", "-d", "internal-messaging"],
                            cwd=str(ROOT), check=False)
        if up.returncode != 0:
            print("[run_local] ERROR: `docker compose up` failed (is Docker running?)")
            return 1
    else:
        # SQLite chat as a host process — no Docker needed.
        base = f"http://localhost:{args.port}"
        env["CHAT_DB_PATH"] = args.db
        print(f"[run_local] starting internal chat (SQLite) on {base}  (db={args.db})")
        procs.append(subprocess.Popen(
            [py, "-m", "uvicorn", "services.internal_messaging.app.main:app",
             "--port", str(args.port), "--log-level", "warning"],
            cwd=str(ROOT), env=env,
        ))

    if not _wait_health(f"{base}/health"):
        print("[run_local] ERROR: chat did not become healthy")
        _shutdown(procs, args.full)
        return 1
    print("[run_local] chat is up.")

    # seed (over REST → works the same for SQLite or Postgres)
    print("[run_local] seeding world ...")
    cid = _seed_via_rest(base)

    # employee worker — needs an LLM key; skip gracefully (keep chat up) if absent.
    want_employee = not args.no_employee
    if want_employee and not env.get("EMPLOYEE_ANTHROPIC_API_KEY"):
        print("[run_local] EMPLOYEE_ANTHROPIC_API_KEY is not set — skipping the employee worker "
              "(the chat stays up). To run the employee, set the key and re-run:")
        print('[run_local]     PowerShell:  $env:EMPLOYEE_ANTHROPIC_API_KEY = "sk-ant-..."')
        print("[run_local]     bash:        export EMPLOYEE_ANTHROPIC_API_KEY=sk-ant-...")
        want_employee = False
    if want_employee:
        env["EMPLOYEE_INTERNAL_MESSAGING_URL"] = base
        print("[run_local] starting employee worker ...")
        procs.append(subprocess.Popen(
            [py, "-m", "services.employee.app.main"], cwd=str(ROOT), env=env,
        ))

    store = "PostgreSQL + Redis + Kafka" if args.full else "SQLite"
    cid_s = cid or "<CID>"
    print(f"\n[run_local] Running ({store}). Wake the employee by posting a mention:")
    if os.name == "nt":
        # PowerShell: `curl` is an alias for Invoke-WebRequest, so use Invoke-RestMethod.
        print(f'  Invoke-RestMethod -Method Post -Uri "{base}/api/channels/{cid_s}/messages" '
              f'-Headers @{{Authorization="Bearer COO-1"}} -ContentType "application/json" '
              f'-Body \'{{"body":"status @EMP-QA-17"}}\'')
    else:
        print(f"  curl -X POST {base}/api/channels/{cid_s}/messages "
              f'-H "Authorization: Bearer COO-1" -H "Content-Type: application/json" '
              f'-d \'{{"body":"status @EMP-QA-17"}}\'')
    print("[run_local] Ctrl+C to stop everything.\n")

    try:
        while True:
            # Host subprocesses (SQLite chat / employee). If any exits, tear down the
            # rest. With no host procs (--full, or employee skipped in Docker mode),
            # just idle until Ctrl+C — the chat runs in Docker.
            if procs and not all(p.poll() is None for p in procs):
                print("[run_local] a process exited; shutting down the rest.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[run_local] stopping ...")
    _shutdown(procs, args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
