"""Descriptive summaries; no independence assumptions or significance tests."""
import csv
import io
from collections import defaultdict


def csv_text(rows, fields):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


SUMMARY_FIELDS = ["animal", "baseline", "question", "judgments", "participants", "image_pairs",
                  "remove_wins", "baseline_wins", "ties", "cannot_judge", "decisive_judgments",
                  "remove_share_decisive", "remove_share_all", "baseline_share_all", "tie_share_all",
                  "cannot_judge_share_all", "favored_decisive"]


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        for animal in ("ALL_ANIMALS", row["animal"]):
            groups[(animal, row["baseline"])].append(row)
    summaries = []
    for (animal, baseline), group in sorted(groups.items()):
        for question in ("realism", "preference"):
            question_group = [r for r in group if r.get(question + "_winner") in {"remove", baseline, "tie", "cannot_judge"}]
            if not question_group:
                continue
            winners = [r[question + "_winner"] for r in question_group]
            removal = winners.count("remove")
            traditional = winners.count(baseline)
            ties, uncertain = winners.count("tie"), winners.count("cannot_judge")
            decisive, total = removal + traditional, len(question_group)
            favored = "no_decisive_votes" if not decisive else "equal" if removal == traditional else "remove" if removal > traditional else baseline
            summaries.append(dict(animal=animal, baseline=baseline, question=question,
                judgments=total, participants=len({r["participant_id"] for r in question_group}),
                image_pairs=len({r["pair_id"] for r in question_group}), remove_wins=removal,
                baseline_wins=traditional, ties=ties, cannot_judge=uncertain,
                decisive_judgments=decisive,
                remove_share_decisive=removal/decisive if decisive else None,
                remove_share_all=removal/total, baseline_share_all=traditional/total,
                tie_share_all=ties/total, cannot_judge_share_all=uncertain/total,
                favored_decisive=favored))
    return summaries


RATING_FIELDS = [
    "rated_method", "rating_responses", "valid_ratings", "rating_cannot_judge",
    "mean_rating", "median_rating", "rating_1", "rating_2", "rating_3",
    "rating_4", "rating_5", "rating_4_or_5_share",
]
SUMMARY_FIELDS += RATING_FIELDS


def summarize_ratings(rows):
    """Summarize Q2 conditional ratings, keeping ties and unknowns separate."""
    from statistics import mean, median
    groups = defaultdict(list)
    for row in rows:
        if row.get("second_question_type") != "selected_image_realism_rating_v1":
            continue
        for animal in ("ALL_ANIMALS", row["animal"]):
            groups[(animal, row["baseline"], row["rated_method"])].append(row)
    result = []
    for (animal, baseline, method), group in sorted(groups.items()):
        ratings = [int(r["selected_image_rating"]) for r in group
                   if r.get("selected_image_rating") not in (None, "")]
        counts = {f"rating_{n}": ratings.count(n) for n in range(1, 6)}
        result.append(dict(
            animal=animal, baseline=baseline, question="selected_image_realism_rating",
            rated_method=method, judgments=len(group), rating_responses=len(group),
            participants=len({r["participant_id"] for r in group}),
            image_pairs=len({r["pair_id"] for r in group}),
            valid_ratings=len(ratings), rating_cannot_judge=len(group)-len(ratings),
            mean_rating=mean(ratings) if ratings else None,
            median_rating=median(ratings) if ratings else None,
            rating_4_or_5_share=(counts["rating_4"]+counts["rating_5"])/len(ratings) if ratings else None,
            **counts))
    return result
