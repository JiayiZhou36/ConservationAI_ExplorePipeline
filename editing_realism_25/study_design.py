"""Fixed, versioned 25-trial study and descriptive summaries."""
import csv
import io
from collections import Counter
from statistics import mean, median

VERSION = 'editing-realism-25-v1'
GROUPS = [('replace','seal'), ('replace','whale'), ('background','penguin'),
          ('background','seal'), ('background','whale')]
TASK_NAMES = {'replace':'Object replacement', 'background':'Background replacement'}
ANIMAL_NAMES = {'seal':'Seals', 'whale':'Whales', 'penguin':'Penguins'}
RATINGS = [
 ('5','Looks completely natural.','I cannot notice any signs of editing.'),
 ('4','Looks mostly natural.','The changed area looks natural, with only small signs of editing.'),
 ('3','Looks partly natural.','Some parts look natural, but others look edited.'),
 ('2','Looks mostly edited.','Most of the changed area looks edited, with only small parts looking natural.'),
 ('1','Looks clearly edited.','The changed area does not look natural.'),
 ('cannot_judge','I cannot judge this image.','The changed area is unclear, or I cannot assess its appearance.')]


def validate_manifest(m):
    if m.get('version') != VERSION:
        raise ValueError('Prepare a new study using this package.')
    trials = m['trials']
    if Counter((t['task'],t['animal']) for t in trials) != Counter({g:5 for g in GROUPS}):
        raise ValueError('Exactly five pairs are required in each of the five task/animal groups.')
    if len({t['id'] for t in trials}) != 25:
        raise ValueError('Trial IDs must be unique.')
    return trials


def summaries(rows):
    """Submitted data only. Ratings are ordinal; mean is descriptive, not a test."""
    groups = [('All tasks','All animals',rows)]
    for task in TASK_NAMES:
        groups.append((TASK_NAMES[task],'All animals',[r for r in rows if r['task']==task]))
    for task, animal in GROUPS:
        groups.append((TASK_NAMES[task],ANIMAL_NAMES[animal],
                       [r for r in rows if r['task']==task and r['animal']==animal]))
    # Also show item-level summaries to avoid hiding differences between five images.
    for tid in sorted({r['trial_id'] for r in rows}):
        subset=[r for r in rows if r['trial_id']==tid]
        groups.append((TASK_NAMES[subset[0]['task']],ANIMAL_NAMES[subset[0]['animal']]+' / '+subset[0]['source_id'],subset))
    out=[]
    for task,animal,subset in groups:
        valid=[int(r['rating']) for r in subset if r['rating']!='cannot_judge']
        counts=Counter(valid)
        record=dict(task=task,animal_or_image=animal,n_participants=len({r['participant_id'] for r in subset}),
                    n_responses=len(subset),n_rated=len(valid),n_cannot_judge=len(subset)-len(valid),
                    mean_rating=round(mean(valid),3) if valid else '',median_rating=median(valid) if valid else '',
                    mostly_or_completely_natural_pct=round(100*sum(x>=4 for x in valid)/len(valid),2) if valid else '')
        record.update({f'rating_{i}_count':counts[i] for i in range(1,6)})
        out.append(record)
    return out


def csv_text(rows, fields=None):
    fields=fields or list(rows[0]) if rows else fields or ['message']
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    return stream.getvalue()
