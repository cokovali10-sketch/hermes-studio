"""Semantic search with TF-IDF-like scoring (stdlib only)."""
import math
import pathlib
import re
from collections import Counter
from typing import Any
# --- константы вынесены FORGE refactor ---
CONST_3 = 3


IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", ".next",
    "venv", ".venv", ".mypy_cache", ".pytest_cache", "vendor",
}
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".scss", ".html", ".json", ".yaml", ".yml", ".md", ".rs", ".go", ".java"}


class SemanticSearch:
    def __init__(self):
        self._index: dict[str, dict] = {}
        self._idf: dict[str, float] = {}
        self._indexed_path: str = ""

    def index_directory(self, path: str) -> int:
        root = pathlib.Path(path)
        if not root.exists():
            return 0

        self._indexed_path = str(root)
        self._index = {}
        doc_count = 0

        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            if any(part in IGNORE_DIRS for part in fpath.relative_to(root).parts):
                continue
            if fpath.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            rel = str(fpath.relative_to(root)).replace("\\", "/")
            chunks = self._chunk_content(content, rel)
            self._index[rel] = {
                "chunks": chunks,
                "full_content": content,
                "lines": content.splitlines(),
            }
            doc_count += 1

        self._compute_idf()
        return doc_count

    def _chunk_content(self, content: str, path: str, chunk_size: int = 40, overlap: int = 10) -> list[dict]:
        lines = content.splitlines()
        chunks = []
        for i in range(0, len(lines), chunk_size - overlap):
            end = min(i + chunk_size, len(lines))
            chunk_text = "\n".join(lines[i:end])
            if chunk_text.strip():
                chunks.append({
                    "text": chunk_text,
                    "start_line": i + 1,
                    "end_line": end,
                    "path": path,
                })
        return chunks

    def _tokenize(self, text: str) -> list[str]:
        return [w.lower() for w in re.findall(r'[a-zA-Z_]\w*', text)]

    def _compute_idf(self):
        doc_freq: Counter = Counter()
        total_docs = len(self._index)

        for path, data in self._index.items():
            seen_terms = set()
            for chunk in data["chunks"]:
                tokens = set(self._tokenize(chunk["text"]))
                for token in tokens:
                    if token not in seen_terms:
                        doc_freq[token] += 1
                        seen_terms.add(token)

        self._idf = {}
        for term, freq in doc_freq.items():
            self._idf[term] = math.log((total_docs + 1) / (freq + 1)) + 1

    def search(self, query: str, path: str = "", max_results: int = 10) -> list[dict[str, Any]]:
        if not self._index:
            if path:
                self.index_directory(path)
            else:
                return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        query_tf = Counter(query_tokens)
        query_vec_len = math.sqrt(sum(v * v for v in query_tf.values())) or 1

        results = []
        for file_path, data in self._index.items():
            if path and not file_path.startswith(path.replace("\\", "/")):
                continue

            for chunk in data["chunks"]:
                chunk_tokens = self._tokenize(chunk["text"])
                chunk_tf = Counter(chunk_tokens)
                chunk_vec_len = math.sqrt(sum(v * v for v in chunk_tf.values())) or 1

                dot_product = 0.0
                for token, q_val in query_tf.items():
                    c_val = chunk_tf.get(token, 0)
                    idf = self._idf.get(token, 1.0)
                    dot_product += q_val * c_val * idf * idf

                score = dot_product / (query_vec_len * chunk_vec_len)

                if score > 0.001:
                    context_lines = data["lines"]
                    start = max(0, chunk["start_line"] - CONST_3)
                    end = min(len(context_lines), chunk["end_line"] + CONST_3)
                    context = "\n".join(
                        f"{i+1:4d} | {context_lines[i]}"
                        for i in range(start, end)
                    )

                    results.append({
                        "file": file_path,
                        "start_line": chunk["start_line"],
                        "end_line": chunk["end_line"],
                        "score": round(score, 4),
                        "chunk": chunk["text"][:500],
                        "context": context,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    def get_indexed_files(self) -> list[str]:
        return list(self._index.keys())

    def get_file_content(self, path: str) -> str | None:
        data = self._index.get(path)
        return data["full_content"] if data else None


semantic_search = SemanticSearch()
