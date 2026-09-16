#!/usr/bin/env python3
"""Native GNOME poster library. All engine work is serialized off the GTK thread."""
from pathlib import Path
import sys,threading,time,traceback,argparse,datetime,colorsys
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,GLib,Gio,Gdk,Graphene,Pango,GdkPixbuf
import ui,library_media,os,game_notes
from desktop_service import DesktopService

ACCENT_PROVIDERS={}
def artwork_accent(path):
    pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,32,32,True)
    data=pix.get_pixels();stride=pix.get_rowstride();channels=pix.get_n_channels();colors=Counter()
    for y in range(pix.get_height()):
        for x in range(pix.get_width()):
            off=y*stride+x*channels
            if channels==4 and data[off+3]<128:continue
            rgb=tuple(data[off+k]/255 for k in range(3));h,s,v=colorsys.rgb_to_hsv(*rgb)
            if s>.25 and .2<v<.98:colors[int(h*24)]+=s*v
    hue=(colors.most_common(1)[0][0]+.5)/24 if colors else .23
    rgb=tuple(round(v*255) for v in colorsys.hsv_to_rgb(hue,.62,.90))
    color='#%02x%02x%02x'%rgb;name='art-'+color[1:]
    if name not in ACCENT_PROVIDERS:
        provider=Gtk.CssProvider()
        provider.load_from_data((f'.game-card.{name}.selected {{ border-color: {color}; box-shadow: 0 2px 12px alpha({color},0.28); }} '
            f'.game-card.{name}:hover {{ border-color: alpha({color},0.65); }} '
            f'.{name} check:checked, .{name} button.suggested-action {{ background: {color}; color: #101010; }} '
            f'.{name} .game-status {{ border-left: 3px solid {color}; background: alpha({color},0.12); }} '
            f'.{name} scale highlight {{ background: {color}; }} '
            f'.{name} .game-heading, .{name} .eyebrow {{ color: {color}; }} '
            f'.{name} button:focus-visible {{ outline-color: {color}; }}').encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        ACCENT_PROVIDERS[name]=provider
    return name

class CoverPicture(Gtk.Picture):
    # Ask the layout for height at the actual allocated width, not the original minimum.
    cover_width=158
    cover_ratio=2/3
    def do_get_request_mode(self):return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    def do_measure(self, orientation, for_size):
        if orientation==Gtk.Orientation.HORIZONTAL:return (self.cover_width,self.cover_width,-1,-1)
        height=__import__('math').ceil((for_size if for_size>0 else self.cover_width)/self.cover_ratio)
        return (height,height,-1,-1)

class HeroPicture(Gtk.Picture):
    def do_measure(self,orientation,for_size):
        return (0,0,-1,-1) if orientation==Gtk.Orientation.HORIZONTAL else (300,300,-1,-1)

CSS=b'''
.settings-sidebar row { padding-left: 16px; padding-right: 16px; }
.control-pod { padding: 10px; border-radius: 12px; background: alpha(@window_fg_color,0.035); border: 1px solid alpha(@window_fg_color,0.06); }
.control-pod scale { padding: 5px 2px; }

.view-action { padding: 5px 8px; margin: 0; min-width: 20px; }
.profile-toggle { padding: 7px 12px; font-weight: 600; }
.status-pill { border-radius: 22px; padding: 9px 16px; margin: 8px; background: @card_bg_color; box-shadow: 0 3px 10px alpha(black,0.25); }
.title-action { min-width: 26px; min-height: 26px; padding: 8px 12px; margin: 3px; }
.hero-title { font-size: 29px; font-weight: 800; letter-spacing: -0.8px; }
.eyebrow { color: #76b900; font-weight: 800; font-size: 10px; letter-spacing: 2px; }
.hero { background: alpha(@window_fg_color,0.045); border: 1px solid alpha(@window_fg_color,0.06); border-radius: 18px; padding: 20px 24px; }
.forge-primary { background: #76b900; color: #111508; font-weight: 800; padding: 10px 18px; }
.forge-primary:hover { background: #b5ef50; }
.bulk-remove { color: #ff928c; padding: 10px 16px; }
.pill { border-radius: 99px; padding: 5px 10px; background: alpha(@window_fg_color,0.07); font-size: 11px; }
.game-card { border-radius: 14px; background: @card_bg_color; border: 2px solid alpha(@window_fg_color,0.06); }
.game-card.selected { border-color: #76b900; box-shadow: 0 2px 12px alpha(#76b900,0.22); }
.poster-button { padding: 0; border: 0; border-radius: 11px 11px 0 0; }
.poster { border-radius: 11px 11px 0 0; background: #242426; }
.poster-fallback { color: #a5a5a8; padding: 22px; font-weight: 800; font-size: 19px; }
.card-info { padding: 10px 12px 12px; }
.card-title { font-weight: 800; font-size: 13px; }
.card-meta { font-size: 10px; opacity: 0.7; }
.cover-badge { background: transparent; color: white; text-shadow: 0 1px 3px black; padding: 5px 8px; border-radius: 8px; font-size: 10px; font-weight: 700; }
.cover-badge.unavailable { color: #ffb3ad; }
.selection-bar { padding: 12px 20px; background: alpha(@window_fg_color,0.04); }
.status-strip { padding: 8px 20px; font-size: 12px; }
.game-hero { padding: 0 18px 12px; }
.hero-fade { background: linear-gradient(to bottom, alpha(@window_bg_color,0.05) 0%, alpha(@window_bg_color,0.35) 40%, @window_bg_color 100%); }
.profile-poster { border: 3px solid @window_bg_color; border-radius: 10px; box-shadow: 0 8px 24px alpha(black,0.4); }
.game-heading { font-size: 27px; font-weight: 800; }
.game-status { padding: 16px; border-radius: 14px; background: alpha(@window_fg_color,0.06); }
.game-caption { font-size: 11px; opacity: 0.65; }
.panel-body { padding: 18px 24px; }
.profile-toggle:checked { background: transparent; color: @accent_color; box-shadow: inset 0 -2px @accent_color; }
.progress-orb { border-radius: 999px; background: alpha(@window_fg_color,0.06); padding: 18px; }
.progress-title { font-size: 22px; font-weight: 800; }
'''

def profile_icon(mode):
    return {'nr-only':'rtx-brush-symbolic','mfg-only':'rtx-windows-symbolic','nr-mfg':'rtx-sparkle-symbolic'}[mode]

def profile_label(mode,text):
    box=Gtk.Box(spacing=6);box.append(Gtk.Image.new_from_icon_name(profile_icon(mode)));box.append(label(text));return box

def label(text,css=None):
    w=Gtk.Label(label=str(text),xalign=0,wrap=True)
    if css:w.add_css_class(css)
    return w
def button(text,fn,css=None):
    w=Gtk.Button(label=text);w.connect('clicked',fn)
    if css:w.add_css_class(css)
    return w
def margins(w,n=16):
    for edge in ('start','end','top','bottom'):getattr(w,'set_margin_'+edge)(n)
def clear(box):
    while box.get_first_child():box.remove(box.get_first_child())
def row(title,subtitle=''):
    w=Adw.ActionRow(title=str(title),subtitle=str(subtitle));w.set_use_markup(False);return w

def demo_games():
    titles=[('Cyberpunk 2077','1091500'),('Hogwarts Legacy','990080'),('PRAGMATA','3357650'),('Star Wars Outlaws','2842040'),('Avatar: Frontiers of Pandora','2840770'),('Forza Horizon 6','')]
    return [{'name':n,'appid':a,'game':'/preview/'+n,'exe':'Game.exe','source':'Steam' if a else 'Non-Steam','library':'Games drive','blocked':'','installed':i<3,'profile':'MFG Only' if i<3 else 'Not installed'} for i,(n,a) in enumerate(titles)]

class Window(Adw.ApplicationWindow):
    def __init__(self,application,options):
        super().__init__(application=application,title='RTXForge',default_width=1160,default_height=820)
        self.options=options;self.service=DesktopService(options.provider)
        self.settings=dict(library_media.DEFAULTS) if options.demo else library_media.load_settings(self.service.config)
        self.strength_presets=__import__('engine_bridge').module(self.service.config).NR_STRENGTH_PRESETS
        self.strength_names=tuple(self.strength_presets);self.multiplier_values=(0,2,3,4,5,6)
        self.settings['enable_effects']=True;self.settings.setdefault('dark',True);self.hardware_info={'ready':True,'gpu':'Preview GPU','reason':'Preview mode'} if options.demo else None;self.games=[];self.cards={};self.mode='mfg-only';self.filter='all'
        self.busy=False;self.task_kind='';self.pending=None;self.cancel_art=threading.Event();self.log=[];self.dialog=None;self.review=None;self.action_buttons=[]
        self.connect('close-request',self.close_request)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK if self.settings['dark'] else Adw.ColorScheme.DEFAULT)
        self.overlay=Adw.ToastOverlay();self.set_content(self.overlay);outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.overlay.set_child(outer)
        header=Adw.HeaderBar();header.set_title_widget(Adw.WindowTitle(title='RTXForge',subtitle='Your whole library. One place.'))
        self.refresh=self.title_button('view-refresh-symbolic','Refresh library',lambda *_:self.scan());header.pack_start(self.refresh)
        self.add=self.title_button('list-add-symbolic','Add game folder',self.choose_folder);header.pack_start(self.add)
        header.pack_end(self.title_button('emblem-system-symbolic','Settings',self.show_settings));header.pack_end(self.title_button('document-open-recent-symbolic','Activity',self.show_activity));outer.append(header)
        top=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);margins(top,18);outer.append(top)
        hero=Gtk.Box(spacing=20);hero.add_css_class('hero');hero_reveal=Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP,reveal_child=True,transition_duration=180);hero_reveal.set_child(hero);top.append(hero_reveal)
        title=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7,hexpand=True);hero.append(title)
        title.append(label('GEFORCE / BUILT FOR LINUX','eyebrow'));title.append(label('Forge your entire library.','hero-title'))
        self.stats=label('Finding your games…','dim-label');title.append(self.stats)
        self.hardware_label=label('Preview mode · no game writes' if options.demo else 'Checking system hardware…','card-meta');title.append(self.hardware_label)
        tuning,self.tuning_widgets=self.tuning_controls(self.settings)
        title.append(tuning);self.strength_slider=self.tuning_widgets['nr_strength']
        bulk=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,valign=Gtk.Align.CENTER);hero.append(bulk)
        self.install_all=button('Add Enhancements to All',lambda *_:self.launch_action('install',True),'forge-primary');bulk.append(self.install_all)
        self.uninstall_all=button('Remove Enhancements from All',lambda *_:self.launch_action('uninstall',True),'bulk-remove');bulk.append(self.uninstall_all)
        self.reset_all=button('Reset All Settings',self.apply_library_settings);bulk.append(self.reset_all)
        for key,widget in self.tuning_widgets.items():widget.connect('notify::selected' if key=='mfg_multiplier' else 'value-changed',self.strength_changed)
        self.strength_changed()
        self.reset_all.set_tooltip_text('Restore current sharpening, NR and menu-font defaults for managed games. Each configuration is backed up. Close running games first.')
        self.install_all.set_tooltip_text('One click: prepare, back up and install wherever possible across every library. Incompatible games are skipped.')
        self.uninstall_all.set_tooltip_text('One click: remove recorded OptiScaler installs across every library, with backups. Your games remain installed.')
        controls=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER);top.append(controls);controls.append(label('Install profile','dim-label'))
        linked=Gtk.Box();linked.add_css_class('linked');controls.append(linked)
        self.mfg=Gtk.ToggleButton(label='MFG Only');self.nr=Gtk.ToggleButton(label='NR + MFG');self.nr.set_group(self.mfg);self.nr_only=Gtk.ToggleButton(label='NR Only');self.nr_only.set_group(self.mfg);self.nr_only.set_sensitive(self.settings.get('runtime_provider','y4my')=='dlss-unlocked')
        for toggle,mode in ((self.nr_only,'nr-only'),(self.mfg,'mfg-only'),(self.nr,'nr-mfg')):
            toggle.set_child(profile_label(mode,{'nr-only':'NR Only','mfg-only':'MFG Only','nr-mfg':'NR + MFG'}[mode]))
            toggle.add_css_class('profile-nr' if mode=='nr-mfg' else 'profile-mfg');toggle.add_css_class('profile-toggle');toggle.connect('toggled',self.profile_changed,mode);linked.append(toggle)
        ({'nr-mfg':self.nr,'nr-only':self.nr_only}.get(self.settings.get('default_profile'),self.mfg)).set_active(True);self.profile_note=label('Game-native frame generation · NR not installed','dim-label');controls.append(self.profile_note)
        viewbar=Gtk.Box(spacing=10);library_title=label('Your games','heading');library_title.set_hexpand(True);viewbar.append(library_title)
        viewbox=Gtk.Box();viewbox.add_css_class('linked');viewbar.append(viewbox);self.view_buttons={};first=None
        for title,key in [('Posters','posters'),('Wide capsules','capsules'),('List','list')]:
            toggle=Gtk.ToggleButton(icon_name={'posters':'view-grid-symbolic','capsules':'view-dual-symbolic','list':'view-list-symbolic'}[key]);toggle.set_tooltip_text(title);toggle.update_property([Gtk.AccessibleProperty.LABEL],[title]);toggle.add_css_class('view-action')
            if first:toggle.set_group(first)
            else:first=toggle
            toggle.set_active(self.settings.get('library_view','posters')==key)
            toggle.connect('toggled',self.view_changed,key);viewbox.append(toggle);self.view_buttons[key]=toggle
        filters=Gtk.Box(spacing=8);top.append(filters)
        self.search=Gtk.SearchEntry(placeholder_text='Search your entire library',hexpand=True);self.search.connect('search-changed',lambda *_:self.filter_games());filters.append(self.search)
        filterbox=Gtk.Box();filterbox.add_css_class('linked');filters.append(filterbox);previous=None
        for name,key in [('All','all'),('Installed','installed'),('Available','available')]:
            b=Gtk.ToggleButton(label=name)
            if previous:b.set_group(previous)
            else:previous=b;b.set_active(True)
            b.connect('toggled',self.filter_changed,key);filterbox.append(b)
        filters.append(button('Select all',lambda *_:self.select_all(True)));filters.append(button('Clear',lambda *_:self.select_all(False)))
        margins(viewbar,18);viewbar.set_margin_top(0);viewbar.set_margin_bottom(0);outer.append(viewbar)
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);outer.append(scroll)
        def collapse_header(adj):
            if adj.get_value()>120 and adj.get_upper()-adj.get_page_size()>300:hero_reveal.set_reveal_child(False)
            elif adj.get_value()<10:hero_reveal.set_reveal_child(True)
        scroll.get_vadjustment().connect('value-changed',collapse_header)
        self.flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=14,row_spacing=16,min_children_per_line=1,max_children_per_line=8,homogeneous=True,valign=Gtk.Align.START);margins(self.flow,18);scroll.set_child(self.flow)
        footer=Gtk.Box(spacing=8);footer.add_css_class('selection-bar');outer.append(footer)
        self.selected_label=label('0 selected',css='heading');self.selected_label.set_hexpand(True);footer.append(self.selected_label)
        for name,op,css in [('Add Enhancements','install','forge-primary'),('Repair Files','repair',None),('Remove Enhancements','uninstall','bulk-remove'),('Reset Settings','reset',None)]:
            b=button(name,lambda _,action=op:self.launch_action(action),css);footer.append(b);self.action_buttons.append(b)
        statusbox=Gtk.Box(spacing=10,halign=Gtk.Align.CENTER);statusbox.add_css_class('status-pill');outer.append(statusbox)
        self.spinner=Gtk.Spinner();statusbox.append(self.spinner);self.status=label('Ready');self.status.set_max_width_chars(48);self.status.set_ellipsize(Pango.EllipsizeMode.END);statusbox.append(self.status)
        self.elapsed=label('','dim-label');statusbox.append(self.elapsed);self.progress=Gtk.ProgressBar(width_request=130,valign=Gtk.Align.CENTER);statusbox.append(self.progress)
        GLib.timeout_add(180,self.tick)
        if options.demo:
            games=demo_games()
            for game in games:
                path=ROOT/'dist/demo-media'/((game['appid'] or 'forza')+'.json')
                if path.exists():game.update(__import__('json').loads(path.read_text()))
            self.show_games(games,False)
            for key in list(self.cards)[:3]:self.cards[key]['check'].set_active(True)
        else:self.scan()
        if options.smoke_test:GLib.timeout_add(800,self.smoke_library)

    def title_button(self,icon,title,callback):
        b=Gtk.Button(icon_name=icon);b.set_tooltip_text(title);b.update_property([Gtk.AccessibleProperty.LABEL],[title]);b.add_css_class('title-action');b.connect('clicked',callback);return b
    def view_changed(self,toggle,key):
        if not toggle.get_active() or self.settings.get('library_view')==key:return
        self.settings['library_view']=key
        self.show_games(self.games,False)
        if not self.options.demo:
            self.start('Saving library view',lambda:library_media.save_settings(self.service.config,self.settings),lambda _:self.fetch_media() if self.settings['online_art'] else None)
    def toast(self,text):self.overlay.add_toast(Adw.Toast.new(str(text)))
    def profile_changed(self,toggle,mode):
        if toggle.get_active():
            self.mode=mode
            if hasattr(self,'profile_note'):self.profile_note.set_text({'nr-only':'Neural Rendering · keep in-game frame generation off','nr-mfg':'NR + MFG · combined pipeline','mfg-only':'Native MFG · Neural Rendering off'}[mode])
    def tuning_controls(self,initial):
        box=Gtk.Box(spacing=8);widgets={}
        for key,title in [('nr_strength','NR Strength'),('sharpening_strength','Sharpening')]:
            group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True);group.add_css_class('control-pod');box.append(group)
            heading=label(title,'heading');group.append(heading)
            slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,len(self.strength_names)-1,1)
            slider.set_digits(0);slider.set_draw_value(False);slider.set_round_digits(0);slider.set_hexpand(True);slider.set_size_request(125,-1)
            slider.update_property([Gtk.AccessibleProperty.LABEL],[title])
            slider.set_tooltip_text('Off · Light · Medium · Strong')
            slider.set_value(self.strength_names.index(initial.get(key) or self.settings.get(key,'strong')))
            group.append(slider);detail=label('','dim-label');group.append(detail)
            def update(w,h=heading,d=detail,k=key,t=title):
                name=self.strength_names[int(round(w.get_value()))];preset=self.strength_presets[name]
                h.set_text(t+' · '+name.title());d.set_text('Disabled' if name=='off' else 'Intensity / skin '+preset['nr'] if k=='nr_strength' else 'Level '+preset['sharpness'])
            slider.connect('value-changed',update);update(slider);widgets[key]=slider
        group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);group.add_css_class('control-pod');box.append(group);group.append(label('MFG' ,'heading'))
        multiplier=Gtk.DropDown.new_from_strings(['Off']+[str(x)+'×' for x in range(2,7)])
        multiplier.set_selected(self.multiplier_values.index(initial['mfg_multiplier'] if initial.get('mfg_multiplier') is not None else self.settings.get('mfg_multiplier',2)))
        multiplier.update_property([Gtk.AccessibleProperty.LABEL],['MFG Multiplier'])
        group.append(multiplier);group.append(label('Requested ratio','dim-label'));widgets['mfg_multiplier']=multiplier
        return box,widgets
    def tuning_values(self,widgets):
        return {key:self.multiplier_values[int(w.get_selected())] if key=='mfg_multiplier' else self.strength_names[int(round(w.get_value()))] for key,w in widgets.items()}
    def chosen_strength(self):return self.tuning_values(self.tuning_widgets)['nr_strength']
    def defaults_changed(self):return any(self.settings.get(k)!=v for k,v in self.tuning_values(self.tuning_widgets).items())
    def strength_changed(self,*_):
        self.reset_all.set_label('Apply Settings' if self.defaults_changed() else 'Reset All Settings')
        if hasattr(self,'mfg'):self.controls()
    def defaults_applied(self,values):
        self.settings.update(values);self.strength_changed()
    def apply_library_settings(self,*_):
        if self.games and any(g.get('installed') for g in self.games):self.launch_action('reset',True);return
        values=self.tuning_values(self.tuning_widgets)
        if self.options.demo:self.defaults_applied(values);return
        self.start('Saving defaults',lambda:self.service.save_visual_defaults(values),lambda _:(self.defaults_applied(values),self.toast('Defaults saved for new installs.')))
    def filter_changed(self,toggle,key):
        if toggle.get_active():self.filter=key;self.filter_games()
    def close_request(self,*_):
        if self.busy and self.task_kind!='art':self.toast('Please wait for the current file operation to finish.');return True
        if self.busy:self.cancel_art.set()
        return False
    def tick(self):
        if self.busy:self.progress.pulse();self.elapsed.set_text(f'{int(time.monotonic()-self.started)}s')
        return True
    def controls(self):
        enabled=not self.busy or self.task_kind=='art'
        compatible=bool(self.hardware_info and self.hardware_info['ready'])
        self.install_all.set_sensitive(enabled and bool(self.games) and compatible);self.uninstall_all.set_sensitive(enabled and bool(self.games))
        self.reset_all.set_sensitive(enabled and (any(g.get('installed') for g in self.games) or self.defaults_changed()))
        for widget in self.tuning_widgets.values():widget.set_sensitive(enabled)
        for entry in self.cards.values():entry['reset'].set_sensitive(enabled and entry['data'].get('installed',False))
        for i,b in enumerate(self.action_buttons):b.set_sensitive(enabled and (compatible or i in (2,3)) and any(v['check'].get_active() for v in self.cards.values()))
        for b in (self.refresh,self.add,self.mfg,self.nr,*self.view_buttons.values()):b.set_sensitive(enabled)
    def event(self,event):
        if event['kind']=='progress':self.status.set_text(event['label'])
        elif event['kind']=='art':
            card=self.cards.get(event['game'])
            if card:card['data'].update(event['data']);self.paint_card(card)
            if getattr(self,'detail_game',None)==event['game'] and self.dialog==getattr(self,'detail_dialog',None) and event['data'].get('hero'):
                try:self.detail_banner.set_paintable(Gdk.Texture.new_from_filename(event['data']['hero']))
                except Exception:pass
        else:self.log.append(event['text']);self.log=self.log[-400:]
        if self.dialog and hasattr(self,'job_label') and self.job_label:self.job_label.set_text(self.status.get_text())
        return False
    def start(self,title,action,done,kind='work'):
        if self.busy:
            if self.task_kind=='art':self.pending=(title,action,done,kind);self.cancel_art.set();self.status.set_text('Finishing current artwork request…')
            return
        self.busy=True;self.task_kind=kind;self.started=time.monotonic();self.spinner.start();self.status.set_text(title);self.progress.set_fraction(0);self.controls()
        def worker():
            try:
                with ui.report_to(lambda e:GLib.idle_add(self.event,e)):result=action()
            except Exception as ex:GLib.idle_add(self.finished,None,done,(str(ex),traceback.format_exc()))
            else:GLib.idle_add(self.finished,result,done,None)
        threading.Thread(target=worker,daemon=False).start()
    def finished(self,result,done,error):
        self.busy=False;self.task_kind='';self.spinner.stop();self.progress.set_fraction(0 if error else 1);self.controls()
        if getattr(self,'operation_cancel',None) is not None and self.operation_cancel.is_set() and (not getattr(self,'operation_executing',False) or (error and 'operation_session.Cancelled' in error[1])):
            self.operation_cancel=None
            if self.dialog:self.dialog.force_close()
            self.dialog=None;self.job_label=None;self.toast('Cancelled · changes undone')
            previous=getattr(self,'operation_previous',None)
            if previous:self.details(previous)
            return
        if error:
            self.log.append(error[1]);self.status.set_text('Stopped · details available in Activity');self.error(error[0])
        else:self.status.set_text('Ready');done(result)
        if self.pending:
            task=self.pending;self.pending=None;self.start(*task)
        return False
    def open_panel(self,title,width=730,height=620):
        if self.dialog:self.dialog.force_close()
        dialog=Adw.Dialog(title=title,content_width=width,content_height=height);self.dialog=dialog;self.job_label=None
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);dialog.set_child(box)
        header=Adw.HeaderBar();header.set_title_widget(Adw.WindowTitle(title=title));box.append(header)
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);box.append(scroll)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);body.add_css_class('panel-body');scroll.set_child(body)
        foot=Gtk.Box(spacing=10,halign=Gtk.Align.END);margins(foot,16);box.append(foot)
        dialog.present(self);return dialog,body,foot
    def organize_pages(self,body,sections):
        children=[];child=body.get_first_child()
        while child:children.append(child);child=child.get_next_sibling()
        for child in children:body.remove(child)
        stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,hexpand=True,vexpand=True)
        stack.set_vhomogeneous(False)
        switcher=Gtk.StackSwitcher(stack=stack,halign=Gtk.Align.CENTER)
        sidebar=Gtk.StackSidebar(stack=stack,width_request=180)
        sidebar.add_css_class('settings-sidebar')
        layout=Gtk.Box(spacing=16);layout.append(sidebar);layout.append(stack)
        body.append(switcher);body.append(layout)
        for title,items in sections:
            page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            for item in items:page.append(item)
            stack.add_titled(page,title,title)
        def responsive(*_):
            wide=body.get_width()>=740
            if sidebar.get_visible()!=wide:sidebar.set_visible(wide);switcher.set_visible(not wide)
            return True
        body.add_tick_callback(responsive);responsive()
        return stack

    def error(self,message):
        d,b,f=self.open_panel('Could not finish',height=390);b.append(label(str(message)));f.append(button('Close',lambda *_:d.close()))
    def scan(self):
        if self.options.demo:return
        extra=list(self.settings['extra_folders']);self.start('Checking hardware and scanning libraries',lambda:{'hardware':self.service.hardware(),'games':self.service.scan_all(extra)},self.scanned)
    def scanned(self,result):
        self.hardware_info=result['hardware'];self.hardware_label.set_text(self.hardware_info['gpu']+' · '+('Hardware check passed' if self.hardware_info['ready'] else 'Install unavailable — see Settings'));self.show_games(result['games'])
    def choose_folder(self,*_):
        d=Gtk.FileChooserNative(title='Add a game folder',transient_for=self,action=Gtk.FileChooserAction.SELECT_FOLDER,accept_label='Add game')
        def selected(dialog,response):
            if response==Gtk.ResponseType.ACCEPT:
                path=dialog.get_file().get_path()
                if path and path not in self.settings['extra_folders']:
                    self.settings['extra_folders'].append(path)
                    self.start('Saving game folder',lambda:library_media.save_settings(self.service.config,self.settings),lambda _:self.scan())
            dialog.destroy()
        d.connect('response',selected);d.show()
    def show_games(self,games,art=True):
        selected={k for k,v in self.cards.items() if v['check'].get_active()}
        previous={g['game']:g for g in self.games}
        clear(self.flow);self.games=games;self.cards={}
        view=self.settings.get('library_view','posters');self.flow.set_max_children_per_line(1 if view=='list' else 8);self.flow.set_homogeneous(view!='list')
        media=library_media.LibraryMedia(self.service.config,{**self.settings,'online_art':False})
        for game in games:
            for key in ('poster','hero','capsule','art_credit','art_link','hero_credit','hero_link','accent_class'):
                if key in previous.get(game['game'],{}):game.setdefault(key,previous[game['game']][key])
            if not self.options.demo:game.update(media.enrich(game))
            game['test_record']=game_notes.load(self.service.config,game['game']) if not self.options.demo else game.get('test_record',{'status':'Untested','notes':''})
            self.make_card(game)
            if game['game'] in selected:self.cards[game['game']]['check'].set_active(True)
        count=sum(g.get('installed',False) for g in games);libs=len(set(g.get('library','') for g in games))
        self.stats.set_text(f'{len(games)} games · {libs} locations · {count} OptiScaler installs detected')
        self.filter_games();self.status.set_text('Your entire library is ready')
        if art and self.settings['online_art'] and games:self.fetch_media()
    def make_card(self,game):
        view=self.settings.get('library_view','posters');scale=self.settings.get('art_scale',100)/100
        width,height=(int(158*scale),int(237*scale)) if view=='posters' else (int(290*scale),int(136*scale)) if view=='capsules' else (54,81)
        card=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if view=='list' else Gtk.Orientation.VERTICAL);card.add_css_class('game-card');card.set_size_request(width+4,-1)
        overlay=Gtk.Overlay(valign=Gtk.Align.START);card.append(overlay)
        pic=CoverPicture(content_fit=Gtk.ContentFit.CONTAIN,can_shrink=True);pic.add_css_class('poster')
        pic.cover_width=width;pic.cover_ratio=width/height
        click=Gtk.Button(child=pic);click.add_css_class('poster-button');click.connect('clicked',lambda *_:self.details(game));overlay.set_child(click)
        fallback=label(game['name'],'poster-fallback');fallback.set_halign(Gtk.Align.CENTER);fallback.set_valign(Gtk.Align.CENTER);fallback.set_max_width_chars(13);overlay.add_overlay(fallback)
        check=Gtk.CheckButton(halign=Gtk.Align.END,valign=Gtk.Align.START);margins(check,10);check.set_tooltip_text('Select '+game['name']);check.connect('toggled',lambda *_:self.selection_changed())
        if view=='list':card.prepend(check);fallback.set_visible(False)
        else:overlay.add_overlay(check)
        badge=label('Unavailable' if game.get('blocked') else game.get('profile','Ready') if game.get('installed') else 'Ready','cover-badge');badge.set_halign(Gtk.Align.START);badge.set_valign(Gtk.Align.END);margins(badge,8)
        badge_mode={'NR Only':'nr-only','MFG Only':'mfg-only','NR + MFG':'nr-mfg'}.get(game.get('profile'))
        if badge_mode:
            badge=profile_label(badge_mode,badge.get_text());badge.add_css_class('cover-badge');badge.set_halign(Gtk.Align.START);badge.set_valign(Gtk.Align.END);margins(badge,8)
        badge.add_css_class('state-unavailable' if game.get('blocked') else 'state-nr' if game.get('profile')=='NR + MFG' else 'state-mfg' if game.get('installed') else 'state-ready')
        if view!='list':overlay.add_overlay(badge)
        text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,hexpand=view=='list',valign=Gtk.Align.CENTER);text.add_css_class('card-info');card.append(text)
        title=label(game['name'],'card-title');title.set_lines(2);title.set_ellipsize(Pango.EllipsizeMode.END);title.set_max_width_chars(70 if view=='list' else 24 if view=='capsules' else 18);text.append(title)
        meta=label(game.get('source',''),'card-meta');meta.set_lines(1);meta.set_ellipsize(Pango.EllipsizeMode.END);meta.set_max_width_chars(80 if view=='list' else 28 if view=='capsules' else 22);text.append(meta)
        reset=button('Reset Settings',lambda *_:self.launch_action('reset',targets=[game]))
        reset.set_tooltip_text('Restore current sharpening, NR and menu-font defaults; back up your existing settings.')
        reset.set_sensitive(game.get('installed',False));text.append(reset)
        self.flow.insert(card,-1);wrapper=card.get_parent()
        entry={'reset':reset,'widget':card,'wrapper':wrapper,'check':check,'picture':pic,'fallback':fallback,'meta':meta,'data':game,'size':(width,height)};self.cards[game['game']]=entry;self.paint_card(entry)
    def paint_card(self,entry):
        game=entry['data'];path=game.get('capsule') if self.settings.get('library_view')=='capsules' else game.get('poster')
        if path:
            try:
                texture=Gdk.Texture.new_from_filename(path)
                entry['picture'].cover_ratio=texture.get_width()/texture.get_height();entry['picture'].queue_resize()
                entry['picture'].set_paintable(texture);entry['fallback'].set_visible(False)
                if game.get('accent_class'):entry['widget'].remove_css_class(game['accent_class'])
                game['accent_class']=artwork_accent(path);entry['widget'].add_css_class(game['accent_class'])
            except Exception:entry['fallback'].set_visible(True)
        else:
            entry['picture'].set_paintable(None);entry['fallback'].set_visible(True)
        entry['meta'].set_text(game.get('source','')+' · '+game.get('test_record',{}).get('status','Untested'))
        entry['widget'].set_tooltip_text(game['name']+'\n'+(game.get('art_credit') or 'Artwork pending'))
    def filter_games(self):
        if not hasattr(self,'search'):return
        text=self.search.get_text().casefold()
        for e in self.cards.values():
            g=e['data'];visible=text in g['name'].casefold() and (self.filter=='all' or self.filter=='installed' and g.get('installed') or self.filter=='available' and not g.get('blocked'))
            e['wrapper'].set_visible(bool(visible))
        self.selection_changed()
    def select_all(self,active):
        # Select ALL always means the unified library, even when search/filter is active.
        for e in self.cards.values():e['check'].set_active(active)
    def selection_changed(self):
        count=0
        for e in self.cards.values():
            if e['check'].get_active():count+=1;e['widget'].add_css_class('selected')
            else:e['widget'].remove_css_class('selected')
        if hasattr(self,'selected_label'):self.selected_label.set_text(f'{count} selected'+(' · across the whole library' if count else ''))
        if hasattr(self,'install_all'):self.controls()
    def fetch_media(self,refresh=False):
        if getattr(self,'art_loading',False):return
        self.art_loading=True;self.cancel_art.clear();games=list(self.games);settings=dict(self.settings)
        def load():
            media=library_media.LibraryMedia(self.service.config,settings)
            for index,game in enumerate(games):
                if self.cancel_art.is_set():break
                try:data=media.enrich(game,refresh)
                except Exception:continue
                GLib.idle_add(self.event,{'kind':'art','game':game['game'],'data':data})
            self.art_loading=False
        threading.Thread(target=load,daemon=True).start()
    def details(self,game):
        d,b,f=self.open_panel(game['name'],width=820,height=720);b.remove_css_class('panel-body')
        if game.get('accent_class'):d.add_css_class(game['accent_class'])
        stage=Gtk.Overlay();b.append(stage)
        background=Gtk.Overlay(valign=Gtk.Align.START);stage.set_child(background)
        banner=HeroPicture(content_fit=Gtk.ContentFit.COVER,can_shrink=True);background.set_child(banner)
        self.detail_game=game['game'];self.detail_dialog=d;self.detail_banner=banner
        if game.get('hero'):
            try:banner.set_paintable(Gdk.Texture.new_from_filename(game['hero']))
            except Exception:pass
        fade=Gtk.Box();fade.add_css_class('hero-fade');background.add_overlay(fade)
        hero=Gtk.Box(spacing=24);hero.set_margin_top(180);hero.add_css_class('game-hero');stage.add_overlay(hero);stage.set_measure_overlay(hero,True)
        path=game.get('poster')
        if path:
            try:
                texture=Gdk.Texture.new_from_filename(path)
                pic=CoverPicture(content_fit=Gtk.ContentFit.CONTAIN,can_shrink=True,valign=Gtk.Align.START)
                pic.add_css_class('profile-poster');pic.cover_width=150;pic.cover_ratio=texture.get_width()/texture.get_height();pic.set_paintable(texture);hero.append(pic)
            except Exception:pass
        summary=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True,valign=Gtk.Align.START);summary.set_margin_top(70);hero.append(summary)
        summary.append(label((game.get('source') or 'YOUR LIBRARY').upper(),'eyebrow'))
        title=label(game['name'],'game-heading');title.set_max_width_chars(28);summary.append(title)
        metadata=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=6,row_spacing=6,max_children_per_line=3)
        for value in [game.get('release'),game.get('genres'),game.get('developers')]:
            if value:metadata.insert(label(value,'pill'),-1)
        summary.append(metadata)
        status=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5);status.add_css_class('game-status');summary.append(status)
        status.append(label(game.get('profile','Installed') if game.get('installed') else 'Ready to enhance' if not game.get('blocked') else 'Installation unavailable','heading'))
        status.append(label(game.get('blocked') or 'Installed files detected · use Repair Files to verify' if game.get('installed') else game.get('blocked') or 'Install checks run before changes are made.','dim-label'))
        tuning_group=Adw.PreferencesGroup(title='Game settings',description='Apply only to this game. Close the game first; changes take effect on its next launch.');margins(tuning_group,20);b.append(tuning_group)
        saved_nr=(game.get('nr_strength') or 'custom').title();saved_sharp=(game.get('sharpening_strength') or 'custom').title()
        saved_mfg='Off' if game.get('mfg_multiplier')==0 else str(game['mfg_multiplier'])+'×' if game.get('mfg_multiplier') else 'Game-controlled'
        tuning_group.add(row('Saved in INI','NR '+saved_nr+' · Sharpening '+saved_sharp+' · MFG '+saved_mfg))
        tuning_box,tuning_widgets=self.tuning_controls(game);margins(tuning_box,20);b.append(tuning_box)
        mode=game.get('feature_mode') or {'NR Only':'nr-only','MFG Only':'mfg-only'}.get(game.get('profile'),'nr-mfg')
        installed=game.get('installed',False)
        for key,widget in tuning_widgets.items():widget.set_sensitive(installed and not (key=='nr_strength' and mode=='mfg-only') and not (key=='mfg_multiplier' and mode=='nr-only'))
        hint=label('MFG requires frame generation enabled in the game. The runtime determines the supported ratio.','dim-label');margins(hint,20);b.append(hint)
        apply_game=button('Apply Settings',lambda *_:self.launch_action('reset',targets=[game],visual_settings=self.tuning_values(tuning_widgets)),'suggested-action');apply_game.set_halign(Gtk.Align.START);margins(apply_game,20);b.append(apply_game)
        def game_tuning_changed(*_):
            values=self.tuning_values(tuning_widgets)
            changed=any(values[k]!=game.get(k) for k,w in tuning_widgets.items() if w.get_sensitive())
            apply_game.set_sensitive(installed and changed)
        for key,widget in tuning_widgets.items():widget.connect('notify::selected' if key=='mfg_multiplier' else 'value-changed',game_tuning_changed)
        game_tuning_changed();self.detail_tuning_widgets=tuning_widgets;self.detail_apply_settings=apply_game
        if game.get('description'):
            description=label(game['description']);margins(description,20);b.append(description)
        info=Adw.PreferencesGroup();margins(info,20);b.append(info)
        technical=Adw.ExpanderRow(title='Installation details',subtitle='Location, compatibility and storage');info.add(technical)
        values=[('Compatibility',game.get('blocked') or 'Native DLSS-G detected; runtime not verified'),('Library',game.get('library')),('Folder',game['game'])]
        if game.get('size_bytes'):values.append(('Installed size',f"{game['size_bytes']/1024**3:.1f} GiB"))
        for name,value in values:
            if value:technical.add_row(row(name,value))
        testing=Adw.PreferencesGroup(title='Your test record',description='Your observations stay local. Bench excludes this game from bulk install and repair.');margins(testing,20);b.append(testing)
        record=game.get('test_record',{'status':'Untested','notes':''});choice={'status':record.get('status','Untested')}
        switches=Gtk.Box(spacing=0);switches.add_css_class('linked');first=None
        for value in game_notes.STATES:
            toggle=Gtk.ToggleButton(label=value)
            if first:toggle.set_group(first)
            else:first=toggle
            toggle.set_active(value==choice['status']);toggle.connect('toggled',lambda w,v=value:choice.update(status=v) if w.get_active() else None);switches.append(toggle)
        state_row=row('Result','Recorded by you; installation is not proof of success.');state_row.add_suffix(switches);testing.add(state_row)
        notes=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=85);notes.get_buffer().set_text(record.get('notes',''));notes.set_margin_start(20);notes.set_margin_end(20);b.append(notes)
        actions=Gtk.Box(spacing=8);margins(actions,20);b.append(actions)
        def save_notes(*_):
            buf=notes.get_buffer();current=game_notes.load(self.service.config,game['game']) if not self.options.demo else record.copy()
            current.update(status=choice['status'],notes=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),True))
            if not self.options.demo:game_notes.save(self.service.config,game['game'],current)
            game['test_record']=current;self.paint_card(self.cards[game['game']]);self.toast('Test notes saved')
        actions.append(button('Save notes',save_notes,'suggested-action'))
        active=bool(record.get('active'))
        test_button=button('Finish test · collect logs' if active else 'Start test',lambda *_:self.record_test(game,active));test_button.set_sensitive(not self.options.demo);actions.append(test_button)
        if active:testing.add(row('Test in progress',record['active']['started']+' · finish after closing the game'))
        elif record.get('sessions'):testing.add(row('Last test',record['sessions'][-1]['finished']))
        credit=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);margins(credit,12);popover=Gtk.Popover();popover.set_child(credit);credits=Gtk.MenuButton(label='Artwork credits',halign=Gtk.Align.START);credits.add_css_class('pill');credits.set_margin_start(20);credits.set_popover(popover);b.append(credits)
        if game.get('art_credit'):credit.append(label(game['art_credit'],'game-caption'))
        if game.get('art_link'):credit.append(Gtk.LinkButton(uri=game['art_link'],label='Poster'))
        if game.get('hero_link'):credit.append(Gtk.LinkButton(uri=game['hero_link'],label='Hero · '+game.get('hero_credit','Artwork source')))
        items=[];child=b.get_first_child()
        while child:items.append(child);child=child.get_next_sibling()
        a=items.index(tuning_group);n=items.index(testing);c=items.index(credits)
        pages=self.organize_pages(b,[('Overview',[stage]+items[items.index(apply_game)+1:n]),
            ('Enhancements',items[a:items.index(apply_game)+1]),('Notes',items[n:c]),('Artwork',[credits])])
        self.detail_pages=pages
        folder=button('Open folder',lambda *_:Gio.AppInfo.launch_default_for_uri(Path(game['game']).as_uri(),None));f.append(folder)
        if game.get('appid') and game.get('source')=='Steam':
            launch=button('Play',lambda *_:Gio.AppInfo.launch_default_for_uri('steam://rungameid/'+str(game['appid']),None));launch.set_sensitive(not self.options.demo);f.append(launch)
        maintenance=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=8,row_spacing=8,max_children_per_line=2,min_children_per_line=1,homogeneous=True)
        pages.get_child_by_name('Enhancements').append(maintenance)
        for title,operation in [('Add / Update Enhancements','install'),('Repair Files','repair'),('Remove Enhancements','uninstall'),('Reset Settings','reset')]:
            action=button(title,lambda _,op=operation:self.launch_action(op,targets=[game]))
            if operation=='install':action.add_css_class('suggested-action')
            if operation=='uninstall':action.add_css_class('bulk-remove')
            action.set_sensitive((operation in ('uninstall','reset') and game.get('installed',False)) or (operation in ('install','repair') and not game.get('blocked') and bool(self.hardware_info and self.hardware_info['ready'])))
            maintenance.insert(action,-1)
    def record_test(self,game,finish=False):
        def done(record):
            game['test_record']=record;self.details(game)
            if not finish and game.get('source')=='Steam' and str(game.get('appid','')).isdigit():
                Gio.AppInfo.launch_default_for_uri('steam://rungameid/'+str(game['appid']),None)
            self.toast('Logs captured. Record your result and save notes.' if finish else 'Test started. Launch your game normally, then return here to finish.')
        self.start('Collecting test logs' if finish else 'Starting test record',lambda:(game_notes.finish if finish else game_notes.start)(self.service.config,game),done)
    def show_reports(self,*_):
        d,b,f=self.open_panel('Library status & reports')
        totals=Counter(g.get('test_record',{}).get('status','Untested') for g in self.games)
        b.append(label(' · '.join(f'{totals[state]} {state.lower()}' for state in game_notes.STATES),'heading'))
        b.append(label('Export includes your notes, game paths, package identity and captured logs. Review the ZIP before sharing. Nothing is uploaded.','dim-label'))
        for game in self.games:
            record=game.get('test_record',{});item=row(game['name'],record.get('status','Untested')+(' · test in progress' if record.get('active') else ''))
            item.add_suffix(button('Open',lambda _,g=game:self.details(g)));b.append(item)
        export=button('Export support ZIP',lambda *_:self.start('Exporting report',lambda:game_notes.export(self.service.config,self.games),lambda p:(self.toast('Saved '+str(p)),Gio.AppInfo.launch_default_for_uri(p.parent.as_uri(),None))),'forge-primary');export.set_sensitive(not self.options.demo);f.append(export)
    def launch_action(self,operation,entire=False,targets=None,visual_settings=None):
        if self.busy and self.task_kind!='art':return
        rows=targets if targets is not None else list(self.games) if entire else [e['data'] for e in self.cards.values() if e['check'].get_active()]
        if entire and operation in ('install','repair'):rows=[g for g in rows if g.get('test_record',{}).get('status')!='Bench']
        if operation=='reset':rows=[g for g in rows if g.get('installed')]
        if not rows:self.toast('No eligible games selected.');return
        applying_strength=operation=='reset' and entire and self.defaults_changed()
        title={'install':'Add Enhancements','repair':'Repair Files','uninstall':'Remove Enhancements','reset':'Reset Settings'}[operation]+(' entire library' if entire else ' selected games')
        if applying_strength:title='Apply Settings to Library'
        elif visual_settings is not None:title='Apply Game Settings'
        self.operation_previous=targets[0] if targets and len(targets)==1 else None
        self.operation_cancel=threading.Event();self.operation_executing=False
        d,b,f=self.open_panel(title,width=560,height=300);d.set_can_close(False)
        self.add_cancel(f)
        self.job_label=label(f'Checking {len(rows)} games…','heading');b.append(self.job_label)
        b.append(label('Your current files are backed up before changes.','dim-label'))
        pulse=Gtk.ProgressBar();b.append(pulse)
        def animate():
            if self.dialog!=d or not self.busy:return False
            pulse.pulse();return True
        GLib.timeout_add(160,animate)
        if self.options.demo:
            preview={'kind':'batch','operation':operation,'title':title,'plans':[],'rows':[{'name':r['name'],'detail':'2 file changes'} for r in rows[:4]],'blocked':[{'name':'Example protected game','reason':'Another graphics tool is installed.'}]}
            self.action_ready(preview,d,b,f,False);return
        mode=self.mode;adopt=self.settings['recognize_previous'];values=self.tuning_values(self.tuning_widgets) if entire and operation=='reset' else visual_settings
        self.start('Preparing '+title.lower(),lambda:self.service.prepare(rows,mode,operation,adopt,visual_settings=values,save_defaults=entire and operation=='reset'),lambda review:self.action_ready(review,d,b,f,entire))
    def add_cancel(self,footer):
        def cancel(w):
            self.operation_cancel.set();w.set_sensitive(False);w.set_label('Undoing…')
            if self.job_label:self.job_label.set_text('Finishing the current game safely, then undoing changes…')
            if not self.busy:
                self.dialog.force_close();self.dialog=None
                if self.operation_previous:self.details(self.operation_previous)
        footer.append(button('Cancel',cancel))

    def action_ready(self,review,d,b,f,automatic=False):
        self.review=review;clear(b);clear(f);self.job_label=None;d.set_can_close(True)
        if getattr(self,'operation_cancel',None) is not None:self.add_cancel(f)
        g=Adw.PreferencesGroup(title=f"Ready · {len(review['rows'])}");b.append(g)
        for item in review['rows']:g.add(row(item['name'],item['detail']))
        if review['blocked']:
            skipped=Adw.PreferencesGroup(title=f"Skipped · {len(review['blocked'])}");b.append(skipped)
            for item in review['blocked']:skipped.add(row(item['name'],item['reason']))
        if not review['rows']:b.append(label('No file changes can be applied.'));f.append(button('Close',lambda *_:d.close()));return
        apply=button('Apply Settings' if review.get('operation')=='reset' else 'Remove Enhancements' if review.get('operation')=='uninstall' else 'Apply to Ready Games',lambda *_:self.execute(review,d,b,f),'forge-primary');apply.set_sensitive(not self.options.demo);f.append(apply)
        if self.options.demo:b.append(label('Preview mode · all file changes are disabled.','dim-label'))
        elif automatic:self.execute(review,d,b,f)
    def execute(self,review,d,b,f):
        if self.options.demo:return
        clear(f);clear(b);d.set_can_close(False);self.job_label=label('Applying changes…','heading');b.prepend(self.job_label)
        if review.get('kind')=='engine':
            self.operation_executing=True;review['cancel_event']=self.operation_cancel;self.add_cancel(f)
        indicator=Gtk.Spinner(spinning=True,width_request=32,height_request=32,halign=Gtk.Align.CENTER);b.prepend(indicator)
        self.start('Applying changes',lambda:self.service.execute(review),lambda path:self.completed(path,d,b,f))
    def completed(self,path,d,b,f):
        self.operation_cancel=None
        self.job_label=None;d.set_can_close(True);clear(b);clear(f)
        if self.review and self.review.get('save_defaults'):self.defaults_applied(self.review['save_defaults'])
        b.append(label('Done.','hero-title'));b.append(label('Your changes are complete. Reset Settings keeps a backup of the previous INI. Remove Enhancements restores the original installation files.'))
        record=label(str(path),'dim-label');record.set_selectable(True);b.append(record)
        f.append(button('Back to library',lambda *_:(d.close(),self.scan()),'forge-primary'))
    def show_activity(self,*_):
        d,b,f=self.open_panel('Activity');text=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR);text.get_buffer().set_text('\n'.join(self.log) or 'No activity yet.');b.append(text);f.append(button('Close',lambda *_:d.close()))
    def show_settings(self,*_):
        d,b,f=self.open_panel('Settings',width=940,height=640)
        if os.environ.get('APPIMAGE'):
            b.append(label('Desktop app · 0.5.8','heading'))
            b.append(button('Install / update this build',self.install_desktop,'forge-primary'))
            b.append(label('Keep this build in your app menu. Repeating this with a new AppImage updates it; your games and backups stay separate.','dim-label'))
        source_group=Adw.PreferencesGroup(title='Graphics provider',description='Exact versions are pinned. Uninstall before changing providers. Updates arrive with new app builds.');b.append(source_group)
        provider_choice={'value':self.settings.get('runtime_provider','y4my')};providers=Gtk.Box(spacing=0);providers.add_css_class('linked');first=None
        for key,title in [('y4my','y4my Multipass'),('dlss-unlocked','DLSS-Unlocked')]:
            toggle=Gtk.ToggleButton(label=title)
            if first:toggle.set_group(first)
            else:first=toggle
            toggle.set_active(provider_choice['value']==key);toggle.connect('toggled',lambda w,k=key:provider_choice.update(value=k) if w.get_active() else None);providers.append(toggle)
        provider_row=row('Installer source','DLSS-Unlocked: separate NR Only and MFG Only pipelines. Uninstall before switching.');provider_row.add_suffix(providers);source_group.add(provider_row)
        for pin in __import__('engine_bridge').providers().values():source_group.add(row(pin['name'],pin['tag']+' · '+pin['commit'][:12]))
        source_group.add(row('Effects start enabled','Your selected pipeline activates on the next game launch. No OptiScaler menu required.'))
        nr_path=Adw.EntryRow(title='Local NR DLL for y4my');nr_path.set_text(self.settings.get('nr_runtime',''));source_group.add(nr_path)
        appearance=Adw.PreferencesGroup(title='Library appearance');b.append(appearance)
        view_group=Gtk.Box(spacing=0);view_group.add_css_class('linked');view_choice={'value':self.settings.get('library_view','posters')};first=None
        for title,key in [('Posters','posters'),('Wide capsules','capsules'),('List','list')]:
            toggle=Gtk.ToggleButton(label=title)
            if first:toggle.set_group(first)
            else:first=toggle
            toggle.set_active(view_choice['value']==key)
            toggle.connect('toggled',lambda widget,value=key:view_choice.update(value=value) if widget.get_active() else None);view_group.append(toggle)
        appearance.add(row('Library layout','Posters show more games at once.'))
        b.append(view_group)
        scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,70,150,10);scale.set_value(self.settings.get('art_scale',100));scale.set_digits(0);scale.set_draw_value(True)
        b.append(label('Artwork size (%)','heading'));b.append(scale)
        defaults=Adw.PreferencesGroup(title='Default install profile');b.append(defaults)
        default_nr=Adw.SwitchRow(title='Start with NR + MFG',subtitle='Off preserves your library profile choice.',active=self.settings.get('default_profile')=='nr-mfg');defaults.add(default_nr)
        dark=Adw.SwitchRow(title='Prefer dark appearance',active=self.settings['dark']);appearance.add(dark)
        art=Adw.SwitchRow(title='SteamGridDB posters',subtitle='Automatic, keyless artwork with Steam fallback and offline caching.',active=self.settings['online_art']);appearance.add(art)
        metadata=Adw.SwitchRow(title='Game metadata',subtitle='Fetch descriptions, developers, genres and release dates from Steam.',active=self.settings['steam_metadata']);appearance.add(metadata)
        install=Adw.PreferencesGroup(title='Installation');b.append(install)
        adopt=Adw.SwitchRow(title='Recognize previous installs',subtitle='Allow updating an identifiable OptiScaler install from another installer.',active=self.settings['recognize_previous']);install.add(adopt)
        network=Adw.ExpanderRow(title='Artwork downloads',subtitle='Existing artwork is kept until you refresh it')
        cache=Gtk.SpinButton.new_with_range(1,30,1);cache.set_value(self.settings.get('cache_days',7));cache.set_valign(Gtk.Align.CENTER)
        cache_row=row('Refresh cached metadata after (days)');cache_row.add_suffix(cache);
        timeout=Gtk.SpinButton.new_with_range(5,30,1);timeout.set_value(self.settings.get('network_timeout',10));timeout.set_valign(Gtk.Align.CENTER)
        timeout_row=row('Request timeout (seconds)');timeout_row.add_suffix(timeout);network.add_row(timeout_row)
        advanced=Adw.PreferencesGroup(title='Advanced');advanced.add(network);advanced.add(button('Refresh artwork',lambda *_:self.fetch_media(True)));b.append(advanced)
        host=self.hardware_info or {'reason':'Hardware check not finished'}
        system=Adw.PreferencesGroup(title='System compatibility');b.append(system)
        for title,key in [('Graphics card','gpu'),('Driver','driver'),('Video memory','vram'),('Processor','cpu'),('System','architecture')]:
            if host.get(key):system.add(row(title,host[key]))
        system.add(row('Hardware check',host.get('reason','Not checked')))
        future=Adw.PreferencesGroup(title='Custom repositories · coming later',description='Select a supported provider above. Arbitrary repositories are not enabled.');b.append(future)
        future.add(row('Supported sources','y4my Multipass / DLSS-Unlocked · pinned releases'))
        repo=Adw.EntryRow(title='Custom OptiScaler repository');repo.set_text('https://github.com/owner/repository');repo.set_sensitive(False);future.add(repo)
        detect=button('Understand repository · coming later',lambda *_:None);detect.set_sensitive(False);b.append(detect)
        b.append(button('Library status & reports',self.show_reports))
        maintenance=Adw.PreferencesGroup(title='Undo and removal tools');b.append(maintenance)
        undo=row('Undo previous changes','Restore a recorded install, uninstall or cleanup.');undo.add_suffix(button('Browse',lambda *_:self.show_undo()));maintenance.add(undo)
        old=row('Remove old NR files','Global DLSS5 cleanup with recovery copies.');old.add_suffix(button('Review',lambda *_:self.show_cleanup()));maintenance.add(old)
        items=[];child=b.get_first_child()
        while child:items.append(child);child=child.get_next_sibling()
        def between(first,last):return items[items.index(first):items.index(last)]
        self.organize_pages(b,[('Graphics',between(source_group,appearance)+[defaults,install]),
            ('Library',[appearance,view_group,scale.get_prev_sibling(),scale,advanced]),
            ('System',items[:items.index(source_group)]+[system]),('Recovery',[maintenance])])
        def save(*_):
            self.settings.update({'runtime_provider':provider_choice['value'],'enable_effects':True,'nr_runtime':nr_path.get_text().strip(),'library_view':view_choice['value'],'art_scale':int(scale.get_value()),'cache_days':cache.get_value_as_int(),'network_timeout':timeout.get_value_as_int(),'default_profile':'nr-mfg' if default_nr.get_active() else self.mode if self.mode!='nr-mfg' else 'mfg-only','dark':dark.get_active(),'online_art':art.get_active(),'steam_metadata':metadata.get_active(),'recognize_previous':adopt.get_active()})
            self.nr_only.set_sensitive(provider_choice['value']=='dlss-unlocked')
            if provider_choice['value']!='dlss-unlocked' and self.mode=='nr-only':self.mfg.set_active(True)
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK if self.settings['dark'] else Adw.ColorScheme.DEFAULT)
            self.view_buttons[self.settings['library_view']].set_active(True)
            if self.options.demo:d.close();self.show_games(self.games,False);return
            self.start('Saving settings',lambda:library_media.save_settings(self.service.config,self.settings),lambda _:(d.close(),self.show_games(self.games,False),self.fetch_media()))
        f.append(button('Save settings',save,'forge-primary'))
    def install_desktop(self,*_):
        import desktop_install
        self.start('Installing desktop app',desktop_install.install,lambda _:self.toast('RTXForge installed in your app menu. This build is now the default.'))
    def show_undo(self):
        if self.options.demo:
            d,b,f=self.open_panel('Undo previous changes');b.append(label('Your install and uninstall backups will appear here.'));return
        self.start('Finding previous changes',self.service.recoveries,self.undo_loaded)
    def undo_loaded(self,records):
        d,b,f=self.open_panel('Undo previous changes');g=Adw.PreferencesGroup(title='Recorded changes');b.append(g)
        for record in records:
            item=row(record['name'],record['detail']);item.add_suffix(button('Review',lambda _,r=record:self.start('Checking restore',lambda:self.service.review_recovery(r),lambda review:self.action_ready(review,d,b,f))));g.add(item)
        if not records:b.append(label('No recorded changes yet.'))
    def show_cleanup(self):
        if self.options.demo:return
        d,b,f=self.open_panel('Remove old NR files');b.append(label('Checking global cleanup candidates…'))
        self.start('Scanning old NR files',self.service.review_cleanup,lambda review:self.action_ready(review,d,b,f))
    def capture(self,name):
        paint=Gtk.WidgetPaintable.new(self);snapshot=Gtk.Snapshot();paint.snapshot(snapshot,self.get_width(),self.get_height());node=snapshot.to_node();rect=Graphene.Rect();rect.init(0,0,self.get_width(),self.get_height());texture=self.get_renderer().render_texture(node,rect);texture.save_to_png(str(ROOT/'dist'/name))
    def smoke_library(self):
        try:
            assert self.reset_all.get_label()=='Reset All Settings'
            for key,widget in self.tuning_widgets.items():
                original=widget.get_selected() if key=='mfg_multiplier' else widget.get_value()
                if key=='mfg_multiplier':widget.set_selected(0)
                else:widget.set_value(0)
                assert self.reset_all.get_label()=='Apply Settings'
                if key=='mfg_multiplier':widget.set_selected(original)
                else:widget.set_value(original)
                assert self.reset_all.get_label()=='Reset All Settings'
            GLib.timeout_add(250,self.smoke_library_ready)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_library_ready(self):
        try:
            self.capture('gnome-library.png')
            self.search.set_text('Cyberpunk');self.select_all(True);assert all(e['check'].get_active() for e in self.cards.values())
            self.nr.set_active(True);assert self.mode=='nr-mfg'
            game={**self.games[0],'feature_mode':'nr-mfg','profile':'NR + MFG','nr_strength':'strong','sharpening_strength':'strong','mfg_multiplier':2}
            self.details(game)
            assert not self.detail_apply_settings.get_sensitive()
            self.detail_tuning_widgets['sharpening_strength'].set_value(0)
            assert self.detail_apply_settings.get_sensitive()
            assert self.tuning_values(self.tuning_widgets)['sharpening_strength']=='strong'
            GLib.timeout_add(700,self.smoke_action)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_action(self):
        try:
            # Scroll the details content so the settings controls are visible.
            content=self.dialog.get_child();scroll=content.get_first_child().get_next_sibling()
            self.detail_pages.set_visible_child_name('Enhancements');scroll.get_vadjustment().set_value(0)
            GLib.timeout_add(300,self.smoke_game_settings)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_game_settings(self):
        try:self.capture('gnome-game-settings.png');self.show_settings();GLib.timeout_add(700,self.smoke_settings)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_settings(self):
        try:self.capture('gnome-settings.png');print('PASS: global dirty labels, independent per-game controls, selection and Settings; demo writes disabled',flush=True)
        except Exception:traceback.print_exc();self.get_application().exit_code=1
        self.get_application().quit();return False

class Application(Adw.Application):
    def __init__(self,options):super().__init__(application_id='io.github.lrnolivia.RTXForge',flags=Gio.ApplicationFlags.NON_UNIQUE);self.options=options;self.exit_code=0
    def do_activate(self):
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(str(ROOT/'gui/icons'));Gtk.Window.set_default_icon_name('io.github.lrnolivia.RTXForge')
        provider=Gtk.CssProvider();provider.load_from_data(CSS);Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window=Window(self,self.options);self.window.present()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--provider',type=Path);parser.add_argument('--demo',action='store_true');parser.add_argument('--smoke-test',action='store_true');options=parser.parse_args()
    if options.smoke_test:options.demo=True
    app=Application(options);result=app.run([sys.argv[0]]);return app.exit_code or result
if __name__=='__main__':sys.exit(main())
