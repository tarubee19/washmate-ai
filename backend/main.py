"""
WashMate AI v2 — Backend API (main.py)
======================================
This file is the ENTIRE backend. It handles:
  1. User database (name, room, phone) — stored in db.json
  2. Machine state with wash modes (Heavy/Light/Spin)
  3. Extend wash by 15 minutes (rainy season feature)
  4. Smart Queue with 5-minute escalation countdown
  5. In-app notifications (stored, polled by frontend)
  6. AI chat with RAG (Claude API)
  7. Peak hour heatmap analytics

HOW TO RUN:
  cd backend
  uvicorn main:app --reload
  Then open frontend/index.html in your browser.
"""

import json
import os
import random
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ═══════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════
app = FastAPI(title="WashMate AI v2", version="2.0.0")

# CORS — allows the HTML file opened in your browser to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════
# DATABASE — one JSON file on disk (db.json)
# Think of this like a simple spreadsheet saved as a file.
# In a real product, this would be PostgreSQL or Supabase.
# ═══════════════════════════════════════════════════════
DB_PATH = Path(__file__).parent / "db.json"


def load_db() -> dict:
    """Open db.json and return its contents as a Python dictionary."""
    if not DB_PATH.exists():
        db = _fresh_db()
        save_db(db)
        return db
    with open(DB_PATH) as f:
        return json.load(f)


def save_db(data: dict) -> None:
    """Save the Python dictionary back into db.json."""
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _fresh_db() -> dict:
    """
    This defines the SCHEMA — the shape/structure of our database.
    Called only once, when db.json doesn't exist yet.
    """
    db = {
        # ── USERS ──────────────────────────────────────────────────────
        # Pre-registered hostel residents. In a real app you'd have a
        # sign-up form. Here we seed 8 users so the demo works immediately.
        "users": [
            {"id": "u1", "name": "Alice Sharma",  "room": "101", "phone": "+91-9000000001"},
            {"id": "u2", "name": "Bob Mehta",     "room": "102", "phone": "+91-9000000002"},
            {"id": "u3", "name": "Charlie Iyer",  "room": "103", "phone": "+91-9000000003"},
            {"id": "u4", "name": "Diana Nair",    "room": "104", "phone": "+91-9000000004"},
            {"id": "u5", "name": "Eve Pillai",    "room": "201", "phone": "+91-9000000005"},
            {"id": "u6", "name": "Frank D'Souza", "room": "202", "phone": "+91-9000000006"},
            {"id": "u7", "name": "Grace Rao",     "room": "203", "phone": "+91-9000000007"},
            {"id": "u8", "name": "Hiro Tanaka",   "room": "204", "phone": "+91-9000000008"},
        ],

        # ── MACHINES ───────────────────────────────────────────────────
        "machines": [
            {
                "id": 1,
                "name": "Machine A",
                "status": "free",           # "free" | "in_use" | "escalation"
                "started_by_user_id": None, # which user started it
                "start_time": None,         # ISO timestamp string
                "cycle_minutes": 0,         # set when wash starts
                "mode": None,               # "heavy" | "light" | "spin"
                "escalation_started_at": None,  # when 5-min countdown began
                "escalation_target_user_id": None,  # who we're waiting on
            },
            {
                "id": 2,
                "name": "Machine B",
                "status": "free",
                "started_by_user_id": None,
                "start_time": None,
                "cycle_minutes": 0,
                "mode": None,
                "escalation_started_at": None,
                "escalation_target_user_id": None,
            },
        ],

        # ── QUEUE ──────────────────────────────────────────────────────
        # Ordered list of users waiting. First in = first served.
        "queue": [],

        # ── NOTIFICATIONS ──────────────────────────────────────────────
        # In-app notification inbox. Frontend polls this every 5 seconds.
        # Format: { id, user_id, message, type, created_at, read }
        "notifications": [],

        # ── SESSION HISTORY ────────────────────────────────────────────
        # Every completed wash is recorded here. The AI reads this.
        "sessions": [],
    }

    # Seed 30 days of fake history so the AI has real data to analyse
    _seed_history(db)
    return db


