#!/usr/bin/env python3
"""Qt/Kirigami frontend using the shared service. Explicit preview before writes."""
from pathlib import Path
import os,sys,json,threading
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from PySide6.QtCore import QObject,Property,Signal,Slot,QUrl,QTimer,Qt,QBuffer,QIODevice,qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon,QFontDatabase,QDesktopServices,QImage,QImageReader
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from frontend_session import FrontendSession,library_columns
import package_catalog,library_media

class Controller(QObject):
    changed=Signal();finished=Signal(object);failed=Signal(str);artReady=Signal(object)
    def __init__(self,demo=False):
        super().__init__();self.session=FrontendSession(demo);self._busy=False;self._message='';self._package={};self._review={};self._catalog=[];self._query='';self._filter='available';self._details={};self._executing=False;self._art_generation=0;self._steam_profiles=[]
        self.finished.connect(self.done);self.failed.connect(self.error);self.artReady.connect(self.art_done)
        if demo:
            self._steam_profiles=[{'root':'/preview/Steam','userid':'42','label':'Preview Steam account · 42'}]
            for name,appid in [('Cyberpunk 2077','1091500'),('Hogwarts Legacy','990080'),('Star Wars Outlaws','2842040'),('Avatar: Frontiers of Pandora','2840770')]:
                poster=ROOT/'dist/demo-media'/f'{appid}.jpg'
                self.session.games.append({'name':name,'game':'/preview/'+appid,'appid':appid,'installed':False,'poster':poster.as_uri() if poster.exists() else ''})
            self._catalog=package_catalog.catalog({'system':'Linux','architecture':'x86_64','ready':True})
        else:self.run(lambda:('scan',self.session.scan()))
    def run(self,fn):
        if self._busy:return
        self._busy=True;self.changed.emit()
        def work():
            try:self.finished.emit(fn())
            except Exception as ex:self.failed.emit(str(ex))
        threading.Thread(target=work,daemon=False).start()
    @Slot(object)
    def done(self,result):
        kind,value=result
        if kind=='scan':
            QTimer.singleShot(0,self.load_artwork)
        if kind=='inspect':self._package=value
        elif kind=='review':self._review=value
        elif kind=='catalog':self._catalog=value
        elif kind=='custom':
            values=value['parameters'];count=values.get('OverrideInterpolationCount','auto')
            self.session.preferences(runtime_provider='custom',custom_package=value,nr_strength=values.get('Intensity',2.0),sharpening_strength=values.get('Sharpness',0.5),mfg_multiplier='auto' if count=='auto' else 0 if count=='0' else int(count)+1)
            self._message='Custom package selected. Review installation for your selected games.'
        elif kind=='apply':self._message='Operation finished. Review the recorded result.';self._review={}
        elif kind=='steam-profiles':
            self._steam_profiles=[{**p,'label':'Steam account '+p['userid']+' · '+p['root']} for p in value]
            self._message='Choose the account whose Steam artwork should change.' if value else 'No Steam profiles found. Open Steam once, then refresh.'
        elif kind=='steam-artwork':
            for key in value['success']:self.session.settings.setdefault('steam_artwork_pending',{}).pop(key,None)
            library_media.save_settings(self.session.service.config,self.session.settings)
            self._message=('Some artwork remains pending: '+'; '.join(value['errors'])) if value['errors'] else 'Artwork synced to Steam. Restart Steam if its cached images have not refreshed.'
        elif kind=='artwork':
            self._message='Artwork saved. '+ ('Steam sync pending: '+value['error'] if value.get('error') else 'Steam artwork updated.')
            QTimer.singleShot(0,self.load_artwork)
        elif kind=='steam-self':
            self._message='rtxForge is in Steam. '+('; '.join(value['errors']) if value['errors'] else 'Its bundled artwork is applied; restart Steam to refresh.')
        self._busy=False;self._executing=False;self.changed.emit()
    @Slot(str)
    def error(self,text):self._busy=False;self._executing=False;self._message=text;self.changed.emit()
    def load_artwork(self):
        if self.session.demo:return
        self._art_generation+=1;generation=self._art_generation
        rows=[dict(g) for g in self.session.games]
        def work():
            media=library_media.LibraryMedia(self.session.service.config,self.session.settings)
            for row in rows:
                try:self.artReady.emit((row['game'],media.enrich(row),generation))
                except Exception:continue
        threading.Thread(target=work,daemon=False).start()
    @Slot(object)
    def art_done(self,value):
        key,media,generation=value
        if generation!=self._art_generation:return
        for game in self.session.games:
            if game['game']==key:
                for k,v in media.items():
                    game[k]=Path(v).as_uri() if k in ('poster','capsule','hero','logo') and v else v
                if self._details.get('game')==key:self._details=dict(game)
                break
        self.changed.emit()
    @Property('QVariantMap',notify=changed)
    def details(self):return self._details
    @Property(str,notify=changed)
    def layout(self):return self.session.settings.get('library_view','posters')
    @Property(str,constant=True)
    def brandIcon(self):return QUrl.fromLocalFile(str(ROOT/'gui/icons/rtxforge-mark.svg')).toString()
    @Property(str,notify=changed)
    def profile(self):return self.session.settings.get('default_profile','mfg-only')
    @Property(int,notify=changed)
    def density(self):return self.session.settings.get('library_columns',7)
    @Property(bool,notify=changed)
    def executing(self):return self._executing
    @Slot(str)
    def setLayout(self,value):
        if not self._busy and value in ('posters','capsules','list'):
            self.session.preferences(library_view=value);self._review={};self.changed.emit()
    @Slot(int)
    def setDensity(self,value):
        if not self._busy:self.session.preferences(library_columns=max(3,min(9,value)));self._review={};self.changed.emit()
    @Slot(str)
    def showDetails(self,key):
        self._details=next((dict(g) for g in self.session.games if g['game']==key),{})
        self.changed.emit()
    @Slot()
    def closeDetails(self):self._details={};self.changed.emit()
    @Slot(str,str)
    def prepareGame(self,key,operation):
        if operation not in ('install','repair','uninstall'):return
        self.run(lambda:('review',self.session.prepare(operation,targets=[key])))
    @Property(bool,constant=True)
    def demo(self):return self.session.demo
    @Property(str,notify=changed)
    def filter(self):return self._filter
    @Property(int,notify=changed)
    def configuredCount(self):return sum(bool(g.get('installed')) for g in self.session.games)
    @Property('QVariantList',notify=changed)
    def games(self):return [{**g,'selected':g['game'] in self.session.selected,'accent':self.session.settings.get('game_accents',{}).get(g['game'],'#76b900')} for g in self.session.games if self._query in g['name'].casefold() and (self._filter=='all' or (self._filter=='installed' and bool(g.get('installed'))) or (self._filter=='available' and not g.get('blocked')))]
    @Property('QVariantList',notify=changed)
    def packages(self):return self._catalog
    @Property('QVariantMap',notify=changed)
    def inspection(self):return self._package
    @Property('QVariantMap',notify=changed)
    def review(self):return self._review
    @Property(bool,notify=changed)
    def busy(self):return self._busy
    @Property(str,notify=changed)
    def message(self):return self._message
    @Property(str,notify=changed)
    def mode(self):return self.session.settings.get('ui_mode','classic')
    @Property(str,notify=changed)
    def startPage(self):return self.session.settings.get('start_page','library')
    @Property(int,notify=changed)
    def selectedCount(self):return len(self.session.selected)
    @Slot(str)
    def setQuery(self,value):self._query=value.casefold();self.changed.emit()
    @Slot(str)
    def setFilter(self,value):
        if value in ('all','installed','available'):self._filter=value;self.changed.emit()
    @Slot(str,str)
    def setPreference(self,key,value):
        if self._busy:return
        if key=='default_profile' and value in ('mfg-only','nr-only','nr-mfg'):
            self.session.preferences(default_profile=value);self._review={};self.changed.emit()
    @Slot()
    def cancelOperation(self):self.session.cancel()
    @Slot(bool)
    def selectAll(self,active):
        if self._busy:return
        for game in self.games:self.session.select(game['game'],active)
        self._review={};self.changed.emit()
    @Slot(str,bool)
    def useCustom(self,values,trusted):
        try:parsed=json.loads(values)
        except ValueError:self.error('Invalid custom settings.');return
        self.run(lambda:('custom',package_catalog.custom_record(self._package,parsed,trusted)))
    @Slot(str,bool)
    def select(self,key,active):
        if self._busy:return
        try:self.session.select(key,active);self._review={};self.changed.emit()
        except Exception as ex:self.error(str(ex))
    def game_row(self,key):
        row=next((dict(g) for g in self.session.games if g['game']==key),None)
        if row is None:raise ValueError('Refresh the library and select this game again.')
        for role in ('poster','capsule','hero','logo'):
            value=row.get(role)
            if isinstance(value,str) and value.startswith('file:'):row[role]=QUrl(value).toLocalFile()
        return row
    @Property('QVariantList',notify=changed)
    def steamProfiles(self):return self._steam_profiles
    @Property(int,notify=changed)
    def steamProfileIndex(self):
        selected=self.session.settings.get('steam_artwork_profile')
        if not selected:return 0
        return next((i+1 for i,p in enumerate(self._steam_profiles) if p['root']==selected.get('root') and p['userid']==str(selected.get('userid'))),-1)
    @Slot()
    def refreshSteamProfiles(self):
        if self.session.demo:self.changed.emit();return
        import steam_artwork
        self.run(lambda:('steam-profiles',steam_artwork.profiles(self.session.service.config)))
    @Slot(int)
    def setSteamProfile(self,index):
        if self._busy:return
        if not 0<=index<=len(self._steam_profiles):self.error('Refresh the Steam account list and choose again.');return
        selected=None if index==0 else {key:self._steam_profiles[index-1][key] for key in ('root','userid')}
        try:self.session.preferences(steam_artwork_profile=selected)
        except Exception as ex:self.error(str(ex));return
        self._message='Steam artwork account selected.' if selected else 'Steam account selection is automatic only when unambiguous.'
        self.changed.emit()

    @Slot(str)
    def playGame(self,key):
        if self.session.demo:return
        import game_launch
        try:
            uri=game_launch.resolve(self.session.service.config,self.game_row(key))
            if not QDesktopServices.openUrl(QUrl(uri)):raise ValueError('Steam could not be opened.')
        except Exception as ex:self.error(str(ex))
    @Slot(str)
    def syncArtwork(self,key):
        if self._busy:return
        if self.session.demo:self.error('Artwork writes are disabled in preview mode.');return
        import steam_artwork
        targets=[self.game_row(key)] if key else [self.game_row(g['game']) for g in self.session.games]
        def work():
            result={'success':[],'errors':[]}
            for game in targets:
                if not (self.session.settings.get('game_artwork',{}).get(game['game']) or self.session.settings.get('steam_artwork_pending',{}).get(game['game']) or any(game.get(r) for r in steam_artwork.SUFFIX)):continue
                try:
                    pending=self.session.settings.get('steam_artwork_pending',{}).get(game['game'],{})
                    steam_artwork.sync_game(self.session.service.config,self.session.settings,game,reset_roles=[r for r,v in pending.items() if v=='reset'],include_displayed=True)
                    result['success'].append(game['game'])
                except Exception as ex:result['errors'].append(game['name']+': '+str(ex))
            return 'steam-artwork',result
        self._executing=True;self.run(work)
    @Slot(str,str,str)
    def chooseArtwork(self,key,role,url):
        if self._busy:return
        if self.session.demo:return
        import artwork_overrides,steam_artwork
        try:game=self.game_row(key);path=QUrl(url).toLocalFile()
        except Exception as ex:self.error(str(ex));return
        def work():
            source=Path(path)
            if source.stat().st_size>artwork_overrides.MAX_BYTES:raise ValueError('Choose an image smaller than 20 MB.')
            data=source.read_bytes()
            def dimensions(raw):
                buffer=QBuffer();buffer.setData(raw);buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                reader=QImageReader(buffer);size=reader.size()
                if size.width()<=0 or size.height()<=0 or size.width()*size.height()>40_000_000:raise ValueError('Choose an image smaller than 40 megapixels.')
                image=QImage.fromData(raw)
                if image.isNull():raise ValueError('Choose a readable PNG or JPEG image.')
                return image.width(),image.height()
            artwork_overrides.store(self.session.service.config,self.session.settings,game,role,data,validate=dimensions)
            error=''
            try:
                steam_artwork.sync_game(self.session.service.config,self.session.settings,game,roles=[role])
                self.session.settings.get('steam_artwork_pending',{}).get(key,{}).pop(role,None)
                library_media.save_settings(self.session.service.config,self.session.settings)
            except Exception as ex:error=str(ex)
            return 'artwork',{'error':error}
        self._executing=True;self.run(work)
    @Slot(str,str)
    def resetArtwork(self,key,role):
        if self._busy:return
        if self.session.demo:return
        import artwork_overrides,steam_artwork
        try:game=self.game_row(key)
        except Exception as ex:self.error(str(ex));return
        def work():
            artwork_overrides.reset(self.session.service.config,self.session.settings,game,role)
            error=''
            try:
                steam_artwork.sync_game(self.session.service.config,self.session.settings,game,roles=[role],reset_roles=[role])
                self.session.settings.get('steam_artwork_pending',{}).get(key,{}).pop(role,None)
                library_media.save_settings(self.session.service.config,self.session.settings)
            except Exception as ex:error=str(ex)
            return 'artwork',{'error':error}
        self._executing=True;self.run(work)
    @Slot()
    def addToSteam(self):
        if self._busy:return
        if self.session.demo:return
        import steam_self_install
        self._executing=True;self.run(lambda:('steam-self',steam_self_install.install(self.session.service.config,self.session.settings)))

    @Slot(str)
    def setMode(self,value):
        if value not in ('classic','new') or self._busy:return
        self.session.preferences(ui_mode=value);self._review={};self.changed.emit()
    @Slot(str)
    def setStart(self,value):
        if self._busy:return
        if value not in ('home','library') or self._busy:return
        self.session.preferences(start_page=value);self._review={};self.changed.emit()
    @Slot(int,result=int)
    def columns(self,width):return library_columns(width,self.session.settings.get('library_columns',7),self.session.settings.get('library_view','posters'))
    @Slot(str)
    def prepare(self,operation):
        if operation not in ('install','repair','uninstall'):return
        self.run(lambda:('review',self.session.prepare(operation)))
    @Slot()
    def cancelReview(self):
        self._review={};self.session.review=None;self.changed.emit()
    @Slot()
    def apply(self):
        if self._busy:return
        self._executing=True
        self.run(lambda:('apply',self.session.apply(self._review.get('revision',-1))))
    @Slot()
    def catalog(self):
        if not self.session.demo:self.run(lambda:('catalog',package_catalog.catalog(self.session.service.hardware())))
    @Slot(str)
    def inspect(self,url):
        path=QUrl(url).toLocalFile();self.run(lambda:('inspect',package_catalog.inspect_archive(path)))
    @Slot(str)
    def usePackage(self,key):
        if self._busy:return
        if not any(p['id']==key and p['available'] for p in self._catalog):return
        self.session.preferences(runtime_provider=key);self._message='Package selected. Select games and review installation.';self.changed.emit()

