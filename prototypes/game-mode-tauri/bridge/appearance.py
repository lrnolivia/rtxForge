"""Fixed native entry point for the shared Game Mode appearance file."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('action', choices=('read', 'write'))
    args = parser.parse_args()
    sys.path.insert(0, str(args.root / 'scripts'))
    import game_mode_appearance
    if args.action == 'read':
        result = game_mode_appearance.load()
    else:
        raw = sys.stdin.buffer.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('The appearance file is too large.')
        result = game_mode_appearance.save(json.loads(raw))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
