"""Toolkit-free desktop operations. A UI owns selection and review; writes stay explicit."""
from pathlib import Path
import rtxforge as app
import discovery,planning,packages,profiles,cleanup,transactions as t
import re,datetime,hardware,engine_bridge,library_media
from storage import storage

class DesktopService:
    def __init__(self,provider=None):
        self.config=app.load_provider(provider)

    def hardware(self):return hardware.detect()

    def libraries(self):
        return sorted(discovery.candidate_libraries(),key=discovery.count_manifests,reverse=True)

    def scan(self,library,extra=()):
        found=discovery.discover_games(Path(library),discovery.discover_nonsteam_roots(Path(library),[]),include_unavailable=True) if library else []
        for path in extra:
            p=Path(path).resolve()
            g=discovery.inspect_game(discovery.Game('',p.name,str(p),'Folder'))
            if g.exe:found.append(g)
        engine=engine_bridge.module(self.config)
        rows=[];seen=set()
        for g in found:
            root=Path(g.root).resolve()
            if str(root) in seen:continue
            seen.add(str(root))
            native=any(Path(p).name.lower() in ('nvngx_dlssg.dll','sl.dlss_g.dll') and 'optiscaler' not in [q.lower() for q in Path(p).relative_to(g.root).parts] for p in g.upscalers)
            reason='No Windows executable found' if not g.exe else 'Anti-cheat detected' if g.anti_cheat else 'No native DLSS-G detected' if not native else ''
            exe=Path(g.exe).relative_to(g.root).as_posix() if g.exe else ''
            config=Path(g.exe).parent/'OptiScaler.ini' if g.exe else root/'OptiScaler.ini'
            ini=discovery.get_ini_values_all(config)
            installed=config.is_file()
            fg=ini.get('FrameGen',{}) if installed else {}
            fg_input=fg.get('FGInput','').lower();replacement=fg.get('FGNvngxReplacement','').lower()
            if fg_input=='dlssg' and replacement in ('','auto','none'):mfg_route='Native Streamline DLSS-G'
            elif fg_input=='nvngxfg' and replacement=='arturs':mfg_route='Enabler compatibility'
            elif installed:mfg_route='Custom / legacy FG route'
            else:mfg_route='Not installed'
            row={'name':g.name,'game':str(root),'exe':exe,'source':g.type,'blocked':reason,'appid':g.appid,
                 'library':str(library or root.parent),'installed':installed,'mfg_route':mfg_route,
                 'profile':('NR + MFG' if ini.get('DlssNr',{}).get('Enabled','false').lower()=='true' else 'MFG Only') if installed else 'Not installed'}
            if installed:
                nr_values=ini.get('DlssNr',{});sharp_values=ini.get('Sharpness',{})

                try:
                    intensity=float(nr_values.get('Intensity',''))
                    skin=float(nr_values.get('SkinStructure',''))
                    row['nr_strength']=(
                        0.0
                        if nr_values.get('Enabled','').lower()=='false'
                        else round(intensity,1)
                        if 0.0<=intensity<=2.0 and abs(intensity-skin)<0.00001
                        else None
                    )
                except (TypeError,ValueError):
                    row['nr_strength']=None

                try:
                    sharp=float(sharp_values.get('Sharpness',''))
                    row['sharpening_strength']=round(sharp,1) if 0.0<=sharp<=1.0 else None
                except (TypeError,ValueError):
                    row['sharpening_strength']=None
                try:
                    count=int(ini.get('DLSSG',{}).get('OverrideInterpolationCount','auto'))
                    row['mfg_multiplier']=0 if count==0 else count+1 if count in range(1,6) else None
                except ValueError:row['mfg_multiplier']=None
                try:
                    baseline=engine.load_baseline(config.parent)
                    current=(baseline or {}).get('current') or {}
                    if current.get('feature_mode'):
                        row['feature_mode']=current['feature_mode']
                        row['profile']={'nr-mfg':'NR + MFG','nr-only':'NR Only','mfg-only':'MFG Only'}.get(current['feature_mode'],'Unknown')
                        row['runtime_provider']=current.get('provider_id','y4my')
                        row['effects_enabled']=ini.get('DLSSG',{}).get('AdaMfgUnlock','false').lower()=='true'
                except (engine.Stop,OSError,ValueError):pass
            if g.manifest:
                try:
                    text=Path(g.manifest).read_text()
                    for key,out in [('SizeOnDisk','size_bytes'),('LastUpdated','updated')]:
                        match=re.search(r'"'+key+r'"\s+"(\d+)"',text)
                        if match:row[out]=int(match[1])
                except OSError:pass
            rows.append(row)
        return sorted(rows,key=lambda r:r['name'].casefold())

    def scan_all(self,extra=()):
        import ui
        rows=[];seen=set();libraries=self.libraries()
        for index,library in enumerate(libraries):
            for row in ui.work(f'Scanning library {index+1}/{len(libraries)}',self.scan,library):
                if row['game'] not in seen:rows.append(row);seen.add(row['game'])
        for row in self.scan(None,extra):
            if row['game'] not in seen:rows.append(row);seen.add(row['game'])
        return sorted(rows,key=lambda r:r['name'].casefold())

    def prepare(self,rows,mode,operation,adopt=False,visual_settings=None,save_defaults=False):
        import ui
        if operation in ('install','repair'):
            host=self.hardware()
            if not host['ready']:return {'kind':'batch','operation':operation,'title':operation.title(),'plans':[],'rows':[],'blocked':[{'name':'Hardware check','reason':host['reason']}]}
        settings=library_media.load_settings(self.config)
        if visual_settings is not None:settings.update(visual_settings)
        review=engine_bridge.prepare(self.config,rows,mode,operation,settings)
        if save_defaults and operation=='reset':review['save_defaults']={k:settings[k] for k in ('nr_strength','sharpening_strength','mfg_multiplier')}
        return review

    def save_visual_defaults(self,values):
        nr=values.get('nr_strength')
        sharp=values.get('sharpening_strength')

        t.need(
            type(nr) in (int,float) and not isinstance(nr,bool) and 0.0<=float(nr)<=2.0,
            'NR strength must be between 0.0 and 2.0',
        )
        t.need(
            type(sharp) in (int,float) and not isinstance(sharp,bool) and 0.0<=float(sharp)<=1.0,
            'Sharpening strength must be between 0.0 and 1.0',
        )
        t.need(
            type(values.get('mfg_multiplier')) is int and
            values['mfg_multiplier'] in (0,2,3,4,5,6),
            'Invalid MFG multiplier',
        )

        settings=library_media.load_settings(self.config)
        settings.update(
            nr_strength=round(float(nr),1),
            sharpening_strength=round(float(sharp),1),
            mfg_multiplier=values['mfg_multiplier'],
        )
        library_media.save_settings(self.config,settings)

    def recoveries(self):
        root=storage(self.config);rows=[]
        for path in sorted((root/'batches').glob('*/batch.json'),reverse=True):
            doc=t.read_json(path)
            if doc['status']!='rolled-back':rows.append({'kind':'rollback','path':str(path),'name':'Batch '+path.parent.name,'detail':doc['status']})
        for path in sorted((root/'cleanup').glob('*/cleanup.json'),reverse=True):
            doc=t.read_json(path)
            if doc['status'] in ('complete','removing','interrupted'):rows.append({'kind':'restore-cleanup','path':str(path),'name':'Cleanup '+path.parent.name,'detail':doc['status']})
        return rows

    def review_recovery(self,row):
        root=storage(self.config);path=t.safe(row['path']);details=[]
        if row['kind']=='rollback':
            t.need(path.is_relative_to(root/'batches'),'Invalid batch record')
            doc=t.read_json(path);t.need(doc['status']!='rolled-back','Already restored')
            for value in reversed(doc['transactions']):
                state=t.safe(value);t.need(state.is_relative_to(root/'transactions'),'Invalid transaction path')
                if not (state/'transaction.json').exists():continue
                if t.read_json(state/'transaction.json')['status'] in ('preparing','rolled-back'):continue
                view=t.rollback_transaction(state);details.append({'name':Path(view['game']).name,'detail':str(len(view['files']))+' files to restore'})
        else:details=[{'name':'Cleanup recovery','detail':str(cleanup.restore(self.config,path))+' files to restore'}]
        return {'kind':row['kind'],'path':str(path),'title':'Restore recorded changes','rows':details,'blocked':[]}

    def review_cleanup(self):
        items=cleanup.discover([Path(self.config['storage']['mount'])],self.config)
        return {'kind':'cleanup','title':'Global DLSS5 cleanup','items':items,'blocked':[],
                'rows':[{'name':Path(r['path']).name,'detail':r['path']} for r in items]}

    def execute(self,review):
        # The desktop must pass the exact in-memory review shown to the user.
        kind=review['kind']
        if kind=='engine':
            result=engine_bridge.execute(review)
            if review.get('save_defaults'):self.save_visual_defaults(review['save_defaults'])
            return result
        if kind=='batch':return str(app.apply_batch(self.config,review['plans']))
        if kind=='cleanup':return str(cleanup.apply(self.config,review['items']))
        if kind=='restore-cleanup':cleanup.restore(self.config,Path(review['path']),True);return review['path']
        t.need(kind=='rollback','Unknown action')
        args=app.parser().parse_args(['rollback','--batch',review['path'],'--apply','--confirm','ROLLBACK'])
        app.rollback(args,self.config);return review['path']


def friendly(message):
    return (message.replace('No ownership record; no broad cleanup is performed','No install record found. RTXForge cannot safely identify which files to remove.')
            .replace('Competing/unowned graphics file:','Another graphics tool uses:')
            .replace('Unowned replacement:','An existing file needs identification:')
            .replace('Owned binary drift:','An installed file changed:')
            .replace('Changed owned file:','An installed file changed:')
            .replace('provide manifest or explicitly adopt recognized files','enable “Recognize previous installs” in Settings if this is OptiScaler'))
