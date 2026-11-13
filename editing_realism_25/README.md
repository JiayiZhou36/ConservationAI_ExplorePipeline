# SPLICE: object and background editing realism study

This is a separate project from the removal comparison website. Do not replace
files in your running removal study. Start with a new folder and, for online use,
a separate Vercel project and a new database.

## Study design

Every participant views all 25 pairs, in a newly shuffled order. Each page shows
the original on the left and the edited image on the right, with one question:
**How realistic does the edited image look?** Only the edited image is rated.

| Task | Animal | Pairs per participant |
|---|---|---:|
| Object replacement | Seal | 5 |
| Object replacement | Whale | 5 |
| Background replacement | Penguin | 5 |
| Background replacement | Seal | 5 |
| Background replacement | Whale | 5 |

Each group is represented exactly five times. Tasks are intentionally unequal
in total size: replacement has 10 trials; background has 15. All participants
see the same selected pairs, in different orders. This is not a trial sampler.
There is no side preference question because there is only one edited version
per trial. The original is a reference, not a competing method.

The five ratings run from completely natural (5) to clearly edited (1), with a
separate Cannot judge option. Each answer has its own row and an explanation.
The app shows the same meaning of realism throughout. It does not tell people
that the method should look realistic or ask them to support a hypothesis.

## 1. Set up a new project folder

Extract this package. Open Terminal and enter the extracted folder:

```bash
cd /your/path/editing_realism_25
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Python 3.12 is recommended and is the configured deployment version.
On Windows use `.venv\Scripts\activate` instead of `source ...`.

## 2. Add five pairs to each group

Copy selected source images into the included folders:

```
images/
  replace/
    seal/
      original/   # five original photographs
      edited/     # their five edited versions
    whale/
      original/
      edited/
  background/
    penguin/
      original/
      edited/
    seal/
      original/
      edited/
    whale/
      original/
      edited/
