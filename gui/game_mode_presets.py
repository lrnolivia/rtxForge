"""Game Mode presets: the Windows Game Mode layout over the shared control vocabulary.

MFG has its own card (On/Off, Auto/Custom/Dynamic, multiplier). The remaining
controls come from providers/skynizz-bridge/controls.json in Windows' order:
Neural rendering and DLSS presets, then Image tuning, Sharpening and Performance.
"""
from gi.repository import Gtk

import game_mode_motion as motion
import mfg_choice
from feature_presets import definitions, normalized, us_label

MFG_DESCRIPTIONS = ("Follows the game's frame generation setting.",
                    'Uses a fixed multiplier. Enable frame generation in the game.',
                    'Uses up to the selected multiplier. Requires a game and driver with Dynamic MFG support.')
NR_GROUPS = ('Neural rendering', 'Image tuning', 'Fine tuning', 'Performance')


def available(item, mode, legacy):
    """FeatureControlSchema.Available on Windows."""
    if legacy and item['key'] not in ('intensity', 'sharpness', 'multiplier'):
        return False
    if item['group'] == 'Frame generation':
        return mode != 'nr-only'
    return mode != 'mfg-only' if item['group'] in NR_GROUPS else True


def display(item, value, advanced):
    if item['key'] == 'skin' and value < 0 and not advanced:
        return 'Follow structure'
    if item['kind'] == 'toggle':
        return 'On' if value else 'Off'
    if item.get('values'):
        return item['choices'][item['values'].index(value)] if value in item['values'] else item['choices'][0]
    if item.get('unit') == 'percent' or item.get('unit') == 'strength' and not advanced:
        return f'{value:.0%}'
    return f'{value:.2f}' if item['kind'] == 'slider' else str(int(value))


