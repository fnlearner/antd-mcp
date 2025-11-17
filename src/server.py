import json
import sys
from typing import Any, Dict

import fetcher

TOOLS = {
    'list_components': {
        'description': 'List AntD components from overview page',
        'input_schema': {'type': 'object', 'properties': {'force': {'type': 'boolean'}}, 'required': []}
    },
    'get_component': {
        'description': 'Get detailed info for a component by name',
        'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'force': {'type': 'boolean'}}, 'required': ['name']}
    },
    'search_components': {
        'description': 'Search components by substring in name or description',
        'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}
    },
    'export_all': {
        'description': 'Fetch all component pages and persist structured JSON locally',
        'input_schema': {'type': 'object', 'properties': {'force': {'type': 'boolean'}, 'filepath': {'type': 'string'}}, 'required': []}
    },
    'get_component_props': {
        'description': 'Return flattened props list (props_flat) for a given component',
        'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'force': {'type': 'boolean'}}, 'required': ['name']}
    }
}

_index_cache = None
_details_cache: Dict[str, Dict[str, Any]] = {}

PRETTY = False
COLOR = False


def ensure_index(force: bool = False):
    global _index_cache
    if _index_cache is None or force:
        _index_cache = fetcher.build_component_index(force=force)
    return _index_cache


def handle_list_components(params: Dict[str, Any]):
    force = params.get('force', False)
    index = ensure_index(force=force)
    return index


def handle_get_component(params: Dict[str, Any]):
    name = params.get('name')
    if not name:
        return {'error': 'Component name not provided in arguments'}
    force = params.get('force', False)
    index = ensure_index(force=force)
    target = next((c for c in index if c['name'].lower() == name.lower()), None)
    if not target:
        return {'error': f'Component {name} not found'}
    url = target['url']
    if url not in _details_cache or force:
        _details_cache[url] = fetcher.get_component_detail(url, force=force)
    return _details_cache[url]


def handle_search_components(params: Dict[str, Any]):
    query = params['query'].lower()
    index = ensure_index()
    results = [c for c in index if query in c['name'].lower() or query in c.get('description', '').lower()]
    return results


def handle_export_all(params: Dict[str, Any]):
    force = params.get('force', False)
    filepath = params.get('filepath')
    summary = fetcher.export_all_components(force=force, filepath=filepath)
    return summary


def handle_get_component_props(params: Dict[str, Any]):
    name = params.get('name')
    if not name:
        return {'error': 'Component name not provided in arguments'}
    force = params.get('force', False)
    index = ensure_index(force=force)
    target = next((c for c in index if c['name'].lower() == name.lower()), None)
    if not target:
        return {'error': f'Component {name} not found'}
    url = target['url']
    if url not in _details_cache or force:
        _details_cache[url] = fetcher.get_component_detail(url, force=force)
    detail = _details_cache[url]
    return {'component': name, 'props_flat': detail.get('props_flat', []), 'count': len(detail.get('props_flat', []))}


def rpc_result(id_: Any, result: Any):
    return {'jsonrpc': '2.0', 'id': id_, 'result': result}


def rpc_error(id_: Any, code: int, message: str):
    return {'jsonrpc': '2.0', 'id': id_, 'error': {'code': code, 'message': message}}


def process_tool_call(tool_name: str, arguments: Dict[str, Any]):
    if tool_name == 'list_components':
        return handle_list_components(arguments)
    if tool_name == 'get_component':
        return handle_get_component(arguments)
    if tool_name == 'search_components':
        return handle_search_components(arguments)
    if tool_name == 'export_all':
        return handle_export_all(arguments)
    if tool_name == 'get_component_props':
        return handle_get_component_props(arguments)
    return {'error': f'Tool {tool_name} not implemented'}


def process_request(req: Dict[str, Any]):
    method = req.get('method')
    id_ = req.get('id')
    if method == 'tools/list':
        tools_meta = []
        for name, meta in TOOLS.items():
            tools_meta.append({'name': name, 'description': meta['description'], 'input_schema': meta['input_schema']})
        return rpc_result(id_, {'tools': tools_meta})
    if method == 'tools/call':
        params = req.get('params', {})
        tool_name = params.get('name')
        arguments = params.get('arguments', {}) or {}
        if tool_name not in TOOLS:
            return rpc_error(id_, -32601, f'Unknown tool {tool_name}')
        try:
            result = process_tool_call(tool_name, arguments)
            return rpc_result(id_, {'content': result})
        except Exception as e:
            return rpc_error(id_, -32603, f'Internal error: {e}')
    return rpc_error(id_, -32601, f'Unknown method {method}')


