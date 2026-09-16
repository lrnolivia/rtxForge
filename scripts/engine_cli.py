#!/usr/bin/env python3
"""Terminal frontend for the same pinned providers and engine as the desktop."""
import argparse,sys
import engine_bridge,rtxforge,library_media

def main():
    p=argparse.ArgumentParser(add_help=False)
    p.add_argument('--runtime-provider',choices=tuple(engine_bridge.providers()))
    p.add_argument('--mfg-multiplier',type=int,choices=(0,2,3,4,5,6),help='Requested native MFG ratio, 0=Off or 2x through 6x')
    p.add_argument('--sharpening-strength',choices=('off','light','medium','strong'),help='Independent sharpening default')
    p.add_argument('--nr-strength',choices=('off','light','medium','strong'),help='Default NR intensity and sharpening; preserves saved tuning on repair')
    p.add_argument('--feature-mode',choices=('mfg-only','nr-only','nr-mfg'))
    p.add_argument('--enable-effects',action='store_true',default=True)
    p.add_argument('--disable-effects',dest='enable_effects',action='store_false',help='Install dormant effects for diagnosis')
    args,remaining=p.parse_known_args()
    config=rtxforge.load_provider();settings=library_media.load_settings(config)
    provider=args.runtime_provider or settings.get('runtime_provider','y4my');mode=args.feature_mode or settings.get('default_profile','mfg-only')
    e=engine_bridge.module(config,provider,mode)
    e.original_archive_loader=e.load_archive_payload
    e.load_archive_payload=lambda archive:engine_bridge.payload(e,config,mode,archive)
    install=e.install_target
    def selected_install(*a,**kw):
        kw.update(feature_mode=mode,enable_effects=args.enable_effects,nr_strength=args.nr_strength or settings.get('nr_strength','strong'),mfg_multiplier=args.mfg_multiplier if args.mfg_multiplier is not None else settings.get('mfg_multiplier',2),sharpening_strength=args.sharpening_strength or settings.get('sharpening_strength','strong'))
        return install(*a,**kw)
    e.install_target=selected_install
    resolve=e.load_user_nr_runtime
    e.load_user_nr_runtime=lambda explicit=None,**kw:resolve(explicit,family=None) if mode=='nr-mfg' and provider=='y4my' else (None,None)
    print(f'Provider: {provider} · {e.Y4MY_PROVIDER["tag"]} · {mode} · effects '+('enabled at startup' if args.enable_effects else 'dormant'))
    print('Options: --runtime-provider y4my|dlss-unlocked --feature-mode mfg-only|nr-only|nr-mfg --enable-effects')
    return e.cli_main(remaining)
if __name__=='__main__':sys.exit(main())
