"""Stage shared install inputs before any per-game plans or game-file writes."""
import json
import engine_bridge
import runtime_updates as runtime
import transactions as t
import ui


def package(config, mode, settings):
    selected = settings.get('runtime_provider', 'skynizz')
    custom = settings.get('custom_package') if selected == 'custom' else None
    t.need(selected != 'custom' or isinstance(custom, dict), 'Choose and review a custom package first.')
    family = custom['family'] if custom else 'y4my' if selected in ('feeder', 'vulkan-native') else selected
    e = engine_bridge.module(config, family, mode)
    if selected == 'feeder':
        import feeder_provider
        feeder_provider.stack_files(e, settings)
        return
    if selected == 'vulkan-native':
        import vulkan_app
        vulkan_app.local_model(settings.get('nr_runtime'), e, e.STATE_ROOT)
        return
    if custom:
        import package_catalog
        package_catalog.validate_parameters(custom.get('parameters', {}))
        e.Y4MY_PROVIDER = dict(custom)
    elif selected == 'skynizz':
        e.Y4MY_PROVIDER = engine_bridge.selected_skynizz_release(settings, mode)
    engine_bridge.payload(e, config, mode)
    if mode != 'mfg-only' and not settings.get('nr_runtime'):
        import vulkan_app
        try:
            vulkan_app.bundled_model(e.STATE_ROOT)
        except t.Refusal:
            # Source-only builds can still resolve the explicit/per-game model later.
            pass


def prepare(config, batches, manage_dlss=True):
    t.need(isinstance(batches, list) and len(batches) <= 16, 'Invalid package staging request.')
    ui.progress('Downloading packages/files', checked=0, total=0)
    dlss_files, unavailable = 0, None
    if manage_dlss:
        try:
            snapshot = runtime.catalog(config)
            for entry in snapshot['entries'].values():
                runtime.download(config, entry)
                dlss_files += 1
        except runtime.CatalogRateLimit as error:
            unavailable = str(error)
    seen = set()
    for batch in batches:
        mode, settings = batch['mode'], batch['settings']
        t.need(mode in ('nr-only', 'nr-mfg', 'mfg-only'), 'Invalid install mode.')
        key = json.dumps({'mode': mode, 'settings': settings}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        package(config, mode, settings)
    return {'packages': len(seen), 'dlss_files': dlss_files, 'dlss_unavailable': unavailable}
