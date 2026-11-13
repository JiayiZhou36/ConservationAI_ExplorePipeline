#!/usr/bin/env python3
"""Check prepared files before local use or deployment."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from study_design import validate_manifest


def check(study='study', public='public/study_images'):
    manifest_path = Path(study) / 'manifest.json'
    if not manifest_path.is_file():
        raise ValueError(
            f'Manifest not found: {manifest_path}. '
            'Preparation has not finished successfully, or --study points to the wrong folder. '
            'Run prepare_study.py first and resolve its errors, then run this checker.'
        )
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    validate_manifest(manifest)
    names = {trial[field] for trial in manifest['trials']
             for field in ['original_asset', 'edited_asset']}
    size = 0
    for name in sorted(names):
        if not isinstance(name, str) or not re.fullmatch(r'[a-f0-9]{64}\.png', name):
            raise ValueError(f'Invalid prepared asset name: {name!r}')
        path = Path(public) / name
        if not path.is_file():
            raise ValueError(f'Missing prepared image: {path}. Check the --public folder and preparation output.')
        data = path.read_bytes()
        size += len(data)
        if hashlib.sha256(data).hexdigest() + '.png' != name:
            raise ValueError(f'Image changed after preparation: {path}. Prepare a new study rather than editing active assets.')
    print(f'OK: 25 trials, {len(names)} unique prepared files, {size / 1024**2:.1f} MiB.')
    if size > 100 * 1024**2:
        print('Large bundle: consider a smaller --max-width in a NEW preparation folder. Check current hosting limits before deploying.')
    print('Keep study/manifest.json and public/study_images in GitHub. Keep source images, session.key, database and credentials out.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', default='study')
    parser.add_argument('--public', default='public/study_images')
    args = parser.parse_args()
    try:
        check(args.study, args.public)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
