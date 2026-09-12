"""AI/ML tools for Hermes agent."""
import asyncio
import json
import os
import re
import sys

TOOLS = [
    {"name": "generate_text", "description": "Generate text using a local LLM (Ollama)", "parameters": {"type": "object", "properties": {"prompt": {"type": "string", "description": "Prompt to generate from"}, "model": {"type": "string", "description": "Model name", "default": "llama3"}, "max_tokens": {"type": "integer", "description": "Max tokens to generate", "default": 1024}, "temperature": {"type": "number", "description": "Temperature (0-1)", "default": 0.7}}, "required": ["prompt"]}},
    {"name": "summarize_text", "description": "Summarize long text into key points", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to summarize"}, "max_length": {"type": "integer", "description": "Approximate max words in summary", "default": 150}, "model": {"type": "string", "description": "Model to use", "default": "llama3"}}, "required": ["text"]}},
    {"name": "translate_text", "description": "Translate text between languages", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to translate"}, "source_lang": {"type": "string", "description": "Source language code (e.g. en, es, fr)", "default": "auto"}, "target_lang": {"type": "string", "description": "Target language code"}, "model": {"type": "string", "description": "Model to use", "default": "llama3"}}, "required": ["text", "target_lang"]}},
    {"name": "analyze_sentiment", "description": "Analyze sentiment of text (positive/negative/neutral)", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to analyze"}, "model": {"type": "string", "description": "Model to use", "default": "llama3"}}, "required": ["text"]}},
    {"name": "extract_keywords", "description": "Extract keywords and key phrases from text", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to extract keywords from"}, "num_keywords": {"type": "integer", "description": "Number of keywords to extract", "default": 10}}, "required": ["text"]}},
    {"name": "generate_code", "description": "Generate code from a natural language description", "parameters": {"type": "object", "properties": {"description": {"type": "string", "description": "What the code should do"}, "language": {"type": "string", "description": "Programming language", "default": "python"}, "model": {"type": "string", "description": "Model to use", "default": "llama3"}}, "required": ["description"]}},
    {"name": "explain_code", "description": "Explain what a piece of code does", "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Code to explain"}, "language": {"type": "string", "description": "Programming language"}, "model": {"type": "string", "description": "Model to use", "default": "llama3"}}, "required": ["code"]}},
    {"name": "refactor_code", "description": "Suggest code improvements and refactoring", "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Code to refactor"}, "language": {"type": "string", "description": "Programming language"}, "focus": {"type": "string", "description": "Focus area: readability, performance, security, general", "default": "general"}, "model": {"type": "string", "description": "Model to use", "default": "llama3"}}, "required": ["code"]}},
    {"name": "detect_language", "description": "Detect the programming language of a code snippet", "parameters": {"type": "object", "properties": {"code": {"type": "string", "description": "Code snippet to identify"}}, "required": ["code"]}},
    {"name": "embed_text", "description": "Generate text embeddings using a local model", "parameters": {"type": "object", "properties": {"text": {"type": "string", "description": "Text to embed"}, "model": {"type": "string", "description": "Embedding model", "default": "nomic-embed-text"}}, "required": ["text"]}},
]

functions = {}

async def _ollama_generate(prompt, model="llama3", temperature=0.7, max_tokens=1024):
    try:
        code = f"""
import json, urllib.request
data = json.dumps({{
    "model": "{model}",
    "prompt": {json.dumps(prompt)},
    "stream": False,
    "options": {{"temperature": {temperature}, "num_predict": {max_tokens}}}
}}).encode()
req = urllib.request.Request("http://localhost:11434/api/generate", data=data, method="POST")
req.add_header("Content-Type", "application/json")
try:
    resp = urllib.request.urlopen(req, timeout=120)
    result = json.loads(resp.read().decode())
    print(json.dumps({{"response": result.get("response", ""), "done": result.get("done", False), "model": result.get("model", "")}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=130)
        return json.loads(stdout.decode(errors="ignore").strip())
    except Exception as e:
        return {"error": str(e)}

async def generate_text(args):
    prompt = args["prompt"]
    model = args.get("model", "llama3")
    max_tokens = args.get("max_tokens", 1024)
    temperature = args.get("temperature", 0.7)
    result = await _ollama_generate(prompt, model, temperature, max_tokens)
    if "error" in result:
        return json.dumps(result)
    return json.dumps({"success": True, "text": result.get("response", ""), "model": result.get("model", model), "tokens": len(result.get("response", "").split())})

async def summarize_text(args):
    text = args["text"]
    max_length = args.get("max_length", 150)
    model = args.get("model", "llama3")
    prompt = f"Summarize the following text in approximately {max_length} words. Be concise and capture the key points:\n\n{text[:4000]}"
    result = await _ollama_generate(prompt, model, 0.3, 512)
    if "error" in result:
        return json.dumps(result)
    return json.dumps({"success": True, "summary": result.get("response", ""), "original_length": len(text.split()), "model": model})

async def translate_text(args):
    text = args["text"]
    source_lang = args.get("source_lang", "auto")
    target_lang = args["target_lang"]
    model = args.get("model", "llama3")
    lang_names = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese", "ru": "Russian", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "hi": "Hindi"}
    target_name = lang_names.get(target_lang, target_lang)
    source_name = lang_names.get(source_lang, "auto-detected") if source_lang != "auto" else "auto-detected"
    prompt = f"Translate the following text from {source_name} to {target_name}. Return ONLY the translation, no explanations:\n\n{text[:3000]}"
    result = await _ollama_generate(prompt, model, 0.2, 2048)
    if "error" in result:
        return json.dumps(result)
    return json.dumps({"success": True, "translation": result.get("response", ""), "source_lang": source_lang, "target_lang": target_lang, "model": model})

async def analyze_sentiment(args):
    text = args["text"]
    model = args.get("model", "llama3")
    prompt = f"""Analyze the sentiment of the following text. Respond with a JSON object containing:
- "sentiment": one of "positive", "negative", or "neutral"
- "confidence": a number from 0 to 1
- "reasoning": brief explanation

Text: {text[:2000]}

Respond with ONLY the JSON object:"""
    result = await _ollama_generate(prompt, model, 0.1, 256)
    if "error" in result:
        return json.dumps(result)
    response = result.get("response", "")
    try:
        json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
        if json_match:
            sentiment = json.loads(json_match.group())
            return json.dumps({"success": True, **sentiment, "model": model})
    except json.JSONDecodeError:
        pass
    return json.dumps({"success": True, "raw_response": response, "model": model})

async def extract_keywords(args):
    text = args["text"]
    num_keywords = args.get("num_keywords", 10)
    prompt = f"Extract the top {num_keywords} keywords/key phrases from this text. Return them as a comma-separated list:\n\n{text[:3000]}"
    result = await _ollama_generate(prompt, "llama3", 0.2, 256)
    if "error" in result:
        return json.dumps(result)
    response = result.get("response", "")
    keywords = [kw.strip().strip('"').strip("'") for kw in re.split(r',|\n', response) if kw.strip()]
    return json.dumps({"success": True, "keywords": keywords[:num_keywords], "count": min(len(keywords), num_keywords), "model": "llama3"})

async def generate_code(args):
    description = args["description"]
    language = args.get("language", "python")
    model = args.get("model", "llama3")
    prompt = f"""Write {language} code that does the following:
{description}

Requirements:
- Clean, well-structured code
- Include necessary imports
- Add brief comments where helpful
- Return ONLY the code, no explanations

Code:"""
    result = await _ollama_generate(prompt, model, 0.3, 2048)
    if "error" in result:
        return json.dumps(result)
    code = result.get("response", "")
    code = re.sub(r'^```[\w]*\n?', '', code, flags=re.MULTILINE)
    code = re.sub(r'```$', '', code.strip(), flags=re.MULTILINE)
    return json.dumps({"success": True, "code": code.strip(), "language": language, "model": model})

async def explain_code(args):
    code = args["code"]
    language = args.get("language", "")
    model = args.get("model", "llama3")
    lang_hint = f" (written in {language})" if language else ""
    prompt = f"""Explain what this code does{lang_hint}. Be clear and thorough:

```{language}
{code[:3000]}
```

Explanation:"""
    result = await _ollama_generate(prompt, model, 0.3, 1024)
    if "error" in result:
        return json.dumps(result)
    return json.dumps({"success": True, "explanation": result.get("response", ""), "model": model})

async def refactor_code(args):
    code = args["code"]
    language = args.get("language", "")
    focus = args.get("focus", "general")
    model = args.get("model", "llama3")
    focus_hints = {
        "readability": "Focus on readability, naming, and code organization.",
        "performance": "Focus on performance optimization and efficiency.",
        "security": "Focus on security improvements and vulnerability fixes.",
        "general": "Suggest general improvements for better code quality.",
    }
    prompt = f"""Refactor the following {language} code. {focus_hints.get(focus, focus_hints['general'])}

Original code:
```{language}
{code[:3000]}
```

Provide:
1. The refactored code
2. A brief explanation of changes

