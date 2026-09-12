"""Security tools for Hermes agent."""
import asyncio
import hashlib
import json
import os
import pathlib
import socket
import struct
import time

TOOLS = [
    {
        "name": "scan_ports",
        "description": "Scan open ports on a target host using TCP connect scan",
        "parameters": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Target hostname or IP"},
                "ports": {"type": "string", "description": "Port range (e.g. '1-1024' or '22,80,443'). Default: common ports"},
                "timeout": {"type": "integer", "description": "Connection timeout in seconds", "default": 1},
            },
            "required": ["host"],
        },
    },
    {
        "name": "check_ssl",
        "description": "Check SSL/TLS certificate details for a domain",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to check"},
                "port": {"type": "integer", "description": "Port to connect to", "default": 443},
            },
            "required": ["domain"],
        },
    },
    {
        "name": "hash_password",
        "description": "Hash a password using bcrypt or argon2",
        "parameters": {
            "type": "object",
            "properties": {
                "password": {"type": "string", "description": "Password to hash"},
                "algorithm": {"type": "string", "enum": ["bcrypt", "argon2"], "description": "Hashing algorithm", "default": "bcrypt"},
            },
            "required": ["password"],
        },
    },
    {
        "name": "verify_password",
        "description": "Verify a password against a stored hash",
        "parameters": {
            "type": "object",
            "properties": {
                "password": {"type": "string", "description": "Password to verify"},
                "hash": {"type": "string", "description": "Stored hash to verify against"},
                "algorithm": {"type": "string", "enum": ["bcrypt", "argon2"], "description": "Algorithm used", "default": "bcrypt"},
            },
            "required": ["password", "hash"],
        },
    },
    {
        "name": "generate_jwt",
        "description": "Generate a JWT token with custom claims",
        "parameters": {
            "type": "object",
            "properties": {
                "payload": {"type": "string", "description": "JSON string of claims (e.g. '{\"sub\": \"user123\"}')"},
                "secret": {"type": "string", "description": "Signing secret key"},
                "algorithm": {"type": "string", "description": "JWT algorithm", "default": "HS256"},
                "expires_in": {"type": "integer", "description": "Expiration in seconds", "default": 3600},
            },
            "required": ["payload", "secret"],
        },
    },
    {
        "name": "verify_jwt",
        "description": "Verify and decode a JWT token",
        "parameters": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "JWT token to verify"},
                "secret": {"type": "string", "description": "Signing secret key"},
                "algorithm": {"type": "string", "description": "Expected algorithm", "default": "HS256"},
            },
            "required": ["token", "secret"],
        },
    },
    {
        "name": "scan_vulnerabilities",
        "description": "Scan source code for known vulnerability patterns (CWE-based)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to scan", "default": "."},
                "language": {"type": "string", "description": "Language filter (python, javascript, go, java)"},
            },
            "required": [],
        },
    },
    {
        "name": "encrypt_file",
        "description": "Encrypt a file using AES-256-CBC",
        "parameters": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string", "description": "Path to file to encrypt"},
                "output_path": {"type": "string", "description": "Path for encrypted output"},
                "password": {"type": "string", "description": "Encryption password/key"},
            },
            "required": ["input_path", "output_path", "password"],
        },
    },
    {
        "name": "decrypt_file",
        "description": "Decrypt an AES-256-CBC encrypted file",
        "parameters": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string", "description": "Path to encrypted file"},
                "output_path": {"type": "string", "description": "Path for decrypted output"},
                "password": {"type": "string", "description": "Decryption password/key"},
            },
            "required": ["input_path", "output_path", "password"],
        },
    },
    {
        "name": "generate_ssh_key",
        "description": "Generate an SSH key pair (RSA or Ed25519)",
        "parameters": {
            "type": "object",
            "properties": {
                "key_type": {"type": "string", "enum": ["ed25519", "rsa"], "description": "Key type", "default": "ed25519"},
                "output_dir": {"type": "string", "description": "Directory to save keys", "default": "."},
                "comment": {"type": "string", "description": "Key comment (e.g. email)"},
                "passphrase": {"type": "string", "description": "Passphrase for the key"},
            },
            "required": [],
        },
    },
]

