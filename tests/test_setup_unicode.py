"""Exercise the actual discovery program against mismatched native code pages."""
import contextlib
import io
import json
from pathlib import Path
import re
import sys
from unittest.mock import patch
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'Setup-DropDL.bat'


def discovery_program():
    text=SOURCE.read_text()
    match=re.search(r"    \$code = '(.+)'",text)
    assert match
    return match.group(1).replace("''", "'")


@pytest.mark.parametrize('name',['ابومجيد','علي محمد','François','中文','user😀',"O'Connor",'user & company'])
def test_python_discovery_path_survives_native_decoding(name):
    executable='C:\\Users\\'+name+'\\AppData\\Local\\Programs\\Python\\Python311\\python.exe'
    stdout=io.StringIO()
    with patch.object(sys,'executable',executable),contextlib.redirect_stdout(stdout):
        exec(discovery_program(),{'__name__':'__main__'})
    wire=stdout.getvalue().strip().encode('ascii')
    for codec in ('cp437','cp850','cp1252','cp1256','utf-8'):
        assert json.loads(wire.decode(codec))['executable']==executable


def test_original_plain_text_transport_reproduces_screenshot_failure():
    original='C:\\Users\\ابومجيد\\AppData\\Local\\Programs\\Python\\Python311\\python.exe'
    corrupted=original.encode('utf-8').decode('cp437')
    assert corrupted!=original and 'ابومجيد' not in corrupted


def test_both_discovery_paths_validate_json_and_existence():
    source=SOURCE.read_text()
    assert 'Read-PythonPath (Probe $launcher' in source
    assert 'Read-PythonPath (Probe $candidate' in source
    reader=source.split('function Read-PythonPath',1)[1].split('function Find-Python',1)[0]
    assert 'ConvertFrom-Json -InputObject $Output -ErrorAction Stop' in reader
    assert '[IO.Path]::IsPathRooted($path)' in reader
    assert 'Test-Path -LiteralPath $path -PathType Leaf' in reader
    assert 'print(sys.executable)' not in source
    assert 'Test-Path -LiteralPath $Python -PathType Leaf' in source
    # Retain BOM-aware UTF-8 environment persistence and hybrid BAT transport.
    assert "'setup-env.ps1') -Value $environmentLines -Encoding UTF8" in source
    assert '[IO.File]::ReadAllText($env:DROP_DL_SETUP_FILE)' in source
