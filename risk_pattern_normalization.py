"""Mathematically justified implication hierarchy for existing V2 chart patterns.

Only structural implication is encoded here. Similar historical performance is
NOT equivalence or proof of future predictive validity. The active daily veto
does not change unless a separate verified parity/research migration is made.
"""
from downside_pattern_research import CATALOG, _COMBOS

def implication_edges():
    """Return proven stronger -> weaker detector implications."""
    edges = set()
    def add(a, b):
        if a not in CATALOG or b not in CATALOG:
            raise ValueError(f"Unknown catalog relation {a} -> {b}")
        edges.add((a, b))
    for days in (1, 3, 5, 10, 20):
        for direction in ("UP", "DOWN"):
            levels = (1, 3, 5, 10)
            for smaller, larger in zip(levels, levels[1:]):
                add(f"R{days:02d}_{direction}{larger:02d}",
                    f"R{days:02d}_{direction}{smaller:02d}")
    for direction in ("UP", "DOWN"):
        for n in range(3, 8):
            add(f"STREAK{n}_{direction}", f"STREAK{n-1}_{direction}")
    for direction in ("HIGH", "LOW"):
        add(f"{direction}20", f"{direction}10")
        add(f"{direction}10", f"{direction}5")
    for family in ("DRAWDOWN", "REBOUND"):
        add(f"{family}20", f"{family}10")
        add(f"{family}10", f"{family}5")
    for side in ("TOP", "BOTTOM"):
        add(f"RANGE_{side}20", f"RANGE_{side}40")
    for days in (5, 10, 20):
        add(f"VOLAT{days}_EXTREME", f"VOLAT{days}_HIGH")
    for direction in ("UP", "DOWN"):
        add(f"VOLUME30_{direction}", f"VOLUME20_{direction}")
        add(f"VOLUME20_{direction}", f"VOLUME15_{direction}")
    add("MA5_20_DEATH", "MA5_20_BEAR")
    add("MA5_20_GOLDEN", "MA5_20_BULL")
    for combined, parts in _COMBOS.items():
        for part in parts:
            add(combined, part)
    return frozenset(edges)


def implication_closure():
    """Transitive implications, never reciprocal 'equivalence' by association."""
    adjacency = {}
    for stronger, weaker in implication_edges():
        adjacency.setdefault(stronger, set()).add(weaker)
    result = {}
    for code in CATALOG:
        visited = set()
        pending = list(adjacency.get(code, ()))
        while pending:
            implied = pending.pop()
            if implied == code:
                raise AssertionError("Implication cycle")
            if implied in visited:
                continue
            visited.add(implied)
            pending.extend(adjacency.get(implied, ()))
        result[code] = frozenset(visited)
    return result


def normalized_or_veto(codes):
    """Collapse only redundant stronger conditions when their weaker veto is present.

    If a weak condition and a strict subset condition both veto a symbol, the
    latter adds no new exclusions; keep the broad rule and record the aliases.
    Do not automatically alter deployed rule decisions from this function.
    """
    selected = frozenset(codes)
    unknown = selected.difference(CATALOG)
    if unknown:
        raise ValueError(f"Unrecognized pattern codes: {sorted(unknown)}")
    closure = implication_closure()
    redundant = {}
    for stronger in selected:
        subsumed_by = sorted(closure[stronger].intersection(selected))
        if subsumed_by:
            redundant[stronger] = subsumed_by
    kept = sorted(selected.difference(redundant))
    return {"original": sorted(selected), "canonical": kept,
            "redundant": {key: redundant[key] for key in sorted(redundant)},
            "original_count": len(selected), "canonical_count": len(kept)}


def factor_family(pattern_code):
    """Descriptive factor type only, not statistical equality."""
    if pattern_code not in CATALOG:
        raise ValueError(pattern_code)
    return CATALOG[pattern_code][0]
