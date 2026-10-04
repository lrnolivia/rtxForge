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
    toolbar = Adw.ToolbarView()
    header=Adw.HeaderBar();toolbar.add_top_bar(header)
    back=Gtk.Button(icon_name='go-previous-symbolic',tooltip_text='Back to packages',visible=False)
    header.pack_start(back)
    footer=Gtk.Box(spacing=16,visible=False);margins(footer,16);toolbar.add_bottom_bar(footer)
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    margins(box)
    scroll.set_child(box); toolbar.set_content(scroll); dialog.set_child(toolbar)
    title = Gtk.Label(label='Choose your graphics package', xalign=0)
    title.add_css_class('title-1'); box.append(title)
    intro = Gtk.Label(label='Use a supported package or inspect your own. Every game change is reviewed before it is applied.', xalign=0, wrap=True)
    intro.add_css_class('dim-label'); box.append(intro)
    status = Gtk.Label(label='Checking your system…', xalign=0, wrap=True)
    box.append(status)
    recommended = Adw.PreferencesGroup(title='Available packages')
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
            dialog.close()
        except Exception as ex:
            status.set_text(user_messages.friendly_error(ex));status.set_tooltip_text(str(ex))

    def render_catalog(host):
        if not alive['value']:return False
        status.set_text('Preview system · NVIDIA RTX 4070 · no game writes' if owner.options.demo else host.get('gpu','System') + ' · ' + host.get('reason',''))
        for item in packages.catalog(host):
            row = Adw.ActionRow(title=item['name'], subtitle=item['version'] + ' · ' + item['summary'])
            button = owner.make_action_button('Use package',lambda _, key=item['id']:select(key))
            button.set_sensitive(item['available'])
            button.set_tooltip_text(user_messages.friendly_error(item['reason']) if not item['available'] else item['reason'])
            if item['recommended']:button.add_css_class('suggested-action')
            row.add_suffix(button);recommended.add(row)
        return False

    def render_inspection(result):
        if not alive['value']:return False
        recommended.set_visible(False);custom.set_visible(False);community.set_visible(False);intro.set_visible(False)
        title.set_text('Review your package');back.set_visible(True)
        while detail.get_first_child():detail.remove(detail.get_first_child())
        group = Adw.PreferencesGroup(title=result['name'], description=result['confidence'])
        family = Adw.ActionRow(title='Detected format', subtitle=result['family'] if result['family']!='unknown' else 'Unrecognized · inspection only')
        group.add(family)
        group.add(Adw.ActionRow(title='Package contents', subtitle=f"{len(result['files'])} files · {result['expanded_bytes']/1024**2:.1f} MiB expanded"))
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
        instructions = Adw.ExpanderRow(title='Original package instructions', subtitle='Commands are never executed')
        for item in result['instructions'][:8]:
            row = Adw.ActionRow(title=item['path'])
            row.set_use_markup(False);row.set_subtitle(item['text'][:4000]);row.set_subtitle_lines(0);instructions.add_row(row)
        instruction_group = Adw.PreferencesGroup();instruction_group.add(instructions);detail.append(instruction_group)
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
        title.set_text('Choose your graphics package');back.set_visible(False)
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
    dialog.present(owner)
    if owner.options.demo:
        render_catalog({'system':'Linux','architecture':'x86_64','ready':True,'gpu':'Preview RTX 4070'})
    else:
        def check_host():
            try:host=owner.service.hardware()
            except Exception as ex:host={'ready':False,'reason':str(ex)}
            GLib.idle_add(render_catalog,host)
        threading.Thread(target=check_host,daemon=True).start()
    if fixture:inspect(fixture)
    return dialog
