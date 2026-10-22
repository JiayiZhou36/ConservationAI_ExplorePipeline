# Plain-language update: removing or hiding animals

The participant wording now explicitly explains that researchers remove or
cover animals to test animal-detection software. It explains that some edits
fill the animal area, while others cover it with a black patch or blur it.
It does not identify which method is A or B, or suggest which should win.

Participants judge how real the photograph looks, separately from how well
the animal was hidden. No technical terms such as inpainting, perturbation,
model robustness, or computer vision are needed in the participant instructions.
The primary outcome is perceived realism. Overall preference remains separate.

Question 1 tie label: Both look equally real.
Question 2 tie label: No preference.
Both still save the same internal tie value. Each question also allows Cannot
judge. The 24-trial, three-species allocation and CSV calculations are unchanged.

This wording is reference-realism-and-overall-v4. Use a fresh prepared study
and database to keep it distinct from earlier pilot wording. Keep your old
project and data; copy only your input images/ folder into this edition.
Follow the installation/preparation/start steps below. Open a private browser
window to review the new introduction from the start.


---

# Three-species image study: exactly 24 trials

This is the complete updated website. Each participant sees an original reference
above two edited versions and answers separate realism and overall-preference
questions. Trial order and A/B method positions are randomized and saved.

## Fixed allocation

| Species | Removal vs blur | Removal vs black mask | Total |
| --- | ---: | ---: | ---: |
| Species 1 | 4 | 4 | 8 |
| Species 2 | 4 | 4 | 8 |
| Species 3 | 4 | 4 | 8 |
| Total | 12 | 12 | 24 |

One trial is one image-pair comparison with two questions. A completed session
therefore contains 24 response rows and 48 question answers.

The code requires exactly three species folders and at least four complete
source-image sets per species. Supply actual species names as folder names;
these become the analysis groups. If more than four sources are available,
the app samples four pairs without replacement for each species/baseline cell.
Every session still has exactly 24 trials. The two baseline cells sample
independently: the selected source images can differ between baseline types.
A source may appear once against each baseline. This ensures species/condition
counts per session, not equal exposure of every source across participants.

The program validates the design during preparation and startup, rather than
silently reducing the number of trials when images are missing.

## 1. Put your images here

```text
human_comparison_24_trials_plain_language/
  app.py
  images/
    species_1/
      original/
        scene_001.png
        scene_002.png
        scene_003.png
        scene_004.png
      remove/
        scene_001_remove.png
        scene_002_remove.png
        scene_003_remove.png
        scene_004_remove.png
      black_mask/
        scene_001_black_mask.png
        scene_002_black_mask.png
        scene_003_black_mask.png
        scene_004_black_mask.png
      blurring/
        scene_001_blurring.png
        scene_002_blurring.png
        scene_003_blurring.png
        scene_004_blurring.png
    species_2/
      original/
      remove/
      black_mask/
      blurring/
    species_3/
      original/
      remove/
      black_mask/
      blurring/
```

Populate species_2 and species_3 with at least four complete source sets too.
Replace species_1/2/3 with your actual species names. Minimum input: 12 original
photographs plus their three edited versions, or 48 image files in total.

Matching filenames must have the same base source ID. Neutral matching names
in every method folder work too. Aliases original/originals, remove/removal,
and blurring/blur are supported; use one folder per method. Batch filenames
such as scene_001.jpg_blurring.png are normalized. Nested relative subfolders
must match across methods. Do not use ALL_ANIMALS as a species folder name.

Use matching dimensions/crops and the same targeted animals across edits.
Use clean final images without labels or boxes. Debug names ending in _mask,
_viz, _original or _detections are excluded after a recognized method suffix is
removed. Original-folder names such as scene_001_original.png are recognized.
Single-frame PNG/JPEG/WEBP/TIFF/BMP inputs are supported.

## 2. Install and prepare

Use Python 3.12 for parity with the deployment configuration. From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python prepare_study.py --images images --study study
python check_vercel.py --study study
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Use a NEW study folder. Preparation freezes RGB PNG copies and records input
hashes, dimensions, question version and balanced_24_v1 design version. The
raw input images remain unchanged. All four versions must have equal dimensions.
No resizing occurs unless you explicitly add `--max-width 1600` to preparation;
that resizes all four versions equally and records the setting. If needed,
choose the resizing policy before collection and report it in your methods.

