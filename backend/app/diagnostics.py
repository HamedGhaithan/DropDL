"""Bounded diagnostics independent of redirected console output."""
import faulthandler
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import threading
from time import time
from .settings import CONFIG_ROOT
from .version import VERSION

_fault_file = None


def configure_diagnostics(role='backend'):
    global _fault_file
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not any(getattr(handler, '_dropdl', False) for handler in root.handlers):
        # Desktop and backend processes never race to rotate the same file.
        name = 'desktop-diagnostics.log' if role == 'desktop' else 'diagnostics.log'
        handler = RotatingFileHandler(CONFIG_ROOT / name, maxBytes=2*1024*1024, backupCount=2, encoding='utf-8')
        handler._dropdl = True
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(process)d:%(threadName)s] %(name)s: %(message)s'))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    if _fault_file is None:
        _fault_file = (CONFIG_ROOT / ('desktop-crash.log' if role=='desktop' else 'crash.log')).open('a', encoding='utf-8')
        faulthandler.enable(file=_fault_file, all_threads=True)
    def unhandled(kind, value, trace):
        logging.getLogger('dropdl').critical('Unhandled application exception', exc_info=(kind, value, trace))
    sys.excepthook = unhandled
    threading.excepthook = lambda args: unhandled(args.exc_type, args.exc_value, args.exc_traceback)
    logging.getLogger('dropdl').info('Diagnostics enabled: role=%s version=%s',role,VERSION)


def session_state():
    try:
        value=json.loads((CONFIG_ROOT/'desktop-session.json').read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def _session_write(value):
    temporary=CONFIG_ROOT/'desktop-session.tmp'
    try:
        CONFIG_ROOT.mkdir(parents=True,exist_ok=True)
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
        temporary.replace(CONFIG_ROOT/'desktop-session.json')
    except OSError:logging.getLogger('dropdl').exception('Could not record desktop session')


def start_session():
    previous=session_state()
    interrupted=bool(previous and previous.get('clean_exit') is False)
    _session_write({'version':VERSION,'pid':os.getpid(),'started':time(),'clean_exit':False,'previous_unclean_exit':interrupted})
    logging.getLogger('dropdl').info('Session started; previous unclean exit=%s',interrupted)


def finish_session():
    value=session_state()
    if value.get('pid')==os.getpid():
        value.update(clean_exit=True,finished=time());_session_write(value)
