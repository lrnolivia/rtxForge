"""Write-disabled screenshots for both layouts and package inspection."""
import argparse, json, os, sys, tempfile, traceback, zipfile, urllib.request
from pathlib import Path
os.environ['GSETTINGS_BACKEND']='memory'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'gui'))
import rtxforge_gtk as classic
from gi.repository import GLib
options=argparse.Namespace(provider=None,demo=True,resize_smoke=False,smoke_test=False,live_smoke=False,library_state_smoke=False,ui_mode='classic')
app=classic.Application(options)
report=[]
fixture=ROOT/'dist/package-review-fixture.zip';fixture.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(fixture,'w') as z:
    for name,data in {'dxgi.dll':b'MZ demo only','OptiScaler.ini':b'[DLSSG]\nOverrideInterpolationCount=2\n[DlssNr]\nIntensity=1.5\n[Sharpness]\nSharpness=0.4','OptiScaler/streamline/sl.interposer.dll':b'MZ demo only','OptiScaler/streamline/sl.dlss_g.dll':b'MZ demo only','README.md':b'Place the files beside the game executable. Review your Proton configuration. No scripts run during inspection.'}.items():z.writestr(name,data)
# Use the application's existing public Steam artwork source for visual QA.
# These are demo fixtures only; no library or user settings are touched.
media=ROOT/'dist/demo-media';media.mkdir(parents=True,exist_ok=True)
for appid in ('1091500','990080','3357650','2842040','2840770'):
    try:
        url=f'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg'
        with urllib.request.urlopen(url,timeout=10) as response:data=response.read(8*1024**2)
        if not data.startswith((b'\xff\xd8',b'\x89PNG')):continue
        image=media/(appid+'.jpg');image.write_bytes(data)
        (media/(appid+'.json')).write_text(json.dumps({'poster':str(image),'art_credit':'Steam'}))
    except Exception as ex:print('Demo artwork unavailable:',appid,type(ex).__name__)
steps=[]
def capture(name):
    path=app.window.capture(name)
    assert path and path.is_file(),name
    report.append({'image':name,'mode':app.window.settings['ui_mode'],'game_writes':False})
def new_mode():
    app.window.set_ui_mode('new',persist=False)
    assert app.window._new_stack.get_child_by_name('library') is app.window._canonical_library
steps=[lambda:app.window.set_default_size(1280,820),lambda:capture('classic-library.png'),lambda:app.window.toggle_compact_header(),lambda:capture('classic-compact.png'),lambda:app.window.show_packages(),lambda:capture('classic-packages.png'),lambda:app.window.packages_dialog.close(),new_mode,lambda:capture('new-library.png'),lambda:app.window._new_stack.set_visible_child_name('home'),lambda:capture('new-home.png'),lambda:classic.show_packages(app.window,fixture),lambda:capture('new-custom-package.png'),lambda:app.window.packages_dialog.close(),lambda:app.window.set_ui_mode('classic',persist=False),lambda:capture('classic-restored.png')]
def run_step():
    try:
        if steps:
            steps.pop(0)();GLib.timeout_add(800,run_step)
        else:
            (ROOT/'dist/ui-package-review.json').write_text(json.dumps(report,indent=2));app.quit()
    except Exception:
        traceback.print_exc();app.exit_code=1;app.quit()
    return False
GLib.timeout_add(3000,run_step)
result=app.run([sys.argv[0]])
raise SystemExit(app.exit_code or result)
