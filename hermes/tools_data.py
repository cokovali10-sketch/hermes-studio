"""Data processing tools for Hermes agent."""
import csv
import io
import json
import pathlib
import re
import xml.etree.ElementTree as ET
# --- константы вынесены FORGE refactor ---
CONST_3 = 3


TOOLS = [
    {"name": "parse_json", "description": "Parse and validate JSON, optionally extract fields", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "JSON string or file path"}, "path": {"type": "string", "description": "JQ-style dot path to extract (e.g. 'data.items[0].name')"}}, "required": ["input"]}},
    {"name": "parse_yaml", "description": "Parse YAML content and return as JSON", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "YAML string or file path"}}, "required": ["input"]}},
    {"name": "parse_csv", "description": "Parse CSV content and return structured data", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "CSV string or file path"}, "delimiter": {"type": "string", "default": ","}, "max_rows": {"type": "integer", "default": 100}}}},
    {"name": "parse_xml", "description": "Parse XML content and return as JSON tree", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "XML string or file path"}}, "required": ["input"]}},
    {"name": "convert_json_yaml", "description": "Convert between JSON and YAML formats", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "Input content or file path"}, "direction": {"type": "string", "enum": ["json_to_yaml", "yaml_to_json"], "description": "Conversion direction"}}, "required": ["input", "direction"]}},
    {"name": "merge_json", "description": "Merge multiple JSON objects or files", "parameters": {"type": "object", "properties": {"sources": {"type": "array", "items": {"type": "string"}, "description": "JSON strings or file paths to merge"}, "strategy": {"type": "string", "enum": ["deep", "shallow", "replace"], "default": "deep"}}}},
    {"name": "diff_files", "description": "Compute line-by-line diff between two files", "parameters": {"type": "object", "properties": {"file_a": {"type": "string", "description": "First file path"}, "file_b": {"type": "string", "description": "Second file path"}, "context_lines": {"type": "integer", "default": CONST_3}}, "required": ["file_a", "file_b"]}},
    {"name": "sort_data", "description": "Sort a JSON array by one or more fields", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "JSON array string or file path"}, "fields": {"type": "array", "items": {"type": "string"}, "description": "Field names to sort by"}, "descending": {"type": "boolean", "default": False}}}},
    {"name": "filter_data", "description": "Filter a JSON array by field conditions", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "JSON array string or file path"}, "field": {"type": "string", "description": "Field to filter on"}, "operator": {"type": "string", "enum": ["eq", "ne", "gt", "lt", "gte", "lte", "contains", "starts_with", "ends_with", "regex"], "description": "Comparison operator"}, "value": {"type": "string", "description": "Value to compare against"}}}},
    {"name": "aggregate_data", "description": "Aggregate/summarize a JSON array (count, sum, avg, min, max, group_by)", "parameters": {"type": "object", "properties": {"input": {"type": "string", "description": "JSON array string or file path"}, "operation": {"type": "string", "enum": ["count", "sum", "avg", "min", "max", "group_by"], "description": "Aggregation operation"}, "field": {"type": "string", "description": "Field to aggregate on (required for sum/avg/min/max/group_by)"}, "group_field": {"type": "string", "description": "Field for group_by (alternative to field)"}}}},
]

functions = {}

def _resolve_input(raw):
    if not raw:
        return raw
    p = pathlib.Path(raw)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    return raw

def _parse_json_path(data, path):
    if not path:
        return data
    parts = re.split(r'\.(?![^\[]*\])', path)
    current = data
    for part in parts:
        arr_match = re.match(r'(\w+)\[(\d+|\*)\]', part)
        if arr_match:
            key = arr_match.group(1)
            idx = arr_match.group(2)
            current = current.get(key, []) if isinstance(current, dict) else []
            if idx == "*":
                continue
            current = current[int(idx)] if int(idx) < len(current) else None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current

async def parse_json(args):
    raw = _resolve_input(args["input"])
    path = args.get("path")
    try:
        data = json.loads(raw)
        if path:
            result = _parse_json_path(data, path)
            return json.dumps({"success": True, "data": result, "path": path})
        return json.dumps({"success": True, "data": data, "keys": list(data.keys()) if isinstance(data, dict) else None, "count": len(data) if isinstance(data, list) else None})
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}", "success": False})

