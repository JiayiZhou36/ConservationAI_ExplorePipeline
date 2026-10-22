# Deploy the reference-enabled study on Vercel

This is the smallest change to the existing Python website: keep Flask, add a
managed PostgreSQL database, and deploy with Vercel's Flask support. No React,
Next.js, custom API frontend, or database dashboard code needs to be written.
The supplied files include these changes.

Vercel hosting is not a replacement for persistent response storage. The app
uses PostgreSQL when DATABASE_URL is present and SQLite only for local use.
Vercel functions have a read-only filesystem except for temporary scratch
space. Do not store study votes in a CSV/SQLite file inside a Vercel function.

## 1. Download or copy the complete updated project

Use `human_comparison_24_trials_plain_language` as the Vercel project root. Keep:

```text
app.py
index.py
database.py
analysis.py
scheduling.py
prepare_study.py
check_vercel.py
requirements.txt
pyproject.toml
vercel.json
templates/
public/assets/
study/manifest.json       # generated in step 2
study/images/            # generated in step 2
```

`index.py` exports the Flask app; `pyproject.toml` tells Vercel which entrypoint
to load. `public/assets` holds the CSS and JavaScript, which Vercel serves
statically. Image files remain in the private function bundle and are served
only for a participant's current trial. Do not move the manifest, responses,
secrets, or method-named source folders into `public`.

## Fixed session design

Every session has exactly 24 pair comparisons: 12 removal-versus-blur and 12
removal-versus-black-mask. Each of exactly three species contributes four of
each comparison type (eight trials per species). At least four complete source
image sets per species are required. More images may be supplied; four pairs
are sampled without replacement from every species/baseline cell per session.
Sampling and A/B positions are randomized. A source may occur once against
each baseline. This does not guarantee equal image coverage across people.

Use a fresh study/database for this design. Earlier prepared manifests or
databases with prior-design sessions are rejected. If an old Vercel environment
has MAX_TRIALS=0 or 20, replace it with 24 and redeploy.

## 2. Prepare the original and edited images locally

From the project folder, install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Supply the four-folder layout described in README.md. Then:

```bash
python prepare_study.py --images images --study study
python check_vercel.py --study study
```

Use the exact output directory `study` for the supplied Vercel configuration.
The preparation step must run before deploying; the deployed app only reads
prepared image files and never performs image generation or preparation.

If the size check reports oversized files, decide whether resizing fits your
study. To prepare a new standardized display set:

```bash
python prepare_study.py --images images --study study --max-width 1600
```

This command requires that `study` not already exist. Rename your previous
pilot folder first, or build in a fresh project copy. All four images are
resized using the same dimensions and LANCZOS filter; no upscaling is performed.
The manifest records input and presented dimensions plus the max-width setting.
Resizing can change how artifacts look. Keep it consistent across methods and
report it in the study description. It is optional, not automatic.

This starter checks that each served PNG is below 4,000,000 bytes to leave room
under Vercel's function payload limit. It also imposes a conservative 150 MB
combined-image budget for this bundled-image deployment. These checks are not
all of Vercel's limits or a guarantee of successful deployment. For hundreds of
large originals, object storage is a better architecture, but is not included
in this small-study starter. Keep the dataset small enough for a pilot first.
Very large response CSV exports also encounter function payload limits; export
from the database directly if your study grows beyond a small pilot.

## 3. Put the code and prepared images in a private GitHub repository

Use your existing GitHub workflow or create a private repository and upload
the project folder contents. The Vercel root should contain `index.py`, not an
extra nested project folder (unless you select that nested root in Vercel).

Include `study/manifest.json` and `study/images/*.png`. Do not commit:

- `study/session.key`
- `responses.sqlite3` or any database sidecar files
- `.env` files, database URLs, passwords or secret keys
- `.venv` or raw input `images/` folders

The provided .gitignore and .vercelignore cover these items. The prepared
manifest contains your original local paths and is private researcher data;
keep the repository private. It is not exposed by the website.

## 4. Create a PostgreSQL database

Use the Vercel Marketplace Neon integration, or create a Neon PostgreSQL
project and copy its pooled PostgreSQL connection string. Either route works.
Use the provider's supplied SSL settings. A typical URL looks like:

