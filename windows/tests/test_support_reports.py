"""Report scope, bounded adjacent logs, redaction and immutable ZIP export."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'windows/engine-host')]
import support_reports as reports
import engine_bridge
import library_media
import game_notes
import transactions as t


class SupportReportTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();(self.root/'VERSION').write_text('1.0.0-beta.3')
        self.rows=[]
        for index in range(3):
            game=self.root/str(index);game.mkdir();(game/'Game.exe').write_bytes(b'MZ')
            (game/'OptiScaler.log').write_text('token=private-value\nuser@example.com\n76561191234567890\n')
            self.rows.append({'game':str(game),'exe':'Game.exe','name':'Game '+str(index),'runtime_provider':'skynizz'})
        engine=SimpleNamespace(STATE_ROOT=self.root/'state',Stop=RuntimeError,load_baseline=lambda *a,**kw:None)
        for mocked in (patch.object(engine_bridge,'module',return_value=engine),
                       patch.object(library_media,'load_settings',return_value={'runtime_provider':'feeder'}),
                       patch.object(game_notes,'load',return_value={'status':'Untested','notes':'private user@example.com'}),
                       patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)})):
            mocked.start();self.addCleanup(mocked.stop)

    def preview(self,rows=None,**kwargs):
        return reports.preview({},self.rows if rows is None else rows,root=self.root,build='test-build',**kwargs)

    def test_one_few_all_scopes_and_current_logs_without_a_test_session(self):
        for size in (1,2,3):
            files=self.preview(self.rows[:size],include_logs=True)
            data=json.loads(files['report.json'])
            self.assertEqual(len(data['games']),size)
            self.assertEqual(data['selected_package_for_new_installs'],'feeder')
            self.assertEqual(data['games'][0]['scan_provider'],'skynizz')
            self.assertEqual(len([n for n in files if n.endswith('OptiScaler.log')]),size)
        text='\n'.join(files.values())
        self.assertNotIn('private-value',text)
        self.assertNotIn('user@example.com',text)
        self.assertNotIn('76561191234567890',text)
        self.assertTrue(any(not item['included'] for item in json.loads(files['manifest.json'])['files']))

    def test_export_does_not_reread_logs_and_omitted_logs_stay_omitted(self):
        frozen=self.preview(self.rows[:1],include_logs=True)
        (Path(self.rows[0]['game'])/'OptiScaler.log').write_text('new data after preview')
        archive=reports.export(frozen,self.root/'Reports')
        with zipfile.ZipFile(archive) as zipped:
            self.assertEqual(zipped.read('logs/000/0/OptiScaler.log').decode(),frozen['logs/000/0/OptiScaler.log'])
        self.assertFalse(any(n.startswith('logs/') for n in self.preview(include_logs=False)))

    def test_limits_and_unsafe_or_duplicate_selection_refuse(self):
        with patch.object(reports,'FILE_LIMIT',8),patch.object(reports,'TOTAL_LIMIT',12):
            files=self.preview(include_logs=True)
            manifest=json.loads(files['manifest.json'])
            self.assertGreaterEqual(manifest['remaining_bytes'],0)
            self.assertTrue(any(item.get('truncated') for item in manifest['files']))
        for rows in ([],[self.rows[0],self.rows[0]],[self.rows[0]|{'exe':'../escape.exe'}]):
            with self.subTest(rows=rows),self.assertRaises(t.Refusal):self.preview(rows)
        with self.assertRaises(t.Refusal):reports.export({'oversize.txt':'x'*reports.ZIP_LIMIT},self.root/'Reports')


if __name__=='__main__':unittest.main()
