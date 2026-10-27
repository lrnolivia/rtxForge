"""Toolkit-free desktop operations. A UI owns selection and review; writes stay explicit."""
from pathlib import Path
import rtxforge as app
import discovery,planning,packages,profiles,cleanup,transactions as t
import re,datetime,hardware,engine_bridge,library_media,cross_os,proton_prefix,operation_session
from types import SimpleNamespace
from storage import storage

UNREADABLE_RECORD=('This game was set up with rtxForge on another system, but its files are not readable here '
                   '(owned by another user). Make them yours, then refresh: sudo chown -R "$USER" "{folder}"')

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
            row['native_dlss']=any(Path(p).name.lower()=='nvngx_dlss.dll' and 'optiscaler' not in [q.lower() for q in Path(p).relative_to(g.root).parts] for p in g.upscalers)
            row['anti_cheat']=bool(g.anti_cheat)
            row['native_dlssg']=native
            if installed:
                nr_values=ini.get('DlssNr',{});sharp_values=ini.get('Sharpness',{})
                row['nr_enabled']=nr_values.get('Enabled','false').split(';',1)[0].strip().lower()=='true'

                try:
                    intensity=float(nr_values.get('Intensity','').split(';',1)[0].strip())
                    skin=float(nr_values.get('SkinStructure','').split(';',1)[0].strip())
                    row['nr_strength']=(
                        round(intensity,1)
                        if 0.0<=intensity<=2.0 and abs(intensity-skin)<0.00001
                        else None
                    )
                except (TypeError,ValueError):
                    row['nr_strength']=None

                try:
                    sharp=float(sharp_values.get('Sharpness','').split(';',1)[0].strip())
                    row['sharpening_strength']=round(sharp,1) if 0.0<=sharp<=1.0 else None
                except (TypeError,ValueError):
                    row['sharpening_strength']=None
                try:
                    raw=ini.get('DLSSG',{}).get('OverrideInterpolationCount','auto').split(';',1)[0].strip()
                    count=int(raw) if raw.lower() != 'auto' else None
                    row['mfg_multiplier']='auto' if count is None else 0 if count==0 else count+1 if count in range(1,6) else None
                except ValueError:row['mfg_multiplier']=None
                # The shared MFG preset replays from the INI: Dynamic plus the dormant saved choice.
                try:
                    force=ini.get('DLSSG',{}).get('OverrideForceDMFG','false').split(';',1)[0].strip().lower()
                    row['dynamic_mfg']=1 if force in ('true','1') else 0
                    saved=ini.get('rtxForge.Presets',{})
                    mode=int(saved.get('MfgMode','').split(';',1)[0].strip() or -1)
                    ratio=int(saved.get('MfgMultiplier','').split(';',1)[0].strip() or -1)
                    if mode in (0,1,2):row['mfg_saved_mode']=mode
                    if ratio in range(2,7):row['mfg_saved_multiplier']=ratio
                except (ValueError,AttributeError):pass
                try:
                    baseline=engine.load_baseline(config.parent)
                    current=(baseline or {}).get('current') or {}
                    if current.get('feature_mode'):
                        row['feature_mode']=current['feature_mode']
                        row['profile']={'nr-mfg':'NR + MFG','nr-only':'NR Only','mfg-only':'MFG Only'}.get(current['feature_mode'],'Unknown')
                        row['runtime_provider']=current.get('provider_id','y4my')
                        if row['runtime_provider']=='skynizz':
                            import skynizz_provider
                            row['feature_controls']=skynizz_provider.read_controls(config)
                        component=((current.get('archive') or {}).get('release') or {}).get('mfg_component')
                        universal=bool(component) and component.get('id')=='universal'
                        row['dynamic_mfg_available']=current.get('provider_id')=='skynizz' and not component
                        if universal:
                            # Only where the plugin has seen the game's DLSS-G report Dynamic support.
                            import universal_mfg_provider
                            support=universal_mfg_provider.dynamic_support(config.parent)
                            row['dynamic_mfg_available']=support is True
                            row['dynamic_mfg_detail']=('' if support else 'Not supported by this game' if support is False
                                                       else 'Launch the game once to check Dynamic support')
                        row['effects_enabled']=ini.get('DLSSG',{}).get('AdaMfgUnlock','false').lower()=='true'
                        if universal:
                            row['effects_enabled']=ini.get('Plugins',{}).get('LoadAsiPlugins','false').split(';',1)[0].strip().lower()=='true'
                            row['mfg_route']='Native DLSS-G · Universal MFG '+component.get('version','')
                        elif component:
                            import ada_mfg_provider
                            try:
                                row.update(ada_mfg_provider.configured_state(config.parent,component))
                                row['effects_enabled']=row['nr_enabled'] or row['mfg_enabled']
                            except (t.Refusal,ValueError,OSError):
                                row['mfg_multiplier']=None
                except (engine.Stop,OSError,ValueError):pass
            if g.manifest:
                try:
                    text=Path(g.manifest).read_text()
                    for key,out in [('SizeOnDisk','size_bytes'),('LastUpdated','updated')]:
                        match=re.search(r'"'+key+r'"\s+"(\d+)"',text)
                        if match:row[out]=int(match[1])
                except OSError:pass
            # Which rtxForge installed these features (shared record in the game folder).
            target=Path(g.exe).parent if g.exe else root
            record=cross_os.read(target)
            row['installed_on']=record['os'] if record else (cross_os.THIS_OS if installed else None)
            if not record and cross_os.unreadable(target):
                # Written by the other OS with permissions this user cannot read. Never offer
                # Adoption over it; the game cannot read those files under Proton either.
                row.update(installed=True,installed_on=None,record_unreadable=True,
                           blocked=UNREADABLE_RECORD.format(folder=target))
            if record and record['os']!=cross_os.THIS_OS:
                # Set Up (adapt) takes the other OS's install over instead of reinstalling it.
                try:local=engine.load_baseline(target)
                except (engine.Stop,OSError,ValueError):local=None
                row['adaptable']=bool(cross_os.adoptable(target,cross_os.THIS_OS,(local or {}).get('cross_os_revision')))
            if record and record['os']=='windows' and cross_os.THIS_OS=='linux':
                row['linux_ready']=bool(proton_prefix.load_record(engine_bridge.prefix_state(engine,SimpleNamespace(target_dir=target))))
            rows.append(row)
        settings=library_media.load_settings(self.config)
        # Feeder NR installs (and Mass Effect LE's three games) are recognised the same way as on Windows.
        import feeder_provider
        rows=feeder_provider.expand_rows(engine,rows,selected=settings.get('runtime_provider')=='feeder')
        import package_adoption
        package_adoption.decorate(engine,rows)
        import vulkan_app
        vulkan_app.decorate(rows,self.config,selected=settings.get('runtime_provider')=='vulkan-native')
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

    def prepare(self,rows,mode,operation,adopt=False,visual_settings=None,save_defaults=False,scope=None):
        import ui
        # Every route (engine, Feeder, Adoption) acts only on the reviewed games:
        # an empty or stale selection refuses instead of widening to the library.
        # Saving library defaults with no games selected changes no game.
        defaults_only=rows==[] and operation=='reset' and bool(save_defaults) and scope is None
        if not defaults_only:engine_bridge.check_scope(rows,scope)
        if operation in ('install','repair','adopt-clean'):
            host=self.hardware()
            if not host['ready']:return {'kind':'batch','operation':operation,'title':operation.title(),'plans':[],'rows':[],'blocked':[{'name':'Hardware check','reason':host['reason']}]}
        settings=library_media.load_settings(self.config)
        if visual_settings is not None:settings.update(visual_settings)
        if scope is not None:settings['operation_scope']=scope
        settings['defaults_only']=defaults_only
        if operation in ('adopt', 'adopt-clean'):
            import package_adoption
            return package_adoption.prepare(self.config, rows, operation, settings)
        settings['apply_requested_presets']=operation=='install' and visual_settings is not None
        # Confirmed Vulkan games use the Vulkan package automatically, as Feeder games use Feeder NR.
        # It always brings frame generation, so NR Only keeps the DLSS package's own route.
        if settings.get('runtime_provider')=='vulkan-native' or (rows and all(row.get('runtime_provider')=='vulkan-native'
                or mode in ('nr-mfg','mfg-only') and row.get('install_provider')=='vulkan-native' and row.get('vulkan_available') is True for row in rows)):
            import vulkan_app
            return vulkan_app.prepare(self.config,rows,mode,operation,settings,engine_bridge.module(self.config))
        feeder = settings.get('runtime_provider') == 'feeder'
        # Restoring an installed Feeder setup must use its actual ownership,
        # regardless of the package currently selected for new installations.
        if feeder or (rows and all(row.get('runtime_provider') == 'feeder'
                                  or row.get('install_provider') == 'feeder' and row.get('feeder_available') is True for row in rows)
                      and operation in ('install', 'uninstall', 'repair', 'reset')):
            import feeder_provider
            return feeder_provider.prepare(self.config, rows, 'nr-only' if not feeder and mode != 'mfg-only' else mode, operation,
                                           settings, engine_bridge.module(self.config))
        review=engine_bridge.prepare(self.config,rows,mode,operation,settings)
        if save_defaults and operation=='reset':review['save_defaults']={k:settings[k] for k in ('nr_strength','sharpening_strength','mfg_multiplier','dynamic_mfg','mfg_saved_mode','mfg_saved_multiplier','feature_controls') if k in settings}
        return review

    # Second-review offers when a game supports only part of NR + MFG (reason code -> user text).
    SUBSET_REASONS={
        'feeder-nr-only':'Feeder provides neural rendering. Frame generation is unavailable for this route.',
        'no-native-dlssg':'Use DirectX 12 and enable DLSS in the game for NR. Native frame generation is unavailable.',
        'nr-runtime-unavailable':'Frame generation is supported. Neural rendering could not be prepared with the selected NR runtime.',
    }

    def prepare_supported(self,rows,mode,operation,adopt=False,visual_settings=None,scope=None):
        """The requested review plus separate, opt-in reviews for games that support only NR or only MFG.

        Mirrors the Windows rule (EngineForgeService.PrepareCoreAsync). Hard
        blockers (anti-cheat, no executable) are never offered. Each offer is
        its own review over exactly its games, so applying it needs an explicit
        choice and its own scope; nothing is merged into the main review.
        """
        review=self.prepare(rows,mode,operation,adopt,visual_settings=visual_settings,scope=scope)
        review['supported']=[]
        if operation!='install' or mode not in ('nr-mfg','nr-only'):return review
        settings=dict(library_media.load_settings(self.config),**(visual_settings or {}))
        skynizz=settings.get('runtime_provider')=='skynizz'
        planned=lambda result:{(p.get('row') or {}).get('game') for p in result.get('plans',[])}-{None}
        ready=planned(review)
        feeder=lambda r:r.get('runtime_provider')=='feeder' or r.get('install_provider')=='feeder' and r.get('feeder_available') is True
        candidates=[r for r in rows if r.get('game') not in ready and not r.get('anti_cheat') and r.get('exe')]
        blocked={b.get('name'):b.get('reason','') for b in review.get('blocked',[])}
        groups=[('feeder-nr-only','nr-only',[r for r in candidates if feeder(r)])]
        if mode=='nr-mfg' and skynizz:
            groups.append(('no-native-dlssg','nr-only',[r for r in candidates if not feeder(r) and r.get('native_dlss') and not r.get('native_dlssg')]))
            nr_missing=lambda reason:any(word in reason.casefold() for word in ('nr runtime','nr model','nvngx_dlssnr'))
            groups.append(('nr-runtime-unavailable','mfg-only',[r for r in candidates if not feeder(r) and r.get('native_dlssg') and nr_missing(blocked.get(r.get('name'),''))]))
        offered=set()
        for code,subset_mode,group in groups:
            group=[r for r in group if r.get('game') not in offered]
            if not group:continue
            values=dict(visual_settings or {},prefer_bundled_nr_only=subset_mode=='nr-only')
            try:
                supported=self.prepare(group,subset_mode,operation,adopt,visual_settings=values,
                                       scope={'kind':'selected','games':[r['game'] for r in group]})
            except (t.Refusal,ValueError,OSError):continue
            games=sorted(planned(supported))
            if not games:continue
            offered.update(games)
            review['supported'].append({'reason_code':code,'reason':self.SUBSET_REASONS[code],'mode':subset_mode,
                                        'nr':subset_mode!='mfg-only','mfg':subset_mode!='nr-only','games':[g for g in games if g],
                                        'review':supported})
        if offered:
            names={r.get('name') for r in rows if r.get('game') in offered}
            review['blocked']=[b for b in review.get('blocked',[]) if b.get('name') not in names]
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
            values.get('mfg_multiplier') == 'auto' or (type(values.get('mfg_multiplier')) is int and
            values['mfg_multiplier'] in (0,2,3,4,5,6)),
            'Invalid MFG multiplier',
        )

        preset=engine_bridge.mfg_preset(values)
        settings=library_media.load_settings(self.config)
        settings.update(
            nr_strength=round(float(nr),1),
            sharpening_strength=round(float(sharp),1),
            mfg_multiplier=values['mfg_multiplier'],
        )
        if preset:settings.update(preset)
        if 'feature_controls' in values:
            import skynizz_provider
            settings['feature_controls']=skynizz_provider.validate_controls(values['feature_controls'])
        library_media.save_settings(self.config,settings)

    def recoveries(self):
        root=storage(self.config);rows=[]
        for path in sorted((root/'batches').glob('*/batch.json'),reverse=True):
            doc=t.read_json(path)
            if doc['status']!='rolled-back':rows.append({'kind':'rollback','path':str(path),'name':'Batch '+path.parent.name,'detail':doc['status']})
        for path in sorted((root/'cleanup').glob('*/cleanup.json'),reverse=True):
            doc=t.read_json(path)
            if doc['status'] in ('complete','removing','interrupted'):rows.append({'kind':'restore-cleanup','path':str(path),'name':'Cleanup '+path.parent.name,'detail':doc['status']})
        # Install/restore runs a crash or forced shutdown left open.
        for session in operation_session.unfinished(engine_bridge.operations_root()):
            checkpoint=session.interrupted()
            name=('Interrupted: '+checkpoint['label']) if checkpoint and checkpoint.get('label') else 'Interrupted operation'
            detail=('Stopped during '+(checkpoint.get('label') or 'a game')) if checkpoint else 'Older record: which game was in progress is unknown'
            rows.append({'kind':'operation','path':str(session.root),'name':name,'detail':detail})
        return rows

    def review_recovery(self,row):
        if row['kind']=='operation':return self.review_operation(row)
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

    def _operation(self,path):
        root=operation_session.canonical(engine_bridge.operations_root())
        session=operation_session.Session.load(t.safe(path))
        t.need(session.root.parent==root and session.root.name.startswith('cancel-'),'Invalid operation record')
        t.need(str(session.root) not in operation_session.LIVE and session.status in operation_session.UNFINISHED,'This operation is not interrupted')
        return session

    def review_operation(self,row):
        """Put back only the game that was in progress; games that finished keep their changes."""
        session=self._operation(row['path']);plan=session.recovery_plan(engine_bridge.steam_owned);details=[]
        if plan['checkpoint'] is None:
            details.append({'name':'Close this record','detail':'It predates per-game checkpoints, so rtxForge cannot tell which game was in progress. Nothing is restored; its copies are kept.'})
            return {'kind':'operation','path':str(session.root),'title':'Close interrupted operation','rows':details,'blocked':[],'close_only':True}
        label=plan['checkpoint'].get('label') or 'The interrupted game'
        details.append({'name':label,'detail':(str(len(plan['restore']))+' item(s) put back as they were before this run' if plan['restore'] else 'Nothing was changed; the record is closed')})
        for entry in plan['leave']:details.append({'name':Path(entry['path']).name,'detail':'Left as it is (Steam or Wine own it)'})
        if plan['completed']:details.append({'name':str(plan['completed'])+' finished game(s)','detail':'Keep their changes'})
        return {'kind':'operation','path':str(session.root),'title':'Recover interrupted operation','rows':details,'blocked':[]}

    def review_cleanup(self):
        roots=self.libraries()
        t.need(roots,'No Steam libraries were found for cleanup.')
        items=cleanup.discover(roots,self.config)
        return {'kind':'cleanup','title':'Global DLSS5 cleanup','items':items,'blocked':[],
                'rows':[{'name':Path(r['path']).name,'detail':r['path']} for r in items]}

    def execute(self,review):
        # The desktop must pass the exact in-memory review shown to the user.
        kind=review['kind']
        if kind=='vulkan-native':
            import vulkan_app
            return vulkan_app.execute(review)
        if kind=='adoption':
            import package_adoption
            return package_adoption.execute(review)
        if kind=='feeder':
            import feeder_provider
            return feeder_provider.execute(review)
        if kind=='engine':
            result=engine_bridge.execute(review)
            if review.get('save_defaults'):self.save_visual_defaults(review['save_defaults'])
            return result
        if kind=='batch':return str(app.apply_batch(self.config,review['plans']))
        if kind=='cleanup':return str(cleanup.apply(self.config,review['items']))
        if kind=='restore-cleanup':cleanup.restore(self.config,Path(review['path']),True);return review['path']
        if kind=='operation':
            session=self._operation(review['path'])
            if review.get('close_only'):session.close('closed')
            else:session.recover(engine_bridge.steam_owned)
            return str(session.root)
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
