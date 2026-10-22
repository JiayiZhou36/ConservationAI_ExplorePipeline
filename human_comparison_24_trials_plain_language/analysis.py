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
        for question in ("comparison_realism", "realism", "preference"):
            source_question = "realism" if question == "comparison_realism" else question
            question_group = [r for r in group
                              if r.get(source_question + "_winner") in {"remove", baseline, "tie", "cannot_judge"}
                              and ((r.get("questions_version") == "individual-realism-three-v1")
                                   if question == "comparison_realism"
                                   else (r.get("questions_version") != "individual-realism-three-v1"))]
            if not question_group:
                continue
            winners = [r[source_question + "_winner"] for r in question_group]
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


SUMMARY_FIELDS += ["rating_position"]


def summarize_individual_ratings(rows):
    """Both methods are rated on every new trial; keep position-specific summaries too."""
    from statistics import mean, median
    groups = defaultdict(list)
    for row in rows:
        if row.get("questions_version") != "individual-realism-three-v1":
            continue
        for side, position in (("a", "A"), ("b", "B")):
            for animal in ("ALL_ANIMALS", row["animal"]):
                for summary_position in ("ALL_POSITIONS", position):
                    key = (animal, row["baseline"], row["image_" + side + "_method"], summary_position)
                    groups[key].append((row, row["image_" + side + "_rating"]))
    result = []
    for (animal, baseline, method, position), entries in sorted(groups.items()):
        values = [int(value) for _, value in entries if value not in (None, "")]
        counts = {f"rating_{n}": values.count(n) for n in range(1, 6)}
        question = {"A": "q1_image_a_rating", "B": "q2_image_b_rating", "ALL_POSITIONS": "individual_image_realism_rating"}[position]
        result.append(dict(animal=animal, baseline=baseline, question=question,
            rated_method=method, rating_position=position, judgments=len(entries),
            rating_responses=len(entries), participants=len({r["participant_id"] for r, _ in entries}),
            image_pairs=len({r["pair_id"] for r, _ in entries}), valid_ratings=len(values),
            rating_cannot_judge=len(entries)-len(values), mean_rating=mean(values) if values else None,
            median_rating=median(values) if values else None,
            rating_4_or_5_share=(counts["rating_4"]+counts["rating_5"])/len(values) if values else None,
            **counts))
    return result