async def parse_yaml(args):
    raw = _resolve_input(args["input"])
    try:
        import yaml
        data = yaml.safe_load(raw)
        return json.dumps({"success": True, "data": data})
    except ImportError:
        try:
            result = {}
            current_key = None
            for line in raw.splitlines():
                if ":" in line and not line.strip().startswith("-"):
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if v:
                        if v.startswith('"') and v.endswith('"'):
                            v = v[1:-1]
                        elif v.lower() in ("true", "false"):
                            v = v.lower() == "true"
                        else:
                            try:
                                v = int(v)
                            except ValueError:
                                try:
                                    v = float(v)
                                except ValueError:
                                    pass
                        result[k] = v
                    else:
                        current_key = k
                        result[k] = {}
            return json.dumps({"success": True, "data": result, "note": "Basic YAML parser (install pyyaml for full support)"})
        except Exception as e:
            return json.dumps({"error": str(e), "success": False})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

async def parse_csv(args):
    raw = _resolve_input(args["input"])
    delimiter = args.get("delimiter", ",")
    max_rows = args.get("max_rows", 100)
    try:
        reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            rows.append(dict(row))
        return json.dumps({"success": True, "rows": rows, "count": len(rows), "fields": list(rows[0].keys()) if rows else []})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

def _element_to_dict(elem):
    result = {}
    if elem.attrib:
        result["@attributes"] = dict(elem.attrib)
    if elem.text and elem.text.strip():
        result["#text"] = elem.text.strip()
    for child in elem:
        child_data = _element_to_dict(child)
        if child.tag in result:
            if not isinstance(result[child.tag], list):
                result[child.tag] = [result[child.tag]]
            result[child.tag].append(child_data)
        else:
            result[child.tag] = child_data
    return result

async def parse_xml(args):
    raw = _resolve_input(args["input"])
    try:
        root = ET.fromstring(raw)
        data = {root.tag: _element_to_dict(root)}
        return json.dumps({"success": True, "data": data})
    except ET.ParseError as e:
        return json.dumps({"error": f"XML parse error: {e}", "success": False})

async def convert_json_yaml(args):
    raw = _resolve_input(args["input"])
    direction = args["direction"]
    try:
        if direction == "json_to_yaml":
            data = json.loads(raw)
            try:
                import yaml
                output = yaml.dump(data, default_flow_style=False, allow_unicode=True)
            except ImportError:
                output = json.dumps(data, indent=2, ensure_ascii=False)
            return json.dumps({"success": True, "output": output, "direction": direction})
        else:
            try:
                import yaml
                data = yaml.safe_load(raw)
            except ImportError:
                data = json.loads(raw)
            output = json.dumps(data, indent=2, ensure_ascii=False)
            return json.dumps({"success": True, "output": output, "direction": direction})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

def _deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = _deep_merge(result[k], v)
            else:
                result[k] = v
        return result
    return override

async def merge_json(args):
    sources = args.get("sources", [])
    strategy = args.get("strategy", "deep")
    try:
        objects = []
        for src in sources:
            raw = _resolve_input(src)
            objects.append(json.loads(raw))
        if not objects:
            return json.dumps({"error": "No sources provided", "success": False})
        if strategy == "shallow":
            result = {}
            for obj in objects:
                if isinstance(obj, dict):
                    result.update(obj)
                else:
                    result = obj
        elif strategy == "replace":
            result = objects[-1] if objects else {}
        else:
            result = objects[0]
            for obj in objects[1:]:
                result = _deep_merge(result, obj)
        return json.dumps({"success": True, "data": result, "merged_count": len(objects), "strategy": strategy})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

