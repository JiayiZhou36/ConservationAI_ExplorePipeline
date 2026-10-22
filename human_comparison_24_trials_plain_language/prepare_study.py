"""Validate and freeze original/edited image sets for a human comparison study."""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from scheduling import DESIGN_VERSION, validate_pairs

METHODS = {"original": ("original", "originals"), "remove": ("remove", "removal"), "black_mask": ("black_mask",), "blurring": ("blurring", "blur")}
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
EXCLUDED = ("_mask", "_viz", "_original", "_detections")


def image_index(folder, method):
    indexed = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        stem = path.stem
        for suffix in METHODS[method]:
            if stem.endswith("_" + suffix):
                stem = stem[:-(len(suffix)+1)]
                break
        # Supports batch output such as seal.jpg_blurring.png.
        if Path(stem).suffix.lower() in EXTENSIONS:
            stem = Path(stem).stem
        if stem.endswith(EXCLUDED):
            continue
        key = (path.relative_to(folder).parent / stem).as_posix()
        if key in indexed:
            raise ValueError(f"Duplicate source ID {key!r} in {folder}")
        indexed[key] = path
    return indexed


def prepare(images, destination, max_width=None):
    if max_width is not None and max_width < 1:
        raise ValueError("max_width must be positive")
    images, destination = Path(images).resolve(), Path(destination).resolve()
    if not images.is_dir():
        raise ValueError(f"Image root does not exist: {images}")
    if destination.exists():
        raise ValueError("Study destination already exists. Use a new folder; existing studies are immutable.")
    image_sets, errors = [], []
    for animal in sorted(images.iterdir()):
        if not animal.is_dir() or animal.name.startswith("."):
            continue
        if animal.name == "ALL_ANIMALS":
            raise ValueError("ALL_ANIMALS is reserved for the aggregate summary; rename this animal folder")
        indices = {}
        for method, aliases in METHODS.items():
            folders = [animal / alias for alias in aliases if (animal / alias).is_dir()]
            if len(folders) != 1:
                errors.append(f"{animal.name}: need exactly one folder for {method}: {aliases}")
                continue
            indices[method] = image_index(folders[0], method)
        if len(indices) != 4:
            continue
        keys = set().union(*(set(index) for index in indices.values()))
        for key in sorted(keys):
            missing = [method for method in METHODS if key not in indices[method]]
            if missing:
                errors.append(f"{animal.name}/{key}: missing {', '.join(missing)}")
                continue
            files = {method: indices[method][key] for method in METHODS}
            sizes = {}
            for method, path in files.items():
                with Image.open(path) as image:
                    image.load()
                    sizes[method] = image.size
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError(f"Animated/multipage input is unsupported: {path}")
            if len(set(sizes.values())) != 1:
                errors.append(f"{animal.name}/{key}: image dimensions differ: {sizes}")
                continue
            image_sets.append((animal.name, key, files))
    if errors:
        raise ValueError("Fix input pairing before preparing:\n" + "\n".join(errors[:100]))
    if not image_sets:
        raise ValueError("No complete original/remove/black_mask/blurring image sets were found.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".study-", dir=destination.parent))
    try:
        (temporary / "images").mkdir()
        sources, pairs = [], []
        for animal, key, files in image_sets:
            source_id = hashlib.sha256(f"{animal}\0{key}".encode()).hexdigest()[:20]
            assets, provenance = {}, {}
            for method, path in files.items():
                original_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                with Image.open(path) as image:
                    rgb = image.convert("RGB")
                    input_size = list(rgb.size)
                    if max_width and rgb.width > max_width:
                        target_height = max(1, round(rgb.height * max_width / rgb.width))
                        rgb = rgb.resize((max_width, target_height), Image.Resampling.LANCZOS)
                    presented_size = list(rgb.size)
                    # Pixel hash avoids exposing original filenames or metadata.
                    asset = hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
                    rgb.save(temporary / "images" / f"{asset}.png")
                assets[method] = asset
                provenance[method] = {"input_path": str(path), "input_sha256": original_sha, "input_size": input_size, "presented_size": presented_size}
            sources.append({"source_id": source_id, "animal": animal, "source_key": key,
                            "assets": assets, "provenance": provenance})
            for baseline in ("black_mask", "blurring"):
                pairs.append({"pair_id": f"{source_id}_{baseline}", "source_id": source_id,
                              "animal": animal, "baseline": baseline, "assets": assets})
        validate_pairs(pairs)
        manifest = {"schema_version": 3, "design_version": DESIGN_VERSION, "sources": sources, "pairs": pairs,
                    "questions_version": "reference-realism-and-overall-v4", "max_width": max_width}
        canonical = json.dumps(manifest, sort_keys=True).encode()
        manifest["study_id"] = hashlib.sha256(canonical).hexdigest()
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        secret_file = temporary / "session.key"
        secret_file.write_text(secrets.token_hex(32), encoding="ascii")
        os.chmod(secret_file, 0o600)
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True)
    parser.add_argument("--study", default="study")
    parser.add_argument("--max-width", type=int, help="Optionally downsize all four versions equally; never upscales")
    args = parser.parse_args()
    try:
        manifest = prepare(args.images, args.study, args.max_width)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    print(f"Prepared {len(manifest['sources'])} source images with references and {len(manifest['pairs'])} pairs.")
    print(f"Study: {Path(args.study).resolve()}")
