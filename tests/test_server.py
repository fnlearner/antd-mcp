import json
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / 'src'
PYTHON = sys.executable  # current interpreter


def run_once(request_obj):
    request_str = json.dumps(request_obj, ensure_ascii=False)
    env = {**os.environ, 'PYTHONPATH': str(SRC_DIR)}
    cmd = [PYTHON, '-m', 'antd_mcp', '--once', request_str]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    if proc.returncode != 0:
        # Fallback to direct server.py invocation if module import failed
        if 'No module named antd_mcp' in proc.stderr:
            server_path = SRC_DIR / 'antd_mcp' / 'server.py'
            cmd = [PYTHON, str(server_path), '--once', request_str]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
        if proc.returncode != 0:
            raise AssertionError(f"Process failed: {proc.stderr}\nCmd: {' '.join(cmd)}")
    out = proc.stdout.strip()
    return json.loads(out)


def test_tools_list():
    resp = run_once({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp['jsonrpc'] == '2.0'
    tools = resp['result']['tools']
    names = {t['name'] for t in tools}
    assert 'list_components' in names
    assert 'get_component' in names
    assert 'get_component_props' in names


def test_list_components():
    resp = run_once({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_components", "arguments": {}}})
    assert 'content' in resp['result']
    comps = resp['result']['content']
    assert isinstance(comps, list)
    assert len(comps) > 0
    first = comps[0]
    assert 'name' in first and 'url' in first


def test_get_component_button():
    resp = run_once({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_component", "arguments": {"name": "Button"}}})
    detail = resp['result']['content']
    assert 'title' in detail
    assert 'props_flat' in detail or 'props' in detail


def test_get_component_props_button():
    resp = run_once({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_component_props", "arguments": {"name": "Button"}}})
    payload = resp['result']['content']
    assert payload['component'] == 'Button'
    assert isinstance(payload['props_flat'], list)


def test_get_component_missing_name():
    resp = run_once({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "get_component", "arguments": {}}})
    assert 'error' in resp['result']['content'] or 'error' in resp['result']


def test_non_existent_component():
    resp = run_once({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "get_component_props", "arguments": {"name": "NoSuchXYZ"}}})
    payload = resp['result']['content']
    assert 'error' in payload

