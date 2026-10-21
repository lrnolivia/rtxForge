"""Native editors for the shared Windows/in-game preset vocabulary."""
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Adw','1')
from gi.repository import Gtk, Adw, GObject
import skynizz_provider


def definitions():
    # MFG has its own On/Off and Auto/Custom/Dynamic editor. The remaining
    # controls retain the schema's runtime units, ranges and ordering.
    return [c for c in skynizz_provider.control_schema() if c['group'] != 'Frame generation']


def normalized(values):
    valid=skynizz_provider.validate_controls(values or {})
    return {c['key']:valid.get(c['key'],c['default']) for c in definitions()}


class FeaturePresets(Gtk.Box):
    __gsignals__={'value-changed':(GObject.SignalFlags.RUN_FIRST,None,())}
    normalized=staticmethod(normalized)

    def __init__(self,values,advanced=False,mode='nr-mfg',legacy=False,installation=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.inputs={}
        self.rows={}
        self.legacy=legacy
        self.mode=mode
        values=normalized(values)
        groups={}
        more=None
        if installation:
            more=Adw.ExpanderRow(title='More settings',expanded=False)
            self.more_expander=more
            more_body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            more_body.set_margin_top(12)
            for side in ('start','end','bottom'):getattr(more_body,'set_margin_'+side)(16)
            more.add_row(more_body)
        for item in definitions():
            group_key='Additional neural settings' if installation and item['key'] in ('preset','passes') else item['group']
            group=groups.get(group_key)
            if group is None:
                name='DLSS presets' if item['group']=='Upscaling' else group_key
                parent=more_body if installation and group_key!='Neural rendering' else self
                if item['group'] in ('Fine tuning','Sharpening','Motion sharpening','Performance'):
                    container=Adw.PreferencesGroup()
                    group=Adw.ExpanderRow(title=name)
                    container.add(group);parent.append(container)
                else:
                    group=Adw.PreferencesGroup(title=name)
                    parent.append(group)
                groups[group_key]=group
            key=item['key'];title=item['advanced'] if advanced else item['label']
            if item['kind']=='toggle':
                row=Adw.SwitchRow(title=title,active=bool(values[key]))
                row.connect('notify::active',lambda *_:self.emit('value-changed'))
                control=row
            elif 'values' in item:
                row=Adw.ComboRow(title=title,model=Gtk.StringList.new(item['choices']))
                row.set_selected(item['values'].index(values[key]))
                row.connect('notify::selected',lambda *_:self.emit('value-changed'))
                control=row
            else:
                row=Adw.ActionRow(title=title,subtitle=f"{item['min']} – {item['max']}")
                adjustment=Gtk.Adjustment(value=values[key],lower=item['min'],upper=item['max'],step_increment=item.get('step',1),page_increment=item.get('step',1)*10)
                control=Gtk.SpinButton(adjustment=adjustment,digits=2 if item['kind']=='slider' else 0,numeric=True,valign=Gtk.Align.CENTER)
                control.connect('value-changed',lambda *_:self.emit('value-changed'))
                row.add_suffix(control)
                if item['kind']=='slider':
                    field=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
                    field.append(row)
                    slider=Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,adjustment=adjustment,draw_value=False,hexpand=True)
                    slider.set_margin_start(16);slider.set_margin_end(16);slider.set_margin_bottom(8)
                    slider.set_tooltip_text(f"{item['min']}–{item['max']}")
                    slider.update_property([Gtk.AccessibleProperty.LABEL],[title])
                    field.append(slider)
                    def display(spin,r=row,i=item):
                        value=spin.get_value()
                        caption=('Follow structure' if i['key']=='skin' and value<0 and not advanced else
                                 f'{value:.0%}' if i.get('unit')=='percent' or i.get('unit')=='strength' and not advanced else f'{value:.2f}')
                        r.set_subtitle(caption)
                    control.connect('value-changed',display);display(control)
                    row=field
            if isinstance(group,Adw.ExpanderRow):group.add_row(row)
            else:group.add(row)
            self.inputs[key]=(item,control);self.rows[key]=row
        if more is not None:
            surface=Adw.PreferencesGroup()
            surface.add(more);self.append(surface)
        self.connect('value-changed',lambda *_:self.refresh_availability())
        self.refresh_availability()

    def refresh_availability(self):
        values=self.get_value()
        dependencies={'reduced':bool(values['pre_sr']),
                      'work_scale':not values['pre_sr'] or bool(values['reduced']),
                      'interval':bool(values['cache']),
                      'sharpness':bool(values['sharpen'] and values['sharp_override']),
                      'motion_sharpness':bool(values['sharpen'] and values['motion_sharpen'])}
        for key,(item,control) in self.inputs.items():
            available=(not self.legacy or key in ('intensity','sharpness')) and not (self.mode=='mfg-only' and item['section']=='DlssNr')
            if not self.legacy:available=available and dependencies.get(key,True)
            self.rows[key].set_sensitive(available)
            if self.legacy and key not in ('intensity','sharpness'):
                self.rows[key].set_tooltip_text('This package does not support this control')

    def get_value(self):
        values={}
        for key,(item,control) in self.inputs.items():
            if item['kind']=='toggle':value=int(control.get_active())
            elif 'values' in item:value=item['values'][control.get_selected()]
            else:value=round(control.get_value(),2) if item['kind']=='slider' else control.get_value_as_int()
            values[key]=value
        return skynizz_provider.validate_controls(values)

    def set_value(self,values):
        if self.legacy:
            current=self.get_value()
            values={**(values or {}),'intensity':current['intensity'],'sharpness':current['sharpness']}
        values=normalized(values)
        for key,(item,control) in self.inputs.items():
            if item['kind']=='toggle':control.set_active(bool(values[key]))
            elif 'values' in item:control.set_selected(item['values'].index(values[key]))
            else:control.set_value(values[key])