Refactored code:"""
    result = await _ollama_generate(prompt, model, 0.3, 2048)
    if "error" in result:
        return json.dumps(result)
    response = result.get("response", "")
    code_match = re.search(r'```[\w]*\n(.*?)```', response, re.DOTALL)
    refactored = code_match.group(1).strip() if code_match else response
    explanation = response.replace(refactored, "").strip()
    return json.dumps({"success": True, "refactored_code": refactored, "explanation": explanation, "focus": focus, "model": model})

async def detect_language(args):
    code = args["code"]
    lang_patterns = [
        ("python", [r'\bdef\s+\w+\s*\(', r'\bimport\s+\w+', r'\bfrom\s+\w+\s+import', r'if\s+__name__\s*==', r'\bprint\s*\(']),
        ("javascript", [r'\bfunction\s+\w+\s*\(', r'\bconst\s+\w+\s*=', r'\blet\s+\w+\s*=', r'\bvar\s+\w+\s*=', r'=>', r'\bconsole\.log\s*\(']),
        ("typescript", [r'\binterface\s+\w+', r'\btype\s+\w+\s*=', r':\s*(string|number|boolean)', r'\bas\s+\w+']),
        ("java", [r'\bpublic\s+class\b', r'\bpublic\s+static\s+void\s+main\b', r'\bSystem\.out\.print', r'\bimport\s+java\.', r'\bfinal\s+class\b']),
        ("go", [r'\bfunc\s+\w+\s*\(', r'\bpackage\s+\w+', r'\bfmt\.Print', r':=', r'\bgo\s+func\b']),
        ("rust", [r'\bfn\s+\w+\s*\(', r'\blet\s+mut\b', r'\bimpl\s+\w+', r'\bpub\s+fn\b', r'\buse\s+std::']),
        ("ruby", [r'\bdef\s+\w+\s*\n', r'\bputs\s+', r'\brequire\s+', r'\bclass\s+\w+\s*<', r'\bend\s*$']),
        ("php", [r'<\?php', r'\bfunction\s+\w+\s*\(', r'\$\w+\s*=', r'\becho\s+', r'\barray\s*\(']),
        ("c", [r'\b#include\s*<', r'\bint\s+main\s*\(', r'\bprintf\s*\(', r'\bmalloc\s*\(', r'\bfree\s*\(']),
        ("cpp", [r'\b#include\s*<', r'\bstd::', r'\bcout\s*<<', r'\bclass\s+\w+\s*\{', r'\btemplate\s*<']),
        ("html", [r'<html', r'<div', r'<body', r'<!DOCTYPE', r'<head']),
        ("css", [r'\{[\s\S]*?:\s*[\w#]+;', r'@media', r'\.[a-zA-Z_]\w*\s*\{', r'#[a-zA-Z_]\w*\s*\{']),
        ("sql", [r'\bSELECT\s+', r'\bFROM\s+', r'\bWHERE\s+', r'\bINSERT\s+INTO\b', r'\bCREATE\s+TABLE\b']),
        ("shell", [r'#!/bin/bash', r'\becho\s+', r'\bif\s*\[', r'\bthen\b', r'\bfi\b']),
        ("powershell", [r'Get-\w+', r'Set-\w+', r'\$\w+\s*=', r'Write-Host', r'Import-Module']),
    ]
    scores = {}
    for lang, patterns in lang_patterns:
        score = sum(1 for p in patterns if re.search(p, code, re.IGNORECASE))
        if score > 0:
            scores[lang] = score
    if scores:
        best = max(scores, key=scores.get)
        lang_dict = dict(lang_patterns)
        total = len(lang_dict.get(best, []))
        confidence = round(scores[best] / total, 2) if total > 0 else 0
        return json.dumps({"success": True, "language": best, "confidence": confidence, "scores": scores})
    return json.dumps({"success": True, "language": "unknown", "confidence": 0, "scores": {}})

async def embed_text(args):
    text = args["text"]
    model = args.get("model", "nomic-embed-text")
    try:
        code = f"""
import json, urllib.request
data = json.dumps({{"model": "{model}", "input": {json.dumps(text[:8000])}}}).encode()
req = urllib.request.Request("http://localhost:11434/api/embeddings", data=data, method="POST")
req.add_header("Content-Type", "application/json")
try:
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode())
    embedding = result.get("embedding", [])
    print(json.dumps({{"embedding": embedding[:10], "dimensions": len(embedding), "truncated": len(embedding) > 10}}))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
"""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=35)
        result = json.loads(stdout.decode(errors="ignore").strip())
        if "error" in result:
            return json.dumps(result)
        return json.dumps({"success": True, "model": model, "dimensions": result.get("dimensions", 0), "embedding_preview": result.get("embedding", [])})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "generate_text": generate_text,
    "summarize_text": summarize_text,
    "translate_text": translate_text,
    "analyze_sentiment": analyze_sentiment,
    "extract_keywords": extract_keywords,
    "generate_code": generate_code,
    "explain_code": explain_code,
    "refactor_code": refactor_code,
    "detect_language": detect_language,
    "embed_text": embed_text,
}
