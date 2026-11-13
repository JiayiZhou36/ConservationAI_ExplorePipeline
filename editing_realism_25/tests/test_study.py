import io,json,re,sys,tempfile,unittest
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import StudyApp,COOKIE
from make_demo import make_demo
from prepare_study import prepare
from study_design import summaries,validate_manifest

class Client:
    def __init__(self,app):self.app=app;self.cookie='';self.body=''
    def request(self,path='/',method='GET',data=None):
        encoded=urlencode(data or {}).encode();status=[];headers=[]
        def start(s,h):status.append(int(s.split()[0]));headers.extend(h)
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'wsgi.input':io.BytesIO(encoded),
             'CONTENT_LENGTH':str(len(encoded)),'HTTP_COOKIE':self.cookie}
        result=b''.join(self.app(env,start))
        for k,v in headers:
            if k=='Set-Cookie':self.cookie=v.split(';',1)[0]
        self.body=result.decode('utf-8',errors='replace');self.headers=dict(headers)
        return status[0]
    def post(self,path,data=None):
        ident=self.app.identity({'HTTP_COOKIE':self.cookie})
        return self.request(path,'POST',dict(data or {},csrf=self.app.csrf(ident)))
    def begin(self):
        assert self.request('/')==200
        assert self.post('/start',{'agree':'yes'})==303
    def all_answers(self):
        for i in range(25):
            assert self.request(f'/trial/{i}')==200
            assert self.post(f'/trial/{i}',{'rating':'cannot_judge' if i==0 else '5','action':'next'})==303

class StudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name)
        make_demo(cls.base/'images')
        cls.manifest=prepare(cls.base/'images',cls.base/'prepared',cls.base/'public'/'study_images',max_width=400)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.work=tempfile.TemporaryDirectory();root=Path(self.work.name)
        (root/'manifest.json').write_text(json.dumps(self.manifest))
        self.app=StudyApp(root,admin_password='researcher-password-long',secret='a'*64,database_url='',public_dir=self.base/'public',secure=False)
        self.client=Client(self.app)
    def tearDown(self):self.work.cleanup()
    def test_exact_quotas(self):
        from collections import Counter
        self.assertEqual(sorted(Counter((t['task'],t['animal']) for t in self.manifest['trials']).values()),[5]*5)
        bad=dict(self.manifest,trials=self.manifest['trials'][:-1])
        with self.assertRaises(ValueError):validate_manifest(bad)
    def test_navigation_revision_and_draft_exclusion(self):
        c=self.client;c.begin();self.assertEqual(c.request('/trial/0'),200)
        self.assertEqual(c.post('/trial/0',{'rating':'1','action':'next'}),303)
        self.assertEqual(c.request('/trial/0'),200);self.assertIn('value="1" checked',c.body)
        self.assertEqual(c.post('/trial/0',{'rating':'4','action':'next'}),303)
        self.assertEqual(self.app.export_rows(),[])
        row=self.app.export_rows(True)[0];self.assertEqual(row['rating'],'4');self.assertEqual(row['revision_count'],1)
    def test_complete_final_and_frozen(self):
        c=self.client;c.begin();c.all_answers()
        self.assertEqual(c.request('/review'),200);self.assertIn('25 of 25 answered',c.body)
        self.assertEqual(c.post('/submit',{'confirm':'yes'}),303)
        rows=self.app.export_rows();self.assertEqual(len(rows),25)
        self.assertEqual(c.post('/trial/0',{'rating':'1','action':'next'}),303)
        self.assertEqual(len(self.app.export_rows()),25)
        self.assertEqual(sum(r['rating']=='5' for r in self.app.export_rows()),24)
        self.assertEqual(c.request('/done'),200);self.assertIn('now final',c.body)
    def test_incomplete_and_invalid_rating_rejected(self):
        c=self.client;c.begin();c.request('/trial/0')
        self.assertEqual(c.post('/submit',{'confirm':'yes'}),400)
        self.assertEqual(c.post('/trial/0',{'rating':'99','action':'next'}),400)
        self.assertEqual(c.request('/trial/25'),404)
    def test_csrf_and_admin_protected(self):
        c=self.client;c.request('/')
        self.assertEqual(c.request('/start','POST',{'agree':'yes'}),403)
        self.assertEqual(c.request('/admin/responses.csv'),303)
        self.assertEqual(c.request('/admin/login'),200)
        self.assertEqual(c.post('/admin/login',{'password':'wrong'}),403)
        self.assertEqual(c.post('/admin/login',{'password':'researcher-password-long'}),303)
        self.assertEqual(c.request('/admin'),200)
        self.assertEqual(c.request('/admin/summary.csv'),200)
    def test_summary_cannot_judge_and_item_level(self):
        c=self.client;c.begin();c.all_answers();c.post('/submit',{'confirm':'yes'})
        summary=summaries(self.app.export_rows());r=summary[0]
        self.assertEqual(r['n_cannot_judge'],1);self.assertEqual(r['n_rated'],24)
        self.assertEqual(r['mean_rating'],5);self.assertEqual(r['mostly_or_completely_natural_pct'],100)
        self.assertEqual(len(summary),33)
    def test_manifest_binding(self):
        root=Path(self.work.name);m=dict(self.manifest,study_id='different')
        (root/'manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError):StudyApp(root,admin_password='researcher-password-long',secret='a'*64,database_url='',public_dir=self.base/'public')
    def test_no_cookie_admin_login_and_asset(self):
        c=self.client;self.assertEqual(c.request('/admin/login'),200)
        self.assertEqual(c.post('/admin/login',{'password':'researcher-password-long'}),303)
        name=self.manifest['trials'][0]['edited_asset']
        self.assertEqual(c.request('/study_images/'+name),200)
        self.assertEqual(c.request('/study_images/../../app.py'),404)

if __name__=='__main__':unittest.main()
