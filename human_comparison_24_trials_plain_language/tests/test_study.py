import csv
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_study import prepare
from analysis import summarize
try:
    from app import create_app
except ModuleNotFoundError as exc:
    if exc.name != "flask":
        raise
    create_app = None


def make_inputs(root):
    for animal in ('seal', 'whale', 'dolphin'):
        for method in ('original', 'remove', 'black_mask', 'blurring'):
            folder = root / animal / method
            folder.mkdir(parents=True)
            for i in range(4):
                Image.new('RGB', (80, 50), {'original':'green','remove':'blue','black_mask':'black','blurring':'gray'}[method]).save(folder/f'scene_{i}_{method}.png')
                # Debug files must not become trials.
                Image.new('L', (80,50), 255).save(folder/f'scene_{i}_{method}_mask.png')


class PreparationTests(unittest.TestCase):
    def test_pairing_and_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_inputs(root/'inputs')
            manifest = prepare(root/'inputs', root/'study')
            self.assertEqual(len(manifest['sources']),12)
            self.assertEqual(len(manifest['pairs']),24)
            self.assertEqual({p['baseline'] for p in manifest['pairs']}, {'black_mask','blurring'})
            self.assertEqual(len(list((root/'study'/'images').glob('*.png'))),4)
            with self.assertRaises(ValueError):
                prepare(root/'inputs',root/'study')

    def test_missing_and_different_dimensions_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_inputs(root/'inputs')
            path=root/'inputs'/'seal'/'remove'/'scene_0_remove.png'
            path.unlink()
            with self.assertRaisesRegex(ValueError, 'missing remove'):
                prepare(root/'inputs',root/'study')
            Image.new('RGB',(81,50)).save(path)
            with self.assertRaisesRegex(ValueError,'dimensions differ'):
                prepare(root/'inputs',root/'study')
            self.assertFalse((root/'study').exists())

    def test_batch_extension_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for animal in ('seal','whale','dolphin'):
                for method, suffix in [('original','original'),('removal','remove'),('black_mask','black_mask'),('blur','blurring')]:
                    folder=root/'inputs'/animal/method
                    folder.mkdir(parents=True)
                    for i in range(4):
                        Image.new('RGB',(20,20)).save(folder/f'scene_{i}.jpg_{suffix}.png')
            manifest=prepare(root/'inputs',root/'study')
            self.assertEqual(manifest['sources'][0]['source_key'],'scene_0')

    def test_original_required_and_uniform_resize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_inputs(root/'inputs')
            reference = root/'inputs'/'seal'/'original'/'scene_0_original.png'
            reference.unlink()
            with self.assertRaisesRegex(ValueError, 'missing original'):
                prepare(root/'inputs', root/'study')
            Image.new('RGB', (80,50),'green').save(reference)
            manifest = prepare(root/'inputs',root/'study',max_width=40)
            self.assertEqual(manifest['max_width'],40)
            for source in manifest['sources']:
                self.assertIn('original',source['assets'])
                for asset in source['assets'].values():
                    with Image.open(root/'study'/'images'/f'{asset}.png') as image:
                        self.assertEqual(image.size,(40,25))

    def test_summary_denominators(self):
        rows=[dict(animal='seal',baseline='black_mask',participant_id=str(i),pair_id='one',
                   realism_winner=vote,preference_winner=vote)
              for i,vote in enumerate(['remove','remove','black_mask','tie','cannot_judge'])]
        row=next(r for r in summarize(rows) if r['animal']=='ALL_ANIMALS' and r['question']=='realism')
        self.assertAlmostEqual(row['remove_share_decisive'],2/3)
        self.assertEqual(row['remove_share_all'],.4)
        self.assertEqual(row['ties'],1)
        self.assertEqual(row['cannot_judge'],1)
        for r in rows:
            r['realism_winner']='tie'
        row=next(r for r in summarize(rows) if r['question']=='realism')
        self.assertIsNone(row['remove_share_decisive'])


