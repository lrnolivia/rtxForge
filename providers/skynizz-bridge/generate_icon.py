"""Convert gui/icons/rtxforge-mark.svg into ForgePanelIcon.h for the in-game panel.

The panel draws the mark with ImGui polygon fills, so no texture upload or
image decoder is needed in the game. Supports the absolute M/H/V/L/C/Z path
commands the mark uses; even-odd subpaths after the first are holes.
Run: python -I generate_icon.py <repo root>
"""
import re, sys
from pathlib import Path
from xml.etree import ElementTree

repo = Path(sys.argv[1])
svg = ElementTree.parse(repo / 'gui/icons/rtxforge-mark.svg').getroot()
token = re.compile(r'[MHVLCZ]|-?\d*\.?\d+(?:e-?\d+)?')

def subpaths(d):
    items, i, current, x, y = token.findall(d), 0, [], 0.0, 0.0
    command, result = None, []
    def number():
        nonlocal i; i += 1; return float(items[i - 1])
    while i < len(items):
        if items[i].isalpha(): command = items[i]; i += 1
        if command == 'M':
            if current: result.append(current)
            x, y = number(), number(); current = [(x, y)]; command = 'L'
        elif command == 'L': x, y = number(), number(); current.append((x, y))
        elif command == 'H': x = number(); current.append((x, y))
        elif command == 'V': y = number(); current.append((x, y))
        elif command == 'C':
            x1, y1, x2, y2, x3, y3 = (number() for _ in range(6))
            for step in range(1, 9):
                t = step / 8; u = 1 - t
                current.append((u**3*x + 3*u*u*t*x1 + 3*u*t*t*x2 + t**3*x3,
                                u**3*y + 3*u*u*t*y1 + 3*u*t*t*y2 + t**3*y3))
            x, y = x3, y3
        elif command == 'Z':
            if current: result.append(current)
            current, command = [], None
    if current: result.append(current)
    return result

def clean(points):
    out = []
    for p in points:
        if not out or abs(p[0]-out[-1][0]) > 1e-3 or abs(p[1]-out[-1][1]) > 1e-3: out.append(p)
    if len(out) > 1 and abs(out[0][0]-out[-1][0]) < 1e-3 and abs(out[0][1]-out[-1][1]) < 1e-3: out.pop()
    return out

def colour(fill, opacity):
    names = {'black': '000000', 'white': 'FFFFFF'}
    value = names.get(fill, fill.lstrip('#'))
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), round(255 * opacity)

shapes = []
for element in svg:
    if not element.tag.endswith('path'): continue
    rgba = colour(element.get('fill'), float(element.get('opacity', '1')))
    for index, points in enumerate(subpaths(element.get('d'))):
        points = clean(points)
        if len(points) >= 3:
            shapes.append((rgba, element.get('fill-rule') == 'evenodd' and index > 0, points))

xs = [p[0] for _, _, ps in shapes for p in ps]; ys = [p[1] for _, _, ps in shapes for p in ps]
left, top, size = min(xs), min(ys), max(max(xs) - min(xs), max(ys) - min(ys))
values, rows, start = [], [], 0
for (r, g, b, a), hole, points in shapes:
    for px, py in points: values += [f'{(px-left)/size:.4f}f', f'{(py-top)/size:.4f}f']
    rows.append(f'  {{ IM_COL32({r},{g},{b},{a}), {str(hole).lower()}, {start}, {len(points)} }},')
    start += len(points)
lines = ['// Generated from gui/icons/rtxforge-mark.svg by generate_icon.py. Do not edit.',
         'struct IconShape { ImU32 colour; bool hole; int start, count; };',
         f'inline constexpr float forgeIconWidth = {(max(xs)-left)/size:.4f}f, forgeIconHeight = {(max(ys)-top)/size:.4f}f;',
         'inline constexpr float forgeIconPoints[] = {']
for k in range(0, len(values), 16): lines.append('  ' + ', '.join(values[k:k+16]) + ',')
lines += ['};', 'inline constexpr IconShape forgeIconShapes[] = {'] + rows + ['};']
(repo / 'providers/skynizz-bridge/ForgePanelIcon.h').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
print(f'{len(shapes)} shapes, {start} points')
