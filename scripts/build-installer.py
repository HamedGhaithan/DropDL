"""Compile an online Windows installer using a staged clean payload."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import os
import json

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {'.venv-macos-build', 'node_modules', '__pycache__', '.pytest_cache', 'target', '.venv', 'downloads', 'dist', '.git'}


def build(compiler=None, output=None, certificate_thumbprint=None):
    if certificate_thumbprint and os.name != 'nt':
        raise SystemExit('Release signing must run on Windows with a trusted certificate in CurrentUser/My.')
    def sign(path):
        if certificate_thumbprint:
            subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                str(ROOT/'scripts/sign-release.ps1'),'-CertificateThumbprint',certificate_thumbprint,
                '-Files',str(path)],check=True)
    executable = compiler or shutil.which('makensis') or shutil.which('makensis.exe')
    if not executable:
        raise SystemExit('Install NSIS and add makensis to PATH.')
    source_version=json.loads((ROOT/'frontend/package.json').read_text())['version']
    manifest=ROOT/'frontend/dist/build.json'
    if not manifest.exists() or json.loads(manifest.read_text()).get('version')!=source_version:
        raise SystemExit('Interface build does not match this release. Run npm run build in frontend first.')
    result = Path(output or ROOT / 'dist' / 'DropDL-Setup.exe').resolve()
    result.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(executable), ('/' if os.name=='nt' else '-')+'DOUTPUT='+str(ROOT/'DropDL.exe'),str(ROOT/'installer'/'launcher.nsi')],check=True,cwd=ROOT/'installer')
    sign(ROOT/'DropDL.exe')  # Sign before embedding the launcher into the setup payload.
    with tempfile.TemporaryDirectory(prefix='dropdl-installer-') as temporary:
        payload = Path(temporary) / 'app'
        for source in ROOT.rglob('*'):
            if not source.is_file(): continue
            relative = source.relative_to(ROOT)
            # Keep built frontend dist, but exclude root dist and caches.
            if relative.parts[0] in {'downloads', 'dist'}: continue
            if any(part in EXCLUDE - {'dist'} or part.startswith('.venv-backup-') for part in relative.parts): continue
            if source.suffix == '.tsbuildinfo' or source.suffix == '.exe' and source.name != 'DropDL.exe' or source.name in {'setup-env.ps1','Setup-Log.txt','.env','cookies.txt','queue.json','settings.json','presets.json','subscriptions.json','browser.json','library.sqlite3'}: continue
            destination = payload / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        if not (payload / 'frontend' / 'dist' / 'index.html').exists():
            raise SystemExit('Build frontend before building the installer.')
        prefix = '/' if os.name == 'nt' else '-'
        subprocess.run([str(executable),f'{prefix}DPAYLOAD={payload}',f'{prefix}DOUTPUT={result}',str(ROOT/'installer'/'dropdl.nsi')],check=True,cwd=ROOT/'installer')
    sign(result)
    return result


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--compiler');parser.add_argument('--output')
    parser.add_argument('--certificate-thumbprint',help='Trusted Windows signing certificate; signs launcher before packaging and setup after building.')
    options=parser.parse_args()
    print(build(options.compiler, options.output, options.certificate_thumbprint))
