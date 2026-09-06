"""Data migration tools for Hermes agent."""
import asyncio
import csv
import json
import os

TOOLS = [
    {"name": "csv_to_json", "description": "Convert CSV file to JSON", "parameters": {"type": "object", "properties": {"input": {"type": "string"}, "output": {"type": "string"}}, "required": ["input", "output"]}},
    {"name": "json_to_csv", "description": "Convert JSON file to CSV", "parameters": {"type": "object", "properties": {"input": {"type": "string"}, "output": {"type": "string"}}, "required": ["input", "output"]}},
    {"name": "xml_to_json", "description": "Convert XML to JSON", "parameters": {"type": "object", "properties": {"input": {"type": "string"}, "output": {"type": "string"}}, "required": ["input", "output"]}},
    {"name": "json_transform", "description": "Transform JSON data with filters and mappings", "parameters": {"type": "object", "properties": {"input": {"type": "string"}, "output": {"type": "string"}, "filter_key": {"type": "string"}, "filter_value": {"type": "string"}, "rename_key": {"type": "string"}, "rename_to": {"type": "string"}}, "required": ["input", "output"]}},
    {"name": "merge_json", "description": "Merge multiple JSON files", "parameters": {"type": "object", "properties": {"inputs": {"type": "array", "items": {"type": "string"}}, "output": {"type": "string"}}, "required": ["inputs", "output"]}},
    {"name": "split_file", "description": "Split a large file into smaller chunks", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "lines_per_file": {"type": "integer", "default": 10000}, "output_dir": {"type": "string"}}}},
    {"name": "encode_decode", "description": "Encode/decode data (base64, hex, url)", "parameters": {"type": "object", "properties": {"data": {"type": "string"}, "operation": {"type": "string", "description": "encode_base64, decode_base64, encode_hex, decode_hex, encode_url, decode_url"}}, "required": ["data", "operation"]}},
]

functions = {}

async def csv_to_json(args):
    try:
        with open(args["input"], 'r') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        with open(args["output"], 'w') as f:
            json.dump(data, f, indent=2)
        return json.dumps({"success": True, "rows": len(data), "output": args["output"]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def json_to_csv(args):
    try:
        with open(args["input"], 'r') as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            with open(args["output"], 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            return json.dumps({"success": True, "rows": len(data), "output": args["output"]})
        return json.dumps({"error": "JSON must be an array of objects"})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def xml_to_json(args):
    try:
        import xml.etree.ElementTree as ET
        def elem_to_dict(elem):
            d = {}
            if elem.attrib:
                d.update(elem.attrib)
            if elem.text and elem.text.strip():
                d["text"] = elem.text.strip()
            for child in elem:
                child_d = elem_to_dict(child)
                if child.tag in d:
                    if not isinstance(d[child.tag], list):
                        d[child.tag] = [d[child.tag]]
                    d[child.tag].append(child_d)
                else:
                    d[child.tag] = child_d
            return d
        tree = ET.parse(args["input"])
        root = tree.getroot()
        data = {root.tag: elem_to_dict(root)}
        with open(args["output"], 'w') as f:
            json.dump(data, f, indent=2)
        return json.dumps({"success": True, "output": args["output"]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def json_transform(args):
    try:
        with open(args["input"], 'r') as f:
            data = json.load(f)
        filter_key = args.get("filter_key")
        filter_value = args.get("filter_value")
        rename_key = args.get("rename_key")
        rename_to = args.get("rename_to")
        if isinstance(data, list) and filter_key:
            data = [item for item in data if str(item.get(filter_key, "")) == str(filter_value)]
        if isinstance(data, list) and rename_key and rename_to:
            for item in data:
                if rename_key in item:
                    item[rename_to] = item.pop(rename_key)
        elif isinstance(data, dict) and rename_key and rename_to:
            if rename_key in data:
                data[rename_to] = data.pop(rename_key)
        with open(args["output"], 'w') as f:
            json.dump(data, f, indent=2)
        return json.dumps({"success": True, "output": args["output"], "items": len(data) if isinstance(data, list) else 1})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def merge_json(args):
    try:
        merged = []
        for input_path in args["inputs"]:
            with open(input_path, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    merged.extend(data)
                else:
                    merged.append(data)
        with open(args["output"], 'w') as f:
            json.dump(merged, f, indent=2)
        return json.dumps({"success": True, "total_items": len(merged), "output": args["output"]})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def split_file(args):
    path = args["path"]
    lines_per = args.get("lines_per_file", 10000)
    output_dir = args.get("output_dir", os.path.dirname(path))
    try:
        with open(path, 'r') as f:
            all_lines = f.readlines()
        chunks = []
        for i in range(0, len(all_lines), lines_per):
            chunk_name = f"{os.path.basename(path)}.part{len(chunks)}"
            chunk_path = os.path.join(output_dir, chunk_name)
            with open(chunk_path, 'w') as f:
                f.writelines(all_lines[i:i+lines_per])
            chunks.append({"path": chunk_path, "lines": min(lines_per, len(all_lines) - i)})
        return json.dumps({"success": True, "total_lines": len(all_lines), "chunks": len(chunks), "files": chunks})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def encode_decode(args):
    import base64
    import urllib.parse
    data = args["data"]
    op = args["operation"]
    try:
        if op == "encode_base64":
            result = base64.b64encode(data.encode()).decode()
        elif op == "decode_base64":
            result = base64.b64decode(data).decode()
        elif op == "encode_hex":
            result = data.encode().hex()
        elif op == "decode_hex":
            result = bytes.fromhex(data).decode()
        elif op == "encode_url":
            result = urllib.parse.quote(data)
        elif op == "decode_url":
            result = urllib.parse.unquote(data)
        else:
            return json.dumps({"error": f"Unknown operation: {op}"})
        return json.dumps({"operation": op, "input": data[:200], "output": result[:2000], "input_length": len(data), "output_length": len(result)})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "csv_to_json": csv_to_json, "json_to_csv": json_to_csv, "xml_to_json": xml_to_json,
    "json_transform": json_transform, "merge_json": merge_json, "split_file": split_file,
    "encode_decode": encode_decode,
}
