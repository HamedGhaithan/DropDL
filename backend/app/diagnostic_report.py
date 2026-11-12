"""Native fallback report; usable even when the backend has stopped."""
import io,json,platform,re,zipfile
from pathlib import Path
from .version import VERSION
LOGS=('diagnostics.log','diagnostics.log.1','desktop-diagnostics.log','desktop-diagnostics.log.1','desktop.log','backend-console.log','crash.log','desktop-crash.log')
def redact(text):
    text=re.sub(r'https?://[^\s<>"\']+','[URL]',text,flags=re.I)
    text=re.sub(r'(?i)((?:cookie|authorization|password|token|api[-_ ]?key)\s*[:=]\s*)[^\r\n,;]+',r'\1[REDACTED]',text)
    return re.sub(re.escape(str(Path.home())),'[USER]',text,flags=re.I)
def offline_bundle(root):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('health.json',json.dumps({'version':VERSION,'python':platform.python_version(),'backend_reachable':False}))
        for name in LOGS:
            try:
                with (root/name).open('rb') as stream:
                    stream.seek(0,2);stream.seek(max(0,stream.tell()-160*1024));tail=redact(stream.read(160*1024).decode('utf-8',errors='replace'))
            except OSError:tail=''
            archive.writestr(name,tail)
        archive.writestr('README.txt','The backend could not be reached. This report contains bounded local startup and crash logs. URLs and recognized credentials are redacted; cookies, settings, queue history and media are excluded. Review before sharing.\n')
    return data.getvalue()
