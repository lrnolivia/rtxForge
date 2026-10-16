"""Native DLSS review/execute adapter shared by both Windows interfaces."""
from pathlib import Path
import uuid
import runtime_updates as runtime
import transactions as t
import ui


def prepare(config, games):
    """Resolve and download exact replacements without writing any game files."""
    snapshot = runtime.catalog(config)
    selected, blocked = [], []
    seen = set()
    for index, game in enumerate(games):
        key = str(Path(game['game']).resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        ui.progress('Checking native DLSS files', game=game['name'], checked=index, total=len(games))
        row = runtime.inspect(config, [game], snapshot)[0]
        identity = {'name': row['name'], 'game': row['game']}
        if row['blocked']:
            blocked.append({**identity, 'reason': row['blocked']})
            continue
        eligible = [item for item in row['files']
                    if item['status'] == 'Update available' and item['current'] != 'Unknown']
        if not eligible:
            if not row['files']:
                reason = 'No eligible native DLSS files. Provider-managed files and backups are excluded.'
            elif any(item['current'] == 'Unknown' for item in row['files']):
                reason = 'DLSS version could not be verified. Unknown builds are left unchanged.'
            else:
                reason = 'Native DLSS files already match or exceed the catalog version.'
            blocked.append({**identity, 'reason': reason})
            continue
        selected.append({**row, 'files': eligible})

    plans = runtime.prepare(config, snapshot, selected)
    by_game = {row['game']: row for row in selected}
    rows = []
    for plan in plans:
        files = {item['path']: item for item in by_game[plan['game']]['files']}
        details = []
        for change in plan['changes']:
            item = files[change['path']]
            details.append(f"{item['path']} · {item['current']} → {item['target']}")
        rows.append({'name': plan['name'], 'game': plan['game'], 'detail': '\n'.join(details)})
    return {'plans': plans, 'rows': rows, 'blocked': blocked}


def execute(config, review):
    """Apply only the reviewed plans; a no-op is never reported as an update."""
    plans = review['plans']
    t.need(plans, 'No newer native DLSS files were reviewed. Check the skipped reasons.')
    # Preflight the entire selection before any target is changed.
    for plan in plans:
        t.check_plan(plan)
    records = []
    for index, plan in enumerate(plans):
        ui.progress('Updating native DLSS files', game=plan['name'], current=index + 1, total=len(plans))
        try:
            records.extend(runtime.apply(config, [plan]))
        except Exception as exc:
            raise t.Refusal(f'{exc} {len(records)} game(s) completed; their backups are available in DLSS Files.') from exc
    return {'updated_games': len(records), 'records': records}


def attach_install(config, review, enabled=True):
    """Include native updates in an install's existing review and recovery session."""
    if not enabled or review.get('operation') not in ('install', 'repair') or not review.get('plans'):
        return
    updates = prepare(config, [item['row'] for item in review['plans']])
    plans = {plan['game']: plan for plan in updates['plans']}
    details = {row['game']: row['detail'] for row in updates['rows']}
    skipped = {row['game']: row['reason'] for row in updates['blocked']}
    for item, row in zip(review['plans'], review['rows']):
        game = str(Path(item['row']['game']).resolve())
        row['game'] = game
        native = plans.get(game)
        if native is None:
            row['detail'] += '\nNative DLSS: ' + skipped.get(game, 'No file changes needed.')
            continue
        state = runtime.storage(config) / 'runtime-transactions' / uuid.uuid4().hex
        # The feature operation's per-game checkpoint owns both the native
        # files and this new recovery record. Failure/cancel/crash recovers
        # them together; successful updates retain their separate DLSS backups.
        item['extra_checkpoint_paths'] = [Path(game) / change['path'] for change in native['changes']] + [state]
        item['before_game'] = lambda plan=native, state=state: runtime.apply(config, [plan], state_paths=[state])
        row['detail'] += '\nNative DLSS updates:\n' + details[game]
