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
            winners = [r[question + "_winner"] for r in group]
            removal = winners.count("remove")
            traditional = winners.count(baseline)
            ties, uncertain = winners.count("tie"), winners.count("cannot_judge")
            decisive, total = removal + traditional, len(group)
            favored = "no_decisive_votes" if not decisive else "equal" if removal == traditional else "remove" if removal > traditional else baseline
            summaries.append(dict(animal=animal, baseline=baseline, question=question,
                judgments=total, participants=len({r["participant_id"] for r in group}),
                image_pairs=len({r["pair_id"] for r in group}), remove_wins=removal,
                baseline_wins=traditional, ties=ties, cannot_judge=uncertain,
                decisive_judgments=decisive,
                remove_share_decisive=removal/decisive if decisive else None,
                remove_share_all=removal/total, baseline_share_all=traditional/total,
                tie_share_all=ties/total, cannot_judge_share_all=uncertain/total,
                favored_decisive=favored))
    return summaries