```

Use exactly five images in every original folder and five matching edits in its
edited folder. Copy files rather than moving your pipeline results. Do not
include plots with detector boxes, confidence labels or side-by-side montages.
Use the final edited photographs only.

By default, match pairs using the same filename stem. Extensions may differ:

```
images/replace/seal/original/seal_01.jpg
images/replace/seal/edited/seal_01.png
```

Both have the stem `seal_01`. PNG, JPG, JPEG, TIFF, BMP and WebP are supported,
including uppercase extensions. Do not keep two original files with the same
stem (for example seal_01.jpg and seal_01.png).

If an edited filename ends in `_replace` or `_background`, rename the COPY to
match the original, or use a pairs CSV as described below. The script does not
guess which unrelated filenames belong together.

Original and edited images must be aligned and equally sized after correcting
EXIF orientation. Preparation stops if they differ, rather than stretching one
image. Export aligned copies from your pipeline before proceeding.

### Optional: tell participants the specific intended change

Add a `description.txt` inside any task/animal folder, alongside original and
edited (not inside them). Its text appears on all five trials in that group.
Use neutral wording matching the actual images, for example:

* `images/replace/seal/description.txt`: “The seal region was edited to replace
  the animal with a buoy.”
* `images/replace/whale/description.txt`: “The whale region was edited to replace
  the animal with a research vessel.”
* `images/background/seal/description.txt`: “The background was changed to a
  winter scene while the seal regions were kept.”

Use these examples only if they describe your actual edits. If replacement
objects or backgrounds differ between the five images, use pair-specific
CSV descriptions instead. Do not claim the change succeeded in these notes.

### Optional: pair files with different names

Create `pairs.csv` with these columns, using paths relative to `images`:

```csv
task,animal,source_id,original,edited,description
replace,seal,seal_01,replace/seal/original/seal_01.jpg,replace/seal/edited/seal_01_replace.png,An animal region was edited to replace the seal with a buoy.
```

Include all 25 pairs, not just this example. Task must be `replace` or
`background`; animal must be `seal`, `whale` or `penguin` in the groups above.
Use a CSV editor or correctly quote descriptions containing commas. Each
(task, animal, source_id) must be unique. Pass `--pairs pairs.csv` at preparation.
Filename matching and folder description files are not used in this mode.

Keep a separate researcher selection log recording source image, seed,
confidence threshold, detector, mask type and prompt for each chosen edit.
This app logs source paths, task and animal but cannot infer those pipeline
settings from image pixels. Select images according to a stated rule before
recruitment; a small selected set does not represent every image your pipeline
can generate. If both tasks use the same original, participants may recognize it.

## 3. Prepare the study

Run from this project folder:

```bash
python prepare_study.py --images images --study study --max-width 1200
python check_study.py --study study
```

With a pairs CSV:

```bash
python prepare_study.py --images images --study study --pairs pairs.csv --max-width 1200
```

This creates:

* `study/manifest.json`: fixed selection, labels, asset names and study ID.
* `public/study_images/`: paired display copies, saved as PNG with hashed names.
* `study/session.key`: a private local signing key. Do not upload it.

The source files are unchanged. Both images in a pair receive the same resize
when wider than 1200 pixels. Smaller images are not enlarged. Transparent
areas are composited onto white. Inspect prepared copies to ensure resizing
and transparency do not obscure the editing artifacts you intend to evaluate.
Use a larger max width before collection if full-resolution artifacts matter.

Preparation refuses nonempty destination folders. Do not regenerate or edit a
manifest after data collection begins. For a new selection or different
questionnaire, create a separate project/study and database.

## 4. Test locally

Choose your own researcher password of at least 16 characters:

```bash
export STUDY_ADMIN_PASSWORD='replace-this-with-your-private-password'
python app.py --study study --port 5000
```

Open http://127.0.0.1:5000 in your browser. Local responses are stored in
`study/responses.sqlite3`. No database account is required for local testing.
The local server is for testing on your computer, not public deployment.

Participant flow:

1. Read the purpose, task explanations and participation instructions.
2. View original and edited images side by side; click either to enlarge it.
3. Choose one rating. Save and next saves that answer in the database.
4. Use Previous to review or change saved answers. A changed radio selection
   is saved only when pressing a navigation button; it is not autosaved.
5. Review all 25 answers on the completion page.
6. Confirm and press Submit study. All answers become final.

“I cannot judge” counts as an answered trial. Participants can resume drafts
using the same browser cookie for up to 30 days. Anonymous cookies cannot
prevent the same person from starting again in another browser; ask people to
complete the study once. No name or email is requested.

Use a different/private browser window for researcher access:

http://127.0.0.1:5000/admin/login

Sign in with STUDY_ADMIN_PASSWORD. Researcher login and participant access use
the same cookie name, so using separate browser windows avoids replacing an
unfinished participant session.

Test at least: changing an answer, going back, enlarging images, completing all
25, final submission, trying to edit after submission, and downloading results.
Try a smaller screen too. Images remain side by side on mobile, while the
question moves below them; a laptop is recommended for careful viewing.

To test with artificial shapes before adding real files, use a SEPARATE copy of
this project and run:

```bash
python make_demo.py --output demo_images
python prepare_study.py --images demo_images --study study
```

Demo images are labeled as synthetic test material. Never recruit using them.

## 5. Researcher results and exports

The admin dashboard displays submitted participants and unsubmitted sessions.
Only FINAL submissions contribute to its summaries. It shows overall results,
each task, each task/animal group, and each individual edited image:

* Number of numeric ratings and Cannot judge responses.
* Mean rating (1 to 5) and median rating.
* Percentage of numeric ratings that are 4 or 5.
* Counts for every rating level.

The 4/5 percentage excludes Cannot judge; its count is always shown separately.
The mean and median are blank when there are no numeric ratings. These are
realism judgments, not preference votes, detector metrics or confirmation that
the intended object was successfully generated.

Exports:

* `responses.csv`: final answers only; 25 rows per submitted participant.
* `summary.csv`: the displayed task, animal and image summaries.
* `drafts.csv`: ALL saved answers, including final submissions and drafts;
  filter response_status if using this file.

Each response logs study and questionnaire version, anonymous participant ID,
task, animal, source ID/paths, description, original/edited asset IDs, randomized
trial position, answer/score, participant creation time, first display time,
first/last save times, save revision count, final submission time and status.
`revision_count` counts saves after the first, even if the value did not change.
`last_visit_seconds` is wall-clock time from the most recent page display to its
save; it can include idle time and is NOT a measure of active viewing time.
Unanswered draft trials do not have response rows.

Export regular backups. There is no public results page or delete-data button.
Avoid publishing participant-level exports without reviewing your research
protocol. The welcome text states that hosting providers may keep operational
logs; the app itself does not explicitly store IP addresses or user agents.
Adapt the participant information to your approved protocol if applicable.

For paper reporting, include participant count, number of images, scale wording,
selection rule and treatment of Cannot judge. Ratings are ordinal, with repeated
responses from each participant and repeated ratings of each image. Descriptive
means are not evidence of statistical significance. The overall score weights
trials equally (15 background, 10 replacement). A method comparison requires
the same rating design and suitable matched images; these new ratings alone do
not measure preference against conventional perturbations.

## 6. Deploy as a NEW Vercel project

The provided entrypoint exports a Flask application around the same WSGI survey
used locally. Prepared images, CSS and JavaScript live in `public/` for static
serving; `study/manifest.json` is included by vercel.json. The app validates all
prepared files on startup, so missing assets give a clear startup error.

1. Create a new GitHub repository, or put this project in its own subfolder.
   Keep your working removal study separate.
2. Upload this project's code, `pyproject.toml`, `requirements.txt`, `vercel.json`,
   `study/manifest.json`, and the entire `public` directory including prepared
   images. Enable display of hidden files so the included `.gitignore` and
   `.vercelignore` are included. Never upload credentials, SQLite files,
   session.key, or the source `images/` folder. Gitignore affects Git; it does
   not make manually uploaded files private.
3. In Neon, create a NEW database for this study. In its connection dialog,
   select that database and copy its PostgreSQL connection string including
   the SSL parameters. Keep it private. Use an empty database for production
   so local test responses do not appear in the final summary.
4. In Vercel, add a new project and import the repository. If this code is in a
   subfolder, set Root Directory to that folder, the one containing index.py
   and pyproject.toml. The framework is Flask; use the included configuration.
   Do not set an npm build command or a static output directory.
5. Add these environment variables for Production (and Preview if testing
   preview deployments):

   | Variable | Value |
   |---|---|
   | DATABASE_URL | The connection string for the NEW database |
   | STUDY_ADMIN_PASSWORD | Your private password, at least 16 characters |
   | SECRET_KEY | A newly generated private random key, at least 32 characters |

   Generate SECRET_KEY locally with:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Paste only its output into the environment-variable value. Keep the key
   stable across redeployments so existing browser sessions remain valid.
   Do NOT bring MAX_TRIALS=24 or STUDY_DIR=study_web1200 from the old app. This
   project uses exactly 25 trials and defaults to its bundled `study` folder.
6. Deploy. If variables were added after deployment, redeploy.
7. Open `/health`, then the home page. Check all images load. Use
   `/admin/login` for researcher access. Share the production home-page link
   with participants, not the admin link or a temporary local URL.
8. Before recruitment, run an online pilot and verify a final submission reaches
   the admin dashboard. If you want a clean production dataset afterwards,
   point the app to ANOTHER empty database and redeploy. Never delete your
   removal-study records to reset this study.

Images are public website assets: do not include sensitive photographs or files
that cannot be distributed. Review current Vercel and database plan limits
before recruitment; this package does not promise a particular plan or price.
For a larger study, externally hosted assets need a deliberate configuration
change; this package serves bundled prepared images.

Official deployment references (checked while preparing this package):
https://vercel.com/docs/frameworks/backend/flask
https://neon.com/docs/connect/connect-from-any-app

## 7. Troubleshooting

* **Missing manifest:** prepare the study; upload study/manifest.json; verify
  Vercel Root Directory. Keep the prepared folder named `study` for deployment.
* **Images missing:** upload public/study_images, not source images only. Do not
  exclude public in vercelignore. Run check_study.py before upload.
* **Database belongs to another study:** use a new database. The manifest hash
  protects an existing selection from accidental mixing.
* **Form expired:** reload. A changed SECRET_KEY, expired cookie or overwritten
  browser session can cause this. Cookies must be enabled.
* **Admin shows zero responses:** summaries require the final Submit study
  action; saved drafts alone do not contribute.
* **Cannot rerun preparation:** choose a new empty project/folder for a different
  study. For correcting test-only images, move old prepared folders and test
  database aside first; do not do this after recruitment begins.

## Verification included with the package

```bash
python -m unittest discover -s tests -v
```

The tests cover exact group counts, draft exclusion, answer revision, final
submission and locking, invalid inputs, admin access, CSV summaries, manifest
binding and prepared-image access. Synthetic data are created in temporary
folders, not in your real study.
