#!/usr/bin/env python3
"""Qt/Kirigami frontend using the shared service. Explicit preview before writes."""
from pathlib import Path
import os,sys,json,threading
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from PySide6.QtCore import QObject,Property,Signal,Slot,QUrl,QTimer,Qt
from PySide6.QtGui import QGuiApplication,QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from frontend_session import FrontendSession,library_columns
import package_catalog

class Controller(QObject):
    changed=Signal();finished=Signal(object);failed=Signal(str)
    def __init__(self,demo=False):
        super().__init__();self.session=FrontendSession(demo);self._busy=False;self._message='';self._package={};self._review={};self._catalog=[];self._query='';self._filter='all'
        self.finished.connect(self.done);self.failed.connect(self.error)
        if demo:
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
        threading.Thread(target=work,daemon=True).start()
    @Slot(object)
    def done(self,result):
        kind,value=result
        if kind=='inspect':self._package=value
        elif kind=='review':self._review=value
        elif kind=='catalog':self._catalog=value
        elif kind=='custom':
            values=value['parameters'];count=values.get('OverrideInterpolationCount','auto')
            self.session.preferences(runtime_provider='custom',custom_package=value,nr_strength=values.get('Intensity',2.0),sharpening_strength=values.get('Sharpness',0.5),mfg_multiplier='auto' if count=='auto' else 0 if count=='0' else int(count)+1)
            self._message='Custom package selected. Review installation for your selected games.'
        elif kind=='apply':self._message='Operation finished. Review the recorded result.';self._review={}
        self._busy=False;self.changed.emit()
    @Slot(str)
    def error(self,text):self._busy=False;self._message=text;self.changed.emit()
    @Property('QVariantList',notify=changed)
    def games(self):return [{**g,'selected':g['game'] in self.session.selected} for g in self.session.games if self._query in g['name'].casefold() and (self._filter=='all' or bool(g.get('installed'))==(self._filter=='installed'))]
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
        if key=='default_profile' and value in ('mfg-only','nr-only','nr-mfg'):
            self.session.preferences(default_profile=value);self.changed.emit()
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
    @Slot(str)
    def setMode(self,value):
        if value not in ('classic','new') or self._busy:return
        self.session.preferences(ui_mode=value);self.changed.emit()
    @Slot(str)
    def setStart(self,value):
        if value not in ('home','library') or self._busy:return
        self.session.preferences(start_page=value);self.changed.emit()
    @Slot(int,result=int)
    def columns(self,width):return library_columns(width,self.session.settings.get('library_columns',7))
    @Slot(str)
    def prepare(self,operation):
        if operation not in ('install','repair','uninstall'):return
        self.run(lambda:('review',self.session.prepare(operation)))
    @Slot()
    def cancelReview(self):
        self._review={};self.session.review=None;self.changed.emit()
    @Slot()
    def apply(self):self.run(lambda:('apply',self.session.apply(self._review.get('revision',-1))))
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
    demo='--demo' in sys.argv or '--smoke-test' in sys.argv
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE','org.kde.desktop')
    if '--smoke-test' in sys.argv:
        from demo_assets import prepare
        prepare(ROOT)
    app=QGuiApplication(sys.argv)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setApplicationName('rtxForge');app.setDesktopFileName('io.github.lrnolivia.RTXForge')
    app.setWindowIcon(QIcon(str(ROOT/'gui/icons/hicolor/256x256/apps/io.github.lrnolivia.RTXForge.png')))
    engine=QQmlApplicationEngine();controller=Controller(demo)
    engine.rootContext().setContextProperty('forge',controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('Main.qml'))))
    if not engine.rootObjects():return 1
    if '--smoke-test' in sys.argv:
        window=engine.rootObjects()[0];out=ROOT/'dist';out.mkdir(exist_ok=True)
        def classic():
            controller.setMode('classic');window.setProperty('page','library')
            QTimer.singleShot(700,lambda:(window.grabWindow().save(str(out/'kde-classic.png')),controller.setMode('new'),QTimer.singleShot(700,new)))
        def new():
            window.grabWindow().save(str(out/'kde-new.png'));window.setProperty('page','packages')
            QTimer.singleShot(700,lambda:(window.grabWindow().save(str(out/'kde-packages.png')),app.quit()))
        QTimer.singleShot(1000,classic)
    return app.exec()
if __name__=='__main__':raise SystemExit(main())
