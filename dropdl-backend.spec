from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas, binaries, hiddenimports = collect_all('yt_dlp')
# 3.0: the Phone Link web app is served from app/phone
datas += [('backend/app/phone', 'app/phone')]
# 3.0: Clip Studio modules some routes import lazily
hiddenimports += ['app.studio', 'app.analysis', 'app.transcripts', 'app.hardware']

analysis = Analysis(
    ['backend/run.py'],
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name='dropdl-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
