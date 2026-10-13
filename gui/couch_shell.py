"""Focus-led game library sharing the desktop service and reviewed operations."""
from pathlib import Path
import re
import time
from gi.repository import Gtk, Adw, Gdk, GLib, Gio, Pango, GObject
import controller_input
import library_media
import ui_colors
import user_messages


CSS = b'''
.couch-prompt-button { background: transparent; border: 0; padding: 6px 2px; color: #c5c7cc; }
.couch-prompt-button:hover { background: #292b30; }
.couch-prompts { transition: opacity 180ms ease-out; }
.couch-shell.bottom-navigation .couch-prompts { font-size: 12px; }
.couch-shell.bottom-navigation .couch-prompt-button { padding: 2px; }

.couch-shell { background: #101113; color: #fafafa; }
.couch-shell, .couch-dialog {
  --accent-bg-color: #76b900;
  --accent-fg-color: #151c07;
  --accent-color: #9bd438;
}
.couch-shell scale highlight, .couch-dialog scale highlight { background: #76b900; }
.couch-shell scale slider:focus-visible, .couch-dialog scale slider:focus-visible { outline-color: #76b900; }
.couch-game-meta { font-size: 15px; color: #c5c7cc; }
.couch-game-summary { font-size: 16px; color: #c5c7cc; }
.couch-badges { font-size: 12px; color: #c5c7cc; }
.couch-tab.focused { outline: 2px solid #fafafa; outline-offset: 2px; }
.couch-shell .couch-library-action { background: #f1f1f2; color: #202124; }
.couch-shade {
  background-image: linear-gradient(0deg, #101113 0%, #101113 22%, rgba(16,17,19,0.72) 43%, rgba(16,17,19,0.12) 76%, rgba(16,17,19,0.58) 100%),
                    linear-gradient(90deg, rgba(16,17,19,0.78), rgba(16,17,19,0.10) 75%);
}
.couch-shell.panel-open .couch-shade { background: rgba(16,17,19,0.92); }
.couch-shell.library-open .couch-shade { background: rgba(16,17,19,0.97); }
.couch-content { padding: 30px 52px 24px; }
.couch-brand { font-family: "Bakbak One"; font-size: 36px; font-weight: 400; }
.couch-shell.compact .couch-brand { font-size: 28px; }
.couch-shell .collapsed .couch-brand { font-size: 24px; }
.couch-context { font-size: 14px; font-weight: 500; color: #c2c4c8; background: #101113; border-radius: 16px; padding: 6px 10px; }
.couch-tabs { border-radius: 30px; background: #1c1d20; padding: 4px; }
.couch-shell button, .couch-shell row { background-image: none; box-shadow: none; }
.couch-tab { background: transparent; box-shadow: none; border: none; border-radius: 26px; padding: 6px 18px; min-height: 24px; color: #d8d9dc; font-size: 16px; font-weight: 600; }
.couch-tab.active { background: rgba(245,245,250,0.16); color: white; }
.couch-tab.focused { background: #fafafa; color: #191a1d; }
.couch-title { font-size: 52px; font-weight: 750; letter-spacing: -1.5px; }
.couch-detail { font-size: 18px; font-weight: 450; color: #d1d2d5; }
.couch-section { font-size: 23px; font-weight: 650; letter-spacing: -0.4px; }
.couch-subtle { font-size: 15px; color: #b2b4ba; }
.couch-tile { background: transparent; border: none; box-shadow: none; padding: 8px; border-radius: 30px; }
.couch-tile:focus { outline: none; }
.couch-cover { border-radius: 22px; background: #27292d; }
.couch-game-poster { border: 2px solid #76b900; border-radius: 14px; background: #27292d; }
.couch-tile.focused .couch-cover { outline: 3px solid #fafafa; outline-offset: 4px; }
.couch-tile-title { font-size: 16px; font-weight: 550; color: #c8c9cc; }
.couch-tile.focused .couch-tile-title { color: white; }
.couch-library-grid { padding: 8px; }
.couch-library-header { margin: 12px 0 6px; }
.couch-view-switch { background: #202226; border-radius: 24px; padding: 4px; }
.couch-view { background: transparent; color: #c9cbd1; box-shadow: none; border: none; border-radius: 20px; padding: 10px 16px; font-size: 15px; font-weight: 550; }
.couch-view.active { background: #37393f; color: #fafafa; }
.couch-list-row { background: #1b1d21; border: none; box-shadow: none; border-radius: 0; padding: 10px 18px; border-bottom: 1px solid #101113; color: #fafafa; }
.couch-list-row.joined-first { border-top-left-radius: 24px; border-top-right-radius: 24px; }
.couch-list-row.joined-last { border-bottom-left-radius: 24px; border-bottom-right-radius: 24px; border-bottom: 0; }
.couch-list-row:focus { outline: none; }
.couch-list-row.focused { background: #27292d; outline: 2px solid #fafafa; outline-offset: -2px; }
.couch-list-title { font-size: 20px; font-weight: 600; }
.couch-list-art { border-radius: 12px; background: #292b30; }
.couch-list-status { font-size: 15px; color: #c4c6cc; }
.couch-library-count { font-size: 16px; color: #b4b7be; }
.couch-action { padding: 16px 26px; border-radius: 24px; background: #2b2c2f; color: #f4f4f6; box-shadow: none; border: none; font-size: 19px; font-weight: 650; }
.couch-action.focused { background: #fafafa; color: #17181b; }
.couch-action:focus { outline: none; }
.couch-action:disabled { color: #9a9da5; background: #1e1f21; }
.couch-options { background: transparent; color: #f4f4f6; }
.couch-options row { border-radius: 24px; margin: 0 0 10px; padding: 18px 24px; min-height: 28px; background: #222326; }
.couch-options row label { font-size: 20px; font-weight: 550; }
.couch-options row:selected { background: #fafafa; color: #191a1d; }
.couch-options.nav-focused row:selected { background: #222326; color: #f4f4f6; }
.couch-options row:disabled { opacity: 0.45; }
.couch-options row:focus { outline: none; }
.couch-value { font-weight: 650; }
.couch-caption { font-size: 16px; color: #c1c3c8; }
.couch-panel-heading { font-size: 36px; font-weight: 700; letter-spacing: -0.8px; }
.couch-prompts { font-size: 14px; color: #b5b8bf; }
.couch-shell.compact .couch-content { padding: 22px 30px 18px; }
.couch-shell.compact .couch-title { font-size: 38px; letter-spacing: -0.8px; }
.couch-shell.compact .couch-tab { padding: 5px 14px; font-size: 14px; }
.couch-shell.compact .couch-detail { font-size: 16px; }
.couch-shell.compact .couch-action { padding: 14px 20px; font-size: 17px; }
.couch-shell.compact .couch-options row { padding: 9px 20px; margin-bottom: 8px; }
.couch-shell.compact .couch-options row label { font-size: 18px; }
.couch-shell.compact .couch-panel-heading { font-size: 30px; }
.couch-shell.compact .couch-view { padding: 9px 12px; font-size: 14px; }
.couch-shell.compact .couch-list-title { font-size: 18px; }
.couch-selection { background: #101113; border-radius: 8px; padding: 5px; }
.couch-shell .couch-settings { padding: 10px; min-width: 24px; min-height: 24px; }
.couch-workspace { padding: 18px 0 12px; }
.couch-sidebar-item { background: transparent; border: 0; box-shadow: none; padding: 14px 18px; border-radius: 12px; color: #d8d9dc; font-size: 18px; }
.couch-sidebar-item.active { background: #303237; color: white; }
.couch-sidebar-item:hover { background: #27292d; }
.couch-sidebar-item:focus-visible { outline: 2px solid #76b900; outline-offset: -2px; }
.couch-adjustment { background: #222428; border-radius: 14px; padding: 24px; }
.couch-adjustment-value { font-size: 28px; font-weight: 700; color: #fafafa; }
.couch-setting-control { background: #222428; border-radius: 12px; padding: 18px 20px; color: #f4f4f6; }
.couch-setting-control button { background: #36383e; border-radius: 8px; }
.couch-workspace-action { background: #303237; color: #fafafa; border: 0; box-shadow: none; padding: 10px 18px; min-height: 28px; border-radius: 12px; font-size: 16px; }
.couch-workspace-action:hover { background: #3c3f45; }
.couch-workspace-action, .couch-action, .couch-sidebar-item,
.couch-setting-control button, .couch-dialog button { border-radius: 999px; }
.couch-workspace-action.suggested-action { background: #76b900; color: #151c07; }
.couch-shell .couch-workspace-action.suggested-action label,
.couch-shell .couch-workspace-action.suggested-action image { color: #151c07; }
.couch-workspace-action:checked { background: #465b24; box-shadow: inset 0 -3px #9bd438; }
.couch-workspace-action.destructive-action { background: #4b2328; color: #ffc1c6; }
.couch-workspace .focused { outline: 2px solid #76b900; outline-offset: -2px; }
.couch-workspace button.focused, .couch-workspace button:focus-visible,
.couch-dialog button:focus-visible { outline: 1px solid rgba(220,224,232,0.20); outline-offset: -1px; }
.couch-workspace button.suggested-action.focused,
.couch-workspace button.suggested-action:focus-visible,
.couch-dialog button.suggested-action:focus-visible { outline-color: rgba(21,28,7,0.22); }
.couch-workspace button.destructive-action.focused,
.couch-workspace button.destructive-action:focus-visible,
.couch-dialog button.destructive-action:focus-visible { outline-color: rgba(255,128,144,0.22); }
.couch-workspace-action:disabled { opacity: 1; background: #25272b; color: #9599a2; }
.couch-shell .couch-workspace-action:disabled label,
.couch-shell .couch-workspace-action:disabled image { color: #9599a2; }
.couch-keycap { background: #303237; color: #fafafa; border-radius: 5px; padding: 3px 7px; font-size: 13px; font-weight: 650; }

'''

PAGES = ('library', 'presets', 'settings')
VIEWS = ('posters', 'capsules', 'list')


def label(text, style=None, wrap=False):
    widget = Gtk.Label(label=text, xalign=0, wrap=wrap)
    if style:
        widget.add_css_class(style)
    return widget


def clear(box):
    while box.get_first_child():
        box.remove(box.get_first_child())


class EmbeddedDetails(Gtk.Box):
    """The existing native Details controls inside the Game Mode workspace."""
    __gsignals__={'closed':(GObject.SignalFlags.RUN_LAST,None,())}
    def __init__(self,couch):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,hexpand=True,vexpand=True)
        self.couch=couch;self.closed=False
        self.add_css_class('couch-embedded-details')
    def get_child(self):return self.get_first_child()
    def set_child(self,child):
        clear(self)
        if child:self.append(child)
    def close(self):self.couch.open('library')
    def force_close(self):self.close()
    def destroy(self):self.close()
    def finish_close(self):
        if not self.closed:self.closed=True;self.emit('closed')