def emit(obj: Dict[str, Any]):
    if PRETTY:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(obj, ensure_ascii=False)
    if COLOR:
        if 'error' in obj:
            text = '\x1b[31m' + text + '\x1b[0m'
        else:
            text = '\x1b[32m' + text + '\x1b[0m'
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description='AntD MCP Server')
    parser.add_argument('--once', help='Provide a single JSON-RPC request string to process then exit')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging to stderr')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    parser.add_argument('--color', action='store_true', help='Colorize output (ANSI)')
    args = parser.parse_args()
    debug = args.debug or bool(os.environ.get('MCP_DEBUG'))
    global PRETTY, COLOR
    PRETTY = args.pretty or bool(os.environ.get('MCP_PRETTY'))
    COLOR = args.color or bool(os.environ.get('MCP_COLOR'))

    if args.once:
        try:
            if debug:
                sys.stderr.write(f'[DEBUG] raw_once={args.once}\n')
            req = json.loads(args.once)
            out = process_request(req)
            emit(out)
        except Exception as e:
            emit(rpc_error(None, -32700, f'Parse error: {e}'))
        return

    for line in sys.stdin:
        if debug:
            sys.stderr.write(f'[DEBUG] raw_line={repr(line)}\n')
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            emit(rpc_error(None, -32700, f'Parse error: {e}'))
            continue
        resp = process_request(req)
        emit(resp)

if __name__ == '__main__':
    main()
import json
import sys
from typing import Any, Dict

# Allow running as script: python src/antd_mcp/server.py
if __package__ is None or __package__ == "":
    import pathlib
    sys.path.append(str(pathlib.Path(__file__).resolve().parent))
    import fetcher  # noqa
else:
    from . import fetcher

TOOLS = {
    'list_components': {
        'description': 'List AntD components from overview page',
        'input_schema': {'type': 'object', 'properties': {'force': {'type': 'boolean'}}, 'required': []}
    },
    'get_component': {
        'description': 'Get detailed info for a component by name',
        'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'force': {'type': 'boolean'}}, 'required': ['name']}
    },
    'search_components': {
        'description': 'Search components by substring in name or description',
        'input_schema': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': ['query']}
    },
    'export_all': {
        'description': 'Fetch all component pages and persist structured JSON locally',
        'input_schema': {'type': 'object', 'properties': {'force': {'type': 'boolean'}, 'filepath': {'type': 'string'}}, 'required': []}
    },
    'get_component_props': {
        'description': 'Return flattened props list (props_flat) for a given component',
        'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'force': {'type': 'boolean'}}, 'required': ['name']}
    }
}

_index_cache = None
_details_cache: Dict[str, Dict[str, Any]] = {}

# Pretty printing flag (set later)
PRETTY = False
COLOR = False


def ensure_index(force: bool = False):
    global _index_cache
    if _index_cache is None or force:
        _index_cache = fetcher.build_component_index(force=force)
    return _index_cache


def handle_list_components(params: Dict[str, Any]):
    force = params.get('force', False)
    index = ensure_index(force=force)
    return index


def handle_get_component(params: Dict[str, Any]):
    name = params.get('name')
    if not name:
        return {'error': 'Component name not provided in arguments'}
    force = params.get('force', False)
    index = ensure_index(force=force)
    target = next((c for c in index if c['name'].lower() == name.lower()), None)
    if not target:
        return {'error': f'Component {name} not found'}
    url = target['url']
    if url not in _details_cache or force:
        _details_cache[url] = fetcher.get_component_detail(url, force=force)
    return _details_cache[url]


def handle_search_components(params: Dict[str, Any]):
    query = params['query'].lower()
    index = ensure_index()
    results = [c for c in index if query in c['name'].lower() or query in c.get('description', '').lower()]
    return results


