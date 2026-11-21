#!/usr/bin/env python3
"""evm0x S7 Bot — Arena Poker Playground
Goal: steady chip growth → top leaderboard

v1 CHANGES from S6:
- S7 competition ID
- Wider VPIP (15%) — more hands = more value opportunities
- Better blind defense from BB
- Postflop c-bet more aggressively on dry boards
- Short stack jam wider (pocket pairs 66+)
- More position-aware aggression
"""

import json, os, time, sys
import urllib.request, urllib.error

# ═══ S7 CONFIG ═══
CID = "cmrcbw41k02chd7tlio0dbebb"
BASE = "https://arena.dev.fun/api/arena"
PID_FILE = "/tmp/poker_s7_bot.pid"

API_KEY = None
AGENT_ID = None


def _load_credentials():
    """Read the arena credentials the first time they are needed.

    This used to run at import time, which meant the decision logic could not be
    imported without a live account on disk, so it could not be tested at all.
    """
    global API_KEY, AGENT_ID
    if API_KEY is None:
        with open(os.path.expanduser("~/.arena-credentials")) as f:
            cred = json.load(f)
        API_KEY = cred["apiKey"]
        AGENT_ID = cred["agentId"]

AGENT_ID = None

RANKS = {r: i for i, r in enumerate("23456789TJQKA")}

# ═══ RANGE ~15% VPIP ═══
CORE_RANGE = {
    "AA", "KK", "QQ", "JJ", "TT", "99", "88", "77", "66",
    "AKs", "AQs", "AJs", "ATs", "A5s", "A4s",
    "KQs", "KJs", "KTs",
    "QJs", "JTs", "T9s", "98s",
    "AKo", "AQo", "AJo",
    "KQo",
}

PREMIUM = {"AA", "KK", "QQ", "AKs", "AKo"}

LATE_RANGE = CORE_RANGE | {
    "55", "44", "A9s", "A8s", "A3s", "A2s",
    "QTs", "K9s", "J9s", "87s", "76s",
    "ATo", "KJo", "QJo",
}

# Short stack jam range
SHORT_JAM = PREMIUM | {"JJ", "TT", "99", "AQs", "AJs", "KQs"}

# BB defend wide
BB_DEFEND = CORE_RANGE | {
    "55", "44", "33", "A9s", "A8s", "A7s", "A3s", "A2s",
    "QTs", "K9s", "J9s", "T8s", "87s", "76s", "65s",
    "ATo", "KJo", "KTo", "QJo", "JTo",
}

def make_hand_key(c1, c2):
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    hi, lo = (r1, r2) if RANKS.get(r1, 0) >= RANKS.get(r2, 0) else (r2, r1)
    # Pocket pairs are written "AA", never "AAo"/"AAs" — every range set spells them that way.
    if hi == lo:
        return f"{hi}{lo}"
    return f"{hi}{lo}{'s' if s1 == s2 else 'o'}"

def legal_bet(pot, fraction, stack, min_raise):
    """A bet the table will accept, or None when no legal bet is that small.

    `minRaiseTo` is the smallest amount the server accepts. The bet sites below
    used to ignore it and return whatever the fraction worked out to, so a small
    pot produced a bet of 0, which the server rejects and the bot retries.
    """
    size = int(pot * fraction) if pot > 0 else min_raise
    if size > stack:
        return stack
    return size if size >= min_raise else None


def hand_strength(hole, board):
    if len(hole) < 2:
        return 0
    all_cards = hole + (board or [])
    ranks = [c[0] for c in all_cards]
    suits = [c[1] for c in all_cards]

    rc = {}
    for r in ranks:
        rc[r] = rc.get(r, 0) + 1

    has_pair = any(c >= 2 for c in rc.values())
    has_two_pair = sum(1 for c in rc.values() if c >= 2) >= 2
    has_trips = any(c >= 3 for c in rc.values())
    has_quads = any(c >= 4 for c in rc.values())
    has_full_house = has_trips and has_two_pair

    sc = {}
    for s in suits:
        sc[s] = sc.get(s, 0) + 1
    fd = any(c >= 4 for c in sc.values())
    has_flush = any(c >= 5 for c in sc.values())

    rv = sorted(set(RANKS.get(r, -1) for r in ranks))
    has_straight = False
    for i in range(len(rv) - 4):
        if rv[i+4] - rv[i] == 4:
            has_straight = True
    if {12, 0, 1, 2, 3}.issubset(set(rv)):
        has_straight = True

    if has_straight and has_flush: base = 100
    elif has_quads: base = 95
    elif has_full_house: base = 92
    elif has_flush: base = 90
    elif has_straight: base = 85
    elif has_trips: base = 80
    elif has_two_pair: base = 65
    elif has_pair:
        pr = max(r for r, c in rc.items() if c >= 2)
        base = 45 + RANKS.get(pr, 5)
    else:
        base = max(0, 5 + sum(RANKS.get(r, 5) for r in ranks[:2]))
    if fd and not has_flush:
        base = min(base + 8, 95)
    return min(base, 100)