# Native GTK styles; browser styles are a reference, never installed as a web UI.
GAME_MODE_CSS=b'''
.couch-shell { background: #000; color: #f2f2f2; font-size: 22px; }
.couch-dialog { font-size: 22px; }
.couch-dialog label,.couch-dialog entry,.couch-dialog textview { font-size: 22px; }
.couch-dialog .title-2,.couch-dialog .title-1 { font-size: 30px; }
.couch-dialog .dim-label,.couch-dialog .subtitle { font-size: 18px; }
.couch-dialog button { font-size: 20px; padding: 10px 16px; }
.couch-dialog row { min-height: 66px; }
.couch-dialog .panel-body { padding: 24px 32px; }
.couch-dialog .control-pod { padding: 16px 22px; }
.couch-dialog .couch-tuning-controls { margin: 12px 0; }
.couch-dialog scale { min-height: 26px; }
.couch-dialog dropdown button { padding: 6px 12px; min-height: 20px; }
.couch-dialog spinbutton button { padding: 6px; min-height: 20px; min-width: 20px; }
.couch-dialog .couch-filter-option { padding: 22px 26px; font-size: 22px; }
.couch-dialog .couch-workspace-action { background: #303030; color: #f2f2f2; }
.couch-dialog .couch-workspace-action:checked { background: #575757; }
.couch-dialog.light .couch-workspace-action { background: #e7e7e7; color: #222; }
.couch-dialog.light .couch-workspace-action:checked { background: #d4d4d4; }
.couch-dialog button:focus-visible,.couch-dialog spinbutton:focus-within,.couch-dialog dropdown:focus-within { outline: 3px solid #f2f2f2; outline-offset: 2px; }
.couch-dialog.light button:focus-visible,.couch-dialog.light spinbutton:focus-within,.couch-dialog.light dropdown:focus-within { outline-color: #222; }
.couch-shell .couch-shade { background: #101010; background-image: none; }
.couch-shell .couch-content { padding: 24px 40px 18px; }
.couch-shell .couch-brand { font-size: 46px; }
.couch-shell .collapsed .couch-brand { font-size: 30px; }
.couch-shell .couch-tab { font-size: 22px; min-height: 36px; padding: 8px 20px; }
.couch-shell .couch-tabs { background: #171717; border-radius: 14px; }
.couch-shell .couch-tab.active { background: #333; }
.couch-shell .couch-action,.couch-shell .couch-workspace-action { font-size: 22px; padding: 12px 20px; border: 1px solid #555; border-radius: 12px; }
.couch-shell .couch-library-action { background: #76b900; color: #111; }
.couch-shell .couch-panel-heading { font-size: 42px; }
.couch-shell .couch-caption,.couch-shell .couch-subtle,.couch-shell .couch-library-count { font-size: 20px; color: #b8b8b8; }
.couch-shell .couch-tile { padding: 0; border-radius: 0; background: transparent; box-shadow: none; }
.couch-shell .couch-cover { border-radius: 12px; border: 1px solid #666; background: #252525; box-shadow: 0 4px 12px alpha(black,.22); }
.couch-shell .couch-tile-title { color: #f2f2f2; font-size: 22px; font-weight: 500; }
.couch-shell .couch-library-grid { padding: 16px 12px 28px; }
.couch-shell .couch-scroll-fade-top { background-image: linear-gradient(0deg,alpha(black,0),#101010); }
.couch-shell .couch-scroll-fade-bottom { background-image: linear-gradient(0deg,#101010,alpha(black,0)); }
.couch-shell.light .couch-scroll-fade-top { background-image: linear-gradient(0deg,alpha(white,0),#fafafa); }
.couch-shell.light .couch-scroll-fade-bottom { background-image: linear-gradient(0deg,#fafafa,alpha(white,0)); }
.couch-shell.dark .couch-scroll-fade-top { background-image: linear-gradient(0deg,alpha(black,0),#2a2a2a); }
.couch-shell.dark .couch-scroll-fade-bottom { background-image: linear-gradient(0deg,#2a2a2a,alpha(black,0)); }
.couch-shell .couch-tile:focus-visible .couch-cover { outline: 4px solid #f2f2f2; outline-offset: 5px; }
.couch-shell .couch-view { border-radius: 10px; font-size: 20px; padding: 10px 18px; }
.couch-shell .couch-library-toolbar { padding: 16px 20px; background: #1c1c1c; border-radius: 16px; }
.couch-shell .couch-mode-segments { background: #292929; border-radius: 12px; padding: 4px; }
.couch-shell .couch-feature-badge { background: #252525; border: 1px solid #454545; border-radius: 10px; padding: 8px 12px; }
.couch-shell .couch-package-pill { background: #292929; border-radius: 999px; padding: 8px 16px; }
.couch-shell.light .couch-library-toolbar { background: white; }
.couch-shell.light .couch-mode-segments,.couch-shell.light .couch-package-pill { background: #e7e7e7; }
.couch-shell .couch-list-row { padding: 18px; min-height: 74px; background: #1c1c1c; border-radius: 12px; border: 1px solid #454545; }
.couch-shell .couch-list-row:focus-within { outline: 4px solid #f2f2f2; outline-offset: 4px; }
.couch-shell .couch-list-title { color: #f2f2f2; font-size: 24px; }
.couch-shell .couch-list-status { color: #b8b8b8; font-size: 20px; }
.couch-shell button:focus-visible,.couch-shell .focused { outline: 4px solid #f2f2f2; outline-offset: 4px; }
.couch-shell .couch-tile:focus-visible,.couch-shell .couch-tile.focused { outline: none; box-shadow: none; }
.couch-shell .couch-tile.focused .couch-cover { outline: 4px solid #f2f2f2; outline-offset: 5px; }
.couch-shell.light .couch-tile.focused .couch-cover,.couch-shell.light .couch-tile:focus-visible .couch-cover { outline-color: #222; }
.couch-shell.controller-focus .couch-tile.focused .couch-cover { transform: scale(1.025); transition: transform 150ms ease-out; }
.couch-shell.controller-focus button.focused { box-shadow: 0 4px 14px alpha(black,.30); }
.couch-shell.controller-focus .couch-tile.focused { box-shadow: none; }
.couch-shell.reduced-motion .couch-cover { transform: none; transition: none; }
.couch-shell.reduced-motion.controller-focus .couch-tile.focused .couch-cover { transform: none; transition: none; }
.couch-shell .couch-view:checked { background: #333; color: #f2f2f2; }
.couch-shell.compact .couch-brand { font-size: 40px; }
.couch-shell.compact .couch-panel-heading { font-size: 36px; }
.couch-shell.compact .couch-action { font-size: 20px; padding: 10px 16px; }
.couch-shell.compact .couch-view { font-size: 18px; padding: 8px 14px; }
.couch-shell.compact .couch-content { padding: 16px 28px 12px; }
.couch-shell .couch-workspace { padding: 22px 0 8px; }
.couch-shell .couch-sidebar-item { font-size: 22px; padding: 16px; }
.couch-shell .couch-setting-control,.couch-shell .couch-adjustment { background: #202020; color: #f2f2f2; padding: 24px; border-radius: 12px; }
.couch-shell .couch-adjustment-value { font-size: 36px; }
.couch-shell .couch-prompts { font-size: 20px; }
.couch-shell .couch-bumper { padding: 2px 7px; border: 1px solid alpha(white,.24); background: alpha(white,.07); font-size: 13px; border-radius: 5px; }
.couch-shell.details-open .couch-content { padding: 0; }
.couch-shell.details-open .couch-header,.couch-shell.details-open .couch-footer { margin: 16px 40px; }
.couch-shell .couch-embedded-details .game-detail-root,.couch-shell .couch-embedded-details .game-detail-main,.couch-shell .couch-embedded-details .game-detail-sidebar { background: #101010; color: #f2f2f2; border-radius: 0; }
.couch-shell .couch-embedded-details .game-banner { border-radius: 0; }
.couch-shell .couch-embedded-details .banner-shade { background-image: linear-gradient(0deg,#101010,alpha(black,.12) 75%),linear-gradient(90deg,alpha(black,.8),alpha(black,.05)); }
.couch-shell .couch-embedded-details .game-detail-close { border-radius: 12px; font-size: 20px; padding: 8px 14px; min-height: 0; min-width: 0; border: 0; background: rgba(18,18,18,.86); color: white; }
.couch-shell .couch-information { background: transparent; }
.couch-shell .couch-information-row { background: #1c1c1c; }
.couch-shell .couch-information-row.first { border-top-left-radius: 12px; border-top-right-radius: 12px; }
.couch-shell .couch-information-row.last { border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; border-bottom: 0; }
.couch-shell .couch-information-row { padding: 22px 26px; border-bottom: 1px solid #454545; }
.couch-shell .couch-information-value { color: #b8b8b8; }
.couch-shell.light .couch-information-row { background: white; }
.couch-shell.light .couch-information-value { color: #666; }
.couch-shell .couch-embedded-details .game-detail-body { padding: 26px 40px; }
.couch-shell .couch-embedded-details .game-detail-sidebar label { font-size: 22px; }
.couch-shell .couch-embedded-details .game-detail-main label { font-size: 22px; }
.couch-shell .couch-embedded-details .game-detail-main .game-detail-title { font-size: 42px; }
.couch-shell .couch-embedded-details .game-detail-main .dim-label { color: #b8b8b8; }
.couch-shell.light { color: #222; background: #f0f0f0; }
.couch-shell.light .couch-shade { background: #fafafa; }
.couch-shell.light .couch-tile-title,.couch-shell.light .couch-list-title { color: #222; }
.couch-shell.light .couch-tabs,.couch-shell.light .couch-setting-control,.couch-shell.light .couch-adjustment,.couch-shell.light .couch-list-row { background: #fff; color: #222; }
.couch-shell.light .couch-tab,.couch-shell.light .couch-view,.couch-shell.light .couch-sidebar-item { color: #222; }
.couch-shell.light .couch-tab.active,.couch-shell.light .couch-sidebar-item.active { background: #dedede; color: #222; }
.couch-shell.light .couch-tab.focused { background: #222; color: white; }
.couch-shell.light .couch-prompt-button,.couch-shell.light .couch-prompts { color: #555; }
.couch-shell.light .couch-keycap { background: #e7e7e7; color: #222; }
.couch-shell.light .couch-view:checked { background: #e7e7e7; color: #222; }
.couch-shell.light .couch-caption,.couch-shell.light .couch-subtle,.couch-shell.light .couch-library-count,.couch-shell.light .couch-list-status { color: #666; }
.couch-shell.light button:focus-visible,.couch-shell.light .focused { outline-color: #222; }
.couch-shell.light .couch-embedded-details .game-detail-root,.couch-shell.light .couch-embedded-details .game-detail-main,.couch-shell.light .couch-embedded-details .game-detail-sidebar { background: #fafafa; color: #222; }
.couch-shell.light .couch-embedded-details .banner-shade { background-image: linear-gradient(0deg,#fafafa,alpha(white,.12) 75%),linear-gradient(90deg,alpha(white,.8),alpha(white,.05)); }
.couch-shell.dark .couch-library-toolbar,.couch-shell.dark .couch-information-row { background: #303030; }
.couch-shell.dark .couch-mode-segments,.couch-shell.dark .couch-package-pill,.couch-shell.dark .couch-feature-badge { background: #383838; }
.couch-shell.dark .couch-shade,.couch-shell.dark .couch-embedded-details .game-detail-root,.couch-shell.dark .couch-embedded-details .game-detail-main,.couch-shell.dark .couch-embedded-details .game-detail-sidebar { background: #2a2a2a; }
.couch-shell.dark .couch-embedded-details .banner-shade { background-image: linear-gradient(0deg,#2a2a2a,alpha(black,.12) 75%),linear-gradient(90deg,alpha(black,.8),alpha(black,.05)); }
'''