def handle_export_all(params: Dict[str, Any]):
    force = params.get('force', False)
    filepath = params.get('filepath')
    summary = fetcher.export_all_components(force=force, filepath=filepath)
    return summary


def handle_get_component_props(params: Dict[str, Any]):
    name = params.get('name')
    if not name:
        return {'error': 'Component name not provided in arguments'}
    force = params.get('force', False)
    index = ensure_index(force=force)
    target = next((c for c in index if c['name'].lower() == name.lower()), None)
    if not target:
        return {'error': f'Component {name} not found'}
    url = target['url']
    if url not in _details_cache or force:
        _details_cache[url] = fetcher.get_component_detail(url, force=force)
    detail = _details_cache[url]
    return {'component': name, 'props_flat': detail.get('props_flat', []), 'count': len(detail.get('props_flat', []))}


def rpc_result(id_: Any, result: Any):
    obj = {'jsonrpc': '2.0', 'id': id_, 'result': result}
    return obj


def rpc_error(id_: Any, code: int, message: str):
    obj = {'jsonrpc': '2.0', 'id': id_, 'error': {'code': code, 'message': message}}
    return obj


def process_tool_call(tool_name: str, arguments: Dict[str, Any]):
    if tool_name == 'list_components':
        return handle_list_components(arguments)
    if tool_name == 'get_component':
        return handle_get_component(arguments)
    if tool_name == 'search_components':
        return handle_search_components(arguments)
    if tool_name == 'export_all':
        return handle_export_all(arguments)
    if tool_name == 'get_component_props':
        return handle_get_component_props(arguments)
    return {'error': f'Tool {tool_name} not implemented'}


def process_request(req: Dict[str, Any]):
    method = req.get('method')
    id_ = req.get('id')
    if method == 'tools/list':
        tools_meta = []
        for name, meta in TOOLS.items():
            tools_meta.append({'name': name, 'description': meta['description'], 'input_schema': meta['input_schema']})
        return rpc_result(id_, {'tools': tools_meta})
    if method == 'tools/call':
        params = req.get('params', {})
        tool_name = params.get('name')
        arguments = params.get('arguments', {}) or {}
        if tool_name not in TOOLS:
            return rpc_error(id_, -32601, f'Unknown tool {tool_name}')
        try:
            result = process_tool_call(tool_name, arguments)
            return rpc_result(id_, {'content': result})
        except Exception as e:
            return rpc_error(id_, -32603, f'Internal error: {e}')
    return rpc_error(id_, -32601, f'Unknown method {method}')


def emit(obj: Dict[str, Any]):
    """Write JSON to stdout with optional pretty formatting and colors."""
    if PRETTY:
        text = json.dumps(obj, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(obj, ensure_ascii=False)
    if COLOR:
        # Simple colorization: errors red, results green.
        if 'error' in obj:
            text = '\x1b[31m' + text + '\x1b[0m'
        else:
            text = '\x1b[32m' + text + '\x1b[0m'
    sys.stdout.write(text + ('\n' if not PRETTY else '\n'))
    sys.stdout.flush()


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description='AntD MCP Server')
    parser.add_argument('--once', help='Provide a single JSON-RPC request string to process then exit')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging to stderr')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    parser.add_argument('--color', action='store_true', help='Colorize output (ANSI)')
    args = parser.parse_args()
    debug = args.debug or bool(os.environ.get('MCP_DEBUG'))
    global PRETTY, COLOR
    PRETTY = args.pretty or bool(os.environ.get('MCP_PRETTY'))
    COLOR = args.color or bool(os.environ.get('MCP_COLOR'))

    if args.once:
        try:
            if debug:
                sys.stderr.write(f'[DEBUG] raw_once={args.once}\n')
            req = json.loads(args.once)
            out = process_request(req)
            emit(out)
        except Exception as e:
            emit(rpc_error(None, -32700, f'Parse error: {e}'))
        return

    for line in sys.stdin:
        if debug:
            sys.stderr.write(f'[DEBUG] raw_line={repr(line)}\n')
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            emit(rpc_error(None, -32700, f'Parse error: {e}'))
            continue
        resp = process_request(req)
        emit(resp)

if __name__ == '__main__':
    import os
    main()