def api(method, path, body=None):
    _load_credentials()
    url = BASE + path
    headers = {"x-arena-api-key": API_KEY, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except:
            return {"error": f"http_{e.code}"}
    except Exception as e:
        return {"error": str(e)[:80]}

def decide(hole, board, stack, bb, pot, current_bet, min_raise, position, seat_count):
    strength = hand_strength(hole, board)
    hand_key = make_hand_key(*hole)
    in_range = hand_key in CORE_RANGE
    in_late = hand_key in LATE_RANGE
    is_late = position >= seat_count - 2
    is_btn = position == seat_count - 1
    is_bb = position == 0
    bb_count = stack // bb if bb > 0 else 100

    board_ranks = [c[0] for c in (board or [])]
    board_suits = [c[1] for c in (board or [])]
    sc = {}
    for s in board_suits:
        sc[s] = sc.get(s, 0) + 1
    is_wet = bool(board) and any(c >= 3 for c in sc.values())
    is_paired = bool(board) and len(set(board_ranks)) < len(board_ranks)
    is_dry = bool(board) and not is_wet and not is_paired and len(board) >= 2
    is_scary = is_wet or is_paired or ("A" in board_ranks and len(board) >= 2)

    # ═══ PREFLOP ═══
    if not board:
        # ULTRA SHORT (<8bb) — push/fold
        if bb_count < 8:
            if hand_key in SHORT_JAM:
                return ("all_in", stack, "ultra short jam")
            if is_late and current_bet == 0 and hand_key in {"88", "77", "66", "ATs", "KJs"}:
                return ("all_in", stack, "ultra late steal")
            return ("fold", 0, "ultra short fold")

        # SHORT (8-18bb)
        if bb_count < 18:
            if hand_key in PREMIUM:
                if current_bet > 0:
                    return ("all_in", stack, "short jam premium")
                return ("raise", min_raise, "short open premium")
            if hand_key in {"JJ", "TT", "99", "AQs", "AJs", "KQs", "88", "77"}:
                if current_bet == 0:
                    return ("raise", min_raise, "short open strong")
                if current_bet <= bb * 3:
                    return ("all_in", stack, "short jam vs raise")
                return ("fold", 0, "short fold big raise")
            if is_bb and current_bet <= bb * 2 and hand_key in BB_DEFEND:
                return ("call", current_bet, "short BB defend")
            return ("fold", 0, "short fold")

        # DEEP
        if current_bet == 0:
            if hand_key in PREMIUM:
                return ("raise", max(min_raise, bb * 4), "premium open 4x")
            if in_range:
                return ("raise", min_raise, "open range")
            if is_late and in_late:
                return ("raise", min_raise, "late steal")
            if is_btn and hand_key in {"A2s", "A3s", "A4s", "A5s", "K9s", "Q9s", "J8s", "T8s"}:
                return ("raise", min_raise, "btn wide steal")
            if is_bb:
                return ("check", 0, "BB free")
            return ("fold", 0, "fold junk")

        # Facing raise
        if hand_key in PREMIUM:
            reraise = max(min_raise, current_bet * 3 + bb)
            if reraise >= stack * 0.55:
                return ("all_in", stack, "4bet jam premium")
            return ("raise", reraise, "3bet premium")

        if hand_key in {"JJ", "TT", "99", "AQs", "AJs"}:
            if current_bet <= bb * 5:
                return ("call", current_bet, "call strong")
            return ("fold", 0, "too big")

        if hand_key in {"88", "77", "66"} and is_late:
            if current_bet <= bb * 3:
                return ("call", current_bet, "set mine")

        if is_bb and current_bet <= bb * 3:
            if hand_key in BB_DEFEND:
                return ("call", current_bet, "BB defend")

        return ("fold", 0, "fold pre")

    # ═══ POSTFLOP ═══
    # MONSTER
    if strength >= 85:
        if current_bet > 0:
            reraise = max(min_raise, current_bet * 3 + pot // 2)
            if reraise >= stack * 0.6:
                return ("all_in", stack, "jam monster")
            return ("raise", reraise, "raise monster")
        bet_size = int(pot * 2.5) if pot > 0 else min_raise
        bet_size = min(bet_size, stack)
        if bet_size < min_raise:
            return ("check", 0, "trap monster")
        return ("bet", bet_size, "bet monster 2.5x")

    # STRONG (two pair, TPTK)
    if strength >= 70:
        if current_bet > 0:
            if current_bet <= pot * 0.6:
                reraise = max(min_raise, current_bet * 2 + pot // 3)
                return ("raise", reraise, "raise strong")
            if current_bet <= pot * 1.5:
                return ("call", current_bet, "call strong")
            return ("fold", 0, "overbet fold")
        size = legal_bet(pot, 1.2, stack, min_raise)
        if size is None:
            return ("check", 0, "value bet 1.2x, below min raise")
        return ("bet", size, "value bet 1.2x")

    # MEDIUM — c-bet dry, check scary
    if strength >= 55:
        if current_bet == 0:
            if is_dry and is_late:
                size = legal_bet(pot, 0.7, stack, min_raise)
                if size is None:
                    return ("check", 0, "c-bet dry, below min raise")
                return ("bet", size, "c-bet dry")
            if not is_scary:
                size = legal_bet(pot, 0.5, stack, min_raise)
                if size is None:
                    return ("check", 0, "c-bet medium, below min raise")
                return ("bet", size, "c-bet medium")
            return ("check", 0, "check medium")
        if current_bet <= pot * 0.35:
            return ("call", current_bet, "call medium small")
        return ("fold", 0, "fold medium")

    # WEAK — float IP, fold OOP
    if strength >= 40:
        if current_bet == 0:
            if is_dry and is_late and not is_scary:
                size = legal_bet(pot, 0.4, stack, min_raise)
                if size is None:
                    return ("check", 0, "stab dry IP, below min raise")
                return ("bet", size, "stab dry IP")
            return ("check", 0, "check weak")
        if current_bet <= pot * 0.25 and is_late:
            return ("call", current_bet, "float cheap IP")
        return ("fold", 0, "fold weak")

    # TRASH
    if current_bet > 0:
        return ("fold", 0, "fold trash")
    return ("check", 0, "check trash")

def main():
    _load_credentials()
    print(f"=== evm0x S7 Bot v1 ===")
    print(f"Agent: {AGENT_ID} | Competition: {CID}")

    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            os.kill(old_pid, 9)
            time.sleep(0.5)
        except (OSError, ValueError):
            pass
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    print("Joining S7 queue...")
    r = api("POST", "/texas/join", {"competitionId": CID})
    print(f"Join: {r.get('kind', r.get('error', r))}")

    consecutive_errors = 0
    _last_dedup = {}
    _stats = {"actions": 0, "folds": 0, "calls": 0, "raises": 0, "checks": 0, "all_ins": 0, "bets": 0}

    while True:
        try:
            now = time.time()
            pa = api("GET", f"/texas/pending-actions?competitionId={CID}")

            if "error" in pa:
                consecutive_errors += 1
                time.sleep(2 if consecutive_errors > 3 else 0.5)
                continue

            tables = pa.get("tables", [])
            if not tables:
                time.sleep(0.3)
                continue

            acted = False
            for t in sorted(tables, key=lambda x: x.get("actionDeadlineAt") or 9e15):
                if acted:
                    break

                deadline = t.get("actionDeadlineAt")
                if deadline:
                    remaining_ms = int(deadline) - int(now * 1000)
                    if remaining_ms < 200:
                        continue

                tid = t.get("tableId") or t.get("id")
                street = t.get("street", "")
                self_seat = None
                hole = []
                stack = 0
                for s in t.get("seats", []):
                    if s.get("agentId") == AGENT_ID:
                        self_seat = s.get("seatNumber")
                        hole = s.get("holeCards", [])
                        stack = s.get("stackChips", 0)

                current_seat = t.get("currentSeatNumber")
                if current_seat != self_seat or len(hole) < 2:
                    continue

                dedup_key = f"{tid}:{street}:{tuple(sorted(hole))}"
                age = now - _last_dedup.get(dedup_key, 0)
                if age < 1.5:
                    continue

                pot = t.get("potChips", 0) or 0
                current_bet = t.get("currentBet", 0) or 0
                min_raise = t.get("minRaiseTo", 4) or 4
                bb = t.get("bigBlindChips", 2) or 2
                board = t.get("boardCards", [])
                seat_count = len(t.get("seats", []))
                position = self_seat if self_seat else 0
                action, amount, reason = decide(
                    hole, board, stack, bb, pot,
                    current_bet, min_raise, position, seat_count
                )

                if action == "check" and current_bet > 0:
                    action = "call"
                if action == "call" and current_bet == 0:
                    action = "check"
                if action in ("raise", "bet") and amount > stack:
                    amount = stack
                if action == "all_in":
                    amount = stack

                hand_key = make_hand_key(*hole)
                hand_str = hand_strength(hole, board)
                bb_count = stack // bb if bb > 0 else 100

                body = {
                    "tableId": tid,
                    "action": action,
                    "amount": amount,
                    "message": f"[S7v1] {reason} | {hand_key} | str={hand_str} | bb={bb_count}"
                }

                print(f"[{_stats['actions']}] {hand_key} {action} {amount} | {reason} (str={hand_str} bb={bb_count})")
                result = api("POST", "/texas/action", body)

                if result.get("error"):
                    print(f"  ERR: {result['error']}")
                else:
                    print(f"  OK")

                _last_dedup[dedup_key] = now
                _stats["actions"] += 1
                stat_key = action.replace("-", "_") + "s"
                _stats[stat_key] = _stats.get(stat_key, 0) + 1
                acted = True
                consecutive_errors = 0
                time.sleep(0.8)

            if acted:
                time.sleep(0.3)
            elif len(tables) > 0:
                time.sleep(0.5)
            else:
                time.sleep(0.3)

            if consecutive_errors >= 5:
                time.sleep(2.0)

        except Exception as e:
            print(f"EXC: {e}")
            consecutive_errors += 1
            time.sleep(3)

if __name__ == "__main__":
    main()