class ControllerGlyph(Gtk.DrawingArea):
    """Fixed-aspect face buttons; PlayStation marks are drawn as geometry."""
    def __init__(self, family, key):
        super().__init__(content_width=26, content_height=26, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        self.family = family
        self.key = key
        self.update_property([Gtk.AccessibleProperty.LABEL], [f'{family.title()} {key} button'])
        self.set_draw_func(self.draw)

    def draw(self, _widget, context, width, height):
        context.save()
        size = min(width, height)
        context.translate((width - size) / 2, (height - size) / 2)
        context.scale(size / 26, size / 26)
        color=self.get_style_context().get_color()
        context.set_source_rgba(color.red,color.green,color.blue,color.alpha)
        if self.family == 'generic':
            positions={'South':(13,21),'East':(21,13),'North':(13,5),'West':(5,13)}
            for name,(x,y) in positions.items():
                context.arc(x,y,3.5,0,6.283185)
                if name==self.key:context.fill()
                else:context.set_line_width(1);context.stroke()
        elif self.family == 'playstation':
            context.set_line_width(2)
            context.set_line_join(1)
            context.set_line_cap(1)
            if self.key == '×':
                context.move_to(6, 6); context.line_to(20, 20)
                context.move_to(20, 6); context.line_to(6, 20)
            elif self.key == '○':
                context.arc(13, 13, 9, 0, 6.283185)
            elif self.key == '△':
                context.move_to(13, 3); context.line_to(24, 22)
                context.line_to(2, 22); context.close_path()
            else:
                context.rectangle(4, 4, 18, 18)
            context.stroke()
        else:
            context.arc(13, 13, 12, 0, 6.283185)
            context.fill()
            ink=.98 if (.2126*color.red+.7152*color.green+.0722*color.blue)<.5 else .10
            context.set_source_rgb(ink,ink,ink)
            context.select_font_face('sans-serif', 0, 1)
            context.set_font_size(14)
            x, y, w, h, _, _ = context.text_extents(self.key)
            context.move_to((26 - w) / 2 - x, (26 - h) / 2 - y)
            context.show_text(self.key)
        context.restore()


class CouchShell(Gtk.Overlay):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.page = 'library'
        self.game_origin = 'library'
        self.preset_origin = 'library'
        self.library_view = owner.settings.get('gaming_mode_view', 'posters')
        self.library_origin=None;self.restoring_library=False
        self.pending_origin={};self.pending_filter=None
        self.details_panel=None;self.details_game=None
        self.view_index = 0
        self.layout_width = 1280
        self.columns = 1
        self.game = None
        self.entries = []
        self.controls = []
        self.pending = {}
        self.dlss_selection = None
        self.selection_kind = 'dlss'
        self.utility_origin = 'library'
        self.settings_section='Gaming Mode'
        self.tools_section='Graphics'
        self.scroll_tick = 0
        self.selection = {}
        self.current = 0
        self.art_path = None
        self.zone = 'content'
        self.tab_index = 0
        self.compact = True
        self.add_css_class('couch-shell')
        self.add_css_class('compact')
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
        self.game_mode_provider=Gtk.CssProvider()
        self.game_mode_provider.load_from_data(GAME_MODE_CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.game_mode_provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+8)
        self.apply_theme()
        self.accent_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.accent_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 5)
        self.artwork_border_provider=Gtk.CssProvider()
        self.artwork_border_colors={}
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.artwork_border_provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+9)
        self.scale_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.scale_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10)
        self.layout_height = 820
        self.accent_color = None
        self.apply_accent(None)
        self.art = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.art.set_opacity(0.9)
        self.art_stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=3500)
        self.art_stack.add_named(self.art,'a')
        self.next_art=Gtk.Picture(content_fit=Gtk.ContentFit.COVER,can_shrink=True);self.next_art.set_opacity(0.9)
        self.art_stack.add_named(self.next_art,'b')
        self.set_child(self.art_stack)
        self.ambient_index=-1;self.ambient_timer=0
        self.connect('map',self.start_ambient)
        self.connect('unmap',self.stop_ambient)
        shade = Gtk.Box()
        shade.add_css_class('couch-shade')
        shade.set_can_target(False)
        self.add_overlay(shade)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        self.main = main
        self.hint_timer = 0
        self.navigation_position = None
        main.add_css_class('couch-content')
        self.add_overlay(main)

        top = Gtk.CenterBox()
        self.top = top
        top.add_css_class('couch-header')
        brand = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        self.brand_icon = icon = owner.make_brand_icon(72)
        brand.append(icon)
        brand.append(label('rtxForge', 'couch-brand'))
        self.brand_button=Gtk.Button(child=brand,tooltip_text='Main menu')
        self.brand_button.add_css_class('flat')
        self.brand_button.connect('clicked',lambda _:self.open('menu'))
        top.set_start_widget(self.brand_button)
        tabs = Gtk.Box(valign=Gtk.Align.CENTER)
        tabs.add_css_class('couch-tabs')
        self.tab_bar = tabs
        self.tabs = []
        for title, page in [('Library', 'library'), ('Presets', 'presets'), ('Settings', 'settings')]:
            button = Gtk.Button(label=title)
            button.add_css_class('couch-tab')
            button.connect('clicked', lambda _, p=page: self.open(p))
            tabs.append(button)
            self.tabs.append(button)
        self.bumper_labels=[]
        for text,first in [('LB',True),('RB',False)]:
            hint=label(text);hint.add_css_class('couch-bumper')
            self.bumper_labels.append(hint)
            tabs.prepend(hint) if first else tabs.append(hint)
        top.set_center_widget(tabs)
        self.badge_started=time.monotonic()
        self.context = label('Preview' if owner.options.demo else 'Game Mode', 'couch-context')
        if not owner.options.demo:GLib.timeout_add(2400,lambda:(self.context.set_visible(False),False)[1])
        utilities = Gtk.Box(spacing=10, valign=Gtk.Align.CENTER)
        utilities.append(self.context)
        self.settings_button = Gtk.Button(icon_name='emblem-system-symbolic', tooltip_text='Settings')
        self.settings_button.update_property([Gtk.AccessibleProperty.LABEL], ['Settings'])
        self.settings_button.add_css_class('couch-tab')
        self.settings_button.add_css_class('couch-settings')
        self.settings_button.connect('clicked', lambda _:self.open('settings'))
        utilities.append(self.settings_button)
        self.tabs.append(self.brand_button)
        top.set_end_widget(utilities)
        main.append(top)

        self.body = Gtk.Stack(vexpand=True, hhomogeneous=False, vhomogeneous=False)
        self.body.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.body.set_transition_duration(180)
        main.append(self.body)
        feature = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        game_header=Gtk.Box(spacing=24,vexpand=True,valign=Gtk.Align.END)
        self.poster_slot=Gtk.Box(valign=Gtk.Align.CENTER)
        game_header.append(self.poster_slot)
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True, valign=Gtk.Align.CENTER)
        hero.set_margin_bottom(8)
        self.title = label('Your library', 'couch-title', wrap=True)
        self.title.set_max_width_chars(32)
        self.title.set_halign(Gtk.Align.START)
        hero.append(self.title)
        self.detail = label('', 'couch-detail', wrap=True)
        self.detail.set_max_width_chars(64)
        hero.append(self.detail)
        self.game_metadata = label('', 'couch-game-meta', wrap=True)
        self.game_metadata.set_max_width_chars(70)
        hero.append(self.game_metadata)
        self.game_summary = label('', 'couch-game-summary', wrap=True)
        self.game_summary.set_max_width_chars(70)
        self.game_summary.set_lines(2)
        self.game_summary.set_ellipsize(Pango.EllipsizeMode.END)
        hero.append(self.game_summary)
        game_header.append(hero)
        feature.append(game_header)
        self.library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        heading = Gtk.Box()
        heading.append(label('Your games', 'couch-section'))
        self.count = label('', 'couch-subtle')
        self.count.set_visible(False)
        self.count.set_hexpand(True)
        self.count.set_halign(Gtk.Align.END)
        heading.append(self.count)
        self.library_link = Gtk.Button(label='View library', tooltip_text='Open the full library')
        self.library_link.add_css_class('couch-view')
        self.library_link.set_visible(False)
        self.library_link.connect('clicked', lambda _: self.open('library'))
        heading.append(self.library_link)
        self.library.append(heading)
        self.shelf = Gtk.Box(spacing=12)
        self.shelf_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.EXTERNAL, vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.shelf_scroll.set_min_content_height(186)
        self.shelf_scroll.set_child(self.shelf)
        shelf_overlay=Gtk.Overlay(child=self.shelf_scroll)
        self.shelf_arrows={}
        for icon,action,align in [('pan-start-symbolic','left',Gtk.Align.START),('pan-end-symbolic','right',Gtk.Align.END)]:
            control=Gtk.Button(icon_name=icon,tooltip_text='Previous game' if action=='left' else 'Next game',halign=align,valign=Gtk.Align.CENTER)
            control.add_css_class('couch-view')
            control.connect('clicked',lambda _,action=action:self.navigate(action))
            shelf_overlay.add_overlay(control);self.shelf_arrows[action]=control
        adjustment=self.shelf_scroll.get_hadjustment()
        adjustment.connect('value-changed',self.update_shelf_arrows)
        adjustment.connect('changed',self.update_shelf_arrows)
        self.library.append(shelf_overlay)
        feature.append(self.library)
        self.game_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        self.actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=4,max_children_per_line=4,row_spacing=12,column_spacing=12)
        self.action_tiles=Adw.BreakpointBin(child=self.actions,width_request=400,height_request=108)
        breakpoint=Adw.Breakpoint.new(Adw.BreakpointCondition.parse('max-width: 1000px'))
        breakpoint.add_setter(self.actions,'min-children-per-line',2)
        breakpoint.add_setter(self.actions,'max-children-per-line',2)
        breakpoint.add_setter(self.action_tiles,'height-request',228)
        self.action_tiles.add_breakpoint(breakpoint)
        self.game_actions.append(self.action_tiles)
        self.action_hint = label('', 'couch-caption', wrap=True)
        self.action_hint.set_max_width_chars(70)
        self.action_hint.set_size_request(-1, 50)
        self.game_actions.append(self.action_hint)
        self.game_actions.set_margin_bottom(32)
        feature.append(self.game_actions)
        self.body.add_named(feature, 'feature')

        library_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        library_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24)
        self.library_header=library_header;self.library_page=library_page
        library_header.add_css_class('couch-library-header')
        library_title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True)
        self.library_heading = label('Library', 'couch-panel-heading')
        library_title.append(self.library_heading)
        self.library_count = label('', 'couch-library-count')
        library_title.append(self.library_count)
        heading_row=Gtk.Box(spacing=20)
        heading_row.append(library_title)
        library_header.append(heading_row)
        self.view_buttons = []
        self.library_action = self.owner.make_action_button('Install to all',lambda _:self.library_primary_action())
        self.library_action.add_css_class('couch-action')
        self.library_action.add_css_class('couch-library-action')
        self.filter_button=self.owner.make_action_button('Filter',lambda _:self.open('library_filters'))
        self.filter_button.add_css_class('couch-view')
        self.library_restore=self.owner.make_action_button('Restore',lambda _:self.owner.launch_action('uninstall',targets=self.operation_targets(installed=True)))
        self.library_update=self.owner.make_action_button('Update DLSS',lambda _:self.owner.update_dlss_games(self.operation_targets()))
        self.library_restore.add_css_class('destructive-action')
        self.library_action_group=Gtk.Box(spacing=10,valign=Gtk.Align.CENTER)
        for control in (self.library_action,self.library_restore,self.library_update):
            control.add_css_class('couch-action');self.library_action_group.append(control)
        features=Gtk.Box(spacing=18,valign=Gtk.Align.CENTER)
        features.append(label('Features','couch-section'))
        segments=Gtk.Box(spacing=4)
        segments.add_css_class('couch-mode-segments')
        self.feature_controls={}
        for mode,title in [('nr-only','NR Only'),('mfg-only','MFG Only'),('nr-mfg','NR + MFG')]:
            control=Gtk.ToggleButton(label=title)
            control.add_css_class('couch-view')
            control.connect('clicked',lambda _,mode=mode:(self.owner.profile_group.set_active_name(mode),self.sync_library_modes()))
            segments.append(control);self.feature_controls[mode]=control
        features.append(segments)
        self.library_controls=Gtk.Box(spacing=20,valign=Gtk.Align.CENTER)
        self.library_controls.add_css_class('couch-library-toolbar')
        features.set_hexpand(True);self.library_controls.append(features)
        self.library_controls.append(self.library_action_group)
        library_header.append(self.library_controls)
        library_page.append(library_header)
        choices=Gtk.CenterBox()
        filters=Gtk.Box(spacing=12,valign=Gtk.Align.CENTER)
        self.filter_summary=label('','couch-caption')
        filters.append(self.filter_summary);filters.append(self.filter_button)
        choices.set_start_widget(filters)
        views=Gtk.Box(spacing=4,valign=Gtk.Align.CENTER)
        views.add_css_class('couch-mode-segments')
        self.layout_controls={}
        for view,title in [('posters','Posters'),('capsules','Wide Capsule'),('list','List')]:
            control=Gtk.ToggleButton(label=title)
            control.add_css_class('couch-view')
            control.connect('clicked',lambda _,view=view:self.set_library_view(view))
            views.append(control);self.layout_controls[view]=control
        choices.set_center_widget(views)
        self.select_button=self.owner.make_action_button('Select Games',lambda _:self.start_selection())
        self.select_button.add_css_class('couch-view');choices.set_end_widget(self.select_button)
        # Two explicit directional rows, in the same order as the visible controls.
        self.library_focus_rows=[[*self.feature_controls.values(),self.library_action,self.library_restore,self.library_update],
                                 [self.filter_button,*self.layout_controls.values(),self.select_button]]
        self.view_buttons=[control for controls in self.library_focus_rows for control in controls]
        for index,control in enumerate(self.view_buttons):
            focus=Gtk.EventControllerFocus()
            focus.connect('enter',lambda _,index=index:(setattr(self,'zone','views'),setattr(self,'view_index',index),self.update_tabs()))
            control.add_controller(focus)
        self.package_label=label('','couch-caption')
        package=Gtk.Box(spacing=10,valign=Gtk.Align.CENTER)
        package.add_css_class('couch-package-pill')
        package.append(Gtk.Image.new_from_icon_name('package-x-generic-symbolic'));package.append(self.package_label)
        package.set_hexpand(True);package.set_halign(Gtk.Align.END);heading_row.append(package)
        library_page.append(choices)
        self.owner.profile_group.connect('notify::active-name',lambda *_:self.sync_library_modes())
        self.grid = Gtk.Grid(column_spacing=18, row_spacing=20, column_homogeneous=True, hexpand=True, valign=Gtk.Align.START)
        self.grid.add_css_class('couch-library-grid')
        self.grid_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.EXTERNAL, vexpand=True)
        self.grid_scroll.set_child(self.grid)
        viewport=self.grid_scroll.get_child()
        if isinstance(viewport,Gtk.Viewport):viewport.set_scroll_to_focus(False)
        self.grid_scroll.get_vadjustment().connect('value-changed',lambda adjustment:self.update_branding(adjustment.get_value()))
        grid_overlay=Gtk.Overlay(child=self.grid_scroll)
        self.grid_overlay=grid_overlay
        self.scroll_fades=[]
        for align,style in [(Gtk.Align.START,'top'),(Gtk.Align.END,'bottom')]:
            fade=Gtk.Box(height_request=12,valign=align,can_target=False)
            fade.add_css_class('couch-scroll-fade-'+style);grid_overlay.add_overlay(fade);self.scroll_fades.append(fade)
        self.grid_scroll.get_vadjustment().connect('value-changed',lambda *_:self.update_scroll_fades())
        self.grid_scroll.get_vadjustment().connect('changed',lambda *_:self.update_scroll_fades())
        library_page.append(grid_overlay)
        self.library_state=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER,vexpand=True)
        library_page.append(self.library_state)
        self.body.add_named(library_page, 'library')

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.panel = panel
        self.panel.set_size_request(660, -1)
        headings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.heading = label('', 'couch-panel-heading')
        self.panel_detail = label('', 'couch-caption')
        self.panel_detail.set_ellipsize(Pango.EllipsizeMode.END)
        headings.append(self.heading)
        headings.append(self.panel_detail)
        panel.append(headings)
        self.menu = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, activate_on_single_click=False)
        self.menu.add_css_class('couch-options')
        self.menu.connect('row-selected', self.selected)
        self.menu.connect('row-activated', lambda _, row: self.activate(row.get_index()))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(360)
        scroll.set_child(self.menu)
        panel.append(scroll)
        self.panel_scroll = scroll
        self.hint = label('', 'couch-caption', wrap=True)
        self.hint.set_max_width_chars(64)
        panel.append(self.hint)
        self.body.add_named(panel, 'panel')
        self.workspace=Gtk.Box(spacing=32,vexpand=True)
        self.workspace.add_css_class('couch-workspace')
        self.section_nav=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,valign=Gtk.Align.START)
        self.section_nav.set_size_request(180,-1)
        self.workspace.append(self.section_nav)
        main_panel=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24,hexpand=True)
        self.workspace.append(main_panel)
        self.workspace_heading=label('','couch-panel-heading')
        self.workspace_detail=label('','couch-caption',wrap=True)
        main_panel.append(self.workspace_heading);main_panel.append(self.workspace_detail)
        self.workspace_content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=24)
        self.workspace_scroll=Gtk.ScrolledWindow(hexpand=True,vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.workspace_scroll.set_child(self.workspace_content);main_panel.append(self.workspace_scroll)
        self.workspace_footer=Gtk.Box(spacing=12,homogeneous=True,halign=Gtk.Align.START)
        main_panel.append(self.workspace_footer)
        self.workspace_hint=label('','couch-caption',wrap=True)
        main_panel.append(self.workspace_hint)
        self.body.add_named(self.workspace,'workspace')


        self.bottom_nav = Gtk.Box(halign=Gtk.Align.CENTER)
        main.append(self.bottom_nav)
        footer = Gtk.Box(spacing=24)
        self.footer = footer
        footer.add_css_class('couch-footer')
        self.prompts = Gtk.Box(spacing=22)
        self.prompts.add_css_class('couch-prompts')
        footer.append(self.prompts)
        self.footer_note = label('', 'couch-subtle')
        self.footer_note.set_ellipsize(Pango.EllipsizeMode.END)
        self.footer_note.set_hexpand(True)
        self.footer_note.set_halign(Gtk.Align.END)
        footer.append(self.footer_note)
        main.append(footer)
        self.apply_navigation_preferences()
        self.render()

    def apply_theme(self):
        theme=self.owner.settings.get('gaming_mode_theme','night')
        if hasattr(self,'artwork_border_colors'):self.artwork_border_colors={}
        for name in ('light','dark','night'):self.remove_css_class(name)
        self.add_css_class(theme if theme in ('light','dark','night') else 'night')
        settings=Gtk.Settings.get_default()
        reduced=settings and not settings.get_property('gtk-enable-animations')
        self.add_css_class('reduced-motion') if reduced else self.remove_css_class('reduced-motion')

    def update_scroll_fades(self):
        adjustment=self.grid_scroll.get_vadjustment()
        self.scroll_fades[0].set_visible(adjustment.get_value()>1)
        self.scroll_fades[1].set_visible(adjustment.get_value()+adjustment.get_page_size()<adjustment.get_upper()-1)

    def details_container(self):
        if self.details_panel:
            self.details_panel.finish_close()
            if self.details_panel.get_parent():self.body.remove(self.details_panel)
        panel=EmbeddedDetails(self);self.details_panel=panel
        shell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header=Gtk.Box();body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll=Gtk.ScrolledWindow(child=body);footer=Gtk.Box()
        shell.append(header);shell.append(scroll);shell.append(footer)
        panel.set_child(shell);self.body.add_named(panel,'details')
        return panel,body,footer

    def has_dirty_presets(self):
        if self.page in ('presets','game_presets'):return self.pending!=self.pending_origin
        if self.page=='game':return bool(getattr(self.owner,'detail_dirty',lambda:False)())
        return False

    def leave(self,action):
        if not self.has_dirty_presets():action();return
        origin=self.owner.get_focus()
        dialog=Adw.AlertDialog(heading='Discard unsaved changes?',body='Your changes have not been applied.')
        dialog.add_response('stay','Stay');dialog.add_response('discard','Discard')
        dialog.set_default_response('stay');dialog.set_close_response('stay')
        def response(_,choice):
            if choice=='discard':
                if self.page=='game':getattr(self.owner,'detail_discard',lambda:None)()
                else:self.pending=dict(self.pending_origin)
                action()
            elif origin:origin.grab_focus()
        dialog.connect('response',response);dialog.present(self.owner)

    def request_exit(self):
        if self.owner.busy:return
        def confirm():
            dialog=Adw.AlertDialog(heading='Exit rtxForge?',body='Return to your current desktop or gaming session.')
            dialog.add_response('stay','Stay');dialog.add_response('exit','Exit App')
            dialog.set_default_response('stay');dialog.set_close_response('stay')
            dialog.connect('response',lambda _,choice:self.owner.close() if choice=='exit' else None)
            dialog.present(self.owner)
        self.leave(confirm)

    def start_selection(self):
        if self.dlss_selection is not None:self.show_selection_menu();return
        self.selection_kind='install';self.dlss_selection=set();self.render()

    def select_all(self):
        targets=self.install_targets() if self.selection_kind=='install' else self.preset_targets() if self.selection_kind=='presets' else self.operation_targets()
        self.dlss_selection={game['game'] for game in targets};self.open('library')

    def stage_filter(self,key):
        self.pending_filter=key;self.render(self.current)

    def apply_filter(self):
        key=self.pending_filter;self.pending_filter=None;self.set_library_filter(key)

    def details_navigate(self,action):
        focus=self.owner.get_focus()
        if isinstance(focus,Gtk.DropDown) and action in ('left','right','accept'):
            count=focus.get_model().get_n_items()
            if count:focus.set_selected((focus.get_selected()+(-1 if action=='left' else 1))%count)
            return
        if isinstance(focus,Gtk.Scale) and action in ('left','right'):
            adjustment=focus.get_adjustment();delta=adjustment.get_step_increment()*(-1 if action=='left' else 1)
            focus.set_value(max(adjustment.get_lower(),min(focus.get_value()+delta,adjustment.get_upper())))
            return
        if action=='accept':
            if focus:focus.activate()
        elif action in ('left','right','up','down'):
            if focus is getattr(self.owner,'detail_scroll',None) and action in ('up','down'):
                adjustment=focus.get_vadjustment();delta=80 if action=='down' else -80
                position=adjustment.get_value();target=max(0,min(position+delta,adjustment.get_upper()-adjustment.get_page_size()))
                if abs(target-position)<1:self.child_focus(Gtk.DirectionType.DOWN if action=='down' else Gtk.DirectionType.UP)
                else:adjustment.set_value(target)
            else:self.child_focus({'left':Gtk.DirectionType.LEFT,'right':Gtk.DirectionType.RIGHT,'up':Gtk.DirectionType.UP,'down':Gtk.DirectionType.DOWN}[action])

    def restore_library(self):
        snapshot=self.library_origin
        if not snapshot:return False
        self.restoring_library=True
        index=next((i for i,e in enumerate(self.entries) if (e.get('game') or {}).get('game')==snapshot['game']),0)
        self.focus(index)
        self.grid_scroll.get_vadjustment().set_value(snapshot['scroll'])
        self.update_branding(snapshot['scroll']);self.restoring_library=False
        return False

    def utility_dialog(self,title):
        from rtxforge_gtk import PresentationDialog
        dialog=PresentationDialog(self.owner,title=title,content_width=700,content_height=500)
        dialog.add_css_class('couch-dialog')
        dialog.add_css_class(self.owner.settings.get('gaming_mode_theme','night'))
        shell=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18)
        for edge in ('top','bottom','start','end'):getattr(shell,'set_margin_'+edge)(32)
        shell.append(label(title,'couch-panel-heading'))
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
        choices=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        scroll.set_child(choices);shell.append(scroll)
        dialog.couch_footer=Gtk.Box(spacing=18,halign=Gtk.Align.END)
        shell.append(dialog.couch_footer);dialog.set_child(shell)
        return dialog,choices

    def show_menu(self):
        origin=self.owner.get_focus();dialog,choices=self.utility_dialog('rtxForge')
        for title,action in [('Library',lambda:self.open('library')),('Packages',lambda:self.open('packages')),('Refresh Library',self.owner.scan),('Desktop UI',lambda:self.leave(lambda:self.owner.set_big_picture_ui(False))),('Exit App',self.request_exit)]:
            control=self.owner.make_action_button(title,lambda _,action=action:(dialog.close(),GLib.idle_add(lambda:(action(),False)[1])))
            control.add_css_class('couch-workspace-action')
            if title=='Exit App':control.set_sensitive(not self.owner.busy)
            choices.append(control)
        back=self.owner.make_action_button('Back',lambda _:dialog.close());back.add_css_class('couch-workspace-action');dialog.couch_footer.append(back)
        dialog.connect('closed',lambda *_:origin.grab_focus() if origin and origin.get_mapped() else None)
        dialog.present(self.owner)

    def show_filters(self):
        dialog,choices=self.utility_dialog('Filter library')
        choices.append(label('Choose the games shown in your Library.','couch-caption',wrap=True))
        current=getattr(self.owner,'filter','available');pending={'value':current};controls={}
        def pick(key):
            pending['value']=key
            for name,control in controls.items():control.set_active(name==key)
        for key,title in [('available','Available'),('installed','Installed'),('all','All')]:
            control=Gtk.ToggleButton(label=title,active=key==current)
            control.add_css_class('couch-filter-option')
            control.add_css_class('couch-workspace-action');control.connect('clicked',lambda _,key=key:pick(key))
            controls[key]=control;choices.append(control)
        for title,action in [('Reset',lambda:pick('available')),('Back',dialog.close),('Apply',lambda:(dialog.close(),self.set_library_filter(pending['value'])))]:
            control=self.owner.make_action_button(title,lambda _,action=action:action());control.add_css_class('couch-workspace-action')
            if title=='Apply':control.add_css_class('suggested-action')
            dialog.couch_footer.append(control)
        dialog.connect('closed',lambda *_:self.filter_button.grab_focus())
        dialog.present(self.owner)
        GLib.idle_add(lambda:(controls[current].grab_focus(),False)[1])

    def show_selection_menu(self):
        dialog,choices=self.utility_dialog('Select Games')
        for title,action in [('Select all',self.select_all),('Clear',lambda:(self.dlss_selection.clear(),self.render())),('Back',lambda:(setattr(self,'dlss_selection',None),self.render()))]:
            control=self.owner.make_action_button(title,lambda _,action=action:(dialog.close(),action()));control.add_css_class('couch-workspace-action');choices.append(control)
        dialog.present(self.owner)

    def panel_navigation(self,dialog):
        nav=Gtk.Box(spacing=4,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        nav.add_css_class('couch-tabs')
        nav.add_css_class('couch-shell')
        for page,title in [('library','Library'),('presets','Presets'),('settings','Settings')]:
            control=Gtk.Button(label=title)
            control.add_css_class('couch-tab')
            if self.page==page:control.add_css_class('active')
            control.set_sensitive(not self.owner.busy or self.owner.task_kind=='art')
            def go(*_,page=page):
                if not dialog.get_can_close():return
                dialog.close()
                self.open(page)
            control.connect('clicked',go)
            nav.append(control)
        return nav

    def apply_navigation_preferences(self):
        position=self.owner.settings.get('navigation_position','top')
        if position != self.navigation_position:
            if self.navigation_position == 'bottom':self.bottom_nav.remove(self.tab_bar)
            else:self.top.set_center_widget(None)
            if position == 'bottom':self.bottom_nav.append(self.tab_bar)
            else:self.top.set_center_widget(self.tab_bar)
            self.navigation_position=position
            self.bottom_nav.set_visible(position=='bottom')
            self.add_css_class('bottom-navigation') if position=='bottom' else self.remove_css_class('bottom-navigation')
            self.footer_note.set_visible(position!='bottom' and self.layout_width>=1050)
            self.prompts.set_hexpand(position=='bottom')
            self.prompts.set_halign(Gtk.Align.CENTER if position=='bottom' else Gtk.Align.START)
            self.wake_hints()
        auto=position=='bottom' or self.owner.settings.get('controller_hints','always')=='auto'
        if auto != getattr(self,'hints_auto',None):
            self.hints_auto=auto
            self.wake_hints()

    def wake_hints(self):
        if self.hint_timer:GLib.source_remove(self.hint_timer)
        self.prompts.set_opacity(1)
        self.prompts.set_can_target(True)
        self.hint_timer=0
        if getattr(self,'hints_auto',False):self.hint_timer=GLib.timeout_add(3500,self.hide_hints)

    def hide_hints(self):
        if self.prompts.get_focus_child():
            self.hint_timer=GLib.timeout_add(3500,self.hide_hints)
            return False
        self.hint_timer=0
        # Preserve the navigation's allocation while hints fade away.
        self.prompts.set_opacity(0)
        self.prompts.set_can_target(False)
        return False

    def update_prompts(self):
        keyboard=getattr(self.owner,'input_kind','keyboard')!='controller'
        self.remove_css_class('controller-focus') if keyboard else self.add_css_class('controller-focus')
        family = self.owner.settings.get('controller_glyphs', 'auto')
        if family == 'auto':
            family = self.owner.controller.family
        bumper=('L1','R1') if family=='playstation' else ('L','R') if family=='nintendo' else ('LB','RB')
        for text,widget in zip(bumper,self.bumper_labels):widget.set_text(text)
        keys = controller_input.GLYPHS.get(family, controller_input.GLYPHS['generic'])
        caption = 'Select' if self.dlss_selection is not None else 'Open' if self.page in ('dashboard', 'library') else 'Select'
        if keyboard:keys=['Enter','Esc','Ctrl+L'];family='keyboard'
        spec = (family, keys[0], keys[1], keys[2], self.page, caption, self.dlss_selection is not None)
        if spec == getattr(self, 'prompt_spec', None):
            return
        self.prompt_spec = spec
        clear(self.prompts)
        prompts = [(keys[0], caption), (keys[1], 'Back')]
        prompts.append((keys[2], 'Library'))
        for key, text in prompts:
            pair = Gtk.Box(spacing=7, valign=Gtk.Align.CENTER)
            if keyboard:
                cap=label(key);cap.add_css_class('couch-keycap');pair.append(cap)
                if key=='Enter':pair.prepend(Gtk.Image.new_from_icon_name('input-mouse-symbolic'))
            else:pair.append(ControllerGlyph(family, key))
            pair.append(label(text))
            control = Gtk.Button(child=pair)
            control.add_css_class('couch-prompt-button')
            action = 'accept' if key == keys[0] else 'back' if key == keys[1] else 'search'
            control.connect('clicked', lambda _, action=action: self.navigate(action))
            self.prompts.append(control)
        if self.page=='library' and not keyboard:
            west={'playstation':'□','nintendo':'Y','generic':'West'}.get(family,'X')
            pair=Gtk.Box(spacing=7);pair.append(ControllerGlyph(family,west));pair.append(label('Select Games'))
            control=Gtk.Button(child=pair);control.add_css_class('couch-prompt-button');control.connect('clicked',lambda _:self.start_selection());self.prompts.append(control)
        self.footer_note.set_text(('Arrows navigate · Tab moves focus · Ctrl+, Settings' if keyboard else 'Bumpers switch pages'))

    def set_game(self, game):
        self.game = game
        self.apply_accent(game if self.page in ('game','features','tools','game_presets') else None)
        clear(self.poster_slot)
        path=self.owner.poster_art_path(game)
        self.game_poster=self.artwork_widget(path,'',140,210,'couch-game-poster')
        self.decorate_game_accent(self.game_poster,game)
        self.owner.decorate_support_artwork(self.game_poster,self.game_poster.picture,game,path)
        self.poster_slot.append(self.game_poster)
        self.title.set_text(game['name'])
        if game.get('blocked'):
            status = 'Unsupported'
        elif game.get('installed'):
            status = game.get('profile', 'Features installed') + ' installed'
            if game.get('nr_enabled') is not None:
                status += '  ·  Neural Rendering ' + ('on' if game['nr_enabled'] else 'off')
        else:
            status = 'Ready to configure'
        self.detail.set_text(status)
        values = [game.get('source'), game.get('developers'), game.get('release'), self.owner.game_status_label(game)]
        self.game_metadata.set_text(' · '.join(', '.join(map(str, value)) if isinstance(value, (list, tuple)) else str(value) for value in values if value))
        self.game_summary.set_text(re.sub('<[^>]+>', '', str(game.get('description') or '')))
        # A portrait cover is never enlarged into a landscape background.
        if self.page in ('game','features','tools','game_presets'):
            self.set_background(game.get('hero') or game.get('capsule'),animate=False)

    def set_background(self,path,animate=True):
        if path==self.art_path:return
        try:texture=Gdk.Texture.new_from_filename(str(path)) if path else None
        except (GLib.Error,OSError):return
        self.art_path=path
        animations=Gtk.Settings.get_default().get_property('gtk-enable-animations')
        self.art_stack.set_transition_duration(3500 if animate and animations else 0)
        self.next_art.set_paintable(texture)
        self.art_stack.set_visible_child(self.next_art)
        self.art,self.next_art=self.next_art,self.art

    def start_ambient(self,*_):
        # The accepted utility uses game art in Details, not a cycling Library.
        return False

    def stop_ambient(self,*_):
        if self.ambient_timer:GLib.source_remove(self.ambient_timer);self.ambient_timer=0

    def cycle_ambient(self):
        if self.page in ('game','features','tools','game_presets'):return True
        paths=list(dict.fromkeys(g.get('hero') or g.get('capsule') for g in self.owner.games if g.get('hero') or g.get('capsule')))
        if not paths:return True
        if self.art_path and not Gtk.Settings.get_default().get_property('gtk-enable-animations'):return True
        self.ambient_index=(self.ambient_index+1)%len(paths)
        self.set_background(paths[self.ambient_index])
        return True

    def update_shelf_arrows(self,*_):
        adjustment=self.shelf_scroll.get_hadjustment()
        self.shelf_arrows['left'].set_visible(adjustment.get_value()>adjustment.get_lower()+1)
        self.shelf_arrows['right'].set_visible(adjustment.get_value()+adjustment.get_page_size()<adjustment.get_upper()-1)

    def decorate_game_accent(self,widget,game):
        """Use the shared game palette only for artwork borders and focus rings."""
        for name in widget.get_css_classes():
            if name.startswith('art-'):widget.remove_css_class(name)
        has_art=bool(game.get('art') or game.get('capsule') or game.get('hero'))
        shared=self.owner._ensure_game_accent(game) if has_art else 'art-b8b8b8'
        shared=shared or 'art-b8b8b8'
        color='#'+shared.removeprefix('art-')
        if not game.get('blocked'):color=self.owner.settings.get('game_accents',{}).get(game.get('game')) or color
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):color='#b8b8b8'
        name='art-'+color[1:].lower();widget.add_css_class(name)
        if name in self.artwork_border_colors:return
        self.artwork_border_colors[name]=color
        rules=[]
        for key,value in self.artwork_border_colors.items():
            surface={'light':'#fafafa','dark':'#2a2a2a'}.get(self.owner.settings.get('gaming_mode_theme'),'#101010')
            ring=ui_colors.vibrant_readable(value,surface,3.0)
            rules.append(f'.couch-shell .couch-tile.{key}.focused .couch-cover {{ border-color: {value}; }} '
                         f'.couch-shell .couch-list-row.{key}:focus-within {{ outline-color: {ring}; }} '
                         f'.couch-shell .couch-tile.{key}.focused .couch-tile-title {{ color: {ring}; }} '
                         f'.couch-shell .couch-game-poster.{key} {{ border-color: {value}; }}')
        self.artwork_border_provider.load_from_data(' '.join(rules).encode())

    def apply_accent(self, game):
        # Consume Classic's resolver and saved override; never create another
        # artwork palette or preference store for the controller interface.
        color = '#76b900'
        if game:
            shared = self.owner._ensure_game_accent(game) or 'art-76b900'
            color = '#' + shared.removeprefix('art-') if game.get('blocked') else self.owner.settings.get('game_accents', {}).get(game['game']) or '#' + shared.removeprefix('art-')
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            color = '#76b900'
        if color == self.accent_color:
            return
        self.accent_color = color
        foreground = ui_colors.readable(ui_colors.mix('#000000', color, 0.82), color)
        ring = '#222' if self.owner.settings.get('gaming_mode_theme')=='light' else '#fafafa'
        tab_background = ui_colors.mix(color, '#1c1d20', 0.22)
        tab_foreground = ui_colors.readable(color, tab_background)
        self.accent_provider.load_from_data(f'''
          .couch-shell, .couch-dialog.couch-game-controls {{
            --accent-bg-color: {color}; --accent-fg-color: {foreground}; --accent-color: {ring};
          }}
          .couch-shell scale highlight, .couch-dialog.couch-game-controls scale highlight {{ background: {color}; }}
          .couch-shell scale slider:focus-visible, .couch-dialog.couch-game-controls scale slider:focus-visible {{ outline-color: {color}; }}
          .couch-shell .couch-selection check:checked {{ background: {color}; color: {foreground}; border-color: {color}; }}
          .couch-shell .couch-tile.focused .couch-cover {{ outline-color: {ring}; }}
          .couch-shell .couch-action.couch-primary,
          .couch-shell .couch-options:not(.nav-focused) row:selected {{ background: {color}; color: {foreground}; }}
          .couch-shell .couch-tab.active:not(.focused) {{ background: #37393f; color: #fafafa; }}
          .couch-shell .couch-view.active:not(.focused) {{ background: #37393f; color: #fafafa; }}
          .couch-shell .couch-view.focused {{ background: {color}; color: {foreground}; }}
          .couch-shell .couch-list-row.focused {{ background: {ui_colors.mix(color, '#101113', 0.13)}; outline-color: {ring}; }}
        '''.encode())

    def entry(self, title, action=None, value=None, adjust=None, enabled=True, game=None, hint=''):
        self.entries.append(dict(title=title, action=action, value=value, adjust=adjust, enabled=enabled, game=game, hint=hint))

    def navigate(self, action):
        self.wake_hints()
        self.add_css_class('controller-focus') if getattr(self.owner,'input_kind','keyboard')=='controller' else self.remove_css_class('controller-focus')
        if action=='select' and self.page=='library':self.start_selection();return
        if action == 'back':
            self.back()
            return
        if action == 'menu':
            self.open('menu')
            return
        if action == 'settings':
            self.open('settings')
            return
        if action == 'search':
            self.open('library')
            return
        if action in ('previous', 'next'):
            if self.tab_index == len(PAGES):
                self.tab_index = -1 if action == 'next' else 0
            self.tab_index = (self.tab_index + (1 if action == 'next' else -1)) % len(PAGES)
            self.open(PAGES[self.tab_index])
            return
        if self.page=='game':self.details_navigate(action);return
        if self.zone=='sidebar':
            if action in ('up','down'):
                self.sidebar_index=(self.sidebar_index+(1 if action=='down' else -1))%len(self.sidebar_buttons)
                self.sidebar_buttons[self.sidebar_index].grab_focus()
            elif action=='accept':self.sidebar_buttons[self.sidebar_index].emit('clicked')
            elif action=='right':self.zone='content';self.focus(self.current)
            return
        if self.body.get_visible_child_name()=='workspace' and action=='left' and self.sidebar_buttons and self.entries and not self.entries[self.current].get('adjust'):
            self.zone='sidebar';self.sidebar_index=0;self.sidebar_buttons[0].grab_focus();return
        if self.zone == 'nav':
            if action in ('left', 'right'):
                self.tab_index = (self.tab_index + (1 if action == 'right' else -1)) % (len(PAGES) + 1)
            elif action == 'accept':
                self.open('menu' if self.tab_index == len(PAGES) else PAGES[self.tab_index])
            elif action == ('up' if self.navigation_position=='bottom' else 'down'):
                self.zone = 'views' if self.page == 'library' and self.navigation_position!='bottom' else 'content'
                if self.zone=='views':
                    first=next((control for row in self.library_focus_rows for control in row if control.get_visible() and control.get_sensitive()),None)
                    if first is not None:self.view_index=self.view_buttons.index(first)
                    else:self.zone='content'
                if self.zone == 'content':
                    self.focus(self.current)
            self.update_tabs()
            return
        if self.zone == 'views':
            rows=[[control for control in row if control.get_visible() and control.get_sensitive()] for row in self.library_focus_rows]
            rows=[row for row in rows if row]
            if not rows:return
            control=self.view_buttons[self.view_index]
            row_index=next((i for i,row in enumerate(rows) if control in row),0)
            row=rows[row_index]
            position=row.index(control) if control in row else 0
            if action in ('left','right'):
                control=row[(position+(1 if action=='right' else -1))%len(row)]
            elif action=='accept':
                if control.get_sensitive():control.emit('clicked')
                return
            elif action=='down':
                if row_index+1<len(rows):control=rows[row_index+1][min(position,len(rows[row_index+1])-1)]
                else:self.zone='content';self.focus(self.current);return
            elif action=='up':
                if row_index>0:control=rows[row_index-1][min(position,len(rows[row_index-1])-1)]
                elif self.navigation_position!='bottom':self.zone='nav';self.update_tabs();return
            self.view_index=self.view_buttons.index(control)
            control.grab_focus();self.update_tabs()
            return
        if self.page == 'game' and self.controls:
            first_y=self.controls[0].get_parent().get_allocation().y
            columns=sum(control.get_parent().get_allocation().y==first_y for control in self.controls)
            columns=max(1,columns)
            if action=='up' and self.current<columns:
                if self.navigation_position!='bottom':self.zone='nav';self.update_tabs()
            elif action=='down' and self.current+columns>=len(self.controls):
                if self.navigation_position=='bottom':self.zone='nav';self.update_tabs()
            elif action in ('left','right','up','down'):
                if action=='left' and self.current%columns==0:return
                if action=='right' and (self.current%columns==columns-1 or self.current==len(self.controls)-1):return
                delta={'left':-1,'right':1,'up':-columns,'down':columns}[action]
                target=self.current+delta
                while 0<=target<len(self.entries) and not self.entries[target]['enabled']:
                    target+=1 if delta>0 else -1
                if 0<=target<len(self.entries):self.focus(target)
            elif action=='accept':self.activate(self.current)
            return
        if self.navigation_position=='bottom' and action=='down' and (self.page in ('dashboard','game') or self.current >= len(self.entries)-(self.columns if self.page=='library' else 1)):
            self.zone='nav'
            self.update_tabs()
            return
        if self.page == 'library':
            if action == 'up' and self.current < self.columns:
                self.zone = 'views'
                self.view_index=self.view_buttons.index(self.filter_button)
                self.filter_button.grab_focus()
                self.update_tabs()
            elif action in ('up', 'down', 'left', 'right'):
                delta = {'up': -self.columns, 'down': self.columns, 'left': -1, 'right': 1}[action]
                if action == 'left' and self.current % self.columns == 0:
                    return
                if action == 'right' and self.current % self.columns == self.columns - 1:
                    return
                self.focus(max(0, min(len(self.entries) - 1, self.current + delta)))
            elif action == 'accept':
                self.activate(self.current)
            return
        horizontal = self.page in ('dashboard', 'game')
        if self.navigation_position!='bottom' and action == 'up' and (horizontal or not any(entry['enabled'] for entry in self.entries[:self.current])):
            self.zone = 'nav'
            self.update_tabs()
            return
        if (horizontal and action in ('left', 'right')) or (not horizontal and action in ('up', 'down')):
            direction = 1 if action in ('right', 'down') else -1
            index = self.current
            for _ in self.entries:
                index = max(0, min(len(self.entries) - 1, index + direction))
                if self.entries[index]['enabled']:
                    self.focus(index)
                    break
        elif action == 'accept':
            self.activate(self.current)
        elif action in ('left', 'right') and self.entries:
            adjust = self.entries[self.current].get('adjust')
            if adjust:
                adjust(1 if action == 'right' else -1)
                self.render(self.current)

    def update_tabs(self):
        active = PAGES.index(self.page) if self.page in PAGES else PAGES.index(self.game_origin)
        for i, button in enumerate(self.tabs):
            button.add_css_class('active') if i == active else button.remove_css_class('active')
            button.add_css_class('focused') if self.zone == 'nav' and i == self.tab_index else button.remove_css_class('focused')
        self.menu.add_css_class('nav-focused') if self.zone == 'nav' else self.menu.remove_css_class('nav-focused')
        for i, button in enumerate(self.controls):
            button.add_css_class('focused') if self.zone == 'content' and i == self.current else button.remove_css_class('focused')
        for i, button in enumerate(self.view_buttons):
            button.remove_css_class('active')
            button.add_css_class('focused') if self.zone == 'views' and i == self.view_index else button.remove_css_class('focused')

    def selected(self, _, row):
        if row is not None:
            self.current = row.get_index()
            self.selection[self.page] = self.current

    def focus(self, index):
        if not self.entries:
            return
        self.current = max(0, min(index, len(self.entries) - 1))
        self.selection[self.page] = self.current
        entry = self.entries[self.current]
        if entry.get('game'):
            self.set_game(entry['game'])
        if self.controls:
            button = self.controls[self.current]
            button.grab_focus()
            if self.page in ('dashboard', 'library') and not self.restoring_library:
                GLib.idle_add(self.reveal_selection)
            self.action_hint.set_text(entry.get('hint') or self.hint.get_text())
            if self.page == 'dashboard':
                self.count.set_text(f'{self.current + 1} of {len(self.entries)} · {self.owner.settings.get("dashboard_row_count",5)} across · browse left / right')
        else:
            row = self.menu.get_row_at_index(self.current)
            self.menu.select_row(row)
            if row and row.get_parent():
                row.grab_focus()
        self.update_tabs()

    def reveal_selection(self):
        if self.page not in ('dashboard', 'library') or not self.controls:
            return False
        button = self.controls[min(self.current, len(self.controls) - 1)]
        allocation = getattr(button,'library_row',button).get_allocation()
        is_grid = self.page == 'library'
        adjustment = self.grid_scroll.get_vadjustment() if is_grid else self.shelf_scroll.get_hadjustment()
        start = allocation.y if is_grid else allocation.x
        end = start + (allocation.height if is_grid else allocation.width)
        position = adjustment.get_value()
        target = max(0, start - 18) if start < position+18 else end - adjustment.get_page_size() + 18 if end > position + adjustment.get_page_size()-18 else position
        target = max(adjustment.get_lower(), min(target, adjustment.get_upper() - adjustment.get_page_size()))
        if self.scroll_tick:
            self.remove_tick_callback(self.scroll_tick)
            self.scroll_tick = 0
        settings = Gtk.Settings.get_default()
        if not settings or not settings.get_property('gtk-enable-animations') or abs(target - position) < 1:
            adjustment.set_value(target)
            return False
        began = time.monotonic()
        def animate(_widget, _clock):
            t = min(1.0, (time.monotonic() - began) / .22)
            adjustment.set_value(position + (target - position) * (1 - (1 - t) ** 3))
            if t >= 1:
                self.scroll_tick = 0
                return False
            return True
        self.scroll_tick = self.add_tick_callback(animate)
        return False

    def open_game(self, game):
        if self.page in ('dashboard', 'library'):
            self.game_origin = self.page
            self.library_origin={'game':game['game'],'scroll':self.grid_scroll.get_vadjustment().get_value(),'view':self.library_view,'filter':getattr(self.owner,'filter','available')}
        self.set_game(game)
        self.open('game')

    def set_library_filter(self,key):
        if key not in ('available','all','installed'):return
        self.owner.filter=key
        control=getattr(self.owner,'filter_buttons',{}).get(key)
        if control:control.set_active(True)
        else:self.owner.filter_games()
        self.open('library')

    def set_library_view(self, view):
        if view not in VIEWS:
            return
        self.library_view = view
        self.owner.settings['gaming_mode_view']=view
        self.view_index = 0
        if not self.owner.options.demo:
            library_media.save_settings(self.owner.service.config,self.owner.settings)
        self.render(self.current)

    def grid_dimensions(self):
        available = max(380, self.layout_width - (76 if self.compact else 120))
        if self.library_view == 'list':
            return 1, available, 82
        factor=getattr(self.owner,'presentation_scale',1.0)
        system_scale=self.owner.get_scale_factor()
        physical_width=self.layout_width*factor*system_scale
        short=self.layout_height*factor*system_scale<=800 and physical_width<=2000
        if self.library_view=='posters':
            columns=max(2,int(available/(126/factor))) if short else 5 if physical_width<=1050 else 7
            ratio=2/3
        else:
            columns=2 if physical_width<=1050 else 4 if short or physical_width>1500 else 3
            ratio=920/430
        width=max(80,int((available-18*(columns-1))/columns)-16)
        height=round(width/ratio)
        return columns, width, height

    def activate(self, index):
        if index >= len(self.entries) or self.owner.busy:
            return
        entry = self.entries[index]
        if entry['enabled'] and entry['action']:
            entry['action']()

    def open(self, page, _guard=True):
        if page=='menu':self.show_menu();return
        if page=='library_filters':self.show_filters();return
        if _guard and page!=self.page and self.has_dirty_presets():
            self.leave(lambda:self.open(page,_guard=False));return
        returning=self.page=='game' and page=='library'
        if returning:self.restoring_library=True
        if self.page=='game' and page!='game' and self.details_panel:self.details_panel.finish_close()
        if page == 'dashboard':page = 'library'
        returning_to_presets = page == 'presets' and self.page == 'library' and self.dlss_selection is not None and self.selection_kind == 'presets'
        if page in ('menu', 'settings') and self.page not in ('menu', 'settings'):
            self.utility_origin = self.page
        if page not in ('library','library_filters'):
            self.dlss_selection = None
        if page in ('game', 'features', 'tools', 'game_presets') and self.game is None:
            page = 'library'
        if page == 'library':
            self.library_view = self.owner.settings.get('gaming_mode_view', 'posters')
            self.view_index = 0
        if page == 'presets' and self.page != 'presets':
            self.preset_origin = self.page if self.page in ('dashboard', 'library', 'game') else self.game_origin
        if page in ('presets', 'game_presets') and not returning_to_presets:
            source = self.game if page == 'game_presets' else self.owner.settings
            self.pending = {key: source.get(key) if source.get(key) is not None else self.owner.settings[key] for key in ('nr_strength', 'sharpening_strength', 'mfg_multiplier')}
            self.pending_origin=dict(self.pending)
        self.page = page
        self.apply_accent(self.game if page in ('game','features','tools','game_presets') else None)
        self.zone = 'content'
        self.tab_index = PAGES.index(page) if page in PAGES else PAGES.index(self.game_origin)
        self.render()
        if returning:GLib.idle_add(self.restore_library)

    def back(self):
        if self.page == 'library' and self.dlss_selection is not None:
            if self.selection_kind=='presets':self.open('presets',_guard=False)
            else:self.dlss_selection=None;self.render()
            return
        if self.zone in ('nav', 'views'):
            self.zone = 'content'
            self.update_tabs()
        elif self.page == 'dashboard':
            return
        elif self.page == 'library':
            return
        elif self.page == 'presets':
            self.open(self.preset_origin)
        elif self.page in ('features_all','library_filters'):
            self.open('library')
        elif self.page in ('features', 'tools', 'game_presets'):
            self.open('game')
        elif self.page == 'game':
            self.open(self.game_origin)
        elif self.page in ('menu', 'settings'):
            self.open(self.utility_origin)
        else:
            self.open('library')

    def sync_library_modes(self):
        active=self.owner.profile_group.get_active_name()
        ready=not self.owner.busy or self.owner.task_kind=='art'
        for mode,control in self.feature_controls.items():
            control.set_active(mode==active)
            control.set_sensitive(ready and (mode!='nr-only' or self.owner.nr_only.get_enabled()))

    def install(self, mode):
        self.owner.profile_group.set_active_name(mode)
        targets = self.install_targets() if self.page == 'features_all' else [self.game]
        self.owner.launch_action('install', targets=targets, visual_settings=dict(self.owner.settings), )

    def select_dlss_games(self):
        self.selection_kind = 'dlss'
        self.dlss_selection = set()
        self.open('library')

    def preset_targets(self):
        return [game for game in self.owner.games if game.get('installed') and not game.get('blocked') and game.get('test_record', {}).get('status') != 'Bench']

    def select_preset_games(self):
        self.selection_kind = 'presets'
        self.dlss_selection = set()
        self.open('library',_guard=False)

    def apply_presets(self, targets):
        eligible = {game['game'] for game in self.preset_targets()}
        targets = [game for game in targets if game['game'] in eligible]
        if targets:
            self.owner.launch_action('reset', targets=targets, visual_settings=dict(self.pending))

    def toggle_dlss_game(self, game):
        if game.get('blocked') or (self.selection_kind == 'presets' and not game.get('installed')):
            return
        key = game['game']
        self.dlss_selection.symmetric_difference_update({key})
        self.render(self.current)

    def install_targets(self):
        return [game for game in self.operation_targets() if game.get('test_record', {}).get('status') != 'Bench']

    def operation_targets(self,installed=False):
        return [game for game in self.owner.games if not game.get('blocked') and (not installed or game.get('installed'))]

    def update_branding(self,offset=None):
        if offset is None:offset=self.grid_scroll.get_vadjustment().get_value()
        previous=getattr(self,'header_collapsed',False)
        collapsed=self.page=='library' and (offset>40 or previous and offset>0)
        old_height=self.top.get_height();self.header_collapsed=collapsed
        self.brand_button.add_css_class('collapsed') if collapsed else self.brand_button.remove_css_class('collapsed')
        self.brand_icon.set_pixel_size(40 if collapsed else 48 if self.compact else 72)
        if collapsed!=previous and offset>0 and not self.restoring_library:
            remaining={'frames':3}
            def preserve(_widget,_clock):
                remaining['frames']-=1
                new_height=self.top.get_height()
                if new_height==old_height and remaining['frames']>0:return True
                adjustment=self.grid_scroll.get_vadjustment()
                adjustment.set_value(max(0,offset+new_height-old_height))
                return False
            self.add_tick_callback(preserve)

    def library_primary_action(self):
        if not self.library_action.get_sensitive():
            return
        if self.dlss_selection is not None:
            targets = [g for g in self.owner.games if g['game'] in self.dlss_selection]
            if self.selection_kind == 'presets':
                self.apply_presets(targets)
            elif self.selection_kind=='install':
                self.owner.launch_action('install',targets=targets,visual_settings=dict(self.owner.settings))
            else:
                self.owner.update_dlss_games(targets)
        else:
            self.owner.launch_action('install',targets=self.install_targets(),visual_settings=dict(self.owner.settings))

    def selection_marker(self, game):
        marker = Gtk.CheckButton(active=game.get('game') in self.dlss_selection, can_focus=False, can_target=False)
        marker.add_css_class('couch-selection')
        marker.set_tooltip_text('Selected' if marker.get_active() else 'Not selected')
        return marker

    def adjust(self, key, direction):
        choices = [0, 2, 3, 4, 5, 6, 'auto'] if key == 'mfg_multiplier' else [round(i / 10, 1) for i in range(21 if key == 'nr_strength' else 11)]
        current = self.pending[key]
        index = choices.index(current) if current in choices else 0
        self.pending[key] = choices[max(0, min(len(choices) - 1, index + direction))]

    def setting(self, key, direction, choices):
        current = self.owner.settings.get(key)
        index = choices.index(current) if current in choices else 0
        self.owner.settings[key] = choices[(index + direction) % len(choices)]
        if not self.owner.options.demo:
            library_media.save_settings(self.owner.service.config, self.owner.settings)
        self.owner.apply_display_preferences()
        self.update_prompts()

    def build_entries(self):
        self.entries = []
        self.hint.set_text('')
        if self.page in ('dashboard', 'library'):
            for game in self.owner.games:
                active_filter=getattr(self.owner,'filter','available')
                if self.page=='library' and ((active_filter=='available' and game.get('blocked')) or (active_filter=='installed' and not game.get('installed'))):continue
                self.entry(game['name'], lambda g=game: self.toggle_dlss_game(g) if self.dlss_selection is not None else self.open_game(g), game=game, enabled=self.dlss_selection is None or (not game.get('blocked') and (self.selection_kind != 'presets' or bool(game.get('installed')))))
            if not self.entries:
                self.entry('Refresh library', self.owner.scan)
                self.detail.set_text('Add a game folder in Classic to get started.')
        elif self.page == 'game':
            game = self.game
            self.entry('Play', lambda:self.owner.play_game(game), enabled=not self.owner.options.demo, hint='Launch using this game’s configured launcher.')
            self.entry('Game Details' if game.get('blocked') else 'Configure', lambda:self.owner.details(game) if game.get('blocked') else self.open('features'), hint='View compatibility details.' if game.get('blocked') else 'Choose Neural Rendering and frame generation for this game.')
            self.entry('Presets', lambda: self.open('game_presets'), enabled=game.get('installed', False), hint='Adjust graphics features for this game. Your other games stay as they are.')
            self.entry('Tools', lambda: self.open('tools'), hint='Diagnose Neural Rendering, update DLSS, or restore original files.')
        elif self.page in ('features', 'features_all'):
            self.entry('Neural Rendering + MFG', lambda: self.install('nr-mfg'))
            self.entry('Frame generation only', lambda: self.install('mfg-only'))
            self.entry('Neural Rendering only', lambda: self.install('nr-only'), enabled=self.owner.settings.get('runtime_provider') in ('dlss-unlocked', 'custom'))
            self.hint.set_text('Review every file change before installing. Your current presets are used.')
        elif self.page in ('presets', 'game_presets'):
            per_game = self.page == 'game_presets'
            mode = (self.game.get('feature_mode') or {'MFG Only': 'mfg-only', 'NR Only': 'nr-only'}.get(self.game.get('profile'), 'nr-mfg')) if per_game else 'nr-mfg'
            for key, title in [('nr_strength', 'Neural Rendering'), ('mfg_multiplier', 'Frame generation'), ('sharpening_strength', 'Sharpening')]:
                raw = self.pending[key]
                value = 'In game' if raw == 'auto' else 'Off' if raw == 0 else str(raw) + ('×' if key == 'mfg_multiplier' else '')
                self.entry(title, value=value, adjust=lambda delta, key=key: self.adjust(key, delta), enabled=not (key == 'nr_strength' and mode == 'mfg-only') and not (key == 'mfg_multiplier' and mode == 'nr-only'))
            if per_game:
                self.entry('Apply to this game', lambda: self.apply_presets([self.game]), enabled=bool(self.game.get('installed')) and not self.game.get('blocked'))
                self.hint.set_text('Only this game will change. Review the changes before applying.')
            else:
                eligible = self.preset_targets()
                self.entry(f'Apply to all configured games ({len(eligible)})', lambda: self.apply_presets(self.preset_targets()), enabled=bool(eligible))
                self.entry('Select games to apply', self.select_preset_games, enabled=bool(eligible))
                self.hint.set_text('Apply to all configured games, or choose your games.')
        elif self.page=='library_filters':
            selected=getattr(self.owner,'filter','available')
            for key,title in [('available','Available'),('installed','Installed'),('all','All')]:
                self.entry(title,lambda key=key:self.set_library_filter(key),value='Selected' if key==selected else '')
            for key,title in [('posters','Posters'),('capsules','Wide'),('list','List')]:
                self.entry(title,lambda key=key:(self.set_library_view(key),self.open('library')),value='Selected' if self.library_view==key else '')
        elif self.page == 'dlss':
            self.entry('Update all', lambda: self.owner.update_dlss_games(self.operation_targets()), enabled=bool(self.operation_targets()))
            self.entry('Select games to update', self.select_dlss_games, enabled=bool(self.operation_targets()))
            self.hint.set_text('Keep native DLSS files up to date across your library. Previous files are backed up.' if self.owner.games else 'Add games to your Library to update their DLSS files.')
        elif self.page == 'tools':
            self.entry('Change artwork',lambda:self.owner.show_game_artwork(self.game),enabled=not self.owner.options.demo)
            self.entry('Sync artwork to Steam',lambda:self.owner.sync_steam_artwork(game=self.game),enabled=not self.owner.options.demo)
            self.entry('Diagnose Neural Rendering', lambda: self.owner.show_diagnostics(self.game))
            self.entry('Update DLSS files', lambda: self.owner.manage_dlss_files(self.game), enabled=not self.owner.options.demo)
            self.entry('Restore DLSS files', lambda: self.owner.manage_dlss_files(self.game, restore=True), enabled=not self.owner.options.demo)
            self.entry('Restore original game files', lambda: self.owner.launch_action('uninstall', targets=[self.game]), enabled=self.game.get('installed', False))
            self.hint.set_text('ReShade and add-on imports are available in Classic with keyboard and mouse.')
            buckets={'Graphics':['Diagnose Neural Rendering','Update DLSS files'],'Artwork':['Change artwork','Sync artwork to Steam'],'Recovery':['Restore DLSS files','Restore original game files']}
            self.entries=[entry for entry in self.entries if entry['title'] in buckets[self.tools_section]]
        elif self.page == 'menu':
            self.entry('Library', lambda: self.open('library'))
            self.entry('Packages', lambda: self.open('packages'))
            self.entry('Refresh library', self.owner.scan)
            self.entry('Desktop UI', lambda: self.owner.set_big_picture_ui(False))
            self.entry('Exit App', self.request_exit,enabled=not self.owner.busy)
        elif self.page == 'packages':
            import package_catalog
            for package in package_catalog.catalog(self.owner.hardware_info):
                self.entry(package['name'], lambda key=package['id']: self.select_package(key), value='Selected' if self.owner.settings['runtime_provider'] == package['id'] else '', enabled=package['available'])
            self.hint.set_text('Choose a package for the next install. Restore an existing provider before switching.')
        elif self.page == 'settings':
            self.entry('Remove from Steam' if self.owner.steam_shortcut_added() else 'Add rtxForge to Steam',self.owner.toggle_rtxforge_in_steam,enabled=not self.owner.options.demo)
            self.entry('Sync artwork to Steam',self.owner.sync_steam_artwork,enabled=not self.owner.options.demo)
            self.entry('Steam artwork profile',self.owner.choose_steam_artwork_profile,enabled=not self.owner.options.demo)
            self.entry('Connect SteamGridDB',self.owner.show_steamgrid_connection,enabled=not self.owner.options.demo)
            self.entry('Interface',lambda:self.owner.set_big_picture_ui(False),value='Big Picture UI',adjust=lambda d:self.owner.set_big_picture_ui(False))
            for key,title,choices in [('theme','Theme',['light','dark','night']),('corner_style','Corners',['system','rounded','square']),('button_glyphs','Button glyphs',[True,False])]:
                self.entry(title,value=str(self.owner.settings.get('gaming_mode_theme','night') if key=='theme' else self.owner.settings.get(key,choices[0])).title(),adjust=lambda d,key=key,choices=choices:self.appearance_setting(key,d,choices))
            glyphs = ['auto', 'xbox', 'playstation', 'nintendo', 'generic']
            self.entry('Button labels', value=self.owner.settings.get('controller_glyphs', 'auto').title(), adjust=lambda d: self.setting('controller_glyphs', d, glyphs))
            self.entry('Library layout', value={'posters': 'Posters', 'capsules': 'Wide', 'list': 'List'}[self.library_view], adjust=lambda d: self.set_library_view(VIEWS[(VIEWS.index(self.library_view) + d) % len(VIEWS)]))
            for key,title,choices,captions in [
                ('ui_scale','UI scale',['auto',100,125,150,175,200],['Automatic','100%','125%','150%','175%','200%']),
                ('navigation_position','Navigation',['top','bottom'],['Top','Bottom']),
                ('controller_hints','Controller hints',['always','auto'],['Always visible','Hide when idle'])]:
                value=self.owner.settings.get(key,library_media.DEFAULTS[key])
                self.entry(title,value=captions[choices.index(value)],adjust=lambda d,key=key,choices=choices:self.setting(key,d,choices))
            self.hint.set_text('Choose Desktop or Big Picture UI in Settings. Input devices keep your chosen interface.')
            buckets={'Gaming Mode':['Add rtxForge to Steam','Remove from Steam','Interface'],
                     'Appearance':['Theme','Corners','Button glyphs'],
                     'Library':['Sync artwork to Steam','Steam artwork profile','Connect SteamGridDB','Library layout'],
                     'Controller':['Button labels','Controller hints'],
                     'System':['UI scale','Navigation']}
            self.entries=[entry for entry in self.entries if entry['title'] in buckets[self.settings_section]]


    def appearance_setting(self,key,direction,choices):
        if key=='theme':
            current=self.owner.settings.get('gaming_mode_theme','night')
            index=choices.index(current) if current in choices else 0
            self.owner.settings['gaming_mode_theme']=choices[(index+direction)%len(choices)]
            if not self.owner.options.demo:library_media.save_settings(self.owner.service.config,self.owner.settings)
            self.owner.apply_input_theme()
        else:
            self.setting(key,direction,choices)
            from rtxforge_gtk import apply_corner_style,set_button_glyphs
            if key=='corner_style':apply_corner_style(self.owner.settings[key])
            elif key=='button_glyphs':set_button_glyphs(self.owner.settings[key])
        self.apply_theme()

    def set_section(self,title):
        if self.page=='settings':self.settings_section=title
        else:self.tools_section=title
        self.zone='content';self.render(0)

    def render_workspace(self):
        clear(self.workspace_content);clear(self.workspace_footer);clear(self.section_nav)
        self.controls=[];self.sidebar_buttons=[]
        side=self.page in ('settings','tools')
        self.workspace_footer.set_orientation(Gtk.Orientation.VERTICAL if side and self.layout_width<1050 else Gtk.Orientation.HORIZONTAL)
        self.section_nav.set_visible(side)
        sections=['Gaming Mode','Appearance','Library','Controller','System'] if self.page=='settings' else ['Graphics','Artwork','Recovery']
        selected=self.settings_section if self.page=='settings' else self.tools_section
        if side:
            self.section_nav.append(label('Settings' if self.page=='settings' else 'Game tools','couch-section'))
            for title in sections:
                control=Gtk.Button(label=title,halign=Gtk.Align.FILL)
                control.add_css_class('couch-sidebar-item')
                if title==selected:control.add_css_class('active')
                control.connect('clicked',lambda _,title=title:self.set_section(title))
                self.section_nav.append(control);self.sidebar_buttons.append(control)
        titles={'presets':'Library presets','game_presets':'Game presets','dlss':'DLSS Files','library_filters':'Filter & View','features':'Install features','features_all':'Install features','menu':'rtxForge','packages':'Packages'}
        self.workspace_heading.set_text(selected if side else titles.get(self.page,self.heading.get_text()))
        self.workspace_detail.set_text(self.game['name'] if self.page in ('tools','game_presets','features') and self.game else self.panel_detail.get_text())
        self.workspace_hint.set_text(self.hint.get_text())
        descriptions={'Gaming Mode':'Use rtxForge from Steam, or switch between Desktop and Big Picture UI.',
                      'Appearance':'Choose your app theme, corners and button icons.',
                      'Library':'Manage the library layout and artwork sources.',
                      'Controller':'Customize controller labels and navigation hints.',
                      'System':'Adjust display scaling and navigation placement.',
                      'Graphics':'Check Neural Rendering or review a DLSS file update for this game.',
                      'Artwork':'Choose separate poster, wide capsule and hero artwork for this game.',
                      'Recovery':'Restore backed-up files. Every change opens a review before you confirm.'}
        if side:self.workspace_detail.set_text(descriptions[selected])

        options=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.workspace_content.append(options)
        preset_grid=Gtk.Grid(column_spacing=24,row_spacing=24,column_homogeneous=True)
        self.preset_grid=preset_grid
        self.preset_controls=[]
        if self.page in ('presets','game_presets'):options.append(preset_grid)
        if self.page=='dlss':
            eligible=self.operation_targets()
            self.workspace_detail.set_text(f'{len(eligible)} supported games · Backups kept before updating')
            options.append(label('Games to check','couch-section'))
            games=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,homogeneous=True,min_children_per_line=1,max_children_per_line=3,column_spacing=20,row_spacing=16)
            for game in eligible:
                line=Gtk.Box(spacing=12)
                art=self.artwork_widget(self.owner.wide_art_path(game),'',112,52,'couch-list-art')
                self.decorate_game_accent(art,game)
                line.append(art);name=label(game['name'],wrap=True);name.set_max_width_chars(24);line.append(name);games.insert(line,-1)
            options.append(games)
            if not eligible:options.append(label('Add a supported game to your Library to update its DLSS files.','couch-caption',wrap=True))
        filter_groups=[]
        if self.page=='library_filters':
            for title in ('Show games','Artwork layout'):
                options.append(label(title,'couch-section'))
                group=Gtk.Box(spacing=8,homogeneous=True);options.append(group);filter_groups.append(group)
        if self.page=='tools' and self.game:
            identity=Gtk.Box(spacing=24,valign=Gtk.Align.START)
            poster=self.artwork_widget(self.owner.poster_art_path(self.game),'',120,180,'couch-game-poster')
            self.decorate_game_accent(poster,self.game);identity.append(poster)
            text=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,valign=Gtk.Align.CENTER)
            text.append(label(self.game['name'],'couch-section'))
            description=label(descriptions[selected],'couch-caption',wrap=True);description.set_max_width_chars(55);text.append(description)
            identity.append(text);options.append(identity)
        for i,entry in enumerate(self.entries):
            action=entry['action'] is not None and entry['adjust'] is None
            primary=self.page in ('presets','game_presets','dlss') and action
            primary=primary or self.page in ('settings','menu','tools') and (entry['title'].startswith(('Add rtxForge','Remove from Steam','Exit','Quit','Restore','Update','Sync','Change artwork','Connect','Diagnose')))
            if self.page=='library_filters':
                control=Gtk.ToggleButton(label=entry['title'],active=entry['value']=='Selected')
                control.add_css_class('couch-workspace-action')
                control.connect('clicked',lambda _,i=i:self.activate(i))
                filter_groups[0 if i<3 else 1].append(control)
            elif self.page in ('presets','game_presets') and i<3:
                control=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,focusable=True)
                control.add_css_class('couch-adjustment')
                control.append(label(entry['title'],'couch-section'))
                value=label(str(entry['value']),'couch-adjustment-value');control.append(value)
                key=['nr_strength','mfg_multiplier','sharpening_strength'][i]
                if key=='mfg_multiplier':
                    choices=[0,2,3,4,5,6,'auto'];captions=['Off','2×','3×','4×','5×','6×','In game']
                    selector=Gtk.DropDown(model=Gtk.StringList.new(captions),selected=choices.index(self.pending[key]) if self.pending[key] in choices else 0)
                    selector.connect('notify::selected',lambda widget,*_,key=key,choices=choices,value=value:(self.pending.__setitem__(key,choices[widget.get_selected()]),value.set_text(captions[widget.get_selected()])))
                    control.append(selector)
                else:
                    scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,2 if key=='nr_strength' else 1,.1)
                    scale.set_draw_value(False);scale.set_value(float(self.pending[key]))
                    scale.connect('value-changed',lambda widget,key=key,value=value:(self.pending.__setitem__(key,round(widget.get_value(),1)),value.set_text(f'{widget.get_value():.1f}')))
                    control.append(scale)
                control.append(label('Adjust before applying.','couch-caption'))
                preset_columns=3 if self.layout_width>=1100 else 1
                preset_grid.attach(control,i%preset_columns,i//preset_columns,1,1)
                self.preset_controls.append(control)
            elif entry['adjust']:
                control=Gtk.Box(spacing=16,focusable=True)
                control.add_css_class('couch-setting-control')
                name=label(entry['title']);name.set_hexpand(True);control.append(name)
                decrease=Gtk.Button(icon_name='pan-start-symbolic',tooltip_text='Previous '+entry['title'])
                increase=Gtk.Button(icon_name='pan-end-symbolic',tooltip_text='Next '+entry['title'])
                for button,direction in [(decrease,-1),(increase,1)]:
                    button.connect('clicked',lambda _,direction=direction,i=i:(self.entries[i]['adjust'](direction),self.render(i)))
                control.append(decrease);control.append(label(str(entry['value']),'couch-value'));control.append(increase)
                options.append(control)
            else:
                title=entry['title']
                if self.page in ('presets','game_presets') and primary:
                    title=re.sub(r'Apply to all configured games','Apply to all',title)
                    if title=='Select games to apply':title='Choose games'
                control=self.owner.make_action_button(title,lambda _,i=i:self.activate(i))
                control.add_css_class('couch-workspace-action')
                control.text_label.set_wrap(True);control.text_label.set_max_width_chars(28)
                if primary:
                    self.workspace_footer.append(control)
                    if entry['title'].startswith(('Apply','Update all','Add rtxForge')):control.add_css_class('suggested-action')
                    if entry['title'].startswith(('Restore','Remove','Exit','Quit')):control.add_css_class('destructive-action')
                else:options.append(control)
            control.set_sensitive(entry['enabled']);self.controls.append(control)
            focus=Gtk.EventControllerFocus()
            focus.connect('enter',lambda _,i=i:(setattr(self,'current',i),setattr(self,'zone','content'),self.update_tabs()))
            control.add_controller(focus)

    def artwork_widget(self, path, title, width, height, style='couch-cover'):
        cover = Gtk.Overlay()
        cover.add_css_class(style)
        cover.set_overflow(Gtk.Overflow.HIDDEN)
        cover.set_size_request(width, height)
        picture = self.owner.make_art_picture(width,height)
        cover.picture = picture
        cover.placeholder = None
        if path:
            try:
                picture.set_filename(path)
            except (GLib.Error, OSError):
                path = None
        if not path or path==self.owner.wide_art_path({}):
            placeholder = Gtk.Image.new_from_icon_name('applications-games-symbolic')
            placeholder.set_pixel_size(40 if style=='couch-cover' else 28)
            placeholder.add_css_class('library-ghost-icon')
            placeholder.set_halign(Gtk.Align.CENTER)
            placeholder.set_valign(Gtk.Align.CENTER)
            cover.add_overlay(placeholder)
            cover.placeholder = placeholder
        cover.set_child(picture)
        return cover

    def game_tile(self, entry, width, height, poster=False):
        game = entry.get('game') or {}
        button = Gtk.Button()
        button.add_css_class('couch-tile')
        self.decorate_game_accent(button,game)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        # Use the same resolved custom/SteamGridDB/Steam assets as Classic.
        path = self.owner.poster_art_path(game) if poster else self.owner.wide_art_path(game)
        button.artwork = self.artwork_widget(path, entry['title'], width, height)
        if self.dlss_selection is not None:
            marker = self.selection_marker(game)
            marker.set_halign(Gtk.Align.END)
            marker.set_valign(Gtk.Align.START)
            marker.set_margin_top(8)
            marker.set_margin_end(8)
            button.artwork.add_overlay(marker)
        column.append(button.artwork)
        name = label(entry['title'], 'couch-tile-title', wrap=True)
        name.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        name.set_lines(2)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_width_chars(1)
        name.set_size_request(-1,round(2.5*getattr(self,'couch_unit',22)))
        button.title_label=name
        button.update_property([Gtk.AccessibleProperty.LABEL],[entry['title']])
        column.append(name)
        button.set_child(column)
        return button

    def game_list_row(self, entry):
        game=entry.get('game') or {}
        row=Gtk.Box(spacing=24,hexpand=True)
        row.add_css_class('couch-list-row');self.decorate_game_accent(row,game)
        if self.dlss_selection is not None:row.append(self.selection_marker(game))
        path=self.owner.wide_art_path(game)
        row.artwork=self.artwork_widget(path,'',144,68,'couch-list-art')
        row.append(row.artwork)
        title=label(entry['title'],'couch-list-title');title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END);row.append(title)
        row.append(label('Unavailable' if game.get('blocked') else 'Configured' if game.get('installed') else 'Not installed','couch-list-status'))
        if not self.compact and game.get('installed'):
            badge=Gtk.Box(spacing=8,valign=Gtk.Align.CENTER)
            badge.add_css_class('couch-feature-badge')
            badge.append(Gtk.Image.new_from_icon_name('emblem-system-symbolic'))
            badge.append(label(game.get('profile','Features installed'),'couch-list-status'))
            row.append(badge)
        action=self.owner.make_action_button('Select' if self.dlss_selection is not None else 'Details',lambda *_:None)
        action.add_css_class('couch-workspace-action');action.set_sensitive(entry['enabled'])
        action.library_row=row;row.focus_button=action;row.append(action)
        click=Gtk.GestureClick()
        click.connect('released',lambda *_:action.grab_focus() if row.get_mapped() else None)
        row.add_controller(click)
        return row

    def artwork_updated(self, game):
        """Apply the main library's async artwork event without rebuilding focus."""
        if self.game and self.game['game'] == game['game']:
            self.set_game(game)
        if self.page not in ('dashboard', 'library'):
            return
        for index, entry in enumerate(self.entries):
            if (entry.get('game') or {}).get('game') != game['game']:
                continue
            path = self.owner.poster_art_path(game) if (self.page == 'library' and self.library_view == 'posters') or (self.page == 'dashboard' and self.owner.settings.get('dashboard_view')=='posters') else self.owner.wide_art_path(game)
            if not path:
                continue
            control=getattr(self.controls[index],'library_row',self.controls[index])
            self.decorate_game_accent(control,game)
            cover = control.artwork
            try:
                cover.picture.set_filename(path)
                if self.page!='library':self.owner.decorate_support_artwork(cover,cover.picture,game,path)
                if cover.placeholder:
                    cover.placeholder.set_visible(False)
            except (GLib.Error, OSError):
                pass

    def render_library_state(self):
        loading=getattr(self.owner,'library_loading',False)
        error=getattr(self.owner,'library_error',None)
        empty=not any(e.get('game') for e in self.entries)
        show=loading or bool(error) or empty
        self.library_state.set_visible(show);self.grid_overlay.set_visible(not show)
        if not show:return False
        clear(self.library_state);self.entries=[];self.controls=[]
        title='Scanning your library…' if loading else 'Library could not be refreshed' if error else 'No games match this filter' if self.owner.games else 'Your library is empty'
        self.library_state.append(label(title,'couch-panel-heading'))
        caption=error or ('Games appear here after discovery.' if loading else 'Choose another filter or add a game folder.')
        self.library_state.append(label(caption,'couch-caption',wrap=True))
        if loading:
            spinner=Gtk.Spinner(spinning=True);self.library_state.append(spinner)
            self.entries=[dict(title=title,action=None,value=None,adjust=None,enabled=True,game=None,hint='Scanning your library')]
            self.library_state.set_focusable(True);self.controls=[self.library_state]
        else:
            choices=[('Retry',self.owner.scan)]
            if self.owner.games:choices.insert(0,('Reset Filter',lambda:self.set_library_filter('available')))
            else:choices.append(('Add Game Folder',self.owner.choose_folder))
            for title,action in choices:
                self.entry(title,action,enabled=not self.owner.options.demo)
                control=self.owner.make_action_button(title,lambda _,action=action:action())
                control.add_css_class('couch-workspace-action');control.set_sensitive(not self.owner.options.demo)
                self.library_state.append(control);self.controls.append(control)
        return True

    def render(self, index=None):
        self.settings_button.set_visible(False)
        self.add_css_class('details-open') if self.page=='game' else self.remove_css_class('details-open')
        self.main.set_spacing(0 if self.page=='game' else 18 if self.compact else 22)
        if self.page=='game':
            if self.details_game!=self.game['game'] or self.details_panel is None or self.details_panel.closed:
                self.owner.details(self.game,couch_embed=self);self.details_game=self.game['game']
            self.body.set_visible_child_name('details')
            self.update_tabs();self.update_prompts();return
        self.build_entries()
        is_feature = self.page in ('dashboard', 'game')
        self.body.set_visible_child_name('feature' if is_feature else 'library' if self.page == 'library' else 'workspace')
        self.remove_css_class('panel-open') if is_feature else self.add_css_class('panel-open')
        self.add_css_class('library-open') if self.page == 'library' else self.remove_css_class('library-open')
        self.library.set_visible(self.page == 'dashboard')
        self.game_actions.set_visible(self.page=='game')
        self.settings_button.set_visible(False)
        if self.game and self.page in ('game','features','tools','game_presets'):self.set_background(self.game.get('hero') or self.game.get('capsule'),animate=False)
        elif self.art_path is None:self.cycle_ambient()
        self.poster_slot.set_visible(self.page=='game')
        self.game_metadata.set_visible(self.page == 'game')
        self.game_summary.set_visible(self.page == 'game' and bool(self.game_summary.get_text()))
        self.count.set_text('Refreshing…' if self.owner.busy else f"{len(self.owner.games)} games · {self.owner.settings.get('dashboard_row_count',5)} across")
        installed = sum(bool(game.get('installed')) for game in self.owner.games)
        selecting = self.dlss_selection is not None
        if selecting:
            self.dlss_selection.intersection_update(g['game'] for g in self.owner.games if not g.get('blocked') and (self.selection_kind != 'presets' or g.get('installed')))
        self.library_heading.set_text('Select games' if selecting else 'Library')
        self.library_count.set_text(f'{len(self.dlss_selection)} selected  ·  ' + ('Presets' if self.selection_kind == 'presets' else 'DLSS Files') if selecting else f"{sum(1 for entry in self.entries if entry.get('game'))} shown of {len(self.owner.games)} games · {installed} configured")
        self.library_action.text_label.set_text(f"{'Apply presets' if self.selection_kind == 'presets' else 'Install Selected' if self.selection_kind=='install' else 'Update selected'} ({len(self.dlss_selection)})" if selecting else 'Install to all')
        self.select_button.text_label.set_text('Selection' if selecting else 'Select Games')
        for name,control in self.layout_controls.items():control.set_active(name==self.library_view)
        import package_catalog
        packages=package_catalog.catalog(self.owner.hardware_info)
        package=next((p['name'] for p in packages if p['id']==self.owner.settings.get('runtime_provider')),self.owner.settings.get('runtime_provider',''))
        self.package_label.set_text(package)
        self.filter_summary.set_text('Show: '+getattr(self.owner,'filter','available').title())
        self.sync_library_modes()
        self.library_action.set_sensitive(bool(self.dlss_selection) if selecting else bool(self.install_targets()))
        self.library_restore.set_sensitive(bool(self.operation_targets(installed=True)))
        self.library_update.set_sensitive(bool(self.operation_targets()))
        self.library_restore.set_visible(not selecting);self.library_update.set_visible(not selecting)
        self.update_branding()
        self.heading.set_text({'library_filters':'Filter & View', 'dashboard': 'Dashboard', 'library': 'Library', 'game': 'Game settings', 'menu': 'Menu', 'features': 'Configure', 'features_all': 'Install to all', 'presets': 'Library presets', 'game_presets': 'Game presets', 'dlss': 'DLSS Files', 'tools': 'Tools', 'settings': 'Settings', 'packages': 'Packages'}[self.page])
        self.panel_detail.set_text(self.game['name'] if self.game and self.page in ('features', 'game_presets', 'tools') else {'presets': 'Across your configured games', 'packages': 'Your graphics toolkit', 'dlss': 'Keep your games current', 'features_all': f'Available games: {len(self.install_targets())}', 'settings': 'Make yourself at home', 'menu': 'rtxForge'}.get(self.page, ''))
        clear(self.shelf)
        clear(self.actions)
        clear(self.menu)
        clear(self.grid)
        self.controls = []
        state=self.render_library_state() if self.page=='library' else False
        self.grid.set_row_spacing(16 if self.library_view=='list' else 24)
        self.columns, width, height = self.grid_dimensions()
        if not is_feature and self.page!='library':self.render_workspace()
        for i, entry in enumerate(self.entries):
            if self.page == 'dashboard':
                count=self.owner.settings.get('dashboard_row_count',5)
                available=self.shelf_scroll.get_width() or self.layout_width-(60 if self.compact else 92)
                shelf_width=max(80,round((available-12*(count-1))/count)-16)
                poster=self.owner.settings.get('dashboard_view','capsules')=='posters'
                ratio=self.owner.library_card_geometry(view='posters' if poster else 'capsules')[5]
                shelf_height=round(shelf_width/ratio)
                self.shelf_scroll.set_min_content_height(shelf_height+80)
                button = self.game_tile(entry, shelf_width, shelf_height, poster)
                self.shelf.append(button)
                self.controls.append(button)
                button.connect('clicked', lambda _, n=i: self.activate(n))
            elif self.page == 'library':
                if state:continue
                button = self.game_list_row(entry) if self.library_view == 'list' else self.game_tile(entry, width, height, self.library_view == 'posters')
                button.set_hexpand(True)
                button.set_halign(Gtk.Align.FILL if self.library_view=='list' else Gtk.Align.START)
                if self.library_view=='list':
                    if i==0:button.add_css_class('joined-first')
                    if i==len(self.entries)-1:button.add_css_class('joined-last')
                self.grid.attach(button, i % self.columns, i // self.columns, 1, 1)
                target=getattr(button,'focus_button',button)
                target.set_sensitive(entry['enabled']);self.controls.append(target)
                target.connect('clicked', lambda _, n=i: self.activate(n))
                focus=Gtk.EventControllerFocus()
                focus.connect('enter',lambda _,i=i:(setattr(self,'current',i),setattr(self,'zone','content'),self.selection.__setitem__(self.page,i),self.update_tabs()))
                target.add_controller(focus)
            elif self.page == 'game':
                button = self.owner.make_action_button(entry['title'],lambda _, n=i:self.activate(n))
                button.set_size_request(180,80);button.text_label.set_wrap(True)
                button.add_css_class('couch-action')
                if self.page=='game' and entry['title']=='Play':button.add_css_class('couch-primary')
                button.set_sensitive(entry['enabled'])
                self.actions.insert(button,-1)
                self.controls.append(button)
            elif self.page=='legacy_panel':
                row = Gtk.ListBoxRow()
                row.set_sensitive(entry['enabled'])
                line = Gtk.Box(spacing=16)
                icon_name = {'Button labels': 'input-gaming-symbolic', 'Library layout': 'view-grid-symbolic', 'Exit app': 'application-exit-symbolic', 'Quit rtxForge': 'application-exit-symbolic', 'Dashboard': 'go-home-symbolic', 'Library': 'folder-games-symbolic', 'Packages': 'package-x-generic-symbolic', 'Refresh library': 'view-refresh-symbolic', 'Desktop controls': 'computer-symbolic', 'Neural Rendering': 'image-x-generic-symbolic', 'Frame generation': 'media-playlist-repeat-symbolic', 'Sharpening': 'image-adjust-color-symbolic'}.get(entry['title'], 'emblem-system-symbolic')
                icon = Gtk.Image.new_from_icon_name(icon_name)
                icon.set_pixel_size(22)
                line.append(icon)
                title = label(entry['title'])
                title.set_hexpand(True)
                title.set_ellipsize(Pango.EllipsizeMode.END)
                line.append(title)
                if entry['value'] is not None:
                    if entry['adjust']:
                        line.append(Gtk.Image.new_from_icon_name('pan-start-symbolic'))
                    line.append(label(entry['value'], 'couch-value'))
                    if entry['adjust']:
                        line.append(Gtk.Image.new_from_icon_name('pan-end-symbolic'))
                row.set_child(line)
                self.menu.append(row)
        position = index if index is not None else self.selection.get(self.page, 0)
        if self.entries:
            position = min(position, len(self.entries) - 1)
            if not self.entries[position]['enabled']:
                position = next((i for i, e in enumerate(self.entries) if e['enabled']), position)
            self.focus(position)
        self.update_tabs()
        self.update_prompts()

    def select_package(self, key):
        self.owner.settings['runtime_provider'] = key
        self.owner.nr_only.set_enabled(key == 'dlss-unlocked')
        if not self.owner.options.demo:
            library_media.save_settings(self.owner.service.config, self.owner.settings)
        self.owner.toast('Package selected for the next install.')
        self.render()

    def refresh(self):
        self.library_view = self.owner.settings.get('gaming_mode_view', 'posters')
        self.view_index = 0
        if self.game:
            match = next((g for g in self.owner.games if g['game'] == self.game['game']), None)
            if match:
                if not self.has_dirty_presets():self.details_game=None
                self.set_game(match)
            else:
                self.page = 'library'
                self.game = None
                self.apply_accent(None)
                self.art_path = None
                self.art.set_paintable(None)
                self.title.set_text('Your library')
                self.detail.set_text('Add games to begin.')
        self.apply_navigation_preferences()
        self.render()

    def resize(self, width, height=None):
        if width < 400:
            return
        height = height or self.layout_height
        preset_reflow=(width>=1100)!=(self.layout_width>=1100)
        height_changed = abs(height - self.layout_height) > 12
        self.layout_height = height
        width_changed = abs(width - self.layout_width) > 12
        if width_changed:
            self.layout_width = width
        compact = width < 1400
        if compact != self.compact or width_changed or height_changed:
            self.compact = compact
            self.library_header.set_orientation(Gtk.Orientation.VERTICAL)
            self.library_controls.set_orientation(Gtk.Orientation.VERTICAL if width<1050 else Gtk.Orientation.HORIZONTAL)
            self.library_action_group.set_halign(Gtk.Align.END if width>=1050 else Gtk.Align.FILL)
            self.library_page.set_spacing(14 if compact else 20)
            self.add_css_class('compact') if compact else self.remove_css_class('compact')
            self.update_branding()
            self.footer_note.set_visible(self.navigation_position!='bottom' and width>=1050)
            self.workspace_footer.set_orientation(Gtk.Orientation.VERTICAL if self.page in ('settings','tools') and compact else Gtk.Orientation.HORIZONTAL)
            scale = max(.82, min(1.0, width / 1280))
            self.panel.set_size_request(min(width - 60, round(660 * scale)), -1)
            self.panel_scroll.set_max_content_height(max(180, height - round(330 * scale)))
            factor=getattr(self.owner,'presentation_scale',1.0)
            system_scale=self.owner.get_scale_factor()
            physical_width=width*factor*system_scale
            factor=getattr(self.owner,'presentation_reference_scale',factor)*system_scale
            unit=46 if physical_width>=3000 else 20 if physical_width<=1050 else 22 if physical_width<=1500 else 26
            self.couch_unit=u=unit/factor
            edge=(104 if physical_width>=3000 else 24 if physical_width<=1050 else 36 if physical_width<=1500 else 56)/factor
            ring=(7 if physical_width>=3000 else 4)/factor
            offset=(9 if physical_width>=3000 else 5)/factor
            self.scale_provider.load_from_data(f'''
              .couch-shell,.couch-dialog {{ font-size: {u}px; }}
              .couch-shell .couch-content {{ padding: {round(24/factor)}px {edge}px {round(12/factor)}px; }}
              .couch-shell.details-open .couch-content {{ padding: 0; }}
              .couch-shell .couch-brand {{ font-size: {1.72*u}px; }}
              .couch-shell .couch-panel-heading {{ font-size: {1.38*u}px; }}
              .couch-shell .couch-section {{ font-size: {1.08*u}px; }}
              .couch-shell .couch-tab,.couch-shell .couch-view,.couch-shell .couch-action {{ font-size: {.85*u}px; }}
              .couch-shell .couch-tab {{ padding: {round(8/factor)}px {round(20/factor)}px; }}
              .couch-shell .couch-caption,.couch-shell .couch-library-count,.couch-shell .couch-subtle,.couch-shell .couch-prompts {{ font-size: {.85*u}px; }}
              .couch-shell .couch-tile-title {{ font-size: {.93*u}px; }}
              .couch-shell .couch-tile.focused .couch-cover,.couch-shell .couch-tile:focus-visible .couch-cover {{ outline-width: {ring}px; outline-offset: {offset}px; }}
              .couch-shell .couch-list-title {{ font-size: {1.04*u}px; }}
              .couch-shell .couch-list-status,.couch-shell .couch-workspace-action,.couch-shell .couch-sidebar-item {{ font-size: {.92*u}px; }}
              .couch-shell .couch-embedded-details .game-banner-title {{ font-size: {1.6*u}px; }}
              .couch-shell .couch-embedded-details .game-detail-meta {{ font-size: {.78*u}px; }}
              .couch-shell .couch-embedded-details .game-detail-body {{ padding: {u}px {edge}px; }}
              .couch-shell .couch-embedded-details .game-detail-main label,.couch-shell .couch-embedded-details .game-detail-sidebar label {{ font-size: {.96*u}px; }}
              .couch-shell .couch-embedded-details .game-detail-main .title-2 {{ font-size: {1.1*u}px; }}
              .couch-shell .couch-information-row {{ padding: {u}px {1.1*u}px; min-height: {2*u}px; }}
              .couch-dialog label,.couch-dialog entry,.couch-dialog textview {{ font-size: {.92*u}px; }}
              .couch-dialog .title-1,.couch-dialog .title-2 {{ font-size: {1.38*u}px; }}
              .couch-dialog .subtitle,.couch-dialog .dim-label {{ font-size: {.8*u}px; }}
              .couch-dialog button {{ font-size: {.85*u}px; }}
              .couch-dialog .couch-filter-option {{ font-size: {u}px; }}
              .couch-dialog row {{ min-height: {2.9*u}px; }}
              .couch-dialog .panel-body {{ padding: {round((72 if physical_width>=3000 else 32)/factor)}px; }}
              .couch-shell .couch-embedded-details .library-meta-pill label {{ font-size: {.75*u}px; }}
            '''.encode())
            if self.page=='game':getattr(self.owner,'detail_fit_hero',lambda:None)()
            self.context.set_visible(self.owner.options.demo or time.monotonic()-self.badge_started<2.4)
        if width_changed and self.page in ('library','dashboard'):
            self.render(self.current)
        elif preset_reflow and self.page in ('presets','game_presets'):
            focus=self.owner.get_focus()
            adjustment=self.workspace_scroll.get_vadjustment()
            position=adjustment.get_value()
            columns=3 if width>=1100 else 1
            for control in self.preset_controls:self.preset_grid.remove(control)
            for i,control in enumerate(self.preset_controls):self.preset_grid.attach(control,i%columns,i//columns,1,1)
            if focus:focus.grab_focus()
            GLib.idle_add(lambda:(adjustment.set_value(position),False)[1])
