<!-- BADGES: DO NOT TOUCH — updated via CI -->
<!-- END BADGES -->

# ♠️ Poker Bot — evm0x

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Arena](https://img.shields.io/badge/Arena-dev.fun-8A2BE2)](https://arena.dev.fun)
[![Status: Active](https://img.shields.io/badge/Status-Active-success?logo=github)](https://github.com/EVM0x/poker-bot)
[![S6 Playground](https://img.shields.io/badge/S6-Playground-orange)](https://arena.dev.fun)
[![Heads-Up Ladder](https://img.shields.io/badge/HU-Ladder_S1-blue)](https://arena.dev.fun/headsup-ladder)

Two production poker bots competing on [**arena.dev.fun**](https://arena.dev.fun) — a competitive platform where AI agents play poker 24/7. One grinds 6-max ring games; the other climbs a ranked heads-up ladder.

---

## 🤖 Bots

| Bot | Mode | Strategy | VPIP | Status |
|---|---|---|---|---|
| `playground_s6_bot.py` | 6-max NLHE | SMART GRIND v2 | ~12% | 🟢 Live |
| `strategy_hu.py` | 1v1 Ladder | AGGRESSIVE TIGHT | ~60%/40% | 🟢 Live |

### S6 Playground Bot
**6-max No-Limit Hold'em** — ring game grinding with matchmaking queue.

- **VPIP ~12%** — ultra-tight preflop, only premium hands
- **Value betting** — 2.5× pot with monsters (straight+, set+)
- **Blind stealing** — aggressive from BTN/CO with fold equity
- **Short-stack optimization** — push/fold below 15 BB
- **Auto-rebuy** — handles Arena's rebuy system
- **Watchdog** — cron-based auto-restart on crash

### Heads-Up Ladder Bot
**1v1 ranked** — uploaded to Arena sandbox, runs server-side 24/7.

- **BTN VPIP ~60%** — wide opening range from position
- **BB VPIP ~40%** — defend wide vs single raise
- **3-bet / 4-bet** — premium selection (AA-JJ, AK, AQ)
- **Board texture** — analyzes wet/paired/scary boards
- **TrueSkill rating** — zero-variance: every deck dealt twice, seats swapped

---

## 📁 Architecture

```
poker-bot/
├── playground_s6_bot.py    # S6 6-max ring game agent
├── strategy_hu.py          # Heads-Up ladder strategy (Arena sandbox)
├── README.md               # This file
└── .gitignore
```

---

## ⚙️ How Arena Works

- **Playground:** Agent polls REST API → joins matchmaking queue → seated at tables → plays hands via action endpoint
- **Heads-Up Ladder:** Upload `strategy.py` → Arena sandbox validates → runs 24/7 against every other builder's bot
- **Zero luck edge:** Every deck is dealt twice with seats swapped — climbing means your bot actually outplayed the field

---

## 🚀 Setup

```bash
# Clone
git clone https://github.com/EVM0x/poker-bot.git
cd poker-bot

# Install dependencies
pip install requests

# Run S6 Playground bot
python3 playground_s6_bot.py

# Heads-Up Ladder: upload strategy_hu.py via Arena web UI
# https://arena.dev.fun/headsup-ladder
```

---

## 📊 Current Rankings

| Competition | Rank | Score |
|---|---|---|
| [Poker] Playground S6 | #60 | 999 chips |
| [Poker] Heads-Up Ladder S1 | TBD | TrueSkill grinding |

---

## 📄 License

MIT — fork it, remix it, ship it. [EVM0x](https://github.com/EVM0x)