```text
postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

The complete URL is a secret. It belongs in Vercel environment variables, not
in Python source or Git. Prefer a pooled connection string for serverless
requests. This code uses psycopg 3 with dictionary rows and automatic prepared
statements disabled for transaction-pool compatibility.

Use one dedicated database per study. The app creates its tables and associates
the database with the prepared study ID. A different manifest using that same
database is rejected, protecting existing responses from dataset mixing.
Do not point a pilot, preview study or new dataset at the production database.

## 5. Import the repository in Vercel

1. In Vercel, create a new project and import the repository.
2. Set the Root Directory to `human_comparison_24_trials_plain_language` if that directory is
   nested inside the repository. Otherwise leave the repository root selected.
3. Use the Flask framework preset. The supplied Python dependencies and
   entrypoint configuration support automatic detection.
4. No frontend build command or output directory is required for this project.
5. Before the first usable deployment, add the environment variables below.

## 6. Set environment variables

In the project's Environment Variables settings, add:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | Your managed PostgreSQL pooled connection URL |
| `SECRET_KEY` | A random secret of at least 32 characters |
| `STUDY_ADMIN_PASSWORD` | Your private researcher password, at least 16 characters |
| `STUDY_DIR` | `study` |
| `MAX_TRIALS` | `24` (or leave unset; this version defaults to 24) |

Generate a secret locally:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy its output into SECRET_KEY. Generate a different random string for your
researcher password if desired. Keep SECRET_KEY stable so participant cookies
remain valid after redeployment. Do not use the same value for both secrets.

If the integration created DATABASE_URL automatically, check that it is a
pooled PostgreSQL URL for the intended study database. If it uses another
variable name, add DATABASE_URL pointing to that URL.

Production variables must be set for the Production environment. If you want
to use Preview deployments, give them a separate pilot database and secrets;
do not send participants to preview URLs or mix preview votes into real data.
If your first deployment starts before variables are configured, set them and
redeploy. Vercel provides its own VERCEL environment flag; do not set it manually.

## 7. Deploy and pilot

Deploy from Vercel. The resulting public study address will look like:

```text
https://your-project.vercel.app
```

Open it in a normal browser window. Confirm that:

1. The entry page explains the task and participation information.
2. Every trial shows the correct original above A and B.
3. All three images load, including their larger-view links.
4. Both questions are required and ties/cannot-judge options work.
5. Submitting advances once; refreshing resumes the same session.
6. At `/admin`, your password opens the researcher dashboard.
7. The response export records reference_asset, source ID, baseline, A/B
   assignments, question version, and both chosen winners correctly.
8. Answers remain present after a new application deployment.

The admin URL is `https://your-project.vercel.app/admin`. Participants get only
the root study URL. Check from an incognito window that participants can open
the study without signing into Vercel. Deployment Protection, if enabled on
that deployment, may require adjustment for an intentionally public study.
Never turn off your app's researcher-password protection.

The site uses HTTPS-secure session cookies automatically on Vercel. No
`--https` command or local Waitress process is needed there. Vercel invokes
`index.py` directly; it does not run `python app.py` as a persistent server.

## 8. Keep collecting and reviewing

Database responses are committed after each pair, independently of Vercel's
function lifecycle. Download response and summary CSVs from /admin regularly,
and use the database provider's backup/export features for a full backup.
The CSVs do not contain unsubmitted session schedules; the database does.

Keep the image set, question wording, fixed 24-trial design and reference-display policy
fixed during collection. Use a fresh study folder and dedicated database for a
new experiment. Configure researcher-login rate limiting in Vercel's firewall
if exposing it widely. A random browser ID is not proof of a unique person;
control recruitment separately if one participation per person is required.

## Fewer-code alternative?

For your existing Python project, keeping this Flask app is less rework than
rewriting the interface in React/Next.js. Vercel plus one managed database still
requires account/environment setup. A static website alone cannot privately
and reliably store this study's shared response data.

A Python-first host with persistent storage can avoid the PostgreSQL adapter,
but it is a different hosting route. This delivery provides the Vercel route
you requested, while preserving a local SQLite mode for development.

## Official references checked for this guide

- https://vercel.com/docs/frameworks/backend/flask
- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/functions/runtimes
- https://vercel.com/docs/functions/limitations
- https://vercel.com/marketplace/neon
- https://neon.com/docs/get-started/connect-neon
- https://www.psycopg.org/psycopg3/docs/basic/usage.html

No Vercel deployment or live PostgreSQL database was created by this delivery.
Run the included web tests and the deployment pilot in your own environment.
