import re
import time
from pathlib import Path
from typing import Dict, Any, List
import requests
from bs4 import BeautifulSoup
import json

BASE_URL = "https://4x.ant.design"
OVERVIEW_PATH = "/components/overview-cn/"
# Use project root cache directory if available to reuse previously cached HTML.
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (MCP Antd Fetcher)"}
EXPORT_DIR = Path(__file__).parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

class FetchError(Exception):
    pass

def fetch_url(url: str, *, force: bool = False, sleep: float = 0.5) -> str:
    cache_file = CACHE_DIR / (re.sub(r'[^a-zA-Z0-9]+', '_', url) + '.html')
    if cache_file.exists() and not force:
        return cache_file.read_text(encoding='utf-8', errors='ignore')
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        raise FetchError(f"Failed {url} status={resp.status_code}")
    text = resp.text
    cache_file.write_text(text, encoding='utf-8')
    time.sleep(sleep)
    return text

def parse_overview(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'lxml')
    components: List[Dict[str, Any]] = []

    def normalize_name(raw: str) -> str:
        raw = raw.strip()
        m = re.match(r'([A-Za-z0-9]+)', raw)
        if m:
            return m.group(1)
        return raw.split()[0] if raw else raw

    for card in soup.select('.components-overview-card'):
        title_el = card.select_one('.components-overview-title')
        if not title_el:
            continue
        full_title = title_el.get_text(strip=True)
        name = normalize_name(full_title)
        link_el = card.find_parent('a') or card.select_one('a[href]')
        href = link_el['href'] if link_el and link_el.has_attr('href') else None
        desc = ''
        url = BASE_URL + href if href and href.startswith('/') else href
        components.append({
            'name': name,
            'display_name': full_title,
            'url': url,
            'description': desc,
        })

    for li in soup.select('ul.ant-menu li a[href*="/components/"]'):
        spans_text = ''.join(span.get_text(strip=True) for span in li.select('span')) or li.get_text(strip=True)
        eng_name = normalize_name(spans_text)
        href = li.get('href')
        url = BASE_URL + href if href and href.startswith('/') else href
        components.append({
            'name': eng_name,
            'display_name': spans_text,
            'url': url,
            'description': ''
        })

    def is_valid(c: Dict[str, Any]) -> bool:
        u = c.get('url')
        if not u or not isinstance(u, str) or '/components/' not in u:
            return False
        if not (u.startswith('http://') or u.startswith('https://')):
            return False
        return True

    cleaned: Dict[str, Dict[str, Any]] = {}
    for c in components:
        if not is_valid(c):
            continue
        key = c['name'].lower()
        if key not in cleaned or len(c.get('display_name','')) > len(cleaned[key].get('display_name','')):
            cleaned[key] = c
    return list(cleaned.values())