functions = {}

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 993: "IMAPS",
    995: "POP3S", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
    6379: "Redis", 8080: "HTTP-Alt", 8443: "HTTPS-Alt", 27017: "MongoDB",
}


def _parse_ports(ports_str: str) -> list:
    if not ports_str:
        return sorted(COMMON_PORTS.keys())
    ports = set()
    for part in ports_str.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-", 1)
            s, e = int(s.strip()), int(e.strip())
            for p in range(s, min(e + 1, s + 5000)):
                ports.add(p)
        elif part.isdigit():
            ports.add(int(part))
    return sorted(ports)


async def scan_ports(args):
    host = args["host"]
    ports = _parse_ports(args.get("ports", ""))
    timeout = min(args.get("timeout", 1), 5)
    open_ports = []
    scan_count = 0

    async def _check(port):
        nonlocal scan_count
        scan_count += 1
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            service = COMMON_PORTS.get(port, "unknown")
            open_ports.append({"port": port, "service": service, "state": "open"})
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            pass

    semaphore = asyncio.Semaphore(200)

    async def _limited_check(port):
        async with semaphore:
            await _check(port)

    await asyncio.gather(*[_limited_check(p) for p in ports])

    return {"success": True, "host": host, "open_ports": open_ports, "total_open": len(open_ports), "scanned": scan_count}