Do not reuse an earlier prepared manifest. Do not reuse a database containing
sessions from an older design. The application rejects these combinations so
new 24-trial data cannot silently mix with old unbalanced sessions.

## 3. Run locally

```bash
export STUDY_ADMIN_PASSWORD='replace-with-your-own-long-private-password'
python app.py --study study --port 8000
```

Open http://127.0.0.1:8000. This version defaults to exactly 24 trials.
If you supply the old --max-trials flag, only `--max-trials 24` is accepted.
Do not use the earlier values 0, 4, 18 or 20.

For local SQLite mode, leave DATABASE_URL and VERCEL unset. The application
saves responses and randomized schedules in study/responses.sqlite3.

## 4. Participant experience

The entry page explains the task and records agreement to participate. Every
trial shows the original reference above edited Image A and Image B at equal
display scale. Methods and source filenames are hidden, though the edits may
make a method visually recognizable. Clicking opens a larger view.

Participants answer which edit looks more like a natural photograph and which
they prefer overall. Both questions allow A/B/about equal/cannot judge. The
original is never an answer option. Optional comments are accepted. Submit is
enabled after all three images load. Timing is logged but there is no enforced
viewing duration. Answers cannot be changed after submission.

Each pair commits to the database before advancing. Refresh resumes the same
browser session, and repeated submission cannot add duplicate trial votes.
Completed participants receive a confirmation page. Full wording is in
PARTICIPANT_GUIDE.md and templates/start.html; adapt actual study information
and contact details before recruitment. Do not announce the expected winner.

A browser ID is pseudonymous, not a verified unique person. Clearing cookies or
using another device can create another session. Hosting may keep access logs.

## 5. Review results

Visit http://127.0.0.1:8000/admin with your researcher password.

- responses.csv: one row per submitted pair, both judgments, participant/source
  IDs, original reference ID, baseline, A/B methods, timing, optional comments,
  completion status, question version and design_version=balanced_24_v1.
- summary.csv: removal/baseline wins, ties, cannot judge, participant/image-pair
  counts and preference shares, by species and all species combined.
- participants.csv: assigned/answered trials and completion status.

The dashboard can include all submissions or completed sessions only. Species
balance is guaranteed for assigned complete sessions; unfinished sessions can
produce unbalanced submitted-response counts. Use completed sessions only when
you need the final counts to retain exact per-session balance. Do not discard
partial responses silently in a report; describe your inclusion rule.

Removal share among decisive judgments = removal wins / (removal wins +
baseline wins). Ties/cannot-judge responses are separate. All-response shares
are also exported. CSV values are fractions; dashboard values are percentages.
No decisive votes produces N/A, not zero. Summaries are descriptive, not
significance tests. For inferential analysis account for participant and source
image clustering. The study measures realism with an original reference.

## 6. Deploy on Vercel

Follow VERCEL_GUIDE.md. All deployment files are included. Use a managed
PostgreSQL DATABASE_URL for responses, not a local SQLite file on Vercel.

Vercel environment variables:

| Variable | Value |
| --- | --- |
| DATABASE_URL | Your managed PostgreSQL connection URL |
| SECRET_KEY | Private random string of at least 32 characters |
| STUDY_ADMIN_PASSWORD | Private password of at least 16 characters |
| STUDY_DIR | study |
| MAX_TRIALS | 24, or leave unset; default is 24 |

If an older deployment has MAX_TRIALS=0 or another number, change it to 24 and
redeploy. Include scheduling.py in the repository. Use a fresh database for this
design and separate pilot/production databases. The site does not deploy itself.

## 7. Synthetic pilot and tests

```bash
python -m unittest discover -s tests -v
python make_demo.py
python prepare_study.py --images demo_images --study demo_study
python app.py --study demo_study --port 8000
```

Demo generation now creates three animal groups and four sources per group,
enough for a full 24-trial pilot. Synthetic images are not genuine experimental
data. Keep them separate from real participant images and responses.

Offline validation includes exact 24-trial and six-cell counts over 100 randomized
schedules, selection uniqueness, seed reproducibility, insufficient-input
rejection, reference pairing, optional resizing, CSV arithmetic and SQLite
persistence/rollback. Flask-dependent web tests are included; see the delivery
message for which checks were executable in the authoring environment.
No live Vercel deployment or PostgreSQL connection is included.