def _seed_history(db: dict) -> None:
    """
    Generate realistic fake wash history for the past 30 days.
    Peak hours: 7–9 AM (morning rush), 12–1 PM (lunch), 6–10 PM (evening rush).
    This is what the AI's Peak Heatmap is based on.
    """
    user_ids = [u["id"] for u in db["users"]]
    modes    = [
        ("heavy", 45), ("heavy", 45),  # heavy appears twice = more common
        ("light", 30),
        ("spin",  15),
    ]
    peak_hours = list(range(7, 10)) + list(range(12, 14)) + list(range(18, 22))
    off_hours  = list(range(0, 7)) + [10, 11] + list(range(14, 18)) + [22, 23]
    days_of_week = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    now = datetime.now()
    for days_ago in range(1, 31):
        base = now - timedelta(days=days_ago)
        dow  = days_of_week[base.weekday()]
        # Monday and Thursday are extra busy (common hostel pattern)
        n = random.randint(8, 12) if dow in ["Monday", "Thursday"] else random.randint(4, 8)
        for _ in range(n):
            hour = random.choice(peak_hours if random.random() < 0.72 else off_hours)
            mode_name, duration = random.choice(modes)
            start = base.replace(hour=hour, minute=random.randint(0, 59), second=0, microsecond=0)
            db["sessions"].append({
                "user_id":       random.choice(user_ids),
                "machine_id":    random.choice([1, 2]),
                "mode":          mode_name,
                "start_time":    start.isoformat(),
                "end_time":      (start + timedelta(minutes=duration)).isoformat(),
                "duration_minutes": duration,
                "day_of_week":   dow,
                "hour":          hour,
            })


# ═══════════════════════════════════════════════════════
# WASH MODE DEFINITIONS
# Each mode has a display name and duration in minutes.
# ═══════════════════════════════════════════════════════
WASH_MODES = {
    "heavy": {"label": "Heavy Wash",  "minutes": 45},
    "light": {"label": "Light Wash",  "minutes": 30},
    "spin":  {"label": "Spin / Dry",  "minutes": 15},
}
EXTEND_MINUTES = 15   # how many minutes "Extend Wash" adds


# ═══════════════════════════════════════════════════════
# PYDANTIC MODELS — these define what data each API
# endpoint expects to RECEIVE from the frontend.
# ═══════════════════════════════════════════════════════
class StartWashRequest(BaseModel):
    machine_id: int
    user_id: str
    mode: str          # "heavy" | "light" | "spin"

class JoinQueueRequest(BaseModel):
    user_id: str

class ConfirmArrivalRequest(BaseModel):
    user_id: str
    machine_id: int

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None


# ═══════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════

def get_user(db: dict, user_id: str) -> Optional[dict]:
    """Find a user by their ID. Returns None if not found."""
    return next((u for u in db["users"] if u["id"] == user_id), None)


def get_user_by_name(db: dict, name: str) -> Optional[dict]:
    """Find a user by name (case-insensitive partial match)."""
    name_lower = name.lower()
    return next((u for u in db["users"] if name_lower in u["name"].lower()), None)


def minutes_remaining(machine: dict) -> int:
    """Calculate how many minutes are left in the current wash cycle."""
    if machine["status"] != "in_use" or not machine["start_time"]:
        return 0
    started = datetime.fromisoformat(machine["start_time"])
    elapsed_mins = (datetime.now() - started).seconds // 60
    remaining    = machine["cycle_minutes"] - elapsed_mins
    return max(remaining, 0)


def escalation_seconds_remaining(machine: dict) -> int:
    """
    How many seconds remain in the 5-minute escalation window.
    Returns 0 if escalation hasn't started or window has passed.
    """
    if machine["status"] != "escalation" or not machine["escalation_started_at"]:
        return 0
    started  = datetime.fromisoformat(machine["escalation_started_at"])
    elapsed  = (datetime.now() - started).seconds
    remaining = (5 * 60) - elapsed
    return max(remaining, 0)


