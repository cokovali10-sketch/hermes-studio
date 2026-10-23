"""API testing tools for Hermes agent."""
import asyncio
import json
import time
# --- константы вынесены FORGE refactor ---
CONST_5 = 5
CONST_200 = 200
CONST_1000 = 1000
CONST_8888 = 8888


TOOLS = [
    {"name": "api_get", "description": "Make GET request to API endpoint", "parameters": {"type": "object", "properties": {"url": {"type": "string", "description": "API URL"}, "headers": {"type": "object", "description": "HTTP headers"}, "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 10}}, "required": ["url"]}},
    {"name": "api_post", "description": "Make POST request to API endpoint", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "data": {"type": "string", "description": "JSON body"}, "headers": {"type": "object"}}, "required": ["url"]}},
    {"name": "api_put", "description": "Make PUT request to API endpoint", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "data": {"type": "string"}, "headers": {"type": "object"}}, "required": ["url"]}},
    {"name": "api_delete", "description": "Make DELETE request to API endpoint", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "headers": {"type": "object"}}, "required": ["url"]}},
    {"name": "api_patch", "description": "Make PATCH request to API endpoint", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "data": {"type": "string"}, "headers": {"type": "object"}}, "required": ["url"]}},
    {"name": "api_benchmark", "description": "Benchmark API endpoint with multiple requests", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string", "default": "GET"}, "requests": {"type": "integer", "description": "Number of requests", "default": 10}, "concurrency": {"type": "integer", "default": 1}}, "required": ["url"]}},
    {"name": "api_validate", "description": "Validate API response against expected schema", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "expected_status": {"type": "integer", "default": CONST_200}, "expected_fields": {"type": "array", "items": {"type": "string"}}}, "required": ["url"]}},
    {"name": "graphql_query", "description": "Execute GraphQL query", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "query": {"type": "string"}, "variables": {"type": "string", "description": "JSON variables"}}, "required": ["url", "query"]}},
    {"name": "websocket_test", "description": "Test WebSocket connection", "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "message": {"type": "string", "description": "Message to send"}, "timeout": {"type": "integer", "default": CONST_5}}, "required": ["url"]}},
    {"name": "api_mock", "description": "Start a simple mock API server", "parameters": {"type": "object", "properties": {"port": {"type": "integer", "default": CONST_8888}, "routes": {"type": "string", "description": "JSON routes config"}}, "required": ["routes"]}},
]

functions = {}

async def _make_request(method, url, headers=None, data=None, timeout=10):
    import urllib.request
    import urllib.error

    req_headers = {"User-Agent": "Hermes-API-Test/1.0"}
    if headers:
        req_headers.update(headers)

    body = data.encode() if data else None
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

    start = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        elapsed = time.time() - start
        body = resp.read().decode(errors="ignore")
        try:
            json_body = json.loads(body)
        except:
            json_body = body
        return {
            "status": resp.status, "headers": dict(resp.headers),
            "body": json_body, "time_ms": round(elapsed * CONST_1000, 2),
            "size_bytes": len(body),
        }
    except urllib.error.HTTPError as e:
        elapsed = time.time() - start
        return {"status": e.code, "error": str(e), "time_ms": round(elapsed * CONST_1000, 2)}
    except Exception as e:
        elapsed = time.time() - start
        return {"error": str(e), "time_ms": round(elapsed * CONST_1000, 2)}

async def api_get(args):
    result = await _make_request("GET", args["url"], args.get("headers"), timeout=args.get("timeout", 10))
    return json.dumps(result)

async def api_post(args):
    result = await _make_request("POST", args["url"], args.get("headers"), args.get("data"))
    return json.dumps(result)

async def api_put(args):
    result = await _make_request("PUT", args["url"], args.get("headers"), args.get("data"))
    return json.dumps(result)

async def api_delete(args):
    result = await _make_request("DELETE", args["url"], args.get("headers"))
    return json.dumps(result)

async def api_patch(args):
    result = await _make_request("PATCH", args["url"], args.get("headers"), args.get("data"))
    return json.dumps(result)

async def api_benchmark(args):
    url = args["url"]
    method = args.get("method", "GET")
    num_requests = args.get("requests", 10)
    concurrency = args.get("concurrency", 1)

    results = []
    total_start = time.time()

    for i in range(num_requests):
        result = await _make_request(method, url)
        results.append(result)

    total_time = time.time() - total_start
    times = [r.get("time_ms", 0) for r in results if "time_ms" in r]
    statuses = [r.get("status", 0) for r in results]

    return json.dumps({
        "url": url, "method": method, "total_requests": num_requests,
        "total_time_seconds": round(total_time, 3),
        "avg_time_ms": round(sum(times) / len(times), 2) if times else 0,
        "min_time_ms": min(times) if times else 0,
        "max_time_ms": max(times) if times else 0,
        "requests_per_second": round(num_requests / total_time, 1) if total_time > 0 else 0,
        "status_distribution": {str(s): statuses.count(s) for s in set(statuses)},
        "errors": len([r for r in results if "error" in r]),
    })

async def api_validate(args):
    url = args["url"]
    expected_status = args.get("expected_status", CONST_200)
    expected_fields = args.get("expected_fields", [])

    result = await _make_request("GET", url)

    issues = []
    if result.get("status") != expected_status:
        issues.append(f"Expected status {expected_status}, got {result.get('status')}")

    if expected_fields and isinstance(result.get("body"), dict):
        for field in expected_fields:
            if field not in result["body"]:
                issues.append(f"Missing field: {field}")

    return json.dumps({"url": url, "valid": len(issues) == 0, "issues": issues, "response": result})

async def graphql_query(args):
    url = args["url"]
    query = args["query"]
    variables = json.loads(args.get("variables", "{}"))

    payload = json.dumps({"query": query, "variables": variables})
    result = await _make_request("POST", url, {"Content-Type": "application/json"}, payload)
    return json.dumps(result)

async def websocket_test(args):
    url = args["url"]
    message = args.get("message", "Hello")
    timeout = args.get("timeout", CONST_5)

    try:
        import websockets
        async with websockets.connect(url) as ws:
            await ws.send(message)
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            return json.dumps({"connected": True, "sent": message, "received": response})
    except ImportError:
        return json.dumps({"error": "websockets library not installed. pip install websockets"})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def api_mock(args):
    port = args.get("port", CONST_8888)
    routes = json.loads(args.get("routes", "{}"))

    mock_code = f"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

class MockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {json.dumps(routes)}
        for path, response in routes.items():
            if self.path.startswith(path):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                return
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b'{{"error": "not found"}}')

    def do_POST(self):
        self.do_GET()

server = HTTPServer(('127.0.0.1', {port}), MockHandler)
print(f'Mock API running on http://127.0.0.1:{port}')
server.serve_forever()
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", mock_code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.sleep(1)
        return json.dumps({"success": True, "port": port, "pid": proc.pid, "message": f"Mock API running on http://127.0.0.1:{port}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "api_get": api_get, "api_post": api_post, "api_put": api_put,
    "api_delete": api_delete, "api_patch": api_patch, "api_benchmark": api_benchmark,
    "api_validate": api_validate, "graphql_query": graphql_query,
    "websocket_test": websocket_test, "api_mock": api_mock,
}