@unittest.skipIf(create_app is None, 'Flask dependencies not installed')
class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        from unittest.mock import patch
        self.environment_patch = patch.dict(os.environ, {'DATABASE_URL':'','VERCEL':'0','SECRET_KEY':''})
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        make_inputs(self.root/'inputs')
        self.manifest=prepare(self.root/'inputs', self.root/'study')
        self.app=create_app(self.root/'study', admin_password='test-password-at-least-16', max_trials=24)
        self.app.config['TESTING']=True
        self.client=self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def token(self):
        with self.client.session_transaction() as session:
            return session['csrf']

    def begin(self):
        self.client.get('/')
        self.client.post('/start',data={'csrf':self.token(),'agree':'yes'})
        self.client.get('/trial')

    def test_trial_blinding_csrf_and_resume(self):
        self.begin()
        page=self.client.get('/trial').get_data(as_text=True)
        self.assertNotIn('black_mask',page)
        self.assertNotIn('blurring',page)
        self.assertNotIn('scene_0',page)
        self.assertEqual(self.client.get('/image/0/left').status_code,200)
        self.assertEqual(self.client.get('/image/0/reference').status_code,200)
        self.assertIn('ORIGINAL PHOTOGRAPH · BEFORE EDITING',page)
        self.assertIn('Which edited image looks more like a real photograph?',page)
        self.assertIn('What was changed?',page)
        self.assertEqual(self.client.get('/assets/style.css').status_code,200)
        self.assertEqual(self.client.get('/assets/study.js').status_code,200)
        self.assertEqual(self.client.get('/image/1/left').status_code,404)
        self.assertEqual(self.client.post('/answer',data={'trial_index':'0','realism':'left','preference':'right'}).status_code,400)
        self.assertEqual(self.client.get('/admin/export/responses').status_code,302)
        self.assertEqual(self.client.get('/').status_code,302)

    def test_duplicate_invalid_and_summary_export(self):
        self.begin()
        data={'csrf':self.token(),'trial_index':'0','realism':'left','preference':'right','comment':'=1+1'}
        self.assertEqual(self.client.post('/answer',data={**data,'realism':'bad'}).status_code,400)
        self.assertEqual(self.client.post('/answer',data=data).status_code,302)
        self.assertEqual(self.client.post('/answer',data=data).status_code,302)
        self.client.get('/admin/login')
        login=self.client.post('/admin/login',data={'csrf':self.token(),'password':'test-password-at-least-16'})
        self.assertEqual(login.status_code,302)
        content=self.client.get('/admin/export/responses').get_data(as_text=True)
        rows=list(csv.DictReader(io.StringIO(content)))
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['reference_asset'])
        self.assertEqual(rows[0]['questions_version'],'reference-realism-and-overall-v4')
        self.assertEqual(rows[0]['realism_winner'], rows[0]['left_method'])
        self.assertEqual(rows[0]['preference_winner'], rows[0]['right_method'])
        self.assertEqual(rows[0]['comment'],"'=1+1")
        self.assertEqual(len(list(csv.DictReader(io.StringIO(self.client.get('/admin/export/responses?complete=1').get_data(as_text=True))))),0)
        self.assertEqual(self.client.get('/admin').status_code,200)

    def test_complete_session_and_balanced_assignments(self):
        self.begin()
        for index in range(24):
            self.client.get('/trial')
            response=self.client.post('/answer',data={'csrf':self.token(),'trial_index':str(index),'realism':'tie','preference':'cannot_judge'})
            self.assertEqual(response.status_code,302)
        self.assertIn('Your responses have been saved',self.client.get('/trial').get_data(as_text=True))
        self.client.get('/admin/login')
        self.client.post('/admin/login',data={'csrf':self.token(),'password':'test-password-at-least-16'})
        rows=list(csv.DictReader(io.StringIO(self.client.get('/admin/export/responses?complete=1').get_data(as_text=True))))
        self.assertEqual(len(rows),24)
        self.assertEqual(sum(r['baseline']=='black_mask' for r in rows),12)
        self.assertTrue(all(r['participant_complete']=='True' for r in rows))
        from collections import Counter
        counts=Counter((r['animal'],r['baseline']) for r in rows)
        self.assertEqual(len(counts),6)
        self.assertTrue(all(count == 4 for count in counts.values()))
        summary=self.client.get('/admin/export/summary').get_data(as_text=True)
        self.assertIn('no_decisive_votes',summary)


if __name__=='__main__':
    unittest.main()
