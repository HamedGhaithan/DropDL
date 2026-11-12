"""Desktop-only bridge. The HTTP API cannot open arbitrary local paths."""
from pathlib import Path
import os
import sys
import subprocess


class NativeAPI:
    def __init__(self, settings, job_lookup=None):
        self._settings = settings
        self._window = None
        self._job_lookup = job_lookup

    def configure_tray(self,enabled,language='en'):
        tray=getattr(self,'_tray',None)
        if not tray:return False
        return tray.configure(enabled,language)

    def choose_folder(self):
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=self._settings.get()['download_directory'])
        if not result: return None
        folder = Path(result[0]).expanduser().resolve()
        return dict(self._settings.change(download_directory=str(folder)), native_folder_picker=True)

    def choose_cookies(self):
        import webview
        paths=self._window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=False)
        if not paths:return None
        return self._settings.import_cookies(paths[0])

    def choose_export_folder(self):
        import webview
        values=self._settings.get()
        folder=Path(values['export_directory'])
        result=self._window.create_file_dialog(webview.FileDialog.FOLDER,directory=str(folder if folder.is_dir() else folder.parent))
        if not result:return None
        return dict(self._settings.change(export_directory=str(Path(result[0]).expanduser().resolve())),native_folder_picker=True)

    def choose_media_files(self):
        import webview
        paths=self._window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=True)
        if not paths:return {'files':[],'errors':[]}
        return self._settings.import_files(list(paths))

    def export_diagnostics(self):
        import webview
        from .settings import CONFIG_ROOT
        paths=self._window.create_file_dialog(webview.FileDialog.SAVE,save_filename='DropDL-diagnostics.zip',file_types=('ZIP files (*.zip)',))
        if not paths:return False
        target=Path(paths[0] if isinstance(paths,(list,tuple)) else paths)
        if target.suffix.lower()!='.zip':target=target.with_suffix('.zip')
        data=None
        backend=getattr(self._settings,'_backend',None)
        if backend:
            from urllib.request import Request,urlopen
            try:
                with urlopen(Request(backend.url+'/api/support/bundle',headers={'X-DropDL-Native-Token':backend._token}),timeout=6) as response:
                    data=response.read(4*1024*1024+1)
                if len(data)>4*1024*1024:raise ValueError('Diagnostic bundle is too large.')
            except (OSError,ValueError):data=None
        if data is None:
            from .diagnostic_report import offline_bundle
            data=offline_bundle(CONFIG_ROOT)
        target.write_bytes(data)
        return True

    def launch_repair(self):
        from .settings import CONFIG_ROOT
        installer = CONFIG_ROOT / 'installer' / 'DropDL-Setup.exe'
        if sys.platform != 'win32' or not installer.is_file():
            raise ValueError('The repair installer is unavailable. Run the current DropDL installer.')
        subprocess.Popen([str(installer), '/REPAIR'])
        return True

    def locate_media(self, identity):
        import webview
        record=self._settings.get_media(identity)
        if not record or record.get('exists'):raise ValueError('Choose a missing library file.')
        paths=self._window.create_file_dialog(webview.FileDialog.OPEN,allow_multiple=False,file_types=('Media (*.mp4;*.mkv;*.webm;*.mov;*.mp3;*.m4a;*.aac;*.wav;*.flac;*.ogg;*.opus)',))
        if not paths:return None
        return self._settings.relink_media(identity,str(Path(paths[0]).resolve()))

    def reveal_library(self, identity):
        record=self._settings.get_media(identity)
        if not record or not record.get('exists'):raise ValueError('The media file was moved or removed.')
        path=Path(record['path'])
        if not path.is_file():raise ValueError('The media file was moved or removed.')
        if sys.platform=='win32':subprocess.Popen(['explorer.exe','/select,',str(path)])
        elif sys.platform=='darwin':subprocess.Popen(['open','-R',str(path)])
        else:subprocess.Popen(['xdg-open',str(path.parent)])
        return True

    def open_library(self, identity):
        if hasattr(self._settings, 'get_media'):
            record = self._settings.get_media(identity)
        else:
            from .media_library import library
            record = library.get(identity)
        if not record or not record.get('exists'):
            raise ValueError('The media file was moved or removed.')
        return self._open_media_path(Path(record['path']))

    def _open_media_path(self, path):
        if not path.is_file():raise ValueError('The downloaded file was moved or removed.')
        if path.suffix.lower() not in {'.mp4','.mkv','.webm','.mov','.mp3','.m4a','.aac','.wav','.flac','.ogg','.opus'}:
            raise ValueError('Only media can be opened.')
        if sys.platform=='win32':os.startfile(str(path))
        elif sys.platform=='darwin':subprocess.Popen(['open',str(path)])
        else:subprocess.Popen(['xdg-open',str(path)])
        return True

    def open_downloaded(self, job_id):
        if self._job_lookup:
            record=self._job_lookup(job_id)
            if not record or record.get('status')!='completed' or not record.get('output_path'):
                raise ValueError('The downloaded media is not ready.')
            path=Path(record['output_path'])
        else:
            from .jobs import jobs
            job=jobs.get(job_id)
            if not job or job.status!='completed' or not job.filename:
                raise ValueError('The downloaded media is not ready.')
            path=Path(job.filename)
        return self._open_media_path(path)

    def open_folder(self, job_id=None):
        folder = Path(self._settings.get()['download_directory'])
        if job_id:
            if self._job_lookup:
                record = self._job_lookup(job_id)
                if not record or not record.get('output_path') or record.get('status') != 'completed':
                    raise ValueError('The output is not ready.')
                folder = Path(record['output_path']).parent
            else:
                from .jobs import jobs
                job = jobs.get(job_id)
                if not job or not job.filename or job.status != 'completed':
                    raise ValueError('The output is not ready.')
                folder = Path(job.filename).parent
        if not folder.is_dir(): raise ValueError('The folder does not exist.')
        if sys.platform == 'win32': os.startfile(str(folder))
        elif sys.platform == 'darwin': subprocess.Popen(['open', str(folder)])
        else: subprocess.Popen(['xdg-open', str(folder)])
        return True

    def open_editor(self, job_id, language='en'):
        from urllib.parse import urlsplit,urlunsplit,urlencode
        record=self._job_lookup(job_id) if self._job_lookup else None
        if not self._job_lookup:
            from .jobs import jobs
            source=jobs.get(job_id);record=source.public() if source else None
        if not record or record.get('status')!='completed' or not record.get('output_path') or not Path(record['output_path']).is_file():
            raise ValueError('Choose a completed local media file.')
        if language not in ('en','ar'):raise ValueError('Unsupported language.')
        import webview
        from .desktop_host import apply_windows_icon
        editors=getattr(self,'_editors',{})
        previous=editors.get(job_id)
        if previous:
            previous.show();return True
        base=urlsplit(self._window.get_current_url())
        if base.hostname not in ('127.0.0.1','localhost'):raise ValueError('The editor requires the local desktop server.')
        url=urlunsplit((base.scheme,base.netloc,'/',urlencode({'editor':job_id,'lang':language}),''))
        child=webview.create_window('DropDL Clip Studio',url,width=1440,height=960,min_size=(1000,720))
        bridge=NativeAPI(self._settings,self._job_lookup);bridge._window=child
        child.expose(bridge.open_downloaded,bridge.open_library,bridge.open_folder,bridge.close_editor,bridge.choose_media_files,bridge.export_diagnostics,bridge.choose_export_folder)
        child.events.loaded += bridge.bind_editor_drops
        child.events.shown += lambda: apply_windows_icon(child)
        child.events.closed += lambda: editors.pop(job_id,None)
        editors[job_id]=child;self._editors=editors
        return True

    def open_player(self, media_key, language='en', position=0, rate=1):
        import math
        from urllib.parse import urlsplit,urlunsplit,urlencode
        if language not in ('en','ar'): raise ValueError('Unsupported language.')
        if not isinstance(media_key,str):raise ValueError('Invalid media identity.')
        kind,sep,identity=media_key.partition(':')
        if not sep or kind not in ('job','library') or not identity.isalnum():raise ValueError('Invalid media identity.')
        if kind=='job':
            if self._job_lookup:record=self._job_lookup(identity)
            else:
                from .jobs import jobs
                job=jobs.get(identity);record=job.public() if job else None
            if not record or record.get('status')!='completed' or not record.get('output_path') or not Path(record['output_path']).is_file():raise ValueError('The downloaded media is not ready.')
        else:
            if hasattr(self._settings,'get_media'):record=self._settings.get_media(identity)
            else:
                from .media_library import library
                record=library.get(identity)
            if not record or not record.get('exists'):raise ValueError('The media file was moved or removed.')
        if not isinstance(position,(int,float)) or not math.isfinite(position) or position<0 or position>86400:raise ValueError('Invalid playback position.')
        if rate not in (.5,.75,1,1.25,1.5,2):raise ValueError('Invalid playback speed.')
        players=getattr(self,'_players',{})
        previous=players.get(media_key)
        if previous:previous.show();return True
        base=urlsplit(self._window.get_current_url())
        if base.hostname not in ('127.0.0.1','localhost'):raise ValueError('The player requires the local desktop server.')
        import webview
        from .desktop_host import apply_windows_icon
        url=urlunsplit((base.scheme,base.netloc,'/',urlencode({'player':media_key,'lang':language,'time':position,'rate':rate}),''))
        child=webview.create_window('DropDL Player',url,width=640,height=500,min_size=(420,320))
        bridge=NativeAPI(self._settings,self._job_lookup);bridge._window=child;bridge._parent=self._window;bridge._player_key=media_key
        child.expose(bridge.open_downloaded,bridge.open_library,bridge.close_player,bridge.dock_player)
        child.events.shown += lambda: apply_windows_icon(child)
        child.events.closed += lambda: players.pop(media_key,None)
        players[media_key]=child;self._players=players
        return True

    def dock_player(self,position=0,rate=1):
        import json,math
        if not hasattr(self,'_parent'):raise ValueError('This player is already attached.')
        if not isinstance(position,(int,float)) or not math.isfinite(position) or not 0<=position<=86400:raise ValueError('Invalid playback position.')
        if rate not in (.5,.75,1,1.25,1.5,2):raise ValueError('Invalid playback speed.')
        payload=json.dumps({'key':self._player_key,'time':position,'rate':rate})
        self._parent.evaluate_js("window.dispatchEvent(new CustomEvent('dropdl-player-docked',{detail:"+payload+"}))")
        self._window.destroy()
        return True

    def close_player(self):
        self._window.destroy()
        return True

    def bind_editor_drops(self):
        """Native file references: no upload/base64 copy of large local media."""
        import json
        from webview.dom import DOMEventHandler
        def dropped(event):
            paths=[item.get('pywebviewFullPath') for item in event.get('dataTransfer',{}).get('files',[]) if item.get('pywebviewFullPath')]
            if not paths:return
            try:
                if len(paths)>100:raise ValueError('Drop up to 100 media files at a time.')
                result=self._settings.import_files(paths)
            except Exception as exc:result={'files':[],'errors':[{'name':'Dropped media','error':str(exc)}]}
            payload=json.dumps(result,ensure_ascii=True)
            self._window.evaluate_js("window.dispatchEvent(new CustomEvent('dropdl-files',{detail:"+payload+"}))")
        # WebView2 supplies native file objects directly. Avoid the global
        # name-to-path cache used by generic DOM events (which can race).
        import os
        if os.name=='nt':
            from threading import Thread
            # loaded handlers run on pywebview worker threads. COM access must
            # be posted to the owning WinForms UI thread, never made here.
            from System import Action
            import logging
            logger=logging.getLogger('dropdl.editor')
            form=self._window.native
            def report(message):
                try:
                    self._window.evaluate_js("window.dispatchEvent(new CustomEvent('dropdl-editor-warning',{detail:"+json.dumps(message)+"}))")
                except Exception:logger.exception('Editor warning could not be displayed')
            def install_script():
                try:
                    self._window.evaluate_js("""(()=>{
                      if(window._dropdlNativeDrop)return;window._dropdlNativeDrop=true;
                      document.addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('Files')){e.preventDefault();e.dataTransfer.dropEffect='copy'}},true);
                      document.addEventListener('drop',e=>{if(!e.dataTransfer.files.length)return;e.preventDefault();const files=Array.from(e.dataTransfer.files);
                        setTimeout(()=>{try{chrome.webview.postMessageWithAdditionalObjects('FilesDropped',files)}catch(error){window.dispatchEvent(new CustomEvent('dropdl-files',{detail:{files:[],errors:[{name:'Dropped media',error:String(error)}]}}))}},0);
                      },true);
                    })()""")
                    logger.info('Editor drop listeners ready')
                except Exception:
                    logger.exception('Editor drop script failed')
                    report('Drag-and-drop setup failed. Import files is still available.')
            def bind_on_ui():
                try:
                    core=form.webview.CoreWebView2
                    if core is None:raise RuntimeError('The editor WebView2 is not ready.')
                    def native_drop(sender,args):
                        try:
                            if args.get_WebMessageAsJson()!='"FilesDropped"':return
                            from urllib.parse import urlsplit
                            if urlsplit(str(args.Source)).hostname not in ('localhost','127.0.0.1'):return
                            objects=args.get_AdditionalObjects()
                            paths=[str(item.Path) for item in list(objects or []) if 'CoreWebView2File' in str(type(item))]
                            event={'dataTransfer':{'files':[{'pywebviewFullPath':path} for path in paths]}}
                            def process():
                                if paths:dropped(event)
                                else:report('Windows did not provide a file reference. Use Import files.')
                            Thread(target=process,daemon=True).start()
                        except Exception:
                            logger.exception('Native editor drop failed')
                            Thread(target=lambda:report('The file drop failed. Use Import files.'),daemon=True).start()
                    if getattr(self,'_drop_core',None) is not core:
                        core.WebMessageReceived += native_drop
                        self._drop_core=core;self._drop_handler=native_drop
                    logger.info('Editor native drop handler bound on UI thread')
                    # evaluate_js waits for UI completion, so it must run on a
                    # worker after this callback returns to the message pump.
                    Thread(target=install_script,daemon=True).start()
                except Exception:
                    logger.exception('Editor native drop setup failed')
                    Thread(target=lambda:report('Drag-and-drop is unavailable. Use Import files.'),daemon=True).start()
            try:
                self._drop_bind_action=Action(bind_on_ui)
                form.BeginInvoke(self._drop_bind_action)
                logger.info('Editor native drop setup queued')
            except Exception:
                logger.exception('Editor UI dispatch failed')
                report('Drag-and-drop is unavailable. Use Import files.')
            return
        self._window.dom.document.events.dragover += DOMEventHandler(lambda event:None,prevent_default=True,stop_propagation=False)
        self._window.dom.document.events.drop += DOMEventHandler(dropped,prevent_default=True,stop_propagation=False)

    def close_editor(self):
        self._window.destroy()
        return True
