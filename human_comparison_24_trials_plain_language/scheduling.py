"""Fixed 24-trial design: three species × two baselines × four pairs."""

TOTAL_TRIALS = 24
SPECIES_COUNT = 3
PER_CELL = 4
BASELINES = ("black_mask", "blurring")
DESIGN_VERSION = "balanced_24_v1"


def validate_pairs(pairs):
    if len({pair["pair_id"] for pair in pairs}) != len(pairs):
        raise ValueError("Duplicate comparison pair IDs in the study manifest")
    animals = sorted({pair["animal"] for pair in pairs})
    if len(animals) != SPECIES_COUNT:
        raise ValueError(
            f"This study requires exactly {SPECIES_COUNT} species folders; "
            f"found {len(animals)}: {', '.join(animals)}"
        )
    groups = {}
    for animal in animals:
        for baseline in BASELINES:
            group = [p for p in pairs if p["animal"] == animal and p["baseline"] == baseline]
            if len({p["source_id"] for p in group}) != len(group):
                raise ValueError(f"Duplicate source images in {animal}/{baseline}")
            if len(group) < PER_CELL:
                raise ValueError(
                    f"{animal}/{baseline}: needs at least {PER_CELL} distinct source images; "
                    f"found {len(group)}. Supply four or more complete image sets per species."
                )
            groups[animal, baseline] = group
    if any(pair["baseline"] not in BASELINES for pair in pairs):
        raise ValueError("Only black_mask and blurring comparisons are supported")
    return groups


def build_schedule(pairs, rng):
    """Sample without replacement in each cell, shuffle, and randomize A/B."""
    groups = validate_pairs(pairs)
    chosen = []
    for group in groups.values():
        chosen.extend(rng.sample(group, PER_CELL))
    rng.shuffle(chosen)
    schedule = []
    for pair in chosen:
        methods = ["remove", pair["baseline"]]
        rng.shuffle(methods)
        schedule.append({"pair_id": pair["pair_id"], "left_method": methods[0], "right_method": methods[1]})
    return schedule
