"""Check the prepared study for this small-study bundled-image deployment."""

import argparse
import json
from pathlib import Path
from scheduling import DESIGN_VERSION, validate_pairs


def check(study):
    root = Path(study)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("questions_version") != "reference-realism-and-overall-v4":
        raise ValueError(
            "Prepare the study with the updated reference-enabled importer"
        )
    if manifest.get("design_version") != DESIGN_VERSION:
        raise ValueError("Prepare a NEW study using this 24-trial version")
    validate_pairs(manifest["pairs"])
    assets = {
        asset for source in manifest["sources"] for asset in source["assets"].values()
    }
    paths = [root / "images" / f"{asset}.png" for asset in assets]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("Missing prepared assets: " + ", ".join(missing[:10]))
    large = [path.name for path in paths if path.stat().st_size >= 4_000_000]
    if large:
        raise ValueError(
            "Images too large for this deployment: "
            + ", ".join(large[:10])
            + ". Prepare a NEW study using --max-width 1600 (or smaller), or use external image storage."
        )
    total = sum(path.stat().st_size for path in paths)
    if total > 200_000_000:
        raise ValueError(
            "Bundled images exceed this starter app's conservative 150 MB budget. Use fewer/smaller images or external image storage for a larger study."
        )
    return len(paths), total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="study")
    args = parser.parse_args()
    try:
        count, size = check(args.study)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    print(f"Checked {count} prepared assets ({size/1_000_000:.1f} MB).")
    print(
        "Size checks passed; run an actual deployment pilot before collecting responses."
    )
