"""Isolate every test run from the real DropDL profile.

The backend reads DROPDL_DATA_ROOT/DOWNLOAD_ROOT at import time, so these must
be set before any test module imports ``app``. Without this, running the suite
on a machine with DropDL installed would rewrite the user's queue and library.
"""
import os
import sys
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix='dropdl-tests-'))
os.environ['DROPDL_DATA_ROOT'] = str(_root / 'profile')
os.environ['DOWNLOAD_ROOT'] = str(_root / 'downloads')
os.environ.setdefault('DROPDL_ENGINE_ROOT', str(_root / 'engine'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
