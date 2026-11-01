"""Game Mode Packages and Extras, using the existing catalog and reviewed operations."""
import threading

from gi.repository import GLib, Gtk
import package_catalog
import user_messages


class GameModeTools:
    def tool_page(self, title, lead):
        t = self.theme
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(20), vexpand=True)
        side = t.px(32 if self.layout_width <= 1050 else 48 if self.layout_width <= 1500 else 64)
        for edge, value in (('start', side), ('end', side), ('top', t.px(24)), ('bottom', t.px(20))):
            getattr(page, 'set_margin_' + edge)(value)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(10))
        heading.append(self.label(title, 'gm-h1'))
        heading.append(self.label(lead, 'gm-p', wrap=True))
        page.append(heading)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(24))
        scroll = self.scroller(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(body)
        page.append(scroll)
        return page, body

    def tool_card(self, title, description, action, version=None, icon=None):
        t = self.theme
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(16), hexpand=True)
        box.add_css_class('gm-tool-card')
        box.append(self.heading(title, icon) if icon else self.label(title, 'gm-h2', wrap=True))
        if version:
            box.append(self.label(version, 'gm-small'))
        box.append(self.label(description, 'gm-p', wrap=True))
        if action is not None:
            action.set_halign(Gtk.Align.END)
            box.append(action)
        return box

    def tool_columns(self, desired):
        count = desired if self.layout_width >= self.theme.px(1120) else 1
        return Gtk.Grid(column_spacing=self.theme.px(24), row_spacing=self.theme.px(24), column_homogeneous=True), count

    def package_card(self, title, version, description, verified, action):
        card = self.tool_card(title, description, None, version)
        footer = Gtk.Box(spacing=self.theme.px(12))
        badges = Gtk.Box(spacing=self.theme.px(8), hexpand=True)
        for name in verified:
            badges.append(self.badge(name.upper(), 'gm-badge-source', 'rtx-os-' + name + '-symbolic'))
        if not verified:
            badges.append(self.badge('EXPERIMENTAL', 'gm-badge-ready'))
        footer.append(badges)
        action.set_halign(Gtk.Align.END)
        footer.append(action)
        card.append(footer)
        return card

    def build_packages(self):
        page, body = self.tool_page('Packages', 'Choose what rtxForge installs. Every game change is reviewed before it is applied.')
        status = self.label('Loading packages…', 'gm-p')
        body.append(self.tool_card('System readiness', None, status, icon='rtx-gm-monitor-symbolic'))
        body.append(self.tool_card('Hardware support', 'RTX 20, 30, 40 and 50. Feature availability depends on the selected package and game.', None, icon='rtx-gm-monitor-symbolic'))
        revision = self.render_revision

        def ready(host):
            if self.page != 'packages' or revision != self.render_revision:
                return GLib.SOURCE_REMOVE
            status.set_text('Preview system · no game writes' if self.owner.options.demo else host.get('gpu', 'System') + ' · ' + host.get('reason', ''))
            catalog = package_catalog.catalog(host)
            paired = next((item for item in catalog if item['id'] == 'skynizz'), None)
            feeder = next((item for item in catalog if item['id'] == 'feeder'), None)
            pairs = self.owner.settings.get('runtime_provider') == 'skynizz'
            columns, count = self.tool_columns(2)
            nr, mfg = (Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16)) for _ in range(2))
            self.section_title(nr, 'NR packages', 'Neural rendering. Choose one for games with DLSS' +
                               ('; ' + feeder['name'] + ' covers games without DLSS automatically.' if feeder and feeder['available'] else '.'))
            names = dict(universal='Universal MFG', integrated='Integrated MFG unlock', **{'mfg-unlock':'MFG Unlock'})
            def use_card(item):
                current = self.owner.settings.get('runtime_provider') == item['id']
                def use():
                    try:
                        self.owner.select_package(item['id'], {})
                        self.toast('Package selected for DLSS games. Select games, then choose Install Features.')
                        self.render(keep_focus=True)
                    except Exception as error:
                        self.toast(user_messages.friendly_error(error))
                name, version = item['name'], item['version']
                if item['id'] == 'skynizz':
                    selected = names.get(self.owner.settings.get('mfg_provider', 'universal'), 'Universal MFG')
                    name += ' + ' + selected
                    version += ' · ' + selected
                return self.package_card(name, version, (item['summary'] if item['available'] else item['reason'])+'\nGraphics API: '+' · '.join(item.get('graphics_apis',[])),
                    item.get('verified', []), self.button('In use' if current else 'Use for DLSS games', use,
                    enabled=bool(item['available'] and not current), key='package-' + item['id']))
            if paired:
                nr.append(use_card(paired))
            if feeder:
                nr.append(self.package_card(feeder['name'], feeder['version'], (feeder['summary'] if feeder['available'] else feeder['reason'])+'\nGraphics API: '+' · '.join(feeder.get('graphics_apis',[])),
                    feeder.get('verified', []), self.button('Used automatically' if feeder['available'] else 'Unavailable', None, enabled=False)))
            pair_name = paired['name'] if paired else 'the paired NR package'
            self.section_title(mfg, 'MFG packages', ('Native NVIDIA frame generation for ' if pairs else 'These pair with ') + pair_name + '.')
            summaries = {
                'universal': "Recommended. Keeps NVIDIA’s DLSS Frame Generation and unlocks 3x to 6x where the driver allows 2x. The multiplier and Dynamic MFG stay in the rtxForge Overlay.",
                'integrated': "Patches NVIDIA’s DLSS Frame Generation for 3x to 6x where the driver allows 2x, with no extra plugin.",
                'mfg-unlock': "Raises NVIDIA’s DLSS Frame Generation multiplier through ReShade. The rtxForge Overlay can’t change its multiplier while you play.",
            }
            for key, name in names.items():
                current = pairs and self.owner.settings.get('mfg_provider', 'universal') == key
                def select_mfg(value=key):
                    self.owner.settings['mfg_provider'] = value
                    self.save_settings()
                    self.render(keep_focus=True)
                versions = (paired or {}).get('mfg_versions', {})
                version = versions.get(key) or ('Built into the bridge' if key == 'integrated' else 'OptiScaler plugin' if key == 'universal' else 'ReShade add-on')
                mfg.append(self.package_card(name, version, summaries[key] + (' Not available under Proton in this build.' if key != 'universal' else '')+'\nGraphics API: DirectX 12', ['windows'],
                    self.button('In use' if current else 'Use with ' + pair_name if key == 'universal' else 'Unavailable', select_mfg,
                    enabled=bool(pairs and not current and key == 'universal'), key='mfg-package-' + key)))
            columns.attach(nr, 0, 0, 1, 1)
            columns.attach(mfg, 1 % count, 1 // count, 1, 1)
            body.append(columns)
            self.section_title(body, 'Unified packages', 'NR and frame generation in one package, for games with DLSS. Choosing one replaces your NR package for those games.')
            unified, count = self.tool_columns(2)
            for index, item in enumerate(item for item in catalog if item['id'] not in ('skynizz', 'feeder')):
                unified.attach(use_card(item), index % count, index // count, 1, 1)
            body.append(unified)
            more, count = self.tool_columns(2)
            own = self.button('Inspect package', self.open_custom_package, key='custom-package')
            more.attach(self.tool_card('Your own package', 'Inspect a ZIP archive, its settings and original instructions before choosing it.', own,
                                       icon='folder-symbolic'), 0, 0, 1, 1)
            community = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(16))
            community.add_css_class('gm-tool-card')
            self.section_title(community, 'Other community projects', "Explore other projects. These sources aren’t curated install options.")
            rows = [self.row_button(record['name'], 'Open', lambda url=record['url']: Gtk.UriLauncher.new(url).launch(self.owner, None, None),
                                    description=record['note']) for record in package_catalog.community_sources()]
            community.append(self.group(rows, True))
            more.attach(community, 1 % count, 1 // count, 1, 1)
            body.append(more)
            return GLib.SOURCE_REMOVE

        if self.owner.options.demo:
            ready({'system': 'Linux', 'architecture': 'x86_64', 'ready': True})
        else:
            def work():
                try:
                    host = self.owner.service.hardware()
                except Exception as error:
                    host = {'ready': False, 'reason': user_messages.friendly_error(error)}
                GLib.idle_add(ready, host)
            threading.Thread(target=work, daemon=True).start()
        return page

    def open_custom_package(self):
        # Keep the existing inspection/trust/review contract; present it inside the Game Mode shell.
        from package_browser import build_packages
        alive = {'value': True}
        def close():
            alive['value'] = False
            self.close_modal()
        content = build_packages(self.owner, on_selected=close, alive=alive, header=False)
        content.add_css_class('gm-native-package')
        self.show_modal('Your own package', content, [self.button('Back', close)], close, 1100)

    def build_extras(self):
        page, body = self.tool_page('Extras', 'Tools for your whole library. Every game change is reviewed before it is applied.')
        t = self.theme
        runtime = self.owner.runtime_api()
        live = runtime is not None and not self.owner.options.demo
        def columns(count):
            return Gtk.Grid(column_spacing=t.px(24), row_spacing=t.px(24), column_homogeneous=True), (count if self.layout_width >= t.px(1120) else 1)
        actions, count = columns(3)
        # Glyphs as on Windows Extras: E777 overlay update, E8AB DLSS update, E7A7 undo.
        specs = [
            ('Update Overlays', 'Review overlay package updates, menus, welcome messages and shortcuts in installed games.',
             self.button('Update Overlays', self.owner.overlay_packages_review, enabled=live), 'rtx-gm-overlay-symbolic'),
            ('Update DLSS files', 'Replace older DLSS files across your library. Originals are backed up.',
             self.button('Review games', lambda: self.run_operation('update-dlss', [g for g in self.owner.games if not g.get('blocked')]), enabled=live),
             'network-transmit-receive-symbolic'),
            ('Undo previous changes', 'Restore the files from an earlier install, update or restore.',
             self.button('Show changes', self.owner.show_undo), 'edit-undo-symbolic'),
        ]
        for index, (title, description, action, icon) in enumerate(specs):
            actions.attach(self.tool_card(title, description, action, icon=icon), index % count, index // count, 1, 1)
        body.append(actions)
        body.append(self.tool_card('RenoDX HDR', 'Install matching HDR mods automatically, or import a custom RenoDX package for a game.', self.button('Choose game', self.choose_hdr_game, enabled=bool(self.owner.games)), icon='rtx-gm-monitor-symbolic'))
        tools, count = columns(2)
        self.global_nr = getattr(self, 'global_nr', None)
        self.global_mfg = getattr(self, 'global_mfg', None)
        once = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=t.px(20), hexpand=True)
        once.add_css_class('gm-tool-card')
        once.append(self.heading('Global Settings', 'rtx-gm-gamepad-symbolic'))
        once.append(self.label('Turn neural rendering or frame generation on or off, or set the multiplier, in every game with a package installed. Defaults for future installs stay the same.', 'gm-p', wrap=True))
        once.append(self.group([
            self.choice('Neural rendering', 'Choose only the setting to change across installed games.',
                        [None, False, True], ['Leave as is', 'Off', 'On'], lambda: self.global_nr, lambda v: setattr(self, 'global_nr', v)),
            self.choice('Multi-Frame Generation', 'Feeder games support NR only. Leave other games as they are, or choose a new mode.',
                        [None, 0, 2, 3, 4, 5, 6, -1], ['Leave as is', 'Off', '2×', '3×', '4×', '5×', '6×', 'Follow game'],
                        lambda: self.global_mfg, lambda v: setattr(self, 'global_mfg', v)),
        ], True))
        action = self.button('Review changes', lambda: self.owner.global_review(self.global_nr, self.global_mfg), 'primary', enabled=live, key='extras-global')
        action.set_halign(Gtk.Align.END)
        once.append(action)
        tools.attach(once, 0, 0, 1, 1)
        tools.attach(self.tool_card('App storage', 'Downloads, backups and caches rtxForge keeps. Clean up what no game needs.',
                                   self.button('View usage', self.owner.review_storage, enabled=live), icon='drive-multidisk-symbolic'), 1 % count, 1 // count, 1, 1)
        body.append(tools)
        return page

    def choose_hdr_game(self):
        choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(12))
        def choose(game):
            self.close_modal()
            self.open_game_tools(game)
        for game in sorted(self.owner.games, key=lambda game: game['name'].casefold()):
            choices.append(self.row_button(game['name'], 'HDR controls', lambda game=game: choose(game), icon='rtx-gm-monitor-symbolic'))
        self.show_modal('RenoDX HDR', choices, [self.button('Back', self.close_modal)], self.close_modal)

    def open_game_tools(self, game):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=self.theme.px(24))
        previous = self.section
        self.section = 'Tools'
        try:
            self.build_section(game, content)
        finally:
            self.section = previous
        self.show_modal(game['name'] + ' · Tools', content, [self.button('Back', self.close_modal)], self.close_modal)
        self.modals[-1]['dialog'].add_css_class(self.accent_class(game))
