#!/usr/bin/env python3
"""Prepare exactly five original/edited pairs in each task/animal group."""
import argparse
import csv
import hashlib
import json
import secrets
from pathlib import Path
from PIL import Image, ImageOps
from study_design import VERSION, GROUPS, validate_manifest

EXTENSIONS={'.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp'}


def image_map(folder):
    result={}
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            if path.stem in result:
                raise ValueError(f'Duplicate filename stem in {folder}: {path.stem}')
            result[path.stem]=path
    return result


def match_images(originals, edited, task, folder):
    """Match exact stems or the pipeline task suffix, without renaming files."""
    matches = {}
    used = set()
    for stem in originals:
        candidates = [name for name in (stem, f'{stem}_{task}') if name in edited]
        if len(candidates) != 1:
            raise ValueError(
                f'{folder}: expected exactly one edit for {originals[stem].name}. '
                f'Accepted edited stems: {stem} or {stem}_{task}. '
                f'Found {len(candidates)} matches. '
                'Remove ambiguous duplicate copies or use --pairs pairs.csv.'
            )
        name = candidates[0]
        if name in used:
            raise ValueError(f'{folder}: edited image {edited[name].name} matches more than one original. Use --pairs pairs.csv.')
        used.add(name)
        matches[stem] = edited[name]
    unused = sorted(set(edited) - used)
    if unused:
        raise ValueError(f'{folder}: edited images without matching originals: {unused}. Keep only your selected five pairs, or use --pairs pairs.csv.')
    return matches


def prepare(images='images', study='study', public='public/study_images', pairs=None, max_width=1200):
    root=Path(images).resolve(); dest=Path(study).resolve(); assets=Path(public).resolve()
    if max_width<100: raise ValueError('max-width must be at least 100.')
    if (dest.exists() and any(dest.iterdir())) or (assets.exists() and any(assets.iterdir())):
        raise ValueError('Study and prepared image folders must be new or empty. Never overwrite an active study.')
    records=[]
    if pairs:
        with Path(pairs).open(newline='',encoding='utf-8-sig') as f:
            reader=csv.DictReader(f)
            if not {'task','animal','source_id','original','edited','description'}.issubset(reader.fieldnames or []):
                raise ValueError('pairs CSV must have task,animal,source_id,original,edited,description columns.')
            for r in reader:
                records.append(dict(r,original=str(root/r['original']),edited=str(root/r['edited'])))
    else:
        for task,animal in GROUPS:
            base=root/task/animal
            if not (base/'original').is_dir() or not (base/'edited').is_dir():
                raise ValueError(f'Missing {base}/original or edited. See README for folder structure.')
            originals=image_map(base/'original');edited=image_map(base/'edited')
            matched=match_images(originals,edited,task,base)
            desc=(base/'description.txt').read_text(encoding='utf-8').strip() if (base/'description.txt').exists() else ''
            for stem in originals:
                records.append(dict(task=task,animal=animal,source_id=stem,original=str(originals[stem]),edited=str(matched[stem]),description=desc))
    # Validate the entire selection before writing any prepared data.
    trials=[]; keys=set()
    for r in records:
        key=(r['task'],r['animal'],r['source_id'])
        if key in keys:raise ValueError(f'Duplicate pair: {key}')
        keys.add(key)
        for field in ['original','edited']:
            if not Path(r[field]).is_file(): raise ValueError(f'Missing image: {r[field]}')
        trials.append(dict(id=hashlib.sha256('|'.join(key).encode()).hexdigest()[:20],
                           task=r['task'],animal=r['animal'],source_id=r['source_id'],description=r['description']))
    manifest=dict(version=VERSION,study_id=secrets.token_hex(16),trials=trials)
    validate_manifest(manifest)
    prepared=[]
    for r,t in zip(records,trials):
        pair=[]
        for field in ['original','edited']:
            with Image.open(r[field]) as img:
                img=ImageOps.exif_transpose(img).convert('RGBA')
                white=Image.new('RGBA',img.size,'white');white.alpha_composite(img)
                pair.append(white.convert('RGB'))
        if pair[0].size!=pair[1].size:
            raise ValueError(f'Original and edited dimensions differ for {r["source_id"]}. Export aligned, equally sized copies before preparing.')
        for field,img in zip(['original','edited'],pair):
            if img.width>max_width:
                img=img.resize((max_width,max(1,round(img.height*max_width/img.width))),Image.Resampling.LANCZOS)
            from io import BytesIO
            buf=BytesIO();img.save(buf,format='PNG',optimize=True)
            data=buf.getvalue();name=hashlib.sha256(data).hexdigest()+'.png'
            t[field+'_asset']=name
            t[field+'_source']=str(Path(r[field]).relative_to(root)) if Path(r[field]).is_relative_to(root) else Path(r[field]).name
            prepared.append((name,data))
    dest.mkdir(parents=True,exist_ok=True);assets.mkdir(parents=True,exist_ok=True)
    for name,data in prepared:(assets/name).write_bytes(data)
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (dest/'session.key').write_text(secrets.token_hex(32),encoding='utf-8')
    print(f'Prepared 25 trials (10 replacement, 15 background), study ID {manifest["study_id"]}.')
    print(f'Manifest: {dest}/manifest.json\nImages: {assets}')
    print('Source images are unchanged. Inspect the prepared images before recruitment.')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images',default='images');p.add_argument('--study',default='study')
    p.add_argument('--public',default='public/study_images');p.add_argument('--pairs')
    p.add_argument('--max-width',type=int,default=1200)
    args=p.parse_args()
    try:prepare(args.images,args.study,args.public,args.pairs,args.max_width)
    except (ValueError,OSError) as e:p.exit(1,f'Error: {e}\n')
