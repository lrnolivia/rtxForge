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
def artwork_accent(path,color=None):
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
    color=color or '#%02x%02x%02x'%rgb;name='art-'+color[1:]
    if name not in ACCENT_PROVIDERS:
        provider=Gtk.CssProvider()
        provider.load_from_data((f'.game-card.{name}.selected {{ border-color: {color}; box-shadow: 0 2px 12px alpha({color},0.28); }} '
            f'.game-card.{name}:hover {{ border-color: alpha({color},0.65); }} '
            f'.{name} check:checked, .{name} button.suggested-action {{ background: {color}; color: white; }} '
            f'.{name} .game-status {{ border-left: 3px solid {color}; background: alpha({color},0.12); }} '
            f'.{name} toggle-group toggle:checked {{ background: {color}; color: white; }} '
            f'.{name} .game-details {{ color: {color}; }} '
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
.dashboard-fade { background: linear-gradient(to bottom, @window_bg_color, alpha(@window_bg_color,0)); }
.settings-navigation { background: alpha(@window_fg_color,0.055); padding: 12px; }
.settings-navigation row { padding: 0; margin: 2px 0; border-radius: 8px; }
.settings-navigation row box { padding: 10px 12px; }
.settings-content { padding: 24px; }
.floating-tabs { padding: 5px; border-radius: 18px; background: alpha(#151518,0.78); color: white; }
.floating-tabs.light { background: alpha(white,0.82); color: #202024; }
.game-banner { background: #252529; }
.banner-shade { background: linear-gradient(to bottom, alpha(black,0.38), alpha(black,0.02) 38%, alpha(@window_bg_color,0.25) 65%, @window_bg_color 100%); }
.game-banner-title { color: @window_fg_color; font-size: 30px; font-weight: 500; }
.progress-content { padding: 22px; color: white; background: linear-gradient(to right, alpha(black,0.82), alpha(black,0.55)); }
.progress-content label { color: white; }
.color-swatch { min-width: 32px; min-height: 32px; border-radius: 99px; padding: 0; }

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
.forge-primary { background: #76b900; color: white; font-weight: 500; padding: 10px 18px; }
.forge-primary:hover { background: #b5ef50; }
.bulk-remove { color: #ff928c; padding: 10px 16px; }
.pill { border-radius: 99px; padding: 5px 10px; background: alpha(@window_fg_color,0.07); font-size: 11px; }
.game-card { border-radius: 14px; background: @card_bg_color; border: 2px solid alpha(@window_fg_color,0.06); }
.game-card.selected { border-color: #76b900; box-shadow: 0 2px 12px alpha(#76b900,0.22); }
.poster-button { padding: 0; border: 0; border-radius: 11px 11px 0 0; }
.poster { border-radius: 11px 11px 0 0; background: #242426; }
.poster-fallback { color: #a5a5a8; padding: 22px; font-weight: 800; font-size: 19px; }
.card-info { padding: 10px 12px 12px; }
.card-title { font-weight: 500; font-size: 15px; letter-spacing: 0; }
.card-meta { font-size: 10px; opacity: 0.7; }
.cover-badge { background: alpha(black,0.65); color: white; text-shadow: 0 1px 3px black; padding: 5px 8px; border-radius: 8px; font-size: 10px; font-weight: 700; }
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
.progress-title { font-size: 22px; font-weight: 600; }
button, button label, toggle-group toggle { font-weight: 500; }
button.suggested-action, button.suggested-action label { color: white; font-weight: 500; }
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
        controls=Gtk.Box(spacing=18);controls.add_css_class('control-pod');top.append(controls)
        profile_text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True,valign=Gtk.Align.CENTER);controls.append(profile_text)
        profile_text.append(label('Enhancement Mode','heading'))
        self.profile_note=label('','dim-label');self.profile_note.set_ellipsize(Pango.EllipsizeMode.END);self.profile_note.set_lines(1);self.profile_note.set_max_width_chars(42);profile_text.append(self.profile_note)
        self.profile_group=Adw.ToggleGroup(homogeneous=True,valign=Gtk.Align.CENTER)
        for mode,title in [('nr-only','NR Only'),('mfg-only','MFG Only'),('nr-mfg','NR + MFG')]:
            toggle=Adw.Toggle(name=mode,label=title,child=profile_label(mode,title));self.profile_group.add(toggle)
            if mode=='nr-only':self.nr_only=toggle;toggle.set_enabled(self.settings.get('runtime_provider','y4my')=='dlss-unlocked')
        controls.append(self.profile_group)
        self.profile_group.connect('notify::active-name',self.profile_changed)
        self.profile_group.set_active_name(self.settings.get('default_profile','mfg-only'));self.profile_changed(self.profile_group)
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
        margins(viewbar,18);viewbar.set_margin_top(0);viewbar.set_margin_bottom(14);viewbar.set_margin_top(20);outer.append(viewbar)
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);library_stage=Gtk.Overlay(vexpand=True);library_stage.set_child(scroll);outer.append(library_stage)
        edge=Gtk.Box(height_request=20,valign=Gtk.Align.START,can_target=False);edge.add_css_class('dashboard-fade');library_stage.add_overlay(edge)
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
    def profile_changed(self,group,*_):
        self.mode=group.get_active_name() or 'mfg-only'
        self.profile_note.set_text({'nr-only':'Neural Rendering','nr-mfg':'Neural Rendering and frame generation','mfg-only':'Native frame generation'}[self.mode])
    def tuning_controls(self,initial):
        box=Gtk.Box(spacing=8);widgets={}
        for key,title in [('nr_strength','NR Strength'),('sharpening_strength','Sharpening')]:
            pod=Gtk.Box(hexpand=True);pod.add_css_class('control-pod');box.append(pod)
            group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True,valign=Gtk.Align.CENTER);pod.append(group)
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
        pod=Gtk.Box();pod.add_css_class('control-pod');box.append(pod)
        group=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,valign=Gtk.Align.CENTER);pod.append(group);group.append(label('MFG','heading'))
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
        if hasattr(self,'profile_group'):self.controls()
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
        for entry in self.cards.values():entry['reset'].set_sensitive(enabled)
        for i,b in enumerate(self.action_buttons):b.set_sensitive(enabled and (compatible or i in (2,3)) and any(v['check'].get_active() for v in self.cards.values()))
        for b in (self.refresh,self.add,self.profile_group,*self.view_buttons.values()):b.set_sensitive(enabled)
    def event(self,event):
        if event['kind']=='progress':
            self.status.set_text(event['label']);self.update_progress_art(event['label'])
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
        def run_task():
            try:
                with ui.report_to(lambda e:GLib.idle_add(self.event,e)):result=action()
            except Exception as ex:GLib.idle_add(self.finished,None,done,(str(ex),traceback.format_exc()))
            else:GLib.idle_add(self.finished,result,done,None)
        threading.Thread(target=run_task,daemon=False).start()
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
    def open_panel(self,title,width=730,height=620,show_close=True):
        if self.dialog:self.dialog.force_close()
        dialog=Adw.Dialog(title=title,content_width=width,content_height=height);self.dialog=dialog;self.job_label=None
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);dialog.set_child(box)
        header=Adw.HeaderBar();header.set_show_end_title_buttons(show_close);header.set_show_start_title_buttons(False);header.set_title_widget(Adw.WindowTitle(title=title));box.append(header)
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);box.append(scroll)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);body.add_css_class('panel-body');scroll.set_child(body)
        foot=Gtk.Box(spacing=10,halign=Gtk.Align.END);margins(foot,16);box.append(foot)
        dialog.present(self);return dialog,body,foot
    def organize_pages(self,body,sections):
        clear(body);body.remove_css_class('panel-body');body.set_vexpand(True)
        stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,hexpand=True,vexpand=True)
        nav=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,width_request=200,valign=Gtk.Align.FILL)
        nav.add_css_class('settings-navigation')
        icons={'Graphics':'video-display-symbolic','Library':'applications-games-symbolic','System':'computer-symbolic','Recovery':'document-revert-symbolic'}
        layout=Gtk.Box(vexpand=True);layout.append(nav);layout.append(stack);body.append(layout)
        switcher=Adw.ToggleGroup(homogeneous=True);body.prepend(switcher)
        for title,items in sections:
            page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20);page.add_css_class('settings-content')
            for item in items:page.append(item)
            scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True);scroll.set_child(page);stack.add_titled(scroll,title,title)
            item=Gtk.ListBoxRow();line=Gtk.Box(spacing=12,valign=Gtk.Align.CENTER);line.append(Gtk.Image.new_from_icon_name(icons.get(title,'preferences-system-symbolic')));line.append(label(title));item.set_child(line);item.page_name=title;nav.append(item)
            switcher.add(Adw.Toggle(name=title,label=title))
        nav.connect('row-selected',lambda _,r:stack.set_visible_child_name(r.page_name) if r else None)
        switcher.connect('notify::active-name',lambda w,*_:stack.set_visible_child_name(w.get_active_name()))
        nav.select_row(nav.get_row_at_index(0))
        def responsive(*_):
            wide=body.get_width()>=740
            nav.set_visible(wide);switcher.set_visible(not wide)
            return True
        body.add_tick_callback(responsive)
        return stack

    def error(self,message):
        d,b,f=self.open_panel('Could Not Finish',width=580,height=300,show_close=False);b.append(label(str(message)));f.append(button('Close',lambda *_:d.close()))
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
        width,height=(max(150,int(158*scale)),int(max(150,int(158*scale))*1.5)) if view=='posters' else (int(290*scale),int(136*scale)) if view=='capsules' else (54,81)
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
        reset=button('Details',lambda *_:self.details(game));reset.add_css_class('game-details')
        reset.set_tooltip_text('Open game details and settings')
        reset.set_sensitive(True);text.append(reset)
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
                game['accent_class']=artwork_accent(path,self.settings.get('game_accents',{}).get(game['game']));entry['widget'].add_css_class(game['accent_class'])
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
        if getattr(self,'art_loading',False):self.art_pending=True;return
        self.art_loading=True;self.cancel_art.clear();games=list(self.games);settings=dict(self.settings)
        def finished_art():
            self.art_loading=False
            if getattr(self,'art_pending',False):self.art_pending=False;self.fetch_media()
            return False
        def load():
            try:
                media=library_media.LibraryMedia(self.service.config,settings)
                for game in games:
                    if self.cancel_art.is_set():break
                    try:data=media.enrich(game,refresh)
                    except Exception:continue
                    GLib.idle_add(self.event,{'kind':'art','game':game['game'],'data':data})
            finally:GLib.idle_add(finished_art)
        threading.Thread(target=load,daemon=True).start()
    def details(self,game):
        d,b,f=self.open_panel(game['name'],width=860,height=700);b.remove_css_class('panel-body');b.set_spacing(0)
        if game.get('accent_class'):d.add_css_class(game['accent_class'])
        banner=Gtk.Overlay();banner.add_css_class('game-banner');b.append(banner)
        image=Gtk.Picture(content_fit=Gtk.ContentFit.COVER,can_shrink=True,height_request=360)
        if game.get('hero'):
            try:image.set_paintable(Gdk.Texture.new_from_filename(game['hero']))
            except Exception:pass
        banner.set_child(image);shade=Gtk.Box();shade.add_css_class('banner-shade');banner.add_overlay(shade)
        self.detail_game=game['game'];self.detail_dialog=d;self.detail_banner=image
        tabs=Adw.ToggleGroup(homogeneous=True,halign=Gtk.Align.CENTER,valign=Gtk.Align.START);tabs.add_css_class('floating-tabs');margins(tabs,16);banner.add_overlay(tabs)
        if game.get('hero'):
            try:
                sample=GdkPixbuf.Pixbuf.new_from_file_at_scale(game['hero'],1,1,False).get_pixels()
                if sum(sample[:3])/3>150:tabs.add_css_class('light')
            except Exception:pass
        heading=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5,valign=Gtk.Align.END);margins(heading,24);heading.append(label(game['name'],'game-banner-title'));banner.add_overlay(heading)
        mode_name=game.get('profile') if game.get('installed') else 'Ready to Enhance'
        status=label(mode_name or 'Ready to Enhance','cover-badge');status.set_halign(Gtk.Align.START);heading.append(status)
        pages=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=220,hexpand=True);pages.set_vhomogeneous(False);b.append(pages)
        content={}
        for name in ('Overview','Enhancements','Notes','Appearance'):
            page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);margins(page,24);content[name]=page;pages.add_titled(page,name,name);tabs.add(Adw.Toggle(name=name,label=name))
        tabs.connect('notify::active-name',lambda w,*_:pages.set_visible_child_name(w.get_active_name()))
        pages.connect('notify::visible-child-name',lambda w,*_:tabs.set_active_name(w.get_visible_child_name()))
        self.detail_pages=pages
        overview=content['Overview']
        if game.get('description'):overview.append(label(game['description']))
        info=Adw.PreferencesGroup(title='Game Information');overview.append(info)
        for title,value in [('Library',game.get('library')),('Location',game['game']),('Compatibility',game.get('blocked') or 'Available'),('Developer',game.get('developers')),('Release',game.get('release'))]:
            if value:info.add(row(title,value))
        enhancements=content['Enhancements'];installed=game.get('installed',False)
        tuning,widgets=self.tuning_controls(game);enhancements.append(tuning)
        mode=game.get('feature_mode') or {'NR Only':'nr-only','MFG Only':'mfg-only'}.get(game.get('profile'),'nr-mfg')
        for key,w in widgets.items():w.set_sensitive(installed and not (key=='nr_strength' and mode=='mfg-only') and not (key=='mfg_multiplier' and mode=='nr-only'))
        apply=button('Apply Settings',lambda *_:self.launch_action('reset',targets=[game],visual_settings=self.tuning_values(widgets)),'suggested-action');apply.set_halign(Gtk.Align.END);enhancements.append(apply)
        def changed(*_):apply.set_sensitive(installed and any(v!=game.get(k) for k,v in self.tuning_values(widgets).items() if widgets[k].get_sensitive()))
        for key,w in widgets.items():w.connect('notify::selected' if key=='mfg_multiplier' else 'value-changed',changed)
        changed();self.detail_tuning_widgets=widgets;self.detail_apply_settings=apply
        maintenance=Adw.PreferencesGroup(title='Installation');enhancements.append(maintenance)
        for title,subtitle,op in [('Install Enhancements','Add or update the selected enhancement mode.','install'),('Repair Files','Replace damaged enhancement files.','repair'),('Reset Settings','Apply your library defaults to this game.','reset'),('Remove Enhancements','Restore the original files.','uninstall')]:
            item=row(title,subtitle);action=button('Install' if op=='install' else 'Repair' if op=='repair' else 'Reset' if op=='reset' else 'Remove',lambda _,o=op:self.launch_action(o,targets=[game]));action.set_valign(Gtk.Align.CENTER)
            action.set_sensitive(installed if op in ('reset','uninstall') else not game.get('blocked') and bool(self.hardware_info and self.hardware_info['ready']))
            if op=='uninstall':action.add_css_class('destructive-action')
            item.add_suffix(action);maintenance.add(item)
        notes_page=content['Notes'];record=game.get('test_record',{'status':'Untested','notes':''});choice=Gtk.DropDown.new_from_strings(list(game_notes.STATES));choice.set_selected(list(game_notes.STATES).index(record.get('status','Untested')));choice.set_valign(Gtk.Align.CENTER)
        group=Adw.PreferencesGroup(title='Your Notes');notes_page.append(group);item=row('Test Result','Bench excludes this game from bulk installation and repair.');item.add_suffix(choice);group.add(item)
        notes=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=100);notes.get_buffer().set_text(record.get('notes',''));notes_page.append(notes)
        def save_notes(*_):
            buf=notes.get_buffer();current=dict(record);current.update(status=list(game_notes.STATES)[choice.get_selected()],notes=buf.get_text(buf.get_start_iter(),buf.get_end_iter(),True))
            if not self.options.demo:game_notes.save(self.service.config,game['game'],current)
            game['test_record']=current;self.toast('Notes saved')
        actions=Gtk.Box(spacing=8);actions.append(button('Save Notes',save_notes,'suggested-action'));active=bool(record.get('active'));test=button('Finish Test' if active else 'Start Test',lambda *_:self.record_test(game,active));test.set_sensitive(not self.options.demo);actions.append(test);notes_page.append(actions)
        appearance=content['Appearance'];appearance.append(label('Accent Color','heading'));swatches=Gtk.Box(spacing=10);appearance.append(swatches)
        colors=[]
        for path in (game.get('poster'),game.get('capsule')):
            if not path:continue
            try:
                pix=GdkPixbuf.Pixbuf.new_from_file_at_scale(path,12,12,True);data=pix.get_pixels();stride=pix.get_rowstride();channels=pix.get_n_channels()
                for y,x in ((3,3),(6,6),(8,4)):
                    y=min(y,pix.get_height()-1);x=min(x,pix.get_width()-1);off=y*stride+x*channels;color='#%02x%02x%02x'%tuple(data[off:off+3])
                    if color not in colors:colors.append(color)
            except Exception:pass
        def set_color(color):
            self.settings.setdefault('game_accents',{})[game['game']]=color
            if not self.options.demo:library_media.save_settings(self.service.config,self.settings)
            old=game.get('accent_class')
            if old:d.remove_css_class(old)
            game['accent_class']=artwork_accent(game.get('poster') or game['capsule'],color);d.add_css_class(game['accent_class']);self.paint_card(self.cards[game['game']])
        for color in colors:
            swatch=button('',lambda _,c=color:set_color(c),'color-swatch');swatch.set_tooltip_text(color);provider=Gtk.CssProvider();provider.load_from_data(('button { background: '+color+'; }').encode());swatch.get_style_context().add_provider(provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+2);swatches.append(swatch)
        credits=Adw.PreferencesGroup(title='Artwork Credits');appearance.append(credits)
        for title,key in [('Poster','art_credit'),('Wide Capsule','capsule_credit'),('Hero','hero_credit')]:credits.add(row(title,game.get(key) or 'Source information unavailable'))
        for title,key in [('Poster Source','art_link'),('Hero Source','hero_link')]:
            if game.get(key):appearance.append(Gtk.LinkButton(uri=game[key],label=title,halign=Gtk.Align.START))
        f.append(button('Open Folder',lambda *_:Gio.AppInfo.launch_default_for_uri(Path(game['game']).as_uri(),None)))
        if game.get('appid') and game.get('source')=='Steam':
            play=button('Play',lambda *_:Gio.AppInfo.launch_default_for_uri('steam://rungameid/'+str(game['appid']),None),'suggested-action');play.set_sensitive(not self.options.demo);f.append(play)
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
        title={'install':'Install Enhancements','repair':'Repair Files','uninstall':'Remove Enhancements','reset':'Reset Settings'}[operation]
        if applying_strength:title='Apply Settings to Library'
        elif visual_settings is not None:title='Apply Game Settings'
        self.operation_previous=targets[0] if targets and len(targets)==1 else None
        self.operation_cancel=threading.Event();self.operation_executing=False
        d,b,f=self.open_panel(title,width=580,height=310,show_close=False);d.set_can_close(False)
        self.add_cancel(f)
        self.operation_games=rows
        self.progress_view(b,f'Checking {len(rows)} games…')
        if self.options.demo:
            preview={'kind':'batch','operation':operation,'title':title,'plans':[],'rows':[{'name':r['name'],'detail':'2 file changes'} for r in rows[:4]],'blocked':[{'name':'Example protected game','reason':'Another graphics tool is installed.'}]}
            self.action_ready(preview,d,b,f,False);return
        mode=self.mode;adopt=self.settings['recognize_previous'];values=self.tuning_values(self.tuning_widgets) if entire and operation=='reset' else visual_settings
        self.start('Preparing '+title.lower(),lambda:self.service.prepare(rows,mode,operation,adopt,visual_settings=values,save_defaults=entire and operation=='reset'),lambda review:self.action_ready(review,d,b,f,entire))
    def progress_view(self,body,message):
        clear(body);body.remove_css_class('panel-body')
        stage=Gtk.Overlay(height_request=180);body.append(stage)
        self.job_art=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=450)
        self.job_pictures=[Gtk.Picture(content_fit=Gtk.ContentFit.COVER,can_shrink=True) for _ in range(2)]
        for i,picture in enumerate(self.job_pictures):self.job_art.add_named(picture,str(i))
        stage.set_child(self.job_art);self.job_picture_index=0;self.job_current_game=None
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,valign=Gtk.Align.FILL);content.add_css_class('progress-content');stage.add_overlay(content)
        inner=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,valign=Gtk.Align.CENTER,vexpand=True);content.append(inner)
        self.job_label=label(message,'title-3');self.job_label.set_max_width_chars(42);inner.append(self.job_label)
        self.job_caption=label('Preparing your changes…');inner.append(self.job_caption)
        bar=Gtk.ProgressBar();inner.append(bar)
        self.update_progress_art('')
        dialog=self.dialog
        def animate():
            if self.dialog!=dialog or not self.job_label:return False
            bar.pulse();return True
        GLib.timeout_add(140,animate)
    def update_progress_art(self,message):
        if not getattr(self,'job_label',None) or not hasattr(self,'job_art'):return
        games=getattr(self,'operation_games',[])
        game=next((g for g in games if g['name'] in message),games[0] if games else None)
        if not game or game['game']==getattr(self,'job_current_game',None):return
        self.job_current_game=game['game'];path=game.get('hero') or game.get('capsule') or game.get('poster')
        if path:
            try:
                self.job_picture_index=1-self.job_picture_index;self.job_pictures[self.job_picture_index].set_paintable(Gdk.Texture.new_from_filename(path));self.job_art.set_visible_child_name(str(self.job_picture_index))
            except Exception:pass
        self.job_caption.set_text(game['name'])

    def add_cancel(self,footer):
        def cancel(w):
            self.operation_cancel.set();w.set_sensitive(False);w.set_label('Undoing…')
            if self.job_label:self.job_label.set_text('Finishing the current game safely, then undoing changes…')
            if not self.busy:
                self.dialog.force_close();self.dialog=None
                if self.operation_previous:self.details(self.operation_previous)
        footer.append(button('Cancel',cancel))

    def action_ready(self,review,d,b,f,automatic=False):
        self.review=review;clear(b);clear(f);b.add_css_class('panel-body');self.job_label=None;d.set_can_close(True)
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
        clear(f);d.set_can_close(False);self.progress_view(b,'Applying changes…')
        if review.get('kind')=='engine':
            self.operation_executing=True;review['cancel_event']=self.operation_cancel;self.add_cancel(f)
        self.start('Applying changes',lambda:self.service.execute(review),lambda path:self.completed(path,d,b,f))
    def completed(self,path,d,b,f):
        self.operation_cancel=None
        self.job_label=None;d.set_can_close(True);clear(b);clear(f)
        if self.review and self.review.get('save_defaults'):self.defaults_applied(self.review['save_defaults'])
        b.add_css_class('panel-body');b.append(label('All Done','title-2'))
        count=len(self.review.get('rows',[])) if self.review else 0
        b.append(label(f'{count} game'+('s' if count!=1 else '')+' updated.','dim-label'))
        self.log.append('Saved report: '+str(path))
        f.append(button('Done',lambda *_:(d.close(),self.scan()),'suggested-action'))
    def show_activity(self,*_):
        d,b,f=self.open_panel('Activity');text=Gtk.TextView(editable=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR);text.get_buffer().set_text('\n'.join(self.log) or 'No activity yet.');b.append(text);f.append(button('Close',lambda *_:d.close()))
    def show_settings(self,*_):
        d,b,f=self.open_panel('Settings',width=940,height=660)
        graphics=Adw.PreferencesGroup(title='Graphics Provider',description='Remove installed enhancements before switching providers.')
        provider_keys=['y4my','dlss-unlocked'];provider=Adw.ComboRow(title='Provider',model=Gtk.StringList.new(['y4my Multipass','DLSS-Unlocked']),selected=provider_keys.index(self.settings.get('runtime_provider','y4my')));graphics.add(provider)
        nr_path=Adw.EntryRow(title='Local NR DLL for y4my');nr_path.set_text(self.settings.get('nr_runtime',''));graphics.add(nr_path)
        defaults=Adw.PreferencesGroup(title='Installation')
        modes=['mfg-only','nr-mfg','nr-only'];profile=Adw.ComboRow(title='Default Mode',model=Gtk.StringList.new(['MFG Only','NR + MFG','NR Only']),selected=modes.index(self.settings.get('default_profile','mfg-only')));defaults.add(profile)
        adopt=Adw.SwitchRow(title='Recognize Existing Enhancements',subtitle='Allow updates to compatible installations from other tools.',active=self.settings['recognize_previous']);defaults.add(adopt)
        appearance=Adw.PreferencesGroup(title='Library Appearance')
        views=['posters','capsules','list'];view=Adw.ComboRow(title='Layout',model=Gtk.StringList.new(['Posters','Wide Capsules','List']),selected=views.index(self.settings.get('library_view','posters')));appearance.add(view)
        scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,70,150,10);scale.set_value(self.settings.get('art_scale',80));scale.set_draw_value(True);scale.set_digits(0);scale.set_size_request(170,-1);scale.set_valign(Gtk.Align.CENTER)
        item=row('Artwork Size');item.add_suffix(scale);appearance.add(item)
        dark=Adw.SwitchRow(title='Dark Appearance',active=self.settings['dark']);appearance.add(dark)
        artwork=Adw.PreferencesGroup(title='Artwork',description='Your Steam poster, capsule, and hero images take priority.')
        art=Adw.SwitchRow(title='Download Missing Artwork',subtitle='Use SteamGridDB and Steam when local images are unavailable.',active=self.settings['online_art']);artwork.add(art)
        metadata=Adw.SwitchRow(title='Download Game Information',subtitle='Descriptions, developers, and release dates from Steam.',active=self.settings['steam_metadata']);artwork.add(metadata)
        refresh=row('Refresh Artwork','Cached images remain available offline.');refresh_button=button('Refresh',lambda *_:self.fetch_media(True));refresh_button.set_valign(Gtk.Align.CENTER);refresh.add_suffix(refresh_button);artwork.add(refresh)
        timeout=Gtk.SpinButton.new_with_range(5,30,1);timeout.set_value(self.settings.get('network_timeout',10));timeout.set_valign(Gtk.Align.CENTER);item=row('Download Timeout','Seconds per request');item.add_suffix(timeout);artwork.add(item)
        system=Adw.PreferencesGroup(title='System');host=self.hardware_info or {}
        for title,key in [('Graphics Card','gpu'),('Driver','driver'),('Video Memory','vram'),('Processor','cpu'),('Architecture','architecture')]:
            if host.get(key):system.add(row(title,host[key]))
        system.add(row('Compatibility',host.get('reason','Not checked')))
        app=Adw.PreferencesGroup(title='Application');app.add(row('RTXForge','Version 0.5.9'))
        if os.environ.get('APPIMAGE'):
            item=row('Desktop Installation');action=button('Update App Menu',self.install_desktop);action.set_valign(Gtk.Align.CENTER);item.add_suffix(action);app.add(item)
        recovery=Adw.PreferencesGroup(title='Recovery')
        for title,subtitle,caption,fn in [('Previous Changes','Browse available recovery records.','Browse',lambda *_:self.show_undo()),('Old NR Files','Review legacy files before removal.','Review',lambda *_:self.show_cleanup()),('Library Reports','View test notes and export a support report.','Open',self.show_reports)]:
            item=row(title,subtitle);action=button(caption,fn);action.set_valign(Gtk.Align.CENTER);item.add_suffix(action);recovery.add(item)
        self.organize_pages(b,[('Graphics',[graphics,defaults]),('Library',[appearance,artwork]),('System',[system,app]),('Recovery',[recovery])])
        def save(*_):
            selected_provider=provider_keys[provider.get_selected()];selected_mode=modes[profile.get_selected()]
            if selected_provider=='y4my' and selected_mode=='nr-only':self.toast('NR Only requires DLSS-Unlocked.');return
            self.settings.update(runtime_provider=selected_provider,nr_runtime=nr_path.get_text().strip(),default_profile=selected_mode,library_view=views[view.get_selected()],art_scale=int(scale.get_value()),dark=dark.get_active(),online_art=art.get_active(),steam_metadata=metadata.get_active(),network_timeout=timeout.get_value_as_int(),recognize_previous=adopt.get_active())
            self.nr_only.set_enabled(selected_provider=='dlss-unlocked')
            self.profile_group.set_active_name(selected_mode)
            Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK if self.settings['dark'] else Adw.ColorScheme.DEFAULT)
            self.view_buttons[self.settings['library_view']].set_active(True)
            if self.options.demo:d.close();self.show_games(self.games,False);return
            self.start('Saving settings',lambda:library_media.save_settings(self.service.config,self.settings),lambda _:(d.close(),self.show_games(self.games,False),self.fetch_media()))
        f.append(button('Save Settings',save,'suggested-action'))
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
            self.profile_group.set_active_name('nr-mfg');assert self.mode=='nr-mfg'
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
        try:
            self.capture('gnome-settings.png')
            d,b,f=self.open_panel('Apply Settings',width=580,height=310,show_close=False)
            self.operation_games=self.games;self.operation_cancel=threading.Event();self.add_cancel(f);self.progress_view(b,'Applying Settings')
            GLib.timeout_add(500,self.smoke_progress)
        except Exception:traceback.print_exc();self.get_application().exit_code=1;self.get_application().quit()
        return False
    def smoke_progress(self):
        try:self.capture('gnome-progress.png');print('PASS: controls, game tabs, settings navigation, and progress; demo writes disabled',flush=True)
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
