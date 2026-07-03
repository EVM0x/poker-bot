#!/usr/bin/env python3
"""evm0x never die — S6 Bot v2 SMART GRIND
Goal: steady chip growth → top 1 by end of season

PHILOSOPHY:
- Tight preflop (12% VPIP) — don't bleed chips on marginal hands
- MEGA value postflop — when we hit, we EXTRACT MAXIMUM
- Position-aware — steal blinds when opportunity arises
- Fold fast when behind — preserve stack for premium spots
- Short stack discipline — push/fold only, no fancy play

v2 CHANGES from v1:
- Added blind stealing from BTN/CO with any playable hand
- Bigger value bets on made hands (2.5x pot for monsters)
- More aggressive 3-bet sizing (3.5x instead of 3x)
- Defend BB wider against late position steals
- Float flops with backdoor equity in position
"""

import json, os, time, sys
import urllib.request, urllib.error

# ═══ S6 CONFIG ═══
CID = "cmr4ou75y1s6vt9h91hqybbsd"
BASE = "https://arena.dev.fun/api/arena"
PID_FILE = "/tmp/poker_s6_bot.pid"

with open(os.path.expanduser("~/.arena-credentials")) as f:
    _cred = json.load(f)
API_KEY = _cred["apiKey"]
AGENT_ID = _cred["agentId"]

RANKS = {r: i for i, r in enumerate("23456789TJQKA")}

# ═══ ELITE RANGE — ~12% VPIP ═══
ELITE_RANGE = {
    "AA", "KK", "QQ", "JJ", "TT", "99",
    "AKs", "AQs", "AJs",
    "KQs",
    "AKo", "AQo",
}

# Late position / steal range
STEAL_RANGE = ELITE_RANGE | {
    "ATs", "KJs", "QJs", "JTs", "T9s", "98s",
    "88", "77",
    "AJo", "KQo", "KJo",
}

# Premium 3-bet / 4-bet / shove
PREMIUM = {"AA", "KK", "QQ", "AKs", "AKo"}

