"""Shared native package flow. Classic and New UI call this exact view."""
from pathlib import Path
import threading
from gi.repository import Adw, Gtk, Gio, GLib
import package_catalog as packages
import user_messages


def margins(widget, value=24):
    for side in ('top','bottom','start','end'):
        getattr(widget, 'set_margin_' + side)(value)


def show_packages(owner, fixture=None):
    dialog = Adw.Dialog(title='Packages', content_width=720, content_height=680)
    owner.packages_dialog = dialog
    alive={'value':True}
    dialog.connect('closed',lambda *_:alive.update(value=False))
    dialog.set_child(build_packages(owner, fixture, dialog.close, alive, header=True))
    dialog.present(owner)
    return dialog


def build_packages(owner, fixture=None, on_selected=None, alive=None, header=False, column=None):
    """The package view, as the Packages page or inside the Packages dialog."""
    alive = alive if alive is not None else {'value':True}
    toolbar = Adw.ToolbarView()
    back=Gtk.Button(icon_name='go-previous-symbolic',tooltip_text='Back to packages',visible=False)
    if header:
        bar=Adw.HeaderBar();toolbar.add_top_bar(bar)
        bar.pack_start(back)
    footer=Gtk.Box(spacing=16,visible=False);margins(footer,16);toolbar.add_bottom_bar(footer)
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    # As a page, one wide centered column like the Library; in the dialog, a reading width.
    clamp = Adw.Clamp(maximum_size=1600 if column else 760, tightening_threshold=1600 if column else 560)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    margins(box)
    clamp.set_child(box); scroll.set_child(clamp); toolbar.set_content(scroll)
    if column:
        box.set_margin_start(0); box.set_margin_end(0)
        def resized(adjustment, *_):
            width = int(adjustment.get_page_size())
            if width > 1:
                side = column(width); clamp.set_margin_start(side); clamp.set_margin_end(side)
        scroll.get_hadjustment().connect('notify::page-size', resized)
    if not header:
        back.set_halign(Gtk.Align.START); back.add_css_class('flat'); box.append(back)
    title = Gtk.Label(label='Packages', xalign=0)
    title.add_css_class('title-1'); box.append(title)
    intro = Gtk.Label(label='Use a supported package or inspect your own. Every game change is reviewed before it is applied.', xalign=0, wrap=True)
    intro.add_css_class('dim-label'); box.append(intro)
    status = Gtk.Label(label='Checking your system…', xalign=0, wrap=True)
    box.append(status)
    recommended = Adw.PreferencesGroup()
    cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24)
    recommended.add(cards)
    box.append(recommended)
    custom = Adw.PreferencesGroup(title='Your own package', description='ZIP archives. Files and instructions are inspected without running them.')
    choose = Adw.ActionRow(title='Add custom package', subtitle='Detect the layout and review suggested settings')
    pick = Gtk.Button(icon_name='document-open-symbolic', valign=Gtk.Align.CENTER)
    pick.set_tooltip_text('Choose package archive'); choose.add_suffix(pick); choose.set_activatable_widget(pick);custom.add(choose);box.append(custom)
    community=Adw.PreferencesGroup(title='Other community projects',description='Source discovery only. RTX 20/30/50 and additional layouts remain unvalidated by this app; the current deployment route targets RTX 40.')
    for source in packages.community_sources():
        item=Adw.ActionRow(title=source['name'],subtitle=source['note'])
        link=Gtk.LinkButton(uri=source['url'],label='View source',valign=Gtk.Align.CENTER)
        item.add_suffix(link);community.add(item)
    box.append(community)
    detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16);box.append(detail)

    def select(record, settings=None):
        try:
            owner.select_package(record, settings or {})
            if on_selected:on_selected()
        except Exception as ex:
            status.set_text(user_messages.friendly_error(ex));status.set_tooltip_text(str(ex))

    def render_catalog(host):
        if not alive['value']:return False
        if getattr(cards,'_resize_handler',None):
            scroll.get_hadjustment().disconnect(cards._resize_handler);cards._resize_handler=None
        while cards.get_first_child():cards.remove(cards.get_first_child())
        current=owner.settings.get('runtime_provider','dlss-unlocked')
        catalog=sorted(packages.catalog(host),key=lambda item:(item['id']!=current,not item['recommended']))
        active=next((item['name'] for item in catalog if item['id']==current),current)
        system='Preview system · NVIDIA RTX 4070 · no game writes' if owner.options.demo else host.get('gpu','System')+' · '+host.get('reason','')
        status.set_text(system+' · In use: '+active)
        def heading(title, description=None):
            block=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            label=Gtk.Label(label=title,xalign=0,wrap=True);label.add_css_class('title-3');block.append(label)
            if description:
                lead=Gtk.Label(label=description,xalign=0,wrap=True);lead.add_css_class('dim-label');block.append(lead)
            return block
        def package_card(title, version, summary, verified, caption, action, enabled=True):
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True)
            card.add_css_class('card')
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True);margins(content,20);card.append(content)
            name=Gtk.Label(label=title,xalign=0,wrap=True);name.add_css_class('heading');content.append(name)
            stamp=Gtk.Label(label=version,xalign=0,wrap=True);stamp.add_css_class('dim-label');content.append(stamp)
            text=Gtk.Label(label=summary,xalign=0,wrap=True,hexpand=True,vexpand=True,valign=Gtk.Align.START)
            text.set_max_width_chars(45);content.append(text)
            footer=Gtk.Box(spacing=12)
            marks=Gtk.Box(spacing=8,hexpand=True,valign=Gtk.Align.CENTER)
            for system in verified or ['experimental']:
                mark=Gtk.Box(spacing=5)
                if system!='experimental':mark.append(Gtk.Image(icon_name='rtx-os-'+system+'-symbolic',pixel_size=14))
                caption_label=Gtk.Label(label=system.upper());caption_label.add_css_class('caption');mark.append(caption_label)
                marks.append(mark)
            footer.append(marks)
            control=owner.make_action_button(caption,lambda *_:action() if action else None)
            control.set_sensitive(enabled);control.set_halign(Gtk.Align.END);footer.append(control);content.append(footer)
            return card
        names={'universal':'Universal MFG','integrated':'Integrated MFG unlock','mfg-unlock':'MFG Unlock'}
        pair=next((item for item in catalog if item['id']=='skynizz'),None)
        feeder=next((item for item in catalog if item['id']=='feeder'),None)
        paired=current=='skynizz'
        def curated(item):
            selected=item['id']==current
            title=item['name'];version=item['version']
            if item['id']=='skynizz':
                component=names.get(owner.settings.get('mfg_provider','universal'),'Universal MFG')
                title+=' + '+component;version+=' · '+component
            def use():
                select(item['id'])
                if alive['value']:render_catalog(host)
            return package_card(title,version,(item['summary'] if item['available'] else item['reason'])+'\nGraphics API: '+' · '.join(item.get('graphics_apis',[])),
                                item.get('verified'), 'In use' if selected else 'Use for DLSS games',use,item['available'] and not selected)
        columns=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20,homogeneous=False)
        nr=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True,valign=Gtk.Align.START)
        mfg=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,hexpand=True,valign=Gtk.Align.START)
        nr.append(heading('NR packages','Neural rendering for games with DLSS.'))
        if pair:nr.append(curated(pair))
        if feeder:
            nr.append(package_card(feeder['name'],feeder['version'],(feeder['summary'] if feeder['available'] else feeder['reason'])+'\nGraphics API: '+' · '.join(feeder.get('graphics_apis',[])),
                                   feeder.get('verified'),'Used automatically' if feeder['available'] else 'Unavailable',None,False))
        pair_name=pair['name'] if pair else 'the paired NR package'
        mfg.append(heading('MFG packages','Native NVIDIA frame generation for '+pair_name+'.'))
        summaries={
            'universal':"Keeps NVIDIA’s DLSS Frame Generation and unlocks 3x to 6x where the driver allows 2x. The multiplier and Dynamic MFG stay in the rtxForge Overlay.",
            'integrated':"Patches NVIDIA’s DLSS Frame Generation for 3x to 6x with no extra plugin.",
            'mfg-unlock':"Raises NVIDIA’s DLSS Frame Generation multiplier through ReShade. The rtxForge Overlay can’t change its multiplier while you play.",
        }
        for key,name in names.items():
            selected=paired and owner.settings.get('mfg_provider','universal')==key
            supported=key=='universal'
            def choose(value=key):
                owner.save_overlay_preference('mfg_provider',value)
                render_catalog(host)
            description=summaries[key]+(' Not available under Proton in this build.' if not supported else '')+'\nGraphics API: DirectX 12'
            version=(pair or {}).get('mfg_versions',{}).get(key) or ('Built into the bridge' if key=='integrated' else 'OptiScaler plugin' if key=='universal' else 'ReShade add-on')
            mfg.append(package_card(name,version,description,['windows'],
                                   'In use' if selected else 'Use with '+pair_name if supported else 'Unavailable',choose,paired and not selected and supported))
        columns.append(nr);columns.append(mfg)
        def resize_columns(adjustment,*_):
            horizontal=adjustment.get_page_size()>=1000
            columns.set_orientation(Gtk.Orientation.HORIZONTAL if horizontal else Gtk.Orientation.VERTICAL)
            columns.set_homogeneous(horizontal)
        cards._resize_handler=scroll.get_hadjustment().connect('notify::page-size',resize_columns)
        resize_columns(scroll.get_hadjustment())
        cards.append(columns)
        unified=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        unified.append(heading('Unified packages','NR and frame generation in one package, for games with DLSS.'))
        for item in catalog:
            if item['id'] not in ('skynizz','feeder'):unified.append(curated(item))
        cards.append(unified)
        return False

    def render_inspection(result):
        if not alive['value']:return False
        recommended.set_visible(False);custom.set_visible(False);community.set_visible(False);intro.set_visible(False)
        title.set_text('Review your package');back.set_visible(True)
        while detail.get_first_child():detail.remove(detail.get_first_child())
        summary=owner.review_list();detail.append(summary)
        summary.append(owner.review_entry(result['name'],result['confidence'],badge='Package',details='Detected format: '+result['family']+'\n'+f"{len(result['files'])} files · {result['expanded_bytes']/1024**2:.1f} MiB expanded",icon='package-x-generic-symbolic'))
        group = Adw.PreferencesGroup(title='Package Settings')
        fields = {}
        for parameter in result['parameters']:
            if parameter['key']=='OverrideInterpolationCount':
                counts=['auto','0','1','2','3','4','5']
                raw=str(parameter['value'])
                choice=__import__('rtxforge_gtk').safe_combo_row(title='MFG multiplier',model=Gtk.StringList.new(['Auto','Off','2×','3×','4×','5×','6×']))
                choice.set_selected(counts.index(raw) if raw in counts else Gtk.INVALID_LIST_POSITION)
                group.add(choice)
                fields[parameter['key']]=lambda choice=choice,raw=raw:counts[choice.get_selected()] if choice.get_selected()<len(counts) else raw
            else:
                entry = Adw.EntryRow(title=parameter['label'] + ' · ' + parameter['origin'])
                entry.set_text(str(parameter['value']));group.add(entry);fields[parameter['key']]=entry.get_text
        detail.append(group)
        warnings = Gtk.Label(label='\n'.join(result['warnings']), xalign=0, wrap=True, selectable=True)
        warnings.add_css_class('dim-label');detail.append(warnings)
        instructions=owner.review_list();detail.append(instructions)
        for item in result['instructions'][:8]:
            instructions.append(owner.review_entry(item['path'],'Original instructions · commands are never executed',badge='Read only',details=item['text'][:4000]))
        detail.append(Gtk.Label(label='Your editable instructions / review notes (never executed)',xalign=0,wrap=True))
        notes=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=120)
        notes.get_buffer().set_text('\n\n'.join(item['text'][:4000] for item in result['instructions'][:8]))
        notes_scroll=Gtk.ScrolledWindow(min_content_height=120,hscrollbar_policy=Gtk.PolicyType.NEVER)
        notes_scroll.set_child(notes);detail.append(notes_scroll)
        trust = Gtk.CheckButton(label='I trust the source of this package')
        while footer.get_first_child():footer.remove(footer.get_first_child())
        trust.set_hexpand(True);footer.append(trust);footer.set_visible(True)
        apply = owner.make_action_button('Use reviewed package',lambda *_:None)
        apply.set_sensitive(False);apply.set_halign(Gtk.Align.END)
        apply.add_css_class('suggested-action');footer.append(apply)
        trust.connect('toggled', lambda *_:apply.set_sensitive(trust.get_active() and result['family']=='dlss-unlocked'))
        def reviewed(*_):
            values={key:read().strip() for key,read in fields.items()}
            trusted=trust.get_active();apply.set_sensitive(False)
            buffer=notes.get_buffer();review_notes=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)
            status.set_text('Verifying the reviewed package…')
            def verified(record):
                if not alive['value']:return False
                parsed=record['parameters'];count=parsed.get('OverrideInterpolationCount','auto')
                settings={'custom_package':record,
                          'nr_strength':parsed.get('Intensity',2.0),
                          'sharpening_strength':parsed.get('Sharpness',0.5),
                          'mfg_multiplier':'auto' if count=='auto' else 0 if count=='0' else int(count)+1}
                select('custom',settings)
                return False
            def failed(message):
                if alive['value']:status.set_text(user_messages.friendly_error(message));status.set_tooltip_text(str(message));apply.set_sensitive(trust.get_active())
                return False
            def verify():
                try:GLib.idle_add(verified,packages.custom_record(result,values,trusted=trusted,review_notes=review_notes))
                except Exception as ex:GLib.idle_add(failed,str(ex))
            threading.Thread(target=verify,daemon=True).start()
        apply.connect('clicked',reviewed)
        status.set_text('Inspection complete. No game files have changed.')
        return False

    def catalog_again(*_):
        footer.set_visible(False)
        detail.set_visible(False);recommended.set_visible(True);custom.set_visible(True);community.set_visible(True);intro.set_visible(True)
        title.set_text('Packages');back.set_visible(False)
        status.set_text('Choose a package to review. No game files have changed.')
    back.connect('clicked',catalog_again)

    def inspect(path):
        detail.set_visible(True)
        status.set_text('Reading package files and configuration…');pick.set_sensitive(False)
        def work():
            try:
                result=packages.inspect_archive(path)
                GLib.idle_add(render_inspection,result)
            except Exception as ex:
                GLib.idle_add(status.set_text,user_messages.friendly_error(ex))
                GLib.idle_add(status.set_tooltip_text,str(ex))
            finally:GLib.idle_add(pick.set_sensitive,True)
        threading.Thread(target=work,daemon=True).start()

    def open_file(*_):
        chooser=Gtk.FileDialog(title='Choose a graphics package')
        file_filter=Gtk.FileFilter();file_filter.set_name('ZIP packages');file_filter.add_pattern('*.zip')
        filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(file_filter);chooser.set_filters(filters)
        def chosen(source,result):
            try:
                file=source.open_finish(result)
                if file and file.get_path():inspect(file.get_path())
            except GLib.Error:pass
        chooser.open(owner,None,chosen)
    pick.connect('clicked',open_file)
    if owner.options.demo:
        render_catalog({'system':'Linux','architecture':'x86_64','ready':True,'gpu':'Preview RTX 4070'})
    else:
        def check_host():
            try:host=owner.service.hardware()
            except Exception as ex:host={'ready':False,'reason':str(ex)}
            GLib.idle_add(render_catalog,host)
        threading.Thread(target=check_host,daemon=True).start()
    if fixture:inspect(fixture)
    return toolbar
