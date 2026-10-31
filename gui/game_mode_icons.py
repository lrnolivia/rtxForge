"""The same pinned Phosphor Regular symbols used by Windows Game Mode."""
import json
from pathlib import Path
from gi.repository import Gtk

ROOT = Path(__file__).resolve().parents[1] / 'assets/game-mode/icons'
MANIFEST = json.loads((ROOT / 'icons.json').read_text(encoding='utf-8'))
_displays = set()


def name(symbol, display):
    if display not in _displays:
        Gtk.IconTheme.get_for_display(display).add_search_path(str(ROOT))
        _displays.add(display)
    # OS and Steam brand marks remain their own artwork.
    icon = MANIFEST['linux'].get(symbol)
    return 'ph-' + icon + '-symbolic' if icon else symbol
