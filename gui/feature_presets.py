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

    def __init__(self,values,advanced=False,mode='nr-mfg'):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.inputs={}
        values=normalized(values)
        groups={}
        for item in definitions():
            group=groups.get(item['group'])
            if group is None:
                group=Adw.PreferencesGroup(title=item['group'])
                self.append(group);groups[item['group']]=group
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
            row.set_sensitive(not (mode=='mfg-only' and item['section']=='DlssNr'))
            group.add(row);self.inputs[key]=(item,control)

    def get_value(self):
        values={}
        for key,(item,control) in self.inputs.items():
            if item['kind']=='toggle':value=int(control.get_active())
            elif 'values' in item:value=item['values'][control.get_selected()]
            else:value=round(control.get_value(),2) if item['kind']=='slider' else control.get_value_as_int()
            values[key]=value
        return skynizz_provider.validate_controls(values)

    def set_value(self,values):
        values=normalized(values)
        for key,(item,control) in self.inputs.items():
            if item['kind']=='toggle':control.set_active(bool(values[key]))
            elif 'values' in item:control.set_selected(item['values'].index(values[key]))
            else:control.set_value(values[key])