def add_notification(db: dict, user_id: str, message: str, notif_type: str = "info") -> None:
    """
    Add a notification to the user's inbox.
    The frontend polls /notifications/{user_id} every 5 seconds to show these.
    notif_type: "info" | "urgent" | "success"
    """
    db["notifications"].append({
        "id":         f"n{len(db['notifications'])+1}",
        "user_id":    user_id,
        "message":    message,
        "type":       notif_type,
        "created_at": datetime.now().isoformat(),
        "read":       False,
    })


# ═══════════════════════════════════════════════════════
# SMART QUEUE ESCALATION LOGIC
# This is the core of Feature 3.
# ═══════════════════════════════════════════════════════

async def queue_escalation_logic(machine_id: int) -> None:
    """
    The 5-minute escalation engine.

    FLOW:
      1. Machine timer hits 0 → current user gets "please collect" notification
      2. If there's a queue → next user gets "machine free! confirm in 5 min"
      3. We wait 5 minutes (300 seconds)
      4. If that user confirmed (status back to "free") → done
      5. If they DIDN'T confirm → skip them, notify the person behind them
      6. Repeat until queue is empty or someone confirms

    This runs as a background task so it doesn't block the API response.
    """
    await asyncio.sleep(2)  # small delay so the finish_wash write completes first

    db = load_db()
    machine = next((m for m in db["machines"] if m["id"] == machine_id), None)
    if not machine:
        return

    # Step 1: Notify the person who just finished
    if machine["started_by_user_id"]:
        add_notification(
            db,
            machine["started_by_user_id"],
            f"⏰ Your wash on {machine['name']} is done! Please collect your clothes.",
            "urgent"
        )

    # Step 2: Try to give the machine to the next person in queue
    await _offer_machine_to_next_in_queue(db, machine_id)


async def _offer_machine_to_next_in_queue(db: dict, machine_id: int) -> None:
    """
    Find the next person in queue, notify them, and start the 5-min countdown.
    """
    if not db["queue"]:
        # No one waiting — machine just becomes free
        machine = next(m for m in db["machines"] if m["id"] == machine_id)
        machine["status"] = "free"
        machine["started_by_user_id"] = None
        machine["start_time"] = None
        machine["mode"] = None
        save_db(db)
        return

    # Get the next person in line
    next_entry = db["queue"][0]
    next_user  = get_user(db, next_entry["user_id"])

    if not next_user:
        # User was deleted — skip them and try the next
        db["queue"].pop(0)
        save_db(db)
        await _offer_machine_to_next_in_queue(db, machine_id)
        return

    # Set machine into "escalation" state (offered but not yet confirmed)
    machine = next(m for m in db["machines"] if m["id"] == machine_id)
    machine["status"]                    = "escalation"
    machine["escalation_started_at"]     = datetime.now().isoformat()
    machine["escalation_target_user_id"] = next_user["id"]

    # Notify the next person
    add_notification(
        db,
        next_user["id"],
        f"🔔 Machine {machine['name']} is FREE! You have 5 minutes to click 'I'm Coming'. "
        f"Your position: #1 in queue.",
        "urgent"
    )
    save_db(db)

    # Wait 5 minutes for them to confirm
    await asyncio.sleep(5 * 60)

    # Re-read db (it might have changed if they confirmed)
    db = load_db()
    machine = next(m for m in db["machines"] if m["id"] == machine_id)

    if machine["status"] != "escalation":
        # They confirmed! (status changed to "in_use" or "free") — we're done.
        return

    # They did NOT confirm in time — escalate to the next person
    add_notification(
        db,
        next_user["id"],
        f"❌ You didn't confirm in time. Your spot for {machine['name']} was given to the next person.",
        "info"
    )

    # Remove them from the front of the queue
    db["queue"] = [q for q in db["queue"] if q["user_id"] != next_user["id"]]
    machine["escalation_started_at"]     = None
    machine["escalation_target_user_id"] = None
    save_db(db)

    # Recurse — offer to the new first person in queue
    await _offer_machine_to_next_in_queue(db, machine_id)


