#!/usr/bin/env python3
"""evm0x — Heads-Up Ladder S1 — AGGRESSIVE TIGHT"""

RANKS = {r: i for i, r in enumerate("23456789TJQKA")}

def hand_key(c1, c2):
    r1, s1 = c1[0], c1[1]; r2, s2 = c2[0], c2[1]
    hi, lo, suited = (r1, r2, s1 == s2) if RANKS.get(r1,0) >= RANKS.get(r2,0) else (r2, r1, s1 == s2)
    return f"{hi}{lo}{'s' if suited else 'o'}"

def hand_strength(hole, board):
    if len(hole) < 2: return 0
    all_cards = hole + (board or [])
    ranks = [c[0] for c in all_cards]
    suits = [c[1] for c in all_cards]
    rc, sc = {}, {}
    for r in ranks: rc[r] = rc.get(r,0) + 1
    for s in suits: sc[s] = sc.get(s,0) + 1
    has_pair = any(c >= 2 for c in rc.values())
    has_2pr = sum(1 for c in rc.values() if c >= 2) >= 2
    has_trips = any(c >= 3 for c in rc.values())
    has_quads = any(c >= 4 for c in rc.values())
    has_flush = any(c >= 5 for c in sc.values())
    fd = any(c >= 4 for c in sc.values())
    rv = sorted(set(RANKS.get(r,-1) for r in ranks))
    has_straight = False
    for i in range(len(rv)-4):
        if rv[i+4] - rv[i] == 4: has_straight = True
    if {12,0,1,2,3}.issubset(set(rv)): has_straight = True
    if has_straight and has_flush: base = 100
    elif has_quads: base = 95
    elif has_flush: base = 90
    elif has_straight: base = 85
    elif has_trips: base = 80
    elif has_2pr: base = 65
    elif has_pair:
        pr = max(r for r,c in rc.items() if c >= 2)
        base = 45 + RANKS.get(pr,5)
    else:
        base = max(0, 5 + sum(RANKS.get(r,5) for r in ranks[:2]))
    if fd and not has_flush: base = min(base+8, 95)
    return min(base, 100)

# HU ranges
BTN_OPEN = {hand_key(r1+s1, r2+s2) for r1 in "AKQJT98765432" for s1 in "shdc" for r2 in "AKQJT98765432" for s2 in "shdc"
            if (r1 != r2 or s1 != s2) and hand_key(r1+s1, r2+s2) in {
    "AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22",
    "AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
    "KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s",
    "QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s",
    "JTs","J9s","J8s","J7s","J6s","J5s","J4s","J3s","J2s",
    "T9s","T8s","T7s","T6s","T5s","T4s","T3s","T2s",
    "98s","97s","96s","95s","94s","93s","92s",
    "87s","86s","85s","84s","83s","82s",
    "76s","75s","74s","73s","72s",
    "65s","64s","63s","62s",
    "54s","53s","52s","43s","42s","32s",
    "AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o",
    "KQo","KJo","KTo","K9o","K8o","K7o","K6o","K5o","K4o","K3o","K2o",
    "QJo","QTo","Q9o","Q8o","JTo","J9o","J8o","T9o","T8o",
    "98o","87o","76o","65o","54o"
}}

PREMIUM_3BET = {"AA","KK","QQ","JJ","TT","AKs","AQs","AKo","AQo"}
PREMIUM_4BET = {"AA","KK","QQ","AKs","AKo"}
BB_DEFEND = {
    "AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22",
    "AKs","AQs","AJs","ATs","A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
    "KQs","KJs","KTs","K9s","K8s","K7s","K6s","K5s","K4s","K3s","K2s",
    "QJs","QTs","Q9s","Q8s","Q7s","Q6s","Q5s","Q4s","Q3s","Q2s",
    "JTs","J9s","J8s","J7s","J6s","J5s","J4s","J3s","J2s",
    "T9s","T8s","T7s","T6s","T5s","T4s","T3s","T2s",
    "98s","97s","96s","95s","94s","93s","87s","86s","85s","84s",
    "76s","75s","74s","65s","64s","54s",
    "AKo","AQo","AJo","ATo","A9o","A8o","A7o","A6o","A5o","A4o","A3o","A2o",
    "KQo","KJo","KTo","K9o","K8o","K7o",
    "QJo","QTo","Q9o","JTo","J9o","T9o","98o","87o","76o","65o","54o"
}