async def diff_files(args):
    file_a = args["file_a"]
    file_b = args["file_b"]
    context = args.get("context_lines", CONST_3)
    try:
        a = pathlib.Path(file_a)
        b = pathlib.Path(file_b)
        if not a.exists():
            return json.dumps({"error": f"File not found: {file_a}", "success": False})
        if not b.exists():
            return json.dumps({"error": f"File not found: {file_b}", "success": False})
        lines_a = a.read_text(encoding="utf-8", errors="replace").splitlines()
        lines_b = b.read_text(encoding="utf-8", errors="replace").splitlines()
        import difflib
        diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=file_a, tofile=file_b, n=context))
        added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
        return json.dumps({"success": True, "diff": "\n".join(diff), "added": added, "removed": removed, "total_diff_lines": len(diff)})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

def _get_nested(obj, field):
    keys = field.split(".")
    current = obj
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current

def _compare(a, op, b):
    try:
        a_num = float(a) if a is not None else None
        b_num = float(b)
        if op == "eq": return a_num == b_num
        if op == "ne": return a_num != b_num
        if op == "gt": return a_num > b_num
        if op == "lt": return a_num < b_num
        if op == "gte": return a_num >= b_num
        if op == "lte": return a_num <= b_num
    except (TypeError, ValueError):
        pass
    a_str = str(a) if a is not None else ""
    b_str = str(b)
    if op == "eq": return a_str == b_str
    if op == "ne": return a_str != b_str
    if op == "contains": return b_str in a_str
    if op == "starts_with": return a_str.startswith(b_str)
    if op == "ends_with": return a_str.endswith(b_str)
    if op == "regex": return bool(re.search(b_str, a_str))
    return False

async def sort_data(args):
    raw = _resolve_input(args["input"])
    fields = args.get("fields", [])
    desc = args.get("descending", False)
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return json.dumps({"error": "Input must be a JSON array", "success": False})
        def sort_key(item):
            vals = []
            for f in fields:
                v = _get_nested(item, f)
                vals.append(v)
            return vals
        data.sort(key=sort_key, reverse=desc)
        return json.dumps({"success": True, "data": data, "count": len(data)})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

async def filter_data(args):
    raw = _resolve_input(args["input"])
    field = args["field"]
    op = args["operator"]
    value = args["value"]
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return json.dumps({"error": "Input must be a JSON array", "success": False})
        filtered = [item for item in data if _compare(_get_nested(item, field), op, value)]
        return json.dumps({"success": True, "data": filtered, "count": len(filtered), "original_count": len(data)})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

async def aggregate_data(args):
    raw = _resolve_input(args["input"])
    operation = args["operation"]
    field = args.get("field")
    group_field = args.get("group_field") or field
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return json.dumps({"error": "Input must be a JSON array", "success": False})
        if operation == "count":
            return json.dumps({"success": True, "result": len(data), "operation": "count"})
        if not field:
            return json.dumps({"error": f"field is required for {operation}", "success": False})
        values = [_get_nested(item, field) for item in data if _get_nested(item, field) is not None]
        if operation == "sum":
            result = sum(float(v) for v in values)
        elif operation == "avg":
            result = sum(float(v) for v in values) / len(values) if values else 0
        elif operation == "min":
            result = min(values) if values else None
        elif operation == "max":
            result = max(values) if values else None
        elif operation == "group_by":
            groups = {}
            for item in data:
                key = _get_nested(item, group_field)
                key_str = str(key)
                if key_str not in groups:
                    groups[key_str] = []
                groups[key_str].append(item)
            result = {k: {"count": len(v), "items": v[:10]} for k, v in groups.items()}
        else:
            return json.dumps({"error": f"Unknown operation: {operation}", "success": False})
        return json.dumps({"success": True, "result": result, "operation": operation, "field": field, "count": len(values)})
    except Exception as e:
        return json.dumps({"error": str(e), "success": False})

functions = {
    "parse_json": parse_json,
    "parse_yaml": parse_yaml,
    "parse_csv": parse_csv,
    "parse_xml": parse_xml,
    "convert_json_yaml": convert_json_yaml,
    "merge_json": merge_json,
    "diff_files": diff_files,
    "sort_data": sort_data,
    "filter_data": filter_data,
    "aggregate_data": aggregate_data,
}