def make_hand_key(c1, c2):
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if RANKS.get(r1, 0) >= RANKS.get(r2, 0):
        return f"{r1}{r2}{'s' if s1 == s2 else 'o'}"
    return f"{r2}{r1}{'s' if s1 == s2 else 'o'}"

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
    in_range = hand_key in ELITE_RANGE
    in_steal = hand_key in STEAL_RANGE
    is_late = position >= seat_count - 2  # CO/BTN
    is_btn = position == seat_count - 1
    is_sb = position == seat_count - 2
    is_bb = position == 0  # assuming BB is position 0 in seat numbering
    bb_count = stack // bb if bb > 0 else 100

    # Board texture
    board_ranks = [c[0] for c in (board or [])]
    board_suits = [c[1] for c in (board or [])]
    sc = {}
    for s in board_suits:
        sc[s] = sc.get(s, 0) + 1
    is_wet = bool(board) and any(c >= 3 for c in sc.values())
    is_paired = bool(board) and len(set(board_ranks)) < len(board_ranks)
    is_scary = is_wet or is_paired or ("A" in board_ranks and len(board) >= 2)

    # ═══ PREFLOP ═══
    if not board:
        # ULTRA SHORT (<10bb) — push/fold
        if bb_count < 10:
            if hand_key in PREMIUM:
                return ("all_in", stack, "ultra short shove premium")
            if hand_key in {"JJ", "TT", "AQs"} and current_bet == 0:
                return ("all_in", stack, "ultra short open strong")
            return ("fold", 0, "ultra short fold")

        # SHORT (10-20bb) — tight push/fold
        if bb_count < 20:
            if hand_key in PREMIUM:
                if current_bet > 0:
                    return ("all_in", stack, "short 4bet shove")
                return ("raise", min_raise, "short open premium")
            if hand_key in {"JJ", "TT", "AQs", "AJs", "KQs"}:
                if current_bet == 0:
                    return ("raise", min_raise, "short open strong")
                if current_bet <= bb * 3:
                    return ("all_in", stack, "short jam vs raise")
                return ("fold", 0, "short fold too big")
            # BB defend short
            if is_bb and current_bet <= bb * 2 and hand_key in STEAL_RANGE:
                return ("all_in", stack, "short BB defend jam")
            return ("fold", 0, "short fold")

        # DEEP — play poker
        # Unopened pot
        if current_bet == 0:
            if hand_key in PREMIUM:
                # Big open with premium
                return ("raise", max(min_raise, bb * 4), "premium open big")
            if in_range:
                return ("raise", min_raise, "open in range")
            # Steal from late position
            if is_late and in_steal:
                return ("raise", min_raise, "late steal")
            # BB defend free
            if is_bb:
                return ("check", 0, "BB free play")
            return ("fold", 0, "fold junk")

        # Facing raise
        if hand_key in PREMIUM:
            # 3-bet BIG
            reraise = max(min_raise, current_bet * 3 + bb)
            if reraise >= stack * 0.55:
                return ("all_in", stack, "4bet jam premium")
            return ("raise", reraise, "3bet premium big")

        # Call 3-bet with strong pairs
        if hand_key in {"JJ", "TT", "AQs"}:
            if current_bet <= bb * 5:
                return ("call", current_bet, "call strong IP")
            return ("fold", 0, "too expensive")

        # Set mine cheap
        if hand_key in {"99", "88", "77"} and is_late:
            if current_bet <= bb * 3:
                return ("call", current_bet, "set mine")

        # BB defend vs late steal
        if is_bb and current_bet <= bb * 3:
            if in_steal:
                return ("call", current_bet, "BB defend")
            if hand_key in {"ATs", "KJs", "KTs", "QJs", "JTs", "AJo"}:
                return ("call", current_bet, "BB defend wide")

        return ("fold", 0, "fold to raise")

    # ═══ POSTFLOP ═══
    # MONSTER (straight+, set, nut flush) — MAX VALUE
    if strength >= 85:
        if current_bet > 0:
            reraise = max(min_raise, current_bet * 3 + pot // 2)
            if reraise >= stack * 0.65:
                return ("all_in", stack, "jam monster")
            return ("raise", reraise, "raise monster huge")
        # Bet BIG for value
        bet_size = int(pot * 2.5) if pot > 0 else min_raise
        bet_size = min(bet_size, stack)
        if bet_size < min_raise:
            return ("check", 0, "trap monster")
        return ("bet", bet_size, "bet monster 2.5x")

    # STRONG (two pair, top pair top kicker) — value bet
    if strength >= 70:
        if current_bet > 0:
            if current_bet <= pot * 0.6:
                reraise = max(min_raise, current_bet * 2 + pot // 3)
                return ("raise", reraise, "raise strong")
            if current_bet <= pot * 1.5:
                return ("call", current_bet, "call strong")
            return ("fold", 0, "overbet vs strong")
        bet_size = int(pot * 1.2) if pot > 0 else min_raise
        return ("bet", min(bet_size, stack), "value bet 1.2x")

    # MEDIUM (top pair weak kicker, middle pair) — pot control
    if strength >= 55:
        if current_bet == 0:
            if not is_scary:
                bet_size = int(pot * 0.6) if pot > 0 else min_raise
                return ("bet", min(bet_size, stack), "c-bet safe")
            return ("check", 0, "check medium scary")
        if current_bet <= pot * 0.35:
            return ("call", current_bet, "call medium small")
        return ("fold", 0, "fold medium")

    # WEAK (draw, bottom pair) — float or fold
    if strength >= 40:
        if current_bet == 0:
            return ("check", 0, "check weak")
        if current_bet <= pot * 0.2 and is_late:
            return ("call", current_bet, "float cheap IP")
        return ("fold", 0, "fold weak")

    # TRASH
    if current_bet > 0:
        return ("fold", 0, "fold trash")
    return ("check", 0, "check trash")

def main():
    print(f"=== evm0x never die S6 v2 SMART GRIND ===")
    print(f"Agent: {AGENT_ID} | Competition: {CID}")

    # Kill old instance
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            os.kill(old_pid, 9)
            time.sleep(0.5)
        except (OSError, ValueError):
            pass
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Join queue
    print("Joining S6 queue...")
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

            # SINGLE ACTION per poll
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

                # Dedup
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

                # Safety
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

                body = {
                    "tableId": tid,
                    "action": action,
                    "amount": amount,
                    "message": f"[S6v2] {reason} | {hand_key} | str={hand_str} | bb={bb_count}"
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
