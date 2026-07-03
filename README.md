# ♠️ Poker Bot — evm0x

Two production poker bots competing on [arena.dev.fun](https://arena.dev.fun):

## Bots

### 1. S6 Playground Bot (`playground_s6_bot.py`)
**6-max No-Limit Texas Hold'em** — ring game grinding

- **Strategy:** SMART GRIND v2
- **VPIP:** ~12% (ultra-tight)
- **Key features:**
  - Value betting 2.5x pot with monsters
  - Blind stealing from late position
  - Short stack push/fold optimization
  - Auto-rebuy handling
  - Watchdog auto-restart on crash

### 2. Heads-Up Ladder Bot (`strategy_hu.py`)
**1v1 ranked ladder** — submitted to Arena sandbox

- **Strategy:** AGGRESSIVE TIGHT
- **VPIP:** ~60% BTN, ~40% BB
- **Key features:**
  - Position-aware ranges (BTN open / BB defend)
  - 3-bet / 4-bet premium selection
  - Board texture analysis (wet/paired/scary)
  - TrueSkill rating system
  - Deck dealt twice — no luck edge

## Architecture

```
poker-bot/
├── playground_s6_bot.py    # S6 ring game agent
├── strategy_hu.py          # Heads-Up ladder strategy
└── README.md
```

## How Arena Works

- **Playground:** Agent polls API, joins matchmaking queue, plays at tables
- **Heads-Up Ladder:** Upload `strategy.py` → Arena server runs it 24/7
- Every deck is dealt twice with seats swapped → pure skill, no variance edge

## Setup

```bash
# Playground
python3 playground_s6_bot.py

# Heads-Up (upload to Arena)
# Submit strategy_hu.py via arena.dev.fun/submissions
```

## Current Rankings

| Competition | Rank | Chips/Rating |
|---|---|---|
| [Poker] Playground S6 | #60 | 999 chips |
| [Poker] Heads-Up Ladder S1 | TBD | TrueSkill grinding |

## License

MIT — feel free to fork and improve.
