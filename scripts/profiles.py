"""Two feature modes; native Streamline DLSS-G is the default MFG route."""
import transactions as t
MODES={'nr-mfg':'NR + MFG','mfg-only':'MFG Only'}
MFG_ROUTES={
    'native-streamline':{'id':'native-streamline-dlssg-ada-v5','FGInput':'dlssg','FGOutput':'dlssg','FGNvngxReplacement':'none'},
}
def render(template,existing,mode,mfg_route='native-streamline'):
    t.need(mode in MODES,'Only NR + MFG and MFG Only are supported')
    t.need(mfg_route in MFG_ROUTES,'Unsupported MFG route')
    route=MFG_ROUTES[mfg_route]
    text=template;old=t.ini(existing) if existing else None
    if old:
        for section in old.sections():
            if section.lower()=='mfgunlock':continue
            for k,v in old[section].items():text=t.setvalue(text,section,k,v)
    def put(section,values):
        nonlocal text
        for k,v in values.items():text=t.setvalue(text,section,k,str(v))
    # Migrate once to the compatibility-selected MFG route, then preserve user choices.
    # Route migration removes the legacy Enabler selection; native multiplier stays automatic.
    sentinel=old.get('BazziteInstaller','MfgRoute',fallback='') if old else ''
    if sentinel!=route['id']:
        put('FrameGen',{'Enabled':'true','FGInput':route['FGInput'],'FGOutput':route['FGOutput'],'FGNvngxReplacement':route['FGNvngxReplacement']})
        put('DLSSG',{'AdaMfgUnlock':'true','AdaBlackwellKernels':'true','UseGamesReflexMarkers':'auto','InterpolationCount':'auto','OverrideInterpolationCount':'auto','OverrideForceDMFG':'false','ForceDMFG':'false'})
        put('NvApi',{'DisableFlipMetering':'true','DisableReflexSync':'true'})
        put('BazziteInstaller',{'MfgRoute':route['id']})
    nr=mode=='nr-mfg'
    profile=old.get('RTXForge','NrProfile',fallback='') if old else ''
    if nr and profile!='nr70-startup-v1':
        put('Upscalers',{'Dx12Upscaler':'dlss'})
        put('DlssNr',{'DualFeature':'true','PreUpscale':'false','DualEnlarger':'dlss','Passes':'1'})
        put('Sharpness',{'Shader':'rcas','OverrideSharpness':'true','Sharpness':'0.30'})
        put('CAS',{'Enabled':'true'})
        put('RTXForge',{'NrProfile':'nr70-startup-v1'})
    # Selection is an explicit request to install this effect already on/off, never hot-enable it.
    put('DlssNr',{'Enabled':str(nr).lower()})
    if nr:put('DlssNr',{'WorkingScale':'0.70','UseProxy':'false'})
    put('RTXForge',{'Pipeline':'streamline-native-dlssg-nr-separate-v2','Mode':mode,'NrPanel':'1' if nr else '0','MfgDefault':'native-streamline','MfgRoute':mfg_route})
    if not old:
        put('Menu',{'OverlayMenu':'true'});put('Log',{'LogToFile':'true','LogLevel':'2'})
    t.ini(text)
    return text