class GameModePresets:
    def preset_rows(self, game, enabled=True, installation=False):
        """Return (widgets, value): widgets are cards laid out like Windows Game Mode's PresetRows."""
        owner, t = self.owner, self.theme
        source = game if game is not None else owner.settings
        mode = (game or {}).get('feature_mode') or owner.mode
        legacy = source.get('runtime_provider', owner.settings.get('runtime_provider')) != 'skynizz'
        advanced = owner.settings.get('overlay_controls') == 'classic'
        schema = {item['key']: item for item in definitions()}
        saved = source.get('feature_controls', owner.settings.get('feature_controls')) or {}
        values = normalized(saved)
        if not saved or legacy:
            # Packages without the shared controls keep their two tuning values (Resolve on Windows).
            values['intensity'] = float(source.get('nr_strength', owner.settings.get('nr_strength', 2.0)) or 0)
            values['sharpness'] = float(source.get('sharpening_strength', owner.settings.get('sharpening_strength', 0.5)) or 0)
            values['sharpen'] = values['sharp_override'] = int(values['sharpness'] > 0)
            values['enabled'] = int(bool(source.get('nr_on_launch', owner.settings.get('nr_on_launch', False))))
        mfg_source = dict(owner.settings)
        mfg_source.update({k: source[k] for k in ('mfg_multiplier', 'dynamic_mfg', 'mfg_saved_mode', 'mfg_saved_multiplier')
                           if source.get(k) is not None})
        dynamic_available = mfg_choice.dynamic_supported(owner.settings, game) and not legacy
        dynamic_reason = mfg_choice.dynamic_reason(dynamic_available, game)
        mfg = dict(zip(('on', 'mode', 'ratio'), mfg_choice.from_values(mfg_source)))
        if mfg['mode'] == mfg_choice.DYNAMIC and not dynamic_available:
            mfg['mode'] = mfg_choice.CUSTOM

        def card(title, *parts):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(20), hexpand=True, valign=Gtk.Align.START)
            box.add_css_class('gm-tool-card')
            if title:
                box.append(self.heading(title))
            for part in parts:
                box.append(part)
            return box

        def responsive(*parts, minimum):
            """Side by side when each part gets `minimum` pixels, stacked otherwise (Windows PresetColumns)."""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24), hexpand=True)
            for part in parts:
                box.append(part)
            def fit(widget, _clock):
                wide = widget.get_width() >= len(parts) * t.px(minimum) + (len(parts) - 1) * t.px(24)
                direction = Gtk.Orientation.HORIZONTAL if wide else Gtk.Orientation.VERTICAL
                if widget.get_orientation() != direction:
                    widget.set_orientation(direction)
                    widget.set_homogeneous(wide)
                return True
            box.add_tick_callback(fit)
            return box

        def pair(*keys):
            return responsive(*(field(key) for key in keys), minimum=360)

        def field(key):
            item = schema[key]
            label = 'Enable NR on launch' if key == 'enabled' else us_label(item['advanced'] if advanced else item['label'])
            editable = enabled and available(item, mode, legacy)
            if item['kind'] == 'toggle':
                # A switch, as in Settings, not an Off/On chooser.
                widget = self.setting_toggle(label, None, lambda: values[key], lambda value: values.__setitem__(key, int(bool(value))))
                widget.set_sensitive(editable)
                self.key(widget, 'preset-field-' + key)
                return widget
            choices = item.get('values')
            if choices:
                captions = ['Off', 'On'] if item['kind'] == 'toggle' else item['choices']
                def put(value, row=None):
                    values[key] = value
                    shown = getattr(widget.get_child(), '_value', None)
                    if shown is not None:
                        shown.set_text(display(item, value, advanced))
                def choose():
                    def pick(value):
                        put(value)
                        self.close_modal()
                    options = [self.row_button(caption, '✓' if values[key] == value else None, lambda value=value: pick(value))
                               for value, caption in zip(choices, captions)]
                    current = next((row for row, value in zip(options, choices) if values[key] == value), None)
                    self.show_modal(label, self.group(options), [self.button('Back', self.close_modal)], self.close_modal, 900, current)
                widget = self.row_button(label, display(item, values[key], advanced), choose, enabled=editable, key='preset-field-' + key)
                widget._gm_adjust = lambda delta: put(choices[max(0, min(len(choices) - 1,
                                                                        (choices.index(values[key]) if values[key] in choices else 0) + delta))])
                return widget
            def adjust(delta):
                step = item.get('step', 1) * (10 if item['kind'] == 'slider' and item.get('unit') in ('strength', 'percent') else 1)
                values[key] = round(max(item['min'], min(item['max'], values[key] + delta * step)), 2)
            note = '−1 follows local structure.' if key == 'skin' and editable else None
            return self.stepper(label, note, lambda: display(item, values[key], advanced), adjust, editable, key='preset-field-' + key)

        def segmented(captions, selected, pick, enabled_for, key):
            box = Gtk.Box(spacing=t.px(4), homogeneous=True, hexpand=True)
            box.add_css_class('gm-segments')
            buttons = []
            for index, caption in enumerate(captions):
                button = motion.MotionButton(preferences=owner.settings, child=self.label(caption, xalign=.5))
                button.connect('clicked', lambda *_, index=index: (pick(index), refresh()))
                self.key(button, f'preset-{key}-{index}')
                buttons.append(button)
                box.append(button)
            def refresh():
                current = selected()
                for index, button in enumerate(buttons):
                    button.set_sensitive(enabled_for(index))
                    (button.add_css_class if index == current else button.remove_css_class)('on')
            box._refresh = refresh
            refresh()
            return box

        def disclosure(title, *parts):
            opened = getattr(self, 'preset_disclosures', set())
            self.preset_disclosures = opened
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12), visible=title in opened)
            for part in parts:
                body.append(part)
            chevron = self.icon('pan-end-symbolic', t.px(16))
            def show():
                # Windows shows a chevron before the heading: down when open, right when closed.
                chevron.set_from_icon_name('pan-down-symbolic' if body.get_visible() else 'pan-end-symbolic')
                button.update_property([Gtk.AccessibleProperty.LABEL], [title + (' expanded' if body.get_visible() else ' collapsed')])
            def toggle():
                body.set_visible(not body.get_visible())
                (opened.add if body.get_visible() else opened.discard)(title)
                show()
                if body.get_visible():
                    motion.reveal(body, owner.settings, motion.FADE_MS, .65)
            line = Gtk.Box(spacing=t.px(12))
            line.append(chevron)
            line.append(self.label(title, 'gm-strong', xalign=0))
            button = motion.MotionButton(preferences=owner.settings, child=line, hexpand=True)
            button.add_css_class('gm-rowbtn')
            button.connect('clicked', lambda *_: toggle())
            self.key(button, 'preset-disclosure-' + title)
            show()
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(12))
            group.append(button)
            group.append(body)
            return group

        def mfg_card():
            allowed = enabled and mode != 'nr-only'
            ratio_label = self.label('', 'gm-p')
            description = self.label('', 'gm-p', wrap=True)
            ratios = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8))
            parts = []
            def changed():
                for part in parts:
                    part._refresh()
                ratios.set_visible(mfg['on'] and mfg['mode'] != mfg_choice.AUTO)
                ratio_label.set_text('Maximum multiplier' if mfg['mode'] == mfg_choice.DYNAMIC else 'Multiplier')
                text = (MFG_DESCRIPTIONS[mfg['mode']] if mfg['on'] else 'Multi-Frame Generation is off.') if allowed else ''
                description.set_text(text + ('\n' + dynamic_reason if text and mfg['on'] and dynamic_reason else ''))
                description.set_visible(bool(description.get_text()))
            def switch(index):
                mfg['on'] = bool(index)
                if mfg['on'] and mfg['mode'] == mfg_choice.DYNAMIC and not dynamic_available:
                    mfg['mode'] = mfg_choice.CUSTOM
            power = segmented(['Off', 'On'], lambda: int(mfg['on']), switch, lambda _: allowed, 'mfg-enabled')
            modes = segmented(list(mfg_choice.MODE_NAMES), lambda: mfg['mode'], lambda i: mfg.update(mode=i),
                              lambda i: allowed and mfg['on'] and (i != mfg_choice.DYNAMIC or dynamic_available), 'mfg-mode')
            ratio = segmented([f'{n}×' for n in mfg_choice.RATIOS], lambda: mfg_choice.RATIOS.index(mfg['ratio']),
                              lambda i: mfg.update(ratio=mfg_choice.RATIOS[i]), lambda _: allowed and mfg['on'], 'mfg-ratio')
            parts.extend((power, modes, ratio))
            # Each choice can enable or hide the others, so every click refreshes the whole card.
            for part in parts:
                for button in children(part):
                    button.connect('clicked', lambda *_: changed())
            if not dynamic_available:
                modes.get_last_child().set_tooltip_text(dynamic_reason or 'Requires the integrated MFG package and a compatible game and driver.')
            header = Gtk.Box(spacing=t.px(20))
            header.append(self.label('Multi-Frame Generation', 'gm-h2', wrap=True))
            header.append(Gtk.Box(hexpand=True))
            power.set_hexpand(False)
            power.set_size_request(t.px(200), -1)
            header.append(power)
            ratios.append(ratio_label)
            ratios.append(ratio)
            changed()
            return card('', header, modes, ratios, description)

        def nr_card(*extra):
            return card('Neural rendering', field('enabled'), style_choice(), field('intensity'), *extra)

        def style_choice():
            item = schema['style']
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(8))
            box.append(self.label(us_label(item['label']), 'gm-strong'))
            box.append(segmented(item['choices'], lambda: item['values'].index(values['style']) if values['style'] in item['values'] else 0,
                                 lambda i: values.update(style=item['values'][i]), lambda _: enabled and available(item, mode, legacy), 'style'))
            return box

        performance = [key for key, item in schema.items() if item['group'] == 'Performance']
        performance_rows = [pair(*performance[i:i + 2]) if i + 1 < len(performance) else field(performance[i])
                            for i in range(0, len(performance), 2)]
        sharpening = (field('sharpen'), pair('sharpen_shader', 'sharp_override'), field('sharpness'))
        if installation:
            main = responsive(mfg_card(), nr_card(), minimum=420)
            more = disclosure('More settings', pair('preset', 'passes'),
                              disclosure('DLSS presets', pair('dlss_preset', 'rr_preset')),
                              disclosure('Image tuning', pair('detail', 'colour'), pair('structure', 'tone'), pair('skin', 'auto_mask')),
                              disclosure('Sharpening', *sharpening, pair('motion_sharpen', 'motion_sharpness')),
                              disclosure('Performance', *performance_rows))
            rows = [main, more]
        else:
            first = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24), hexpand=True)
            first.append(nr_card(pair('preset', 'passes')))
            first.append(card('DLSS presets', self.label("Applies when the game next starts DLSS. Game default keeps the game's own choice.", 'gm-p', wrap=True),
                              pair('dlss_preset', 'rr_preset')))
            second = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24), hexpand=True)
            second.append(card('Image tuning', pair('detail', 'colour'),
                               disclosure('Fine tuning', pair('structure', 'tone'), pair('skin', 'auto_mask'))))
            second.append(card('', disclosure('Sharpening', *sharpening,
                                              disclosure('Motion sharpening', field('motion_sharpen'), field('motion_sharpness')))))
            second.append(card('', disclosure('Performance', *performance_rows)))
            rows = [mfg_card(), responsive(first, second, minimum=560)]

        def value():
            result = {'nr_strength': round(float(values['intensity']), 2), 'sharpening_strength': round(float(values['sharpness']), 2),
                      **mfg_choice.to_values(mfg['on'], mfg['mode'], mfg['ratio'], dynamic_available)}
            if not legacy:
                result['feature_controls'] = dict(values)
            return result
        return rows, value


def children(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()