def main():
    smoke='--smoke-test' in sys.argv
    demo='--demo' in sys.argv or smoke
    if smoke:
        qInstallMessageHandler(lambda kind,context,message:print('QT_DIAGNOSTIC:',message,file=sys.stderr,flush=True))
        print('QT_BOOTSTRAP: starting native application',flush=True)
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','org.kde.desktop')
    if '--smoke-test' in sys.argv:
        from demo_assets import prepare
        prepare(ROOT)
    # qqc2-desktop-style derives native controls from the application QStyle.
    app=QApplication(sys.argv)
    # QWidget's Breeze style is not a QML module called 'Breeze'. Select the
    # actual qqc2 desktop module explicitly before constructing the QML engine.
    QQuickStyle.setStyle(os.environ.get('QT_QUICK_CONTROLS_STYLE','org.kde.desktop'))
    if smoke:print('QT_BOOTSTRAP: application style='+app.style().objectName()+'; quick style='+QQuickStyle.name(),flush=True)
    app.setApplicationName('rtxForge');app.setDesktopFileName('io.github.lrnolivia.RTXForge')
    app.setWindowIcon(QIcon(str(ROOT/'gui/icons/hicolor/scalable/apps/io.github.lrnolivia.RTXForge.svg')))
    engine=QQmlApplicationEngine();controller=Controller(demo)
    if smoke:engine.warnings.connect(lambda errors:print('QML_WARNINGS:',[error.toString() for error in errors],file=sys.stderr,flush=True))
    # KDE owns control colors and neutral surfaces; never copy Adwaita grays here.
    QFontDatabase.addApplicationFont(str(ROOT/'gui/fonts/BakbakOne-Regular.ttf'))
    def update_launcher_theme(*_):
        import desktop_install
        dark=app.palette().window().color().lightnessF()<0.5
        name='io.github.lrnolivia.RTXForge'+('' if dark else '-light')
        app.setWindowIcon(QIcon(str(ROOT/'gui/icons/hicolor/scalable/apps'/(name+'.svg'))))
        if not demo:
            try:desktop_install.refresh_launcher_icon(dark)
            except (OSError,ValueError,RuntimeError):pass
    app.paletteChanged.connect(update_launcher_theme);update_launcher_theme()
    engine.rootContext().setContextProperty('forge',controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('Main.qml'))))
    if not engine.rootObjects():
        print('QT_BOOTSTRAP: Main.qml produced no root window',file=sys.stderr,flush=True);return 1
    if smoke:print('QT_BOOTSTRAP: root window loaded',flush=True)
    if '--smoke-test' in sys.argv:
        if os.environ.get('QT_STYLE_OVERRIDE','').casefold()=='breeze':
            assert 'breeze' in app.style().objectName().casefold(), 'Native Breeze style was not loaded'
        window=engine.rootObjects()[0];out=ROOT/'dist';out.mkdir(exist_ok=True)
        report=[]
        def capture(name, expected_page='library'):
            assert window.property('page') == expected_page, 'Wrong page for '+name+': '+str(window.property('page'))
            if not window.grabWindow().save(str(out/name)):raise RuntimeError('Capture failed: '+name)
            report.append(name)
        def review_profiles():
            controller.setSteamProfile(1)
            assert controller.steamProfileIndex==1 and controller.session.settings['steam_artwork_profile']['userid']=='42'
            controller.setSteamProfile(0)
            assert controller.steamProfileIndex==0 and controller.session.settings['steam_artwork_profile'] is None
        steps=[review_profiles,lambda:controller.setMode('classic'),lambda:capture('kde-classic.png'),
               lambda:controller.setMode('new'),lambda:capture('kde-new.png'),
               lambda:controller.setLayout('capsules'),lambda:capture('kde-wide.png'),
               lambda:controller.setLayout('list'),lambda:capture('kde-list.png'),
               lambda:window.setProperty('page','settings'),lambda:capture('kde-settings.png', 'settings'),
               lambda:window.setProperty('page','recovery'),lambda:capture('kde-recovery.png', 'recovery'),
               lambda:window.setProperty('page','packages'),lambda:capture('kde-packages.png', 'packages'),
               lambda:window.setProperty('page','library'),lambda:controller.setMode('classic'),
               lambda:window.resize(800,600),lambda:controller.setLayout('posters'),lambda:capture('kde-classic-800.png'),
               lambda:controller.setLayout('list'),lambda:capture('kde-list-800.png')]
        def advance():
            try:
                if steps:
                    steps.pop(0)();QTimer.singleShot(700,advance)
                else:
                    (out/'kde-review.json').write_text(json.dumps({'game_writes':False,'captures':report,'widget_style':app.style().objectName()}))
                    app.quit()
            except Exception as ex:
                print('Qt review failed:',ex,file=sys.stderr);app.exit(1)
        QTimer.singleShot(1000,advance)
    return app.exec()
if __name__=='__main__':raise SystemExit(main())
