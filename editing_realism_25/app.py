"""25-trial realism survey. Standard WSGI locally; Flask entrypoint on Vercel."""
import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import random
import re
import secrets
import time
import traceback
from datetime import datetime, timezone
from html import escape
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server
from database import Database
from study_design import VERSION, RATINGS, TASK_NAMES, ANIMAL_NAMES, validate_manifest, summaries, csv_text

BASE=Path(__file__).resolve().parent
COOKIE='splice_realism25'
VALID={r[0] for r in RATINGS}

def now():return datetime.now(timezone.utc).isoformat()
def e(x):return escape(str(x),quote=True)
def fields(data):return {k:v[-1] for k,v in parse_qs(data,keep_blank_values=True).items()}
def token(secret,value):return hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()

def page(title,content):
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)} · SPLICE image study</title>'
            '<link rel="stylesheet" href="/style.css"><script defer src="/study.js"></script></head>'
            '<body><header><a href="/">SPLICE image study</a><span>Image realism evaluation</span></header>'
            f'<main>{content}</main><footer>There are no right or wrong answers. Please give your own impression.</footer></body></html>')

class Problem(Exception):
    def __init__(self,status,message):self.status=status;self.message=message

class StudyApp:
    def __init__(self,study_dir=None,admin_password=None,database_url=None,secret=None,secure=None,public_dir=None):
        self.root=Path(study_dir or os.environ.get('STUDY_DIR',str(BASE/'study'))).resolve()
        self.public=Path(public_dir or BASE/'public').resolve()
        self.manifest=json.loads((self.root/'manifest.json').read_text(encoding='utf-8'))
        self.trials={t['id']:t for t in validate_manifest(self.manifest)}
        self.study_id=self.manifest['study_id']
        self.password=admin_password or os.environ.get('STUDY_ADMIN_PASSWORD','')
        if len(self.password)<16:raise ValueError('Set STUDY_ADMIN_PASSWORD to at least 16 characters.')
        self.secure=bool(os.environ.get('VERCEL')) if secure is None else secure
        url=database_url if database_url is not None else os.environ.get('DATABASE_URL')
        self.secret=secret or os.environ.get('SECRET_KEY')
        if os.environ.get('VERCEL') and (not url or not self.secret):
            raise ValueError('Deployment requires DATABASE_URL and SECRET_KEY. SQLite is for local use only.')
        if not self.secret:self.secret=(self.root/'session.key').read_text().strip()
        if len(self.secret)<32:raise ValueError('SECRET_KEY must have at least 32 characters.')
        self.database=Database(self.root/'responses.sqlite3',url)
        for t in self.trials.values():
            for f in ['original_asset','edited_asset']:
                if not re.fullmatch(r'[a-f0-9]{64}\.png',t[f]) or not (self.public/'study_images'/t[f]).is_file():
                    raise ValueError(f'Missing or invalid prepared image: {t[f]}. Include public/study_images in deployment.')
        with self.database.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS realism25_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS realism25_participants (
              id TEXT PRIMARY KEY, schedule TEXT NOT NULL, created_at TEXT NOT NULL, submitted_at TEXT);
            CREATE TABLE IF NOT EXISTS realism25_exposures (
              participant_id TEXT NOT NULL REFERENCES realism25_participants(id), trial_id TEXT NOT NULL,
              first_shown_at TEXT NOT NULL, last_shown_epoch DOUBLE PRECISION NOT NULL,
              PRIMARY KEY(participant_id, trial_id));
            CREATE TABLE IF NOT EXISTS realism25_answers (
              participant_id TEXT NOT NULL REFERENCES realism25_participants(id), trial_id TEXT NOT NULL,
              rating TEXT NOT NULL, first_saved_at TEXT NOT NULL, last_saved_at TEXT NOT NULL,
              revision_count INTEGER NOT NULL, last_visit_seconds DOUBLE PRECISION NOT NULL,
              PRIMARY KEY(participant_id, trial_id));
            ''')
            fingerprint=hashlib.sha256(json.dumps(self.manifest,sort_keys=True).encode()).hexdigest()
            c.execute('INSERT INTO realism25_meta VALUES (?,?) ON CONFLICT DO NOTHING',('manifest_hash',fingerprint))
            old=c.execute('SELECT value FROM realism25_meta WHERE key=?',('manifest_hash',)).fetchone()
            if old['value']!=fingerprint:raise ValueError('This database belongs to a different image selection. Use a NEW database or schema search_path; do not change a live manifest.')

    def sign(self,payload):
        value=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')
        return value+'.'+token(self.secret,value)

    def identity(self,environ):
        try:
            cookie=SimpleCookie();cookie.load(environ.get('HTTP_COOKIE',''))
            value,sig=cookie[COOKIE].value.split('.')
            if not hmac.compare_digest(sig,token(self.secret,value)):return None
            payload=json.loads(base64.urlsafe_b64decode(value+'='*(-len(value)%4)))
            if payload['study']!=self.study_id or payload['expires']<time.time():return None
            return payload
        except (KeyError,ValueError,TypeError):return None

    def cookie(self,role,ident):
        payload=dict(role=role,id=ident,study=self.study_id,expires=time.time()+86400*30)
        value=self.sign(payload)
        return ('Set-Cookie',f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000'+('; Secure' if self.secure else ''))

    def csrf(self,identity):return token(self.secret,'csrf:'+identity['role']+':'+identity['id']+':'+self.study_id)
    def hidden(self,identity):return f'<input type="hidden" name="csrf" value="{self.csrf(identity)}">'

    def __call__(self,environ,start_response):
        try:
            status,headers,body=self.route(environ)
        except Problem as exc:
            status=exc.status;headers=[];body=page('Unable to continue',f'<section><h1>Unable to continue</h1><p>{e(exc.message)}</p><a href="/">Return to the study</a></section>')
        except Exception:
            traceback.print_exc();status=500;headers=[];body=page('Temporary problem','<section><h1>We could not save or load this page.</h1><p>Please try again. Your previously saved answers remain available in this browser.</p></section>')
        if isinstance(body,str):body=body.encode('utf-8')
        if not any(k.lower()=='content-type' for k,v in headers):headers.append(('Content-Type','text/html; charset=utf-8'))
        headers.extend([('Content-Length',str(len(body))),('Cache-Control','no-store'),
                        ('X-Content-Type-Options','nosniff'),('Referrer-Policy','same-origin'),
                        ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")])
        labels={200:'OK',303:'See Other',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',409:'Conflict',413:'Content Too Large',500:'Internal Server Error'}
        start_response(f'{status} {labels[status]}',headers);return [body]

    def route(self,env):
        method=env['REQUEST_METHOD'];path=env.get('PATH_INFO','/');ident=self.identity(env)
        if method not in {'GET','POST'}:raise Problem(400,'Unsupported request.')
        data={}
        if method=='POST':
            size=int(env.get('CONTENT_LENGTH') or 0)
            if size>16384:raise Problem(413,'Request is too large.')
            data=fields(env['wsgi.input'].read(size).decode('utf-8'))
        def redirect(url,headers=None):return 303,[('Location',url)]+(headers or []),''
        if path in ['/style.css','/study.js'] or path.startswith('/study_images/'):
            if method!='GET':raise Problem(404,'Not found.')
            asset=path.lstrip('/')
            allowed={t[f] for t in self.trials.values() for f in ['original_asset','edited_asset']}
            if path.startswith('/study_images/') and asset.split('/',1)[1] not in allowed:raise Problem(404,'Image not found.')
            p=self.public/asset
            if not p.is_file():raise Problem(404,'Not found.')
            return 200,[('Content-Type',mimetypes.guess_type(str(p))[0] or 'application/octet-stream')],p.read_bytes()
        if path=='/favicon.ico':return 404,[],''
        if path=='/health':return 200,[('Content-Type','application/json')],json.dumps({'status':'ok','trials':25})
        if path=='/':
            if ident and ident['role']=='participant':
                return redirect('/done' if self.participant(ident)['submitted_at'] else '/trial/0')
            # Stateless signed guest token protects study start and admin login forms.
            if not ident:
                guest=dict(role='guest',id=secrets.token_hex(16),study=self.study_id,expires=time.time()+86400)
            else:guest=ident
            html='''<section class="intro"><p class="eyebrow">Help us evaluate edited wildlife images</p>
            <h1>How natural do the edited images look?</h1>
            <p>We are studying ways to change wildlife photographs so researchers can test how animal-detection software responds. We would like your opinion on how realistic the edited images look. No technical knowledge is needed.</p>
            <h2>What will you see?</h2><p>Each page shows an original photograph on the left and an edited version on the right.</p>
            <ul><li><strong>Object replacement:</strong> an animal region was edited to replace the animal with another object.</li>
            <li><strong>Background replacement:</strong> the surroundings were changed while the animal regions were kept.</li></ul>
            <p>Use the original to identify what changed. Rate <strong>only the edited image</strong>. Consider the changed area's texture, lighting, edges and how well it fits the rest of the photograph. A scene can be unfamiliar and still look like a natural photograph.</p>
            <h2>How to take part</h2><ol><li>View 25 image pairs and choose one realism rating for each.</li>
            <li>Use Previous and Next to save, review or change your answers.</li><li>Review the completion page, then click Submit study. Answers become final after submission.</li></ol>
            <p>You can enlarge either image. Choose “I cannot judge” if needed. Please use a laptop or desktop if possible. Participation is voluntary; you may leave before submitting.</p>
            <p>No name or email is requested. A browser cookie identifies your responses. Please use this browser throughout and complete the study once. Researcher downloads include a random participant ID, answers and timestamps. Hosting services may keep their own operational logs.</p>'''
            html+=f'<form method="post" action="/start">{self.hidden(guest)}<label class="choice"><input type="checkbox" name="agree" value="yes" required> I have read the instructions and agree to take part.</label><button>Start the study</button></form></section>'
            return 200,([] if ident else [self.cookie('guest',guest['id'])]),page('Welcome',html)
        if method=='POST':
            if not ident or not hmac.compare_digest(data.get('csrf',''),self.csrf(ident)):
                raise Problem(403,'Your form expired. Reload the page and try again.')
        if path=='/start' and method=='POST':
            if ident['role']=='participant':return redirect('/trial/0')
            if data.get('agree')!='yes':raise Problem(400,'Please read the instructions and agree before starting.')
            pid=secrets.token_hex(24);schedule=list(self.trials);random.SystemRandom().shuffle(schedule)
            with self.database.connect() as c:
                c.execute('INSERT INTO realism25_participants VALUES (?,?,?,NULL)',(pid,json.dumps(schedule),now()))
            return redirect('/trial/0',[self.cookie('participant',pid)])
        if path.startswith('/admin'):
            return self.admin(path,method,data,ident,redirect)
        if not ident or ident['role']!='participant':return redirect('/')
        participant=self.participant(ident);schedule=json.loads(participant['schedule'])
        if participant['submitted_at'] and path!='/done':return redirect('/done')
        if path=='/done':
            if not participant['submitted_at']:return redirect('/review')
            return 200,[],page('Thank you','<section><h1>Thank you for taking part.</h1><p>Your 25 answers have been submitted. They are now final and cannot be changed.</p><p>You may close this page.</p></section>')
        match=re.fullmatch(r'/trial/(\d+)',path)
        if match:
            index=int(match[1])
            if index>=25:raise Problem(404,'Trial not found.')
            tid=schedule[index];trial=self.trials[tid]
            if method=='POST':
                rating=data.get('rating','')
                # Previous can leave an unanswered trial; Next requires a choice.
                if rating not in VALID and not (data.get('action')=='previous' and rating==''):
                    raise Problem(400,'Choose a realism rating before continuing. Use your browser Back button to return.')
                with self.database.connect() as c:
                    self.lock(c,ident['id'])
                    if rating:
                        exposure=c.execute('SELECT last_shown_epoch FROM realism25_exposures WHERE participant_id=? AND trial_id=?',(ident['id'],tid)).fetchone()
                        elapsed=max(0,time.time()-exposure['last_shown_epoch']) if exposure else 0
                        stamp=now()
                        c.execute('''INSERT INTO realism25_answers VALUES (?,?,?,?,?,0,?) ON CONFLICT(participant_id,trial_id)
                        DO UPDATE SET rating=excluded.rating,last_saved_at=excluded.last_saved_at,
                        revision_count=realism25_answers.revision_count+1,last_visit_seconds=excluded.last_visit_seconds''',
                        (ident['id'],tid,rating,stamp,stamp,elapsed))
                return redirect(f'/trial/{max(0,index-1)}' if data.get('action')=='previous' else ('/review' if index==24 else f'/trial/{index+1}'))
            with self.database.connect() as c:
                c.execute('''INSERT INTO realism25_exposures VALUES (?,?,?,?) ON CONFLICT(participant_id,trial_id)
                DO UPDATE SET last_shown_epoch=excluded.last_shown_epoch''',(ident['id'],tid,now(),time.time()))
                answer=c.execute('SELECT rating FROM realism25_answers WHERE participant_id=? AND trial_id=?',(ident['id'],tid)).fetchone()
                completed=c.execute('SELECT COUNT(*) AS n FROM realism25_answers WHERE participant_id=?',(ident['id'],)).fetchone()['n']
            rating=answer['rating'] if answer else ''
            html=f'<p class="eyebrow">Image pair {index+1} of 25 · {completed} answers saved</p><h1>{e(TASK_NAMES[trial["task"]])}: {e(ANIMAL_NAMES[trial["animal"]])}</h1>'
            explanation=('An animal region was edited to replace the animal with another object. Focus on how natural the new object and the edited area look within the photograph.' if trial['task']=='replace' else 'The surroundings were changed while the animal regions were kept. Focus on how natural the new background looks and how well its lighting, texture and edges fit the animals.')
            html+=f'<p class="task-note">{explanation}</p>'
            if trial.get('description'):html+=f'<p><strong>Intended change:</strong> {e(trial["description"])}</p>'
            html+='<div class="trial-layout"><div class="pair">'
            for f,label in [('original','Original photograph'),('edited','Edited photograph — rate this image')]:
                html+=f'<figure><figcaption>{e(label)}</figcaption><button type="button" class="image-button" data-zoom="/study_images/{trial[f+"_asset"]}" aria-label="Enlarge {f} photograph"><img src="/study_images/{trial[f+"_asset"]}" alt="{f.capitalize()} wildlife photograph" loading="eager"></button><small>Click to enlarge</small></figure>'
            html+='</div><section class="rating-panel"><h2>How realistic does the edited image look?</h2><p>Could the changed area pass as part of a natural, unedited photograph? Rate its appearance, rather than whether you like the change.</p>'
            html+=f'<form method="post">{self.hidden(ident)}<fieldset><legend class="sr-only">Realism rating</legend>'
            for value,label,desc in RATINGS:
                html+=f'<label class="choice"><input type="radio" name="rating" value="{value}" {"checked" if rating==value else ""}><span><strong>{e(label)}</strong><small>{e(desc)}</small></span></label>'
            html+='</fieldset><div class="buttons">'
            if index:html+='<button class="secondary" name="action" value="previous">Previous</button>'
            html+=f'<button name="action" value="next">{"Save and review" if index==24 else "Save and next"}</button></div></form><a class="review-link" href="/review">Review saved answers</a><small>Use the buttons to save your current selection before leaving this page.</small></section></div>'
            return 200,[],page('Rate an edited image',html)
        if path=='/review' and method=='GET':
            with self.database.connect() as c:answers={r['trial_id']:r['rating'] for r in c.execute('SELECT * FROM realism25_answers WHERE participant_id=?',(ident['id'],)).fetchall()}
            labels={v:l for v,l,d in RATINGS}
            html='<section><h1>Review your answers</h1><p>Your answers are saved as a draft. You can still change them. After you click Submit study, your answers become final.</p>'
            html+=f'<p><strong>{len(answers)} of 25 answered.</strong></p><div class="table-scroll"><table><thead><tr><th>Pair</th><th>Task and animal</th><th>Your answer</th><th>Review</th></tr></thead><tbody>'
            for i,tid in enumerate(schedule):
                t=self.trials[tid];html+=f'<tr><td>{i+1}</td><td>{e(TASK_NAMES[t["task"]])}: {e(ANIMAL_NAMES[t["animal"]])}</td><td>{e(labels.get(answers.get(tid),"Not answered"))}</td><td><a href="/trial/{i}">View or change</a></td></tr>'
            html+='</tbody></table></div>'
            if len(answers)==25:html+=f'<form method="post" action="/submit">{self.hidden(ident)}<label class="choice"><input type="checkbox" name="confirm" value="yes" required> I have reviewed my answers and am ready to submit.</label><button>Submit study</button></form>'
            else:html+='<p>Please answer every pair before submitting. “I cannot judge” is a valid answer.</p>'
            return 200,[],page('Review',html+'</section>')
        if path=='/submit' and method=='POST':
            if data.get('confirm')!='yes':raise Problem(400,'Please confirm you are ready to submit.')
            with self.database.connect() as c:
                self.lock(c,ident['id'])
                answers=c.execute('SELECT trial_id,rating FROM realism25_answers WHERE participant_id=?',(ident['id'],)).fetchall()
                if {r['trial_id'] for r in answers}!=set(schedule) or any(r['rating'] not in VALID for r in answers):
                    raise Problem(400,'All 25 image pairs need an answer before submission.')
                c.execute('UPDATE realism25_participants SET submitted_at=? WHERE id=?',(now(),ident['id']))
            return redirect('/done')
        raise Problem(404,'Page not found.')

    def participant(self,ident):
        with self.database.connect() as c:r=c.execute('SELECT * FROM realism25_participants WHERE id=?',(ident['id'],)).fetchone()
        if not r:raise Problem(401,'This participant session is no longer available.')
        return r

    def lock(self,c,pid):
        # Serialize edits and final submission across tabs and requests.
        if not self.database.postgres:c.execute('BEGIN IMMEDIATE')
        r=c.execute('SELECT submitted_at FROM realism25_participants WHERE id=?'+(' FOR UPDATE' if self.database.postgres else ''),(pid,)).fetchone()
        if not r:raise Problem(401,'Participant session not found.')
        if r['submitted_at']:raise Problem(409,'Your study is already submitted. Answers are final.')

    def export_rows(self,include_drafts=False):
        with self.database.connect() as c:
            rows=c.execute('''SELECT p.id AS participant_id,p.schedule,p.created_at,p.submitted_at,
            a.trial_id,a.rating,a.first_saved_at,a.last_saved_at,a.revision_count,a.last_visit_seconds,
            x.first_shown_at FROM realism25_participants p JOIN realism25_answers a ON a.participant_id=p.id
            LEFT JOIN realism25_exposures x ON x.participant_id=p.id AND x.trial_id=a.trial_id'''+('' if include_drafts else ' WHERE p.submitted_at IS NOT NULL')+' ORDER BY p.id,a.trial_id').fetchall()
        out=[]
        for raw in rows:
            r=dict(raw);t=self.trials[r['trial_id']];schedule=json.loads(r.pop('schedule'))
            r.update(study_id=self.study_id,questions_version=VERSION,task=t['task'],animal=t['animal'],
                     source_id=t['source_id'],description=t.get('description',''),original_asset=t['original_asset'],
                     edited_asset=t['edited_asset'],original_source=t.get('original_source',''),edited_source=t.get('edited_source',''),
                     trial_index=schedule.index(t['id'])+1,response_status='submitted' if r['submitted_at'] else 'draft',
                     rating_score='' if r['rating']=='cannot_judge' else int(r['rating']))
            out.append(r)
        return out

    def admin(self,path,method,data,ident,redirect):
        if path=='/admin/login':
            headers=[]
            if not ident:
                ident=dict(role='guest',id=secrets.token_hex(16))
                headers=[self.cookie('guest',ident['id'])]
            if method=='POST':
                if not hmac.compare_digest(data.get('password','').encode(),self.password.encode()):
                    # No detailed credential errors. Apply host-level rate limiting for public deployments.
                    raise Problem(403,'Sign-in failed.')
                return redirect('/admin',[self.cookie('admin',secrets.token_hex(16))])
            return 200,headers,page('Researcher login',f'<section><h1>Researcher sign-in</h1><form method="post">{self.hidden(ident)}<label>Password <input type="password" name="password" required autocomplete="current-password"></label><button>Sign in</button></form></section>')
        if not ident or ident['role']!='admin':return redirect('/admin/login' if ident else '/')
        if path=='/admin/logout' and method=='POST':return redirect('/',[('Set-Cookie',f'{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax')])
        if method!='GET':raise Problem(404,'Not found.')
        rows=self.export_rows();summary=summaries(rows)
        if path in ['/admin/responses.csv','/admin/summary.csv','/admin/drafts.csv']:
            export=summary if path.endswith('summary.csv') else self.export_rows(include_drafts=path.endswith('drafts.csv'))
            # Spreadsheet formula injection protection for source descriptions and names.
            export=[{k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in r.items()} for r in export]
            return 200,[('Content-Type','text/csv; charset=utf-8'),('Content-Disposition',f'attachment; filename="{path.rsplit("/",1)[1]}"')],csv_text(export)
        if path!='/admin':raise Problem(404,'Not found.')
        with self.database.connect() as c:
            total=c.execute('SELECT COUNT(*) AS n FROM realism25_participants').fetchone()['n']
            complete=c.execute('SELECT COUNT(*) AS n FROM realism25_participants WHERE submitted_at IS NOT NULL').fetchone()['n']
        html=f'<section><h1>Study results</h1><p>{complete} submitted participants · {total-complete} unsubmitted participants</p><p>Only final submissions contribute to the summaries below. Ratings of 4 or 5 mean mostly or completely natural. “Cannot judge” is excluded from rating means, medians and percentages, and is reported separately.</p><p><a href="/admin/responses.csv">Download submitted responses</a> · <a href="/admin/summary.csv">Download summary</a> · <a href="/admin/drafts.csv">Download all saved answers, including drafts</a></p><p>These are descriptive results. Ratings from the same person and repeated ratings of the same image are related. The overall score weights groups by their number of trials: background has 15, replacement has 10. This study does not ask for a preference between editing methods.</p><div class="table-scroll"><table><thead><tr><th>Task</th><th>Animal or image</th><th>Participants</th><th>Rated</th><th>Cannot judge</th><th>Mean / 5</th><th>Median</th><th>Rated 4 or 5</th><th>Counts: 1 / 2 / 3 / 4 / 5</th></tr></thead><tbody>'
        for r in summary:
            html+='<tr>'+''.join(f'<td>{e(v)}</td>' for v in [r['task'],r['animal_or_image'],r['n_participants'],r['n_rated'],r['n_cannot_judge'],r['mean_rating'],r['median_rating'],str(r['mostly_or_completely_natural_pct'])+'%' if r['n_rated'] else 'Not available',' / '.join(str(r[f'rating_{i}_count']) for i in range(1,6))])+'</tr>'
        html+=f'</tbody></table></div><form method="post" action="/admin/logout">{self.hidden(ident)}<button class="secondary">Sign out</button></form></section>'
        return 200,[],page('Researcher results',html)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',default=str(BASE/'study'));p.add_argument('--port',type=int,default=5000)
    a=p.parse_args();app=StudyApp(study_dir=a.study)
    print(f'Open http://127.0.0.1:{a.port}; researcher login: /admin/login')
    with make_server('127.0.0.1',a.port,app) as server:server.serve_forever()