def act(table):
    """
    table keys:
      hole_cards: [str, str] — your cards, e.g. ["Ah","Kd"]
      community_cards: [str] — board cards
      stack: int — your chips
      current_bet: int — amount to call (0 if no bet)
      pot: int — total pot
      min_raise: int — minimum raise amount (or raise_to)
      big_blind: int — big blind amount
      position: str — "BTN" or "BB"
      seat_count: int — 2 for heads-up
      allowed_actions: list — ["fold","check","call","bet","raise","all_in"] or similar
    """
    hole = table.get("hole_cards", [])
    board = table.get("community_cards", [])
    stack = table.get("stack", 1000)
    bb = table.get("big_blind", 2)
    pot = table.get("pot", 0)
    current_bet = table.get("current_bet", 0)
    min_raise = table.get("min_raise", bb)
    pos = table.get("position", "BB")
    allowed = table.get("allowed_actions", [])

    if len(hole) < 2:
        return {"action": "fold"}

    strength = hand_strength(hole, board)
    hk = hand_key(*hole)
    is_btn = (pos == "BTN")
    bb_count = stack // bb if bb > 0 else 100

    # Board analysis
    board_ranks = [c[0] for c in board] if board else []
    board_suits = [c[1] for c in board] if board else []
    sc = {}
    for s in board_suits: sc[s] = sc.get(s,0) + 1
    is_wet = bool(board) and any(c >= 3 for c in sc.values())
    is_paired = bool(board) and len(set(board_ranks)) < len(board_ranks)
    is_scary = is_wet or is_paired or ("A" in board_ranks and len(board) >= 2)

    # ═══ PREFLOP ═══
    if not board:
        if bb_count < 15:  # SHORT STACK
            if is_btn:
                if hk in PREMIUM_3BET or hk in {"99","88","AJs","ATs","KQs"}:
                    return {"action": "all_in", "amount": stack}
                if hk in BTN_OPEN:
                    return {"action": "raise", "amount": min_raise}
                return {"action": "fold"}
            else:  # BB
                if current_bet == 0:
                    return {"action": "check"}
                if hk in PREMIUM_3BET:
                    return {"action": "all_in", "amount": stack}
                if current_bet <= bb * 2.5:
                    return {"action": "call", "amount": current_bet}
                return {"action": "fold"}

        # BTN
        if is_btn:
            if current_bet == 0:
                if hk in BTN_OPEN:
                    if hk in PREMIUM_3BET:
                        return {"action": "raise", "amount": max(min_raise, bb * 3)}
                    return {"action": "raise", "amount": min_raise}
                return {"action": "fold"}
            else:  # facing 3-bet
                if hk in PREMIUM_4BET:
                    r = max(min_raise, current_bet * 3)
                    if r >= stack * 0.5:
                        return {"action": "all_in", "amount": stack}
                    return {"action": "raise", "amount": r}
                if hk in PREMIUM_3BET:
                    if current_bet <= bb * 8:
                        return {"action": "call", "amount": current_bet}
                    return {"action": "fold"}
                if hk in {"99","88","77","AJs","ATs","KQs","KJs"}:
                    if current_bet <= bb * 5:
                        return {"action": "call", "amount": current_bet}
                return {"action": "fold"}

        # BB
        if current_bet == 0:
            return {"action": "check"}
        if hk in PREMIUM_3BET:
            r = max(min_raise, current_bet * 3 + bb)
            return {"action": "raise", "amount": r}
        if hk in BB_DEFEND:
            if current_bet <= bb * 3:
                return {"action": "call", "amount": current_bet}
        return {"action": "fold"}

    # ═══ POSTFLOP ═══
    if strength >= 85:  # Monster
        if current_bet > 0:
            r = max(min_raise, current_bet * 3 + pot // 2)
            if r >= stack * 0.6: return {"action": "all_in", "amount": stack}
            return {"action": "raise", "amount": r}
        bet = int(pot * 2.5) if pot > 0 else min_raise
        return {"action": "bet", "amount": min(bet, stack)}

    if strength >= 70:  # Strong
        if current_bet > 0:
            if current_bet <= pot * 0.7:
                r = max(min_raise, current_bet * 2 + pot // 3)
                return {"action": "raise", "amount": r}
            if current_bet <= pot * 1.5:
                return {"action": "call", "amount": current_bet}
            return {"action": "fold"}
        bet = int(pot * 1.0) if pot > 0 else min_raise
        return {"action": "bet", "amount": min(bet, stack)}

    if strength >= 55:  # Medium
        if current_bet == 0:
            if not is_scary:
                bet = int(pot * 0.5) if pot > 0 else min_raise
                return {"action": "bet", "amount": min(bet, stack)}
            return {"action": "check"}
        if current_bet <= pot * 0.4:
            return {"action": "call", "amount": current_bet}
        return {"action": "fold"}

    if strength >= 40:  # Weak
        if current_bet == 0:
            if not is_scary and is_btn:
                bet = int(pot * 0.4) if pot > 0 else min_raise
                return {"action": "bet", "amount": min(bet, stack)}
            return {"action": "check"}
        if current_bet <= pot * 0.2 and is_btn:
            return {"action": "call", "amount": current_bet}
        return {"action": "fold"}

    # Trash
    if current_bet > 0:
        return {"action": "fold"}
    return {"action": "check"}
