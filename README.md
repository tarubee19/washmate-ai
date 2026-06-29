# 🫧 WashMate AI v3

> A physical-digital laundry management system for student hostels — combining IoT hardware control, Smart Queue escalation, roll-number identity, roommate fallback notifications, and a compliance reputation engine.

---

## The Problem

In a 60-person hostel sharing 2 washing machines, three compounding failures occur daily:

| Problem | Root Cause | User Impact |
|---|---|---|
| Blind trips | No visibility into machine status | Wasted walk, wasted time |
| Clothes abandoned | No accountability after cycle ends | Machine blocked for 1–2 hours |
| Ghost queues | Users not present when their turn arrives | Machine sits idle between users |
| Rogue usage | Users bypass the app entirely | System data becomes untrustworthy |
| No accountability | Anonymous usage, no consequences | Repeat offenders ruin it for everyone |

---

## Solution Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (index.html)                          │
│  Roll Login │ Mode Select │ Basket Policy │ Ready Check │ Chat      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP REST
┌──────────────────────────────▼──────────────────────────────────────┐
│                     FASTAPI BACKEND (main.py)                        │
│                                                                     │
│  ┌────────────────────┐   ┌─────────────────────────────────────┐  │
│  │  Identity Layer    │   │  Smart Queue Engine                 │  │
│  │  roll → name,room  │   │  join / leave / ready-check         │  │
│  │  roommate mapping  │   │  5-min escalation + auto-fallback   │  │
│  └────────────────────┘   └─────────────────────────────────────┘  │
│                                                                     │
│  ┌────────────────────┐   ┌─────────────────────────────────────┐  │
│  │  Wash Cycle Monitor│   │  RAG + LLM (Claude API)             │  │
│  │  10-min ready check│   │  live DB context → grounded answers │  │
│  │  abandonment alert │   └─────────────────────────────────────┘  │
│  │  roommate fallback │                                            │
│  └────────────────────┘   ┌─────────────────────────────────────┐  │
│                           │  Compliance Engine                  │  │
│  ┌────────────────────┐   │  strikes / bans / leaderboard       │  │
│  │  Relay Controller  │   └─────────────────────────────────────┘  │
│  │  relay_control()   │                                            │
│  │  sends HTTP to     │                                            │
│  │  ESP32 → ON/OFF    │                                            │
│  └────────────────────┘                                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP (local WiFi)
┌──────────────────────────────▼──────────────────────────────────────┐
│                     ESP32 + RELAY (hardware/esp32_firmware.ino)      │
│  Receives ON/OFF commands → opens/closes relay → machine on/off     │
│  CT current sensor → detects rogue washers (machine used without app)│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Feature List

### Core Features
- **Roll-number login** — maps to name, room, phone, roommate automatically
- **3 wash modes** — Heavy (45 min), Light (30 min), Spin/Dry (15 min)
- **Extend +15 min** — rainy season buffer, notifies queue of delay
- **Basket policy checkbox** — mandatory before starting (creates physical handover protocol)
- **Machine occupancy display** — "In Use by Arjun Sharma · Room A-101 · Heavy Wash"

### Smart Queue Escalation
```
T-10 min  → Ready Check: "Still coming? YES/NO"
T=0       → Cycle ends, relay OFF, abandonment timer starts
T+0       → Next person: "Machine free! Confirm in 5 min"
T+5 min   → No confirm → STRIKE + try next person in queue
T+5 min   → No clothes collected → STRIKE + roommate notification
T+10 min  → System permits next user to move clothes to basket
```

### Compliance Engine
- 3 strikes in 7 days = 24-hour queue-priority ban
- Compliance rate shown per student (0–100%)
- Leaderboard tab shows community compliance standing
- Strikes reset every 30 days (proportionate punishment)

### Crowdsourced Fault Detection
- "Report Broken" button on any machine
- 2 unique reports → machine auto-set to OUT OF ORDER
- Queue for that machine paused, users notified
- Warden alert logged (SMS/WhatsApp in production)

### IoT Hardware Integration
- ESP32 microcontroller + relay module (~₹500 total)
- Machine cannot start without app registration (relay defaults OFF)
- CT current sensor detects rogue washers (machine active without relay ON)
- Software-only mode available (RELAY_ENABLED = False)

### AI Assistant (RAG)
- Live data injected into Claude prompt before every answer
- Answers: "Is Arjun in Room A-101 using a machine?" → checks live occupancy data
- Peak hour heatmap (7 days × 24 hours) from 30 days of historical data
- Compliance queries: "Who has the best compliance score?"

---

## Getting Started

### Software Only (no hardware needed)

```bash
git clone https://github.com/YOUR_USERNAME/washmate-ai.git
cd washmate-ai/backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-your-key"
uvicorn main:app --reload
# Open frontend/index.html in browser
```

### With Hardware (ESP32 + Relay)

1. Buy: ESP32 dev board (₹400) + 5V relay module (₹80) + jumper wires
2. Wire relay: ESP32 pin 26 → relay IN | 5V → VCC | GND → GND
3. Wire machine: wall socket → relay NO/COM → washing machine (live wire only)
4. Open `hardware/esp32_firmware.ino` in Arduino IDE
5. Set your WiFi credentials and upload to ESP32
6. Note the IP address printed in Serial Monitor
7. In `backend/main.py`: set `RELAY_ENABLED = True` and update `RELAY_IPS`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla HTML/CSS/JS (zero build step) |
| Backend | Python + FastAPI |
| AI | Anthropic Claude claude-sonnet-4-6 (RAG) |
| Async | Python asyncio + FastAPI BackgroundTasks |
| Hardware | ESP32 + relay + optional CT-013 current sensor |
| Database | JSON file (swap for PostgreSQL in production) |

---

## North Star Metric

**Machine Utilisation Rate** — percentage of time machines are actively running washes vs sitting idle. Every feature maps directly to improving this:
- Ready checks eliminate idle time between users
- Abandonment alerts reduce post-cycle dead time
- Compliance strikes reduce repeat offenders
- Peak heatmap shifts demand away from peak hours

---

## Known Limitations & V4 Roadmap

| Limitation | V4 Solution |
|---|---|
| Relay can be physically bypassed | CT current sensor detects it + warden alert |
| Phone-off users miss notifications | WhatsApp Business API via Twilio |
| Manual "mark done" not reliable | Computer vision on machine door |
| JSON DB doesn't scale | PostgreSQL + Supabase |
| Single hostel | Multi-hostel SaaS dashboard |

---

*Built as an AI Product Management portfolio project — demonstrating hardware-software integration, edge case analysis, and AI-powered scheduling at the hostel scale.*