# ═══════════════════════════════════════════════════════
# API ROUTES
# These are the "endpoints" — URLs the frontend calls.
# ═══════════════════════════════════════════════════════

@app.get("/")
def health():
    return {"status": "WashMate AI v2 running ✅"}


# ── USERS ──────────────────────────────────────────────

@app.get("/users")
def get_users():
    """Return all registered users (for the login dropdown)."""
    db = load_db()
    return db["users"]


# ── MACHINES ───────────────────────────────────────────

@app.get("/machines")
def get_machines():
    """Return all machines with live status, time remaining, and occupant details."""
    db = load_db()
    result = []
    for m in db["machines"]:
        occupant = None
        if m["started_by_user_id"]:
            u = get_user(db, m["started_by_user_id"])
            if u:
                occupant = {"name": u["name"], "room": u["room"]}

        result.append({
            **m,
            "minutes_remaining":         minutes_remaining(m),
            "escalation_seconds_remaining": escalation_seconds_remaining(m),
            "occupant":                  occupant,
            "mode_label":                WASH_MODES.get(m["mode"], {}).get("label", "") if m["mode"] else "",
        })
    return result


@app.post("/machines/{machine_id}/start")
def start_wash(machine_id: int, body: StartWashRequest, bg: BackgroundTasks):
    """
    Start a wash cycle on a machine.
    Requires: user_id, machine_id, mode (heavy/light/spin)
    """
    db = load_db()

    # Validate inputs
    machine = next((m for m in db["machines"] if m["id"] == machine_id), None)
    if not machine:
        raise HTTPException(404, "Machine not found")
    if machine["status"] == "in_use":
        raise HTTPException(409, "Machine is already in use")
    if body.mode not in WASH_MODES:
        raise HTTPException(400, f"Invalid mode. Choose: {list(WASH_MODES.keys())}")

    user = get_user(db, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Set machine state
    machine["status"]              = "in_use"
    machine["started_by_user_id"]  = user["id"]
    machine["start_time"]          = datetime.now().isoformat()
    machine["cycle_minutes"]       = WASH_MODES[body.mode]["minutes"]
    machine["mode"]                = body.mode
    machine["escalation_started_at"]    = None
    machine["escalation_target_user_id"] = None

    # Remove user from queue (they got the machine they were waiting for)
    db["queue"] = [q for q in db["queue"] if q["user_id"] != body.user_id]

    add_notification(db, user["id"],
        f"✅ Started {WASH_MODES[body.mode]['label']} on {machine['name']}. "
        f"Done in ~{WASH_MODES[body.mode]['minutes']} minutes.", "success")

    save_db(db)
    return {"message": f"{user['name']} started {WASH_MODES[body.mode]['label']} on {machine['name']}"}


@app.post("/machines/{machine_id}/finish")
def finish_wash(machine_id: int, bg: BackgroundTasks):
    """
    Mark a wash cycle as complete and trigger the escalation flow.
    Called either manually by the user or would be auto-called by a timer.
    """
    db = load_db()
    machine = next((m for m in db["machines"] if m["id"] == machine_id), None)
    if not machine:
        raise HTTPException(404, "Machine not found")

    # Log session to history
    if machine["status"] == "in_use" and machine["start_time"]:
        start_dt = datetime.fromisoformat(machine["start_time"])
        end_dt   = datetime.now()
        db["sessions"].append({
            "user_id":          machine["started_by_user_id"],
            "machine_id":       machine["id"],
            "mode":             machine["mode"],
            "start_time":       machine["start_time"],
            "end_time":         end_dt.isoformat(),
            "duration_minutes": int((end_dt - start_dt).seconds / 60),
            "day_of_week":      start_dt.strftime("%A"),
            "hour":             start_dt.hour,
        })

    prev_user_id = machine["started_by_user_id"]

    # Reset machine (escalation flow will update status as needed)
    machine["started_by_user_id"] = None
    machine["start_time"]         = None
    machine["mode"]               = None
    machine["cycle_minutes"]      = 0
    # Keep status as "in_use" temporarily — escalation logic will set it to
    # "escalation" or "free". We need to mark it so the escalation knows who used it.
    machine["status"] = "in_use"  # escalation_logic reads started_by before clearing

    # Temporarily store previous user for notification
    machine["started_by_user_id"] = prev_user_id
    save_db(db)

    # Kick off the background escalation flow (non-blocking)
    bg.add_task(queue_escalation_logic, machine_id)

    return {"message": "Wash marked complete. Escalation flow started."}


@app.post("/machines/{machine_id}/extend")
def extend_wash(machine_id: int):
    """
    Rainy Season Feature: Add 15 minutes to the current wash cycle.
    Only works if the machine is currently in use.
    """
    db = load_db()
    machine = next((m for m in db["machines"] if m["id"] == machine_id), None)
    if not machine:
        raise HTTPException(404, "Machine not found")
    if machine["status"] != "in_use":
        raise HTTPException(409, "Machine is not currently in use")

    machine["cycle_minutes"] += EXTEND_MINUTES

    user = get_user(db, machine["started_by_user_id"])
    if user:
        add_notification(db, user["id"],
            f"⏱ Extended wash by {EXTEND_MINUTES} mins. New total: {machine['cycle_minutes']} mins.",
            "info")

    save_db(db)
    return {"message": f"Wash extended by {EXTEND_MINUTES} minutes"}


@app.post("/machines/{machine_id}/confirm-arrival")
def confirm_arrival(machine_id: int, body: ConfirmArrivalRequest, bg: BackgroundTasks):
    """
    Called when the next person in queue clicks "I'm Coming!".
    Transitions machine from 'escalation' → 'in_use' for that user.
    """
    db = load_db()
    machine = next((m for m in db["machines"] if m["id"] == machine_id), None)
    if not machine:
        raise HTTPException(404, "Machine not found")
    if machine["status"] != "escalation":
        raise HTTPException(409, "Machine is not in escalation state")
    if machine["escalation_target_user_id"] != body.user_id:
        raise HTTPException(403, "You are not the next person in queue")

    user = get_user(db, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # The user confirmed — check if they actually selected a mode
    # For confirm-arrival, we auto-assign "light" wash; they can extend if needed
    machine["status"]             = "in_use"
    machine["started_by_user_id"] = body.user_id
    machine["start_time"]         = datetime.now().isoformat()
    machine["cycle_minutes"]      = WASH_MODES["light"]["minutes"]
    machine["mode"]               = "light"
    machine["escalation_started_at"]     = None
    machine["escalation_target_user_id"] = None

    # Remove from queue
    db["queue"] = [q for q in db["queue"] if q["user_id"] != body.user_id]

    add_notification(db, body.user_id,
        f"✅ Great! You're now using {machine['name']}. Machine started with Light Wash (30 min).",
        "success")

    save_db(db)
    return {"message": f"{user['name']} confirmed arrival and started machine"}


# ── QUEUE ──────────────────────────────────────────────

@app.get("/queue")
def get_queue():
    db = load_db()
    # Enrich queue entries with user details
    result = []
    for i, entry in enumerate(db["queue"]):
        user = get_user(db, entry["user_id"])
        result.append({
            **entry,
            "position": i + 1,
            "user_name": user["name"] if user else "Unknown",
            "user_room": user["room"] if user else "?",
        })
    return result


@app.post("/queue/join")
def join_queue(body: JoinQueueRequest):
    db = load_db()
    if any(q["user_id"] == body.user_id for q in db["queue"]):
        raise HTTPException(409, "You are already in the queue")
    user = get_user(db, body.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    db["queue"].append({"user_id": body.user_id, "joined_at": datetime.now().isoformat()})
    position = len(db["queue"])

    add_notification(db, body.user_id,
        f"📋 You're #{position} in the queue. We'll notify you when a machine is free.",
        "info")

    save_db(db)
    return {"position": position, "message": f"{user['name']} joined the queue at position #{position}"}


@app.post("/queue/leave")
def leave_queue(body: JoinQueueRequest):
    db = load_db()
    db["queue"] = [q for q in db["queue"] if q["user_id"] != body.user_id]
    save_db(db)
    return {"message": "Left the queue"}


# ── NOTIFICATIONS ──────────────────────────────────────

@app.get("/notifications/{user_id}")
def get_notifications(user_id: str):
    """Return unread notifications for a user. Frontend polls this every 5s."""
    db = load_db()
    notifs = [n for n in db["notifications"] if n["user_id"] == user_id and not n["read"]]
    return notifs


@app.post("/notifications/{notif_id}/read")
def mark_read(notif_id: str):
    """Mark a notification as read so it doesn't appear again."""
    db = load_db()
    for n in db["notifications"]:
        if n["id"] == notif_id:
            n["read"] = True
    save_db(db)
    return {"ok": True}


# ── ANALYTICS ──────────────────────────────────────────

@app.get("/analytics/peak-hours")
def get_peak_hours():
    """Returns hourly busyness scores for the bar chart."""
    db = load_db()
    counts = {h: 0 for h in range(24)}
    for s in db["sessions"]:
        counts[s["hour"]] += 1
    max_count = max(counts.values()) or 1
    return [
        {
            "hour": h,
            "label": f"{h:02d}:00",
            "sessions": counts[h],
            "busyness_score": round((counts[h] / max_count) * 100),
        }
        for h in range(24)
    ]


@app.get("/analytics/peak-heatmap")
def get_peak_heatmap():
    """
    Peak Heatmap by Day × Hour.
    Returns a 7×24 grid of busyness scores for the heatmap visualisation.
    This lets users see "Monday 9 PM is always packed" at a glance.
    """
    days  = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    db    = load_db()
    grid  = {d: {h: 0 for h in range(24)} for d in days}

    for s in db["sessions"]:
        day = s.get("day_of_week")
        hr  = s.get("hour")
        if day in grid and hr is not None:
            grid[day][hr] += 1

    # Find global max for normalisation
    all_vals = [grid[d][h] for d in days for h in range(24)]
    max_val  = max(all_vals) or 1

    result = []
    for d in days:
        for h in range(24):
            result.append({
                "day":            d,
                "hour":           h,
                "sessions":       grid[d][h],
                "busyness_score": round((grid[d][h] / max_val) * 100),
            })
    return result


# ═══════════════════════════════════════════════════════
# AI CHAT — RAG + Claude
# ═══════════════════════════════════════════════════════

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """
You are WashMate AI, the smart laundry assistant for a student hostel.
Personality: helpful, warm, concise. Use emojis sparingly.

You have access to LIVE DATA about current machine usage, registered residents,
queue status, and HISTORICAL DATA about 30 days of usage patterns.

Rules:
1. Ground every answer in the live data provided — never make up machine names or resident names.
2. For "who is using machine X?" questions — look in the OCCUPANT DATA section.
3. For "is [Name] in Room [X] using a machine?" — check the occupant data by name AND room.
4. For "best time" questions — reference the actual quietest hours from the peak data.
5. If machines are free, say so immediately and clearly.
6. Keep responses under 100 words unless the user asks for detail.
7. If asked something unrelated to laundry/hostel scheduling, politely redirect.
8. For peak heatmap questions, mention specific days and hours from the data.
"""


def build_rag_context(db: dict) -> str:
    """
    RETRIEVAL-AUGMENTED GENERATION (RAG):
    We pull structured data from our database and turn it into
    a plain-English context block that Claude reads before answering.

    This is why Claude can answer "Is Alice in Room 101 using the machine?" —
    because we're injecting that answer into the prompt as context.
    """
    # Machine occupancy
    machine_lines = []
    for m in db["machines"]:
        if m["status"] == "in_use" and m["started_by_user_id"]:
            u = get_user(db, m["started_by_user_id"])
            if u:
                rem = minutes_remaining(m)
                machine_lines.append(
                    f"  - {m['name']}: IN USE by {u['name']} (Room {u['room']}) | "
                    f"Mode: {WASH_MODES.get(m['mode'],{}).get('label','?')} | "
                    f"{rem} min remaining"
                )
        elif m["status"] == "escalation":
            target = get_user(db, m.get("escalation_target_user_id"))
            machine_lines.append(
                f"  - {m['name']}: AWAITING CONFIRMATION from "
                f"{target['name'] if target else 'next user'} (5-min window active)"
            )
        else:
            machine_lines.append(f"  - {m['name']}: FREE")

    # Queue
    queue_lines = []
    for i, q in enumerate(db["queue"]):
        u = get_user(db, q["user_id"])
        if u:
            queue_lines.append(f"  #{i+1}: {u['name']} (Room {u['room']})")

    # Peak hours (top 3 busiest)
    counts = {h: 0 for h in range(24)}
    for s in db["sessions"]:
        counts[s["hour"]] += 1
    top3  = sorted(counts, key=counts.get, reverse=True)[:3]
    low3  = sorted(counts, key=counts.get)[:3]

    # Busiest day-hour combos
    day_hour = {}
    for s in db["sessions"]:
        key = f"{s['day_of_week']} at {s['hour']:02d}:00"
        day_hour[key] = day_hour.get(key, 0) + 1
    top_slots = sorted(day_hour, key=day_hour.get, reverse=True)[:3]

    # All registered users (for identity queries)
    user_lines = [f"  - {u['name']} | Room {u['room']} | Phone {u['phone']}" for u in db["users"]]

    return f"""
=== LIVE HOSTEL DATA ({datetime.now().strftime('%A %H:%M')}) ===

MACHINE STATUS:
{chr(10).join(machine_lines)}

QUEUE ({len(db['queue'])} waiting):
{chr(10).join(queue_lines) if queue_lines else '  (empty)'}

REGISTERED RESIDENTS:
{chr(10).join(user_lines)}

PEAK HOUR ANALYSIS (from {len(db['sessions'])} historical sessions):
  Busiest hours of day: {', '.join(f'{h:02d}:00' for h in top3)}
  Quietest hours of day: {', '.join(f'{h:02d}:00' for h in low3)}
  Busiest day+time slots: {', '.join(top_slots)}
""".strip()


@app.post("/chat")
async def chat(body: ChatRequest):
    """
    The AI chat endpoint.
    Flow: user message → fetch live DB context → inject into Claude → return answer.
    """
    if not ANTHROPIC_API_KEY:
        return {
            "reply": (
                "⚠️ Demo mode — AI key not set. Based on historical data, "
                "the quietest times are typically 10:00–12:00 and 14:00–17:00. "
                "Set ANTHROPIC_API_KEY in your terminal to enable the full AI assistant."
            )
        }

    db = load_db()
    context = build_rag_context(db)

    augmented_message = f"""
[LIVE DATA CONTEXT — use this to answer the question]
{context}

[USER QUESTION]
{body.message}
""".strip()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key":          ANTHROPIC_API_KEY,
                "anthropic-version":  "2023-06-01",
                "content-type":       "application/json",
            },
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": 350,
                "system":     SYSTEM_PROMPT,
                "messages":   [{"role": "user", "content": augmented_message}],
            },
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Claude API error: {resp.text}")

    return {"reply": resp.json()["content"][0]["text"]}
