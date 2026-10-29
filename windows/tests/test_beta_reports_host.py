"""Windows beta reports through the real host: shared beta_report drafts, corrections, logs and export."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

HOST_TEST = r'''
import sys,zipfile
from pathlib import Path
repo=Path(sys.argv[1]); base=Path(sys.argv[2]); local=base/'local'/'rtxForge'
sys.path[:0]=[str(repo/'scripts'),str(repo/'windows/engine-host')]
saved=sys.stdout
import rtxforge_win_host as host
sys.stdout=saved
game=base/'Example Game'; (game/'bin').mkdir(parents=True); (game/'bin/Game.exe').write_bytes(b'MZ')
(game/'bin/OptiScaler.log').write_text('token=private-value\nloaded C:\\Users\\someone\\game\n')
local.mkdir(parents=True,exist_ok=True); (local/'engine.log').write_text('engine started for me@example.com\n')
row={'game':str(game),'exe':'bin/Game.exe','name':'Example Game','appid':'123'}

try:host.METHODS['report_draft']({'rows':[row,row]})
except Exception as error:assert 'twice' in str(error),error
else:raise AssertionError('a game selected twice was accepted')

draft=host.METHODS['report_draft']({'rows':[row],'format':'Windows installer','channel':'Beta'})
report=draft['reports'][0]
assert report['fields']['platform']=='Windows',report
assert report['fields']['app-format']=='Windows installer',report
assert report['sources']['app-format']=='Detected on this computer',report
assert report['fields']['feature-package'].endswith('(selected, not installed)'),report
assert report['problems']==['What happened? is empty.'],report['problems']
assert [f['id'] for f in draft['fields'] if f['required']]==['platform','observations'],draft['fields']
guessed=host.METHODS['report_draft']({'rows':[row],'format':'Portable please'})['reports'][0]
assert guessed['fields']['app-format']=='Not sure','unverified formats are never guessed'

draft=host.METHODS['report_draft']({'rows':[row],'format':'Windows installer'})
report=draft['reports'][0]
try:host.METHODS['report_preview']({'ids':[report['id']]})
except Exception as error:assert 'What happened?' in str(error),error
else:raise AssertionError('an empty report was accepted')
try:host.METHODS['report_preview']({'ids':[report['id']],'edits':{report['id']:{'nr-result':'Amazing'}}})
except Exception as error:assert 'listed answers' in str(error),error
else:raise AssertionError('an unlisted answer was accepted')

documents=base/'Documents'; documents.mkdir()
edits={report['id']:{'observations':'Crashed at the title screen','nr-result':'Not working in-game'}}
review=host.METHODS['report_preview']({'ids':[report['id']],'edits':edits,'logs':True,'notes':False,'documents':str(documents)})
assert review['kind']=='report',review
titles=[item['title'] for item in review['items']]
assert any(t.endswith('logs/OptiScaler.log') for t in titles),titles
assert 'app/engine.log' in titles,titles
assert any(item['badge']=='Skipped' and item['title']=='crash.log' for item in review['items']),titles
text='\n'.join(item['details'] or '' for item in review['items'])
for secret in ('private-value','me@example.com','someone'):
    assert secret not in text,secret
(game/'bin/OptiScaler.log').write_text('CHANGED AFTER REVIEW')
result=host.METHODS['run']({'token':review['token']})
archive=Path(result['path'])
assert archive.parent==documents/'rtxForge Reports',archive
with zipfile.ZipFile(archive) as zipped:
    log=next(name for name in zipped.namelist() if name.endswith('logs/OptiScaler.log'))
    assert 'CHANGED' not in zipped.read(log).decode(),'export reread the game log'
    assert 'Crashed at the title screen' in zipped.read(next(n for n in zipped.namelist() if n.endswith('report.md'))).decode()

links=host.METHODS['report_links']({'ids':[report['id']]})
url=links['links'][0]['url']
assert 'template=beta-report.yml' in url and 'nr-result=Not+working+in-game' in url,url
existing=host.METHODS['report_links']({'ids':[report['id']],'issue':'#42','archive':str(archive)})
assert existing['issue']=={'number':42,'url':'https://github.com/lrnolivia/rtxForge/issues/42'},existing
assert archive.name in existing['comment'],existing['comment']
try:host.METHODS['report_links']({'ids':[report['id']],'issue':'https://example.com/lrnolivia/rtxForge/issues/42'})
except Exception as error:assert 'github.com' in str(error),error
else:raise AssertionError('an issue outside rtxForge was accepted')
print('host beta report draft, validation, redacted game and app logs, frozen export and issue links passed')
'''


@unittest.skipUnless(os.name == 'nt', 'Windows host adapters')
class WindowsHostBetaReportTest(unittest.TestCase):
    def test_real_host_beta_report_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            # The transaction engine refuses path aliases; use the canonical temp directory.
            base = Path(folder).resolve()
            local = base / 'local'
            env = dict(os.environ, LOCALAPPDATA=str(local), RTXFORGE_ROOT=str(ROOT),
                       RTXFORGE_STATE_ROOT=str(local / 'rtxForge/state'),
                       RTXFORGE_DLSS_UNLOCKED_STATE=str(local / 'rtxForge/engine-state'), PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-X', 'utf8', '-c', HOST_TEST, str(ROOT), str(base)],
                                    env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:] + result.stdout[-2000:])
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main()
