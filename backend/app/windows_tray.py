"""Optional WinForms notification-area host; no extra process or dependencies."""
import logging
import os

class TrayPolicy:
    def __init__(self):self.enabled=False;self.ready=False;self.exiting=False;self.language='en'
    def intercept(self,user_close=True):return user_close and self.ready and self.enabled and not self.exiting

class WindowsTray:
    def __init__(self,window,webview,settings):
        self.window=window;self.webview=webview;self.settings=settings
        self.policy=TrayPolicy();self.icon=None;self.menu=None;self.native=None;self._owned_icon=None
    def _ui(self,fn):
        from System import Action
        if self.native.InvokeRequired:self.native.Invoke(Action(fn))
        else:fn()
    def install(self):
        if os.name!='nt':return
        try:
            preferences=self.settings.get()
            from System.Drawing import Icon
            from System.Windows.Forms import NotifyIcon,ContextMenuStrip,ToolStripMenuItem,CloseReason,RightToLeft
            from .desktop_host import desktop_icon
            self.native=self.window.native
            def setup():
                if self.icon:return
                self._owned_icon=Icon(str(desktop_icon()))
                self.icon=NotifyIcon();self.icon.Icon=self._owned_icon;self.icon.Text='DropDL Studio'
                self.menu=ContextMenuStrip();self.open_item=ToolStripMenuItem('Open DropDL');self.exit_item=ToolStripMenuItem('Exit')
                self.open_item.Click += lambda sender,event:self.restore()
                self.exit_item.Click += lambda sender,event:self.exit()
                self.menu.Items.Add(self.open_item);self.menu.Items.Add(self.exit_item)
                self.icon.ContextMenuStrip=self.menu
                self.icon.DoubleClick += lambda sender,event:self.restore()
                def closing(sender,event):
                    # Let Windows logoff/shutdown close the app normally.
                    if self.policy.intercept(event.CloseReason==CloseReason.UserClosing):
                        event.Cancel=True
                        self.native.Hide()
                self._closing=closing
                self.native.FormClosing += closing
                self.native.FormClosed += lambda sender,event:self._dispose_ui()
                self.policy.ready=True
                self.policy.enabled=bool(preferences.get('keep_in_tray',False))
                self._refresh()
            self._ui(setup)
        except Exception:
            self.policy.ready=False
            logging.getLogger('dropdl.tray').exception('Tray unavailable; normal close remains enabled')
    def _refresh(self):
        if not self.icon:return
        ar=self.policy.language=='ar'
        self.open_item.Text='فتح DropDL' if ar else 'Open DropDL'
        self.exit_item.Text='خروج' if ar else 'Exit'
        from System.Windows.Forms import RightToLeft
        self.menu.RightToLeft=RightToLeft.Yes if ar else RightToLeft.No
        self.icon.Visible=self.policy.enabled and not self.policy.exiting
    def configure(self,enabled,language='en'):
        if type(enabled) is not bool or language not in ('en','ar'):raise ValueError('Invalid tray preference.')
        self.policy.enabled=enabled;self.policy.language=language
        if self.native:
            def apply():
                if not enabled and not self.native.Visible:self.restore()
                self._refresh()
            self._ui(apply)
        return self.policy.ready
    def restore(self):
        from System.Windows.Forms import FormWindowState
        self.native.Show()
        if self.native.WindowState==FormWindowState.Minimized:self.native.WindowState=FormWindowState.Normal
        self.native.Activate();self.native.BringToFront()
    def exit(self):
        self.policy.exiting=True
        self._refresh()
        for child in list(self.webview.windows):
            if child is not self.window:child.destroy()
        self.window.destroy()
    def _dispose_ui(self):
        self.policy.ready=False
        if self.icon:self.icon.Visible=False;self.icon.Dispose();self.icon=None
        if self.menu:self.menu.Dispose();self.menu=None
        if self._owned_icon:self._owned_icon.Dispose();self._owned_icon=None
    def dispose(self):
        if not self.native:return
        try:self._ui(self._dispose_ui)
        except Exception:logging.getLogger('dropdl.tray').exception('Tray cleanup failed')