async def check_ssl(args):
    domain = args["domain"]
    port = args.get("port", 443)

    try:
        proc = await asyncio.create_subprocess_exec(
            "python", "-c", f"""
import ssl, socket, json, sys
from datetime import datetime

ctx = ssl.create_default_context()
try:
    with ctx.wrap_socket(socket.socket(), server_hostname='{domain}') as s:
        s.connect(('{domain}', {port}))
        cert = s.getpeercert()
        cipher = s.cipher()
        protocol = s.version()

        subject = dict(x[0] for x in cert.get('subject', []))
        issuer = dict(x[0] for x in cert.get('issuer', []))
        san = [x[1] for x in cert.get('subjectAltName', [])]

        not_before = cert.get('notBefore', '')
        not_after = cert.get('notAfter', '')

        expires = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
        days_left = (expires - datetime.utcnow()).days

        print(json.dumps({{
            'subject': subject,
            'issuer': issuer,
            'not_before': not_before,
            'not_after': not_after,
            'days_until_expiry': days_left,
            'serial_number': cert.get('serialNumber', ''),
            'san': san,
            'protocol': protocol,
            'cipher': cipher[0] if cipher else 'unknown',
            'cipher_bits': cipher[2] if cipher else 0,
            'valid': days_left > 0,
        }}))
except Exception as e:
    print(json.dumps({{'error': str(e)}}))
""",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        result = json.loads(stdout.decode("utf-8", errors="replace").strip())
        result["success"] = "error" not in result
        return result
    except Exception as e:
        return {"error": str(e), "domain": domain, "success": False}


async def hash_password(args):
    password = args["password"]
    algorithm = args.get("algorithm", "bcrypt")

    try:
        if algorithm == "bcrypt":
            try:
                import bcrypt
                salt = bcrypt.gensalt(rounds=12)
                hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
                return {"success": True, "hash": hashed.decode("utf-8"), "algorithm": "bcrypt"}
            except ImportError:
                return {"error": "bcrypt not installed. Run: pip install bcrypt", "success": False}

        elif algorithm == "argon2":
            try:
                from argon2 import PasswordHasher
                ph = PasswordHasher(
                    time_cost=3, memory_cost=65536, parallelism=4,
                    hash_len=32, salt_len=16,
                )
                hashed = ph.hash(password)
                return {"success": True, "hash": hashed, "algorithm": "argon2"}
            except ImportError:
                return {"error": "argon2-cffi not installed. Run: pip install argon2-cffi", "success": False}
        else:
            return {"error": f"Unsupported algorithm: {algorithm}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def verify_password(args):
    password = args["password"]
    stored_hash = args["hash"]
    algorithm = args.get("algorithm", "bcrypt")

    try:
        if algorithm == "bcrypt":
            try:
                import bcrypt
                match = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
                return {"success": True, "valid": match, "algorithm": "bcrypt"}
            except ImportError:
                return {"error": "bcrypt not installed", "success": False}

        elif algorithm == "argon2":
            try:
                from argon2 import PasswordHasher
                from argon2.exceptions import VerifyMismatchError, VerificationError
                ph = PasswordHasher()
                try:
                    valid = ph.verify(stored_hash, password)
                    return {"success": True, "valid": valid, "algorithm": "argon2"}
                except VerifyMismatchError:
                    return {"success": True, "valid": False, "algorithm": "argon2"}
                except VerificationError as e:
                    return {"success": True, "valid": False, "algorithm": "argon2", "error": str(e)}
            except ImportError:
                return {"error": "argon2-cffi not installed", "success": False}
        else:
            return {"error": f"Unsupported algorithm: {algorithm}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


async def generate_jwt(args):
    payload = json.loads(args["payload"])
    secret = args["secret"]
    algorithm = args.get("algorithm", "HS256")
    expires_in = args.get("expires_in", 3600)

    try:
        import jwt as pyjwt
    except ImportError:
        try:
            import PyJWT as pyjwt
        except ImportError:
            return {"error": "PyJWT not installed. Run: pip install PyJWT", "success": False}

    try:
        now = int(time.time())
        payload["iat"] = now
        if "exp" not in payload:
            payload["exp"] = now + expires_in
        if "iss" not in payload:
            payload["iss"] = "hermes-agent"

        token = pyjwt.encode(payload, secret, algorithm=algorithm)
        return {"success": True, "token": token, "expires_in": expires_in, "algorithm": algorithm}
    except Exception as e:
        return {"error": str(e), "success": False}


async def verify_jwt(args):
    token = args["token"]
    secret = args["secret"]
    algorithm = args.get("algorithm", "HS256")

    try:
        import jwt as pyjwt
    except ImportError:
        try:
            import PyJWT as pyjwt
        except ImportError:
            return {"error": "PyJWT not installed", "success": False}

    try:
        decoded = pyjwt.decode(token, secret, algorithms=[algorithm])
        return {"success": True, "valid": True, "payload": decoded}
    except pyjwt.ExpiredSignatureError:
        return {"success": True, "valid": False, "error": "Token has expired"}
    except pyjwt.InvalidTokenError as e:
        return {"success": True, "valid": False, "error": str(e)}
    except Exception as e:
        return {"error": str(e), "success": False}


VULNERABILITY_PATTERNS = {
    "python": [
        (r'eval\s*\(', "CWE-95", "Code Injection via eval()"),
        (r'exec\s*\(', "CWE-95", "Code Injection via exec()"),
        (r'os\.system\s*\(', "CWE-78", "OS Command Injection"),
        (r'os\.popen\s*\(', "CWE-78", "OS Command Injection"),
        (r'subprocess\.call\(.*shell\s*=\s*True', "CWE-78", "Shell Injection via subprocess"),
        (r'subprocess\.Popen\(.*shell\s*=\s*True', "CWE-78", "Shell Injection via subprocess"),
        (r'pickle\.loads?\s*\(', "CWE-502", "Deserialization of untrusted data"),
        (r'marshal\.loads?\s*\(', "CWE-502", "Deserialization of untrusted data"),
        (r'yaml\.load\s*\([^)]*\)', "CWE-502", "Unsafe YAML loading"),
        (r'yaml\.unsafe_load\s*\(', "CWE-502", "Unsafe YAML loading"),
        (r'tempfile\.mktemp\s*\(', "CWE-377", "Insecure temp file creation"),
        (r'assert\s+', "CWE-617", "Assert used for control flow"),
        (r'hashlib\.md5\s*\(', "CWE-328", "Weak hash algorithm MD5"),
        (r'hashlib\.sha1\s*\(', "CWE-328", "Weak hash algorithm SHA1"),
        (r'DEBUG\s*=\s*True', "CWE-489", "Debug mode enabled"),
    ],
    "javascript": [
        (r'eval\s*\(', "CWE-95", "Code Injection via eval()"),
        (r'new\s+Function\s*\(', "CWE-95", "Dynamic function creation"),
        (r'innerHTML\s*=', "CWE-79", "XSS via innerHTML"),
        (r'dangerouslySetInnerHTML', "CWE-79", "React XSS risk"),
        (r'document\.write\s*\(', "CWE-79", "XSS via document.write"),
        (r'setTimeout\s*\(["\']', "CWE-95", "String-based setTimeout"),
        (r'setInterval\s*\(["\']', "CWE-95", "String-based setInterval"),
        (r'\.exec\s*\(', "CWE-78", "Child process exec"),
        (r'child_process', "CWE-78", "Child process usage"),
        (r'__proto__\s*=', "CWE-1321", "Prototype pollution"),
        (r'Object\.assign\s*\(\s*{}', "CWE-502", "Object deserialization risk"),
    ],
    "go": [
        (r'exec\.Command\s*\(', "CWE-78", "OS Command Execution"),
        (r'os\.Exec\s*\(', "CWE-78", "OS Command Execution"),
        (r'template\.HTML\s*\(', "CWE-79", "Unescaped HTML template"),
        (r'sql\.Query\s*\(.*\+', "CWE-89", "SQL Injection risk"),
        (r'unsafe\.Pointer', "CWE-787", "Unsafe pointer usage"),
    ],
    "java": [
        (r'Runtime\.getRuntime\(\)\.exec', "CWE-78", "OS Command Execution"),
        (r'ProcessBuilder', "CWE-78", "Process builder usage"),
        (r'ObjectInputStream', "CWE-502", "Java deserialization"),
        (r'ScriptEngine.*eval', "CWE-95", "Script engine eval"),
        (r'SQL.*\+\s*', "CWE-89", "SQL Injection risk"),
    ],
}


async def scan_vulnerabilities(args):
    path = args.get("path", ".")
    language = args.get("language", "")
    findings = []
    scan_count = 0

    ext_map = {
        "python": (".py",),
        "javascript": (".js", ".jsx", ".ts", ".tsx", ".mjs"),
        "go": (".go",),
        "java": (".java",),
    }

    if language:
        extensions = ext_map.get(language, ())
        patterns = VULNERABILITY_PATTERNS.get(language, [])
    else:
        extensions = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".mjs")
        patterns = []
        for lang_patterns in VULNERABILITY_PATTERNS.values():
            patterns.extend(lang_patterns)

    scan_path = pathlib.Path(path)
    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", "vendor"}

    for fpath in scan_path.rglob("*"):
        if not fpath.is_file():
            continue
        if any(skip in fpath.parts for skip in skip_dirs):
            continue
        if extensions and fpath.suffix not in extensions:
            continue

        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
            scan_count += 1
            for pattern, cwe, desc in patterns:
                import re as _re
                for match in _re.finditer(pattern, content):
                    line_num = content[:match.start()].count("\n") + 1
                    findings.append({
                        "file": str(fpath),
                        "line": line_num,
                        "cwe": cwe,
                        "description": desc,
                        "match": match.group()[:100],
                        "context": content.splitlines()[line_num - 1].strip()[:200] if line_num <= len(content.splitlines()) else "",
                    })
        except (PermissionError, OSError):
            continue

    severity_map = {
        "CWE-95": "critical", "CWE-78": "critical", "CWE-502": "critical",
        "CWE-89": "high", "CWE-79": "high", "CWE-787": "high",
        "CWE-377": "medium", "CWE-328": "medium", "CWE-617": "low",
        "CWE-489": "low", "CWE-1321": "high",
    }
    for f in findings:
        f["severity"] = severity_map.get(f["cwe"], "medium")

    return {
        "success": True,
        "findings": findings,
        "total": len(findings),
        "files_scanned": scan_count,
        "by_severity": {
            s: sum(1 for f in findings if f.get("severity") == s)
            for s in ("critical", "high", "medium", "low")
        },
    }


async def encrypt_file(args):
    input_path = args["input_path"]
    output_path = args["output_path"]
    password = args["password"]

    try:
        import hashlib as _hl
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import padding as _pad
    except ImportError:
        return {"error": "cryptography not installed. Run: pip install cryptography", "success": False}

    try:
        key = _hl.sha256(password.encode("utf-8")).digest()
        iv = os.urandom(16)

        with open(input_path, "rb") as f:
            plaintext = f.read()

        padder = _pad.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()

        with open(output_path, "wb") as f:
            f.write(iv + ciphertext)

        return {
            "success": True,
            "input": input_path,
            "output": output_path,
            "size_before": len(plaintext),
            "size_after": len(iv + ciphertext),
        }
    except Exception as e:
        return {"error": str(e), "success": False}


async def decrypt_file(args):
    input_path = args["input_path"]
    output_path = args["output_path"]
    password = args["password"]

    try:
        import hashlib as _hl
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import padding as _pad
    except ImportError:
        return {"error": "cryptography not installed. Run: pip install cryptography", "success": False}

    try:
        key = _hl.sha256(password.encode("utf-8")).digest()

        with open(input_path, "rb") as f:
            data = f.read()

        iv = data[:16]
        ciphertext = data[16:]

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = _pad.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()

        with open(output_path, "wb") as f:
            f.write(plaintext)

        return {
            "success": True,
            "input": input_path,
            "output": output_path,
            "size_decrypted": len(plaintext),
        }
    except Exception as e:
        return {"error": str(e), "success": False}


async def generate_ssh_key(args):
    key_type = args.get("key_type", "ed25519")
    output_dir = args.get("output_dir", ".")
    comment = args.get("comment", "")
    passphrase = args.get("passphrase", "")

    try:
        key_path = os.path.join(output_dir, f"id_{key_type}")
        cmd = ["ssh-keygen", "-t", key_type, "-f", key_path, "-N", passphrase or ""]
        if comment:
            cmd.extend(["-C", comment])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            return {"error": stderr.decode("utf-8", errors="replace"), "success": False}

        pub_path = key_path + ".pub"
        pub_key = ""
        if os.path.exists(pub_path):
            with open(pub_path, "r") as f:
                pub_key = f.read().strip()

        priv_key = ""
        if os.path.exists(key_path):
            with open(key_path, "r") as f:
                priv_key = f.read().strip()

        return {
            "success": True,
            "key_type": key_type,
            "private_key_path": key_path,
            "public_key_path": pub_path,
            "public_key": pub_key,
            "fingerprint": pub_key.split()[-1] if pub_key else "",
        }
    except Exception as e:
        return {"error": str(e), "success": False}


functions = {
    "scan_ports": scan_ports,
    "check_ssl": check_ssl,
    "hash_password": hash_password,
    "verify_password": verify_password,
    "generate_jwt": generate_jwt,
    "verify_jwt": verify_jwt,
    "scan_vulnerabilities": scan_vulnerabilities,
    "encrypt_file": encrypt_file,
    "decrypt_file": decrypt_file,
    "generate_ssh_key": generate_ssh_key,
}