def parse_component(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'lxml')
    data: Dict[str, Any] = {}
    h1 = soup.select_one('h1')
    if h1:
        data['title'] = h1.get_text(strip=True)
    intro_parts = []
    for p in soup.select('p')[:5]:
        text = p.get_text(strip=True)
        if text:
            intro_parts.append(text)
    data['intro'] = intro_parts

    props_tables: List[Dict[str, Any]] = []
    event_tables: List[Dict[str, Any]] = []
    method_tables: List[Dict[str, Any]] = []
    other_tables: List[Dict[str, Any]] = []

    def classify(header: List[str]) -> str:
        h_join = ' '.join(header)
        if any(k in h_join for k in ["事件", "回调", "listener", "on" ]):
            return 'events'
        if any(k in h_join for k in ["方法", "method", "函数"]):
            return 'methods'
        prop_keywords = ["参数", "属性", "属性名", "名称", "配置项", "参数名", "字段", "Prop", "Property", "选项", "可配置项"]
        if any(pk in h_join for pk in prop_keywords):
            return 'props'
        if any(k in h_join for k in ["类型", "默认", "必填", "必选", "可选值"]) and 'API' in h_join:
            return 'props'
        if 'API' in h_join and any(k in h_join for k in ["类型", "默认", "参数"]):
            return 'props'
        return 'other'

    for tbl in soup.select('table'):
        header = [th.get_text(strip=True) for th in tbl.select('thead tr th')]
        rows_struct = []
        for tr in tbl.select('tbody tr'):
            cells = [td.get_text('\n', strip=True) for td in tr.select('td')]
            if cells:
                if header and len(header) == len(cells):
                    row_dict = {header[i]: cells[i] for i in range(len(header))}
                else:
                    row_dict = {'cells': cells}
                rows_struct.append(row_dict)
        table_obj = {'header': header, 'rows': rows_struct}
        kind = classify(header)
        if kind == 'props':
            props_tables.append(table_obj)
        elif kind == 'events':
            event_tables.append(table_obj)
        elif kind == 'methods':
            method_tables.append(table_obj)
        else:
            other_tables.append(table_obj)

    data['props'] = props_tables
    data['events'] = event_tables
    data['methods'] = method_tables
    data['other_tables'] = other_tables
    data['table_summary'] = {
        'props': len(props_tables),
        'events': len(event_tables),
        'methods': len(method_tables),
        'other': len(other_tables)
    }

    examples = []
    for code in soup.select('pre code'):
        content = code.get_text('\n', strip=False)
        if content:
            examples.append(content)
    data['examples'] = examples

    header_synonyms = {
        '参数': 'name', '属性': 'name', '属性名': 'name', '名称': 'name', '配置项': 'name', '参数名': 'name', '字段': 'name', 'Prop': 'name', 'Property': 'name', '可配置项': 'name',
        '说明': 'description', '描述': 'description', '备注': 'description', '含义': 'description',
        '类型': 'type', 'Type': 'type', '数据类型': 'type',
        '默认值': 'default', '默认': 'default', '缺省值': 'default',
        '版本': 'version', 'Since': 'version',
        '可选值': 'options', '选项': 'options', '可选': 'options', '枚举': 'options',
        '是否必填': 'required', '必填': 'required', '必选': 'required', '是否必选': 'required'
    }

    props_flat: List[Dict[str, Any]] = []

    def normalize_row(row: Dict[str, Any], header: List[str]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {'raw': row}
        if 'cells' in row:
            for i, h in enumerate(header):
                key = header_synonyms.get(h, h)
                cells = row['cells']
                if i < len(cells):
                    normalized[key] = cells[i]
        else:
            for k, v in row.items():
                key = header_synonyms.get(k, k)
                normalized[key] = v
        name = normalized.get('name')
        if name:
            normalized['name'] = name.split('\n')[0].strip()
        req_val = normalized.get('required')
        if isinstance(req_val, str):
            if any(token in req_val for token in ['是', '必填', '必选', 'true', '必须']):
                normalized['required'] = True
            elif any(token in req_val for token in ['否', '可选', 'false', '选填']):
                normalized['required'] = False
        return normalized

    for tbl in props_tables:
        header = tbl['header']
        for row in tbl['rows']:
            props_flat.append(normalize_row(row, header))

    data['props_flat'] = props_flat
    return data

def build_component_index(force: bool = False) -> List[Dict[str, Any]]:
    html = fetch_url(BASE_URL + OVERVIEW_PATH, force=force)
    return parse_overview(html)

def get_component_detail(url: str, force: bool = False) -> Dict[str, Any]:
    html = fetch_url(url, force=force)
    data = parse_component(html)
    data['source_url'] = url
    return data

def export_all_components(*, force: bool = False, filepath: str | None = None, validate: bool = True) -> Dict[str, Any]:
    index = build_component_index(force=force)
    all_details = []
    for comp in index:
        try:
            if not comp.get('url'):
                raise FetchError('Missing URL')
            detail = get_component_detail(comp['url'], force=force)
            detail['name'] = comp['name']
            all_details.append(detail)
        except Exception as e:
            all_details.append({'name': comp.get('name'), 'error': str(e)})
    if validate:
        all_details = [d for d in all_details if 'error' not in d]
    export_path = filepath or str(EXPORT_DIR / 'antd_components_all.json')
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump({'generated_at': time.time(), 'count': len(all_details), 'components': all_details}, f, ensure_ascii=False, indent=2)
    return {'filepath': export_path, 'count': len(all_details), 'errors': sum(1 for d in all_details if 'error' in d)}
import re
import time
from pathlib import Path
from typing import Dict, Any, List
import requests
from bs4 import BeautifulSoup
import json

BASE_URL = "https://4x.ant.design"
OVERVIEW_PATH = "/components/overview-cn/"
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (MCP Antd Fetcher)"}
EXPORT_DIR = Path(__file__).parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

class FetchError(Exception):
    pass

def fetch_url(url: str, *, force: bool = False, sleep: float = 0.5) -> str:
    """Fetch URL with simple caching."""
    cache_file = CACHE_DIR / (re.sub(r'[^a-zA-Z0-9]+', '_', url) + '.html')
    if cache_file.exists() and not force:
        return cache_file.read_text(encoding='utf-8', errors='ignore')
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        raise FetchError(f"Failed {url} status={resp.status_code}")
    text = resp.text
    cache_file.write_text(text, encoding='utf-8')
    time.sleep(sleep)
    return text


def parse_overview(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, 'lxml')
    components: List[Dict[str, Any]] = []

    def normalize_name(raw: str) -> str:
        raw = raw.strip()
        # Extract leading ASCII/word part for English name
        m = re.match(r'([A-Za-z0-9]+)', raw)
        if m:
            return m.group(1)
        # Fallback: remove Chinese characters spaces
        return raw.split()[0] if raw else raw

    # Cards listing components (cards are wrapped by anchor)   
    for card in soup.select('.components-overview-card'):
        # Card title location
        title_el = card.select_one('.components-overview-title')
        if not title_el:
            continue
        full_title = title_el.get_text(strip=True)
        name = normalize_name(full_title)
        # Anchor may be parent of card
        link_el = card.find_parent('a') or card.select_one('a[href]')
        href = link_el['href'] if link_el and link_el.has_attr('href') else None
        desc = ''  # overview cards have no description
        url = BASE_URL + href if href and href.startswith('/') else href
        components.append({
            'name': name,
            'display_name': full_title,
            'url': url,
            'description': desc,
        })

    # Aside menu list items (English + Chinese spans)
    for li in soup.select('ul.ant-menu li a[href*="/components/"]'):
        spans_text = ''.join(span.get_text(strip=True) for span in li.select('span')) or li.get_text(strip=True)
        eng_name = normalize_name(spans_text)
        href = li.get('href')
        url = BASE_URL + href if href and href.startswith('/') else href
        components.append({
            'name': eng_name,
            'display_name': spans_text,
            'url': url,
            'description': ''
        })

    def is_valid(c: Dict[str, Any]) -> bool:
        u = c.get('url')
        if not u:
            return False
        if not isinstance(u, str):
            return False
        if '/components/' not in u:
            return False
        if not (u.startswith('http://') or u.startswith('https://')):
            return False
        return True

    cleaned: Dict[str, Dict[str, Any]] = {}
    for c in components:
        if not is_valid(c):
            continue
        key = c['name'].lower()
        # Prefer entries with longer display_name (likely includes Chinese) for same key
        if key not in cleaned or len(c.get('display_name','')) > len(cleaned[key].get('display_name','')):
            cleaned[key] = c
    return list(cleaned.values())


def parse_component(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, 'lxml')
    data: Dict[str, Any] = {}
    h1 = soup.select_one('h1')
    if h1:
        data['title'] = h1.get_text(strip=True)
    intro_parts = []
    for p in soup.select('p')[:5]:  # heuristic
        text = p.get_text(strip=True)
        if text:
            intro_parts.append(text)
    data['intro'] = intro_parts

    # Classification containers
    props_tables: List[Dict[str, Any]] = []
    event_tables: List[Dict[str, Any]] = []
    method_tables: List[Dict[str, Any]] = []
    other_tables: List[Dict[str, Any]] = []

    def classify(header: List[str]) -> str:
        h_join = ' '.join(header)
        lower_join = h_join.lower()
        # Events
        if any(k in h_join for k in ["事件", "回调", "listener", "on" ]):
            return 'events'
        # Methods
        if any(k in h_join for k in ["方法", "method", "函数"]):
            return 'methods'
        # Props heuristics
        prop_keywords = ["参数", "属性", "属性名", "名称", "配置项", "参数名", "字段", "Prop", "Property", "选项", "可配置项"]
        if any(pk in h_join for pk in prop_keywords):
            return 'props'
        # If header includes type/default/required combos treat as props
        if any(k in h_join for k in ["类型", "默认", "必填", "必选", "可选值"]) and 'API' in h_join:
            return 'props'
        if 'API' in h_join and any(k in h_join for k in ["类型", "默认", "参数"]):
            return 'props'
        return 'other'

    for tbl in soup.select('table'):
        header = [th.get_text(strip=True) for th in tbl.select('thead tr th')]
        rows_struct = []
        for tr in tbl.select('tbody tr'):
            cells = [td.get_text('\n', strip=True) for td in tr.select('td')]
            if cells:
                if header and len(header) == len(cells):
                    row_dict = {header[i]: cells[i] for i in range(len(header))}
                else:
                    row_dict = {'cells': cells}
                rows_struct.append(row_dict)
        table_obj = {'header': header, 'rows': rows_struct}
        kind = classify(header)
        if kind == 'props':
            props_tables.append(table_obj)
        elif kind == 'events':
            event_tables.append(table_obj)
        elif kind == 'methods':
            method_tables.append(table_obj)
        else:
            other_tables.append(table_obj)

    data['props'] = props_tables
    data['events'] = event_tables
    data['methods'] = method_tables
    data['other_tables'] = other_tables
    data['table_summary'] = {
        'props': len(props_tables),
        'events': len(event_tables),
        'methods': len(method_tables),
        'other': len(other_tables)
    }

    examples = []
    for code in soup.select('pre code'):
        content = code.get_text('\n', strip=False)
        if content:
            examples.append(content)
    data['examples'] = examples

    # Expanded header synonyms for props normalization
    header_synonyms = {
        '参数': 'name', '属性': 'name', '属性名': 'name', '名称': 'name', '配置项': 'name', '参数名': 'name', '字段': 'name', 'Prop': 'name', 'Property': 'name', '可配置项': 'name',
        '说明': 'description', '描述': 'description', '备注': 'description', '含义': 'description',
        '类型': 'type', 'Type': 'type', '数据类型': 'type',
        '默认值': 'default', '默认': 'default', '缺省值': 'default',
        '版本': 'version', 'Since': 'version',
        '可选值': 'options', '选项': 'options', '可选': 'options', '枚举': 'options',
        '是否必填': 'required', '必填': 'required', '必选': 'required', '是否必选': 'required'
    }

    props_flat: List[Dict[str, Any]] = []

    def normalize_row(row: Dict[str, Any], header: List[str]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {'raw': row}
        if 'cells' in row:
            for i, h in enumerate(header):
                key = header_synonyms.get(h, h)
                cells = row['cells']
                if i < len(cells):
                    normalized[key] = cells[i]
        else:
            for k, v in row.items():
                key = header_synonyms.get(k, k)
                normalized[key] = v
        # Cleanup name
        name = normalized.get('name')
        if name:
            normalized['name'] = name.split('\n')[0].strip()
        # Normalize required flag
        req_val = normalized.get('required')
        if isinstance(req_val, str):
            if any(token in req_val for token in ['是', '必填', '必选', 'true', '必须']):
                normalized['required'] = True
            elif any(token in req_val for token in ['否', '可选', 'false', '选填']):
                normalized['required'] = False
        return normalized

    for tbl in props_tables:
        header = tbl['header']
        for row in tbl['rows']:
            props_flat.append(normalize_row(row, header))

    data['props_flat'] = props_flat
    return data


def build_component_index(force: bool = False) -> List[Dict[str, Any]]:
    html = fetch_url(BASE_URL + OVERVIEW_PATH, force=force)
    return parse_overview(html)


def get_component_detail(url: str, force: bool = False) -> Dict[str, Any]:
    html = fetch_url(url, force=force)
    data = parse_component(html)
    data['source_url'] = url
    return data


def export_all_components(*, force: bool = False, filepath: str | None = None, validate: bool = True) -> Dict[str, Any]:
    """Fetch all component details and persist to a JSON file.
    Filters out entries with invalid or error details when validate=True.
    """
    index = build_component_index(force=force)
    all_details = []
    for comp in index:
        try:
            if not comp.get('url'):
                raise FetchError('Missing URL')
            detail = get_component_detail(comp['url'], force=force)
            detail['name'] = comp['name']
            all_details.append(detail)
        except Exception as e:
            all_details.append({'name': comp.get('name'), 'error': str(e)})
    if validate:
        all_details = [d for d in all_details if 'error' not in d]
    export_path = filepath or str(EXPORT_DIR / 'antd_components_all.json')
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump({'generated_at': time.time(), 'count': len(all_details), 'components': all_details}, f, ensure_ascii=False, indent=2)
    return {'filepath': export_path, 'count': len(all_details), 'errors': sum(1 for d in all_details if 'error' in d)}
