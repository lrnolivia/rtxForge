"""Plain-language presentation of reviewed plans; never changes execution data."""


def blocked_summary(reason):
    return {
        'Existing OptiScaler configuration/runtime is unmanaged. Restore or remove it before installing Skynizz.':
            'Other OptiScaler files are already here. Restore or remove that mod, then try again.',
        'An unmanaged NR forwarder is already present. Restore or remove that installation before using Skynizz.':
            'Another NR mod is already here. Restore or remove it, then try again.',
        'No eligible native DLSS files. Provider-managed files and backups are excluded.':
            'No separate DLSS files need an update. Mod files and backups are left alone.',
        'DLSS version could not be verified. Unknown builds are left unchanged.':
            "Couldn't identify the DLSS version. These files will be left alone.",
        'Native DLSS files already match or exceed the catalog version.':
            'DLSS is already up to date.',
    }.get(reason, reason)


def attach(review):
    operation = review.get('operation')
    for plan, row in zip(review.get('plans', []), review.get('rows', [])):
        preview = plan.get('preview', {})
        if preview.get('feature_controls'):
            import skynizz_provider
            values = preview['feature_controls']
            settings = []
            for field in skynizz_provider.control_schema():
                if field['key'] not in values: continue
                value = values[field['key']]
                if field['kind'] == 'toggle': value = 'On' if value else 'Off'
                elif 'values' in field: value = field['choices'][field['values'].index(value)]
                settings.append(field['label'] + ': ' + str(value))
            row['detail'] = (row.get('detail') or '') + '\n' + '\n'.join(settings)
        mode = preview.get('feature_mode')
        if operation == 'uninstall':
            summary = ('Restore the setup saved before Adoption.' if preview.get('restore_boundary') == 'before-adoption' else 'Restore the original files backed up by rtxForge.')
        elif operation == 'reset':
            summary = ('Apply presets: ' + preview['launch_options'] if preview.get('launch_options') else
                       'Apply your selected presets. The installed package stays the same.')
        elif review.get('title') == 'Update NR + MFG bridge':
            summary = 'Update NR + MFG support. Keep your current tuning and NR model.'
        elif mode in ('nr-only', 'mfg-only', 'nr-mfg'):
            feature = {'nr-only': 'NR', 'mfg-only': 'MFG', 'nr-mfg': 'NR + MFG'}[mode]
            summary = f"{'Repair' if operation == 'repair' else 'Install'} {feature}."
            if review.get('apply_requested_presets'):
                multiplier = review.get('mfg_multiplier', 'auto')
                if mode != 'nr-only':
                    summary += (' Use the frame generation setting from the game.' if multiplier == 'auto'
                                else ' Start with frame generation off.' if multiplier == 0
                                else f' Request {multiplier}× frame generation.')
            else:
                summary += ' Keep your current tuning.'
        else:
            # Cross-OS adoption and record-only cleanup have different effects.
            # Keep their explicit description instead of implying a fresh install.
            summary = preview.get('launch_options') or 'Review the technical details before continuing.'
        if operation == 'install' and mode != 'mfg-only':
            summary += ' NR starts ' + ('on.' if review.get('nr_on_launch', False) else 'off; enable it from the overlay.')
        additions = ['Back up the support files kept by your earlier restore.' if preview.get('restored_support_tree') else None,
                     row.get('native_summary'), row.get('display_summary')]
        row['summary'] = '\n'.join([summary] + [text for text in additions if text])
    for row in review.get('blocked', []):
        row['summary'] = blocked_summary(row.get('reason', ''))
