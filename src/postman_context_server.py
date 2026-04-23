"""
Postman Context Agent - MCP Server
====================================
MCP Server untuk membaca Postman Collection secara dinamis.
Mendukung Postman Cloud API (online) dengan fallback ke cache lokal (offline).

Dirancang untuk Suitmedia - sebagai CTX 4 dalam Multi-Agent RAG Workflow.
Dioptimalkan untuk menerima context dari GitLab Agent dan memberikan API contract
yang relevan dengan fitur yang sedang dikembangkan.

Usage:
    python postman_context_server.py
    python postman_context_server.py --api-key YOUR_POSTMAN_API_KEY
    python postman_context_server.py --collection-json /path/to/collection.json

Environment Variables (alternatif argumen):
    POSTMAN_API_KEY         : API Key dari Postman
    POSTMAN_WORKSPACE_ID    : (opsional) filter workspace tertentu
    POSTMAN_COLLECTION_JSON : path ke file collection JSON lokal
    POSTMAN_CACHE_DIR       : direktori cache lokal (default: ./postman_cache)
"""

import sys
import os
import re
import json
import argparse
import time
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

import httpx
import functools
import traceback
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from fastmcp import FastMCP
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# Dekorator kustom untuk menangkap error pada level tool
def wrap_tool_call(func):
    """
    Menangkap semua exception pada tool dan mengembalikannya sebagai string.
    Hal ini mencegah agen dari crash dan memungkinkan LLM untuk mendiagnosis masalah.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Error executing tool '{func.__name__}': {str(e)}"
            print(f"❌ [Postman Tool Error] {error_msg}", file=sys.stderr)
            return error_msg
    return wrapper

# ──────────────────────────────────────────────
# Konfigurasi
# ──────────────────────────────────────────────

def resolve_config() -> dict:
    """Load .env dan argumen CLI, return konfigurasi."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                value = value.strip().strip('"\'')
                if key not in os.environ:
                    os.environ[key] = value

    parser = argparse.ArgumentParser(description="Postman Context MCP Server", add_help=False)
    parser.add_argument("--api-key",         type=str, default=None)
    parser.add_argument("--workspace-id",    type=str, default=None)
    parser.add_argument("--collection-json", type=str, default=None)
    parser.add_argument("--cache-dir",       type=str, default="./postman_cache")
    args, _ = parser.parse_known_args()

    return {
        "api_key":         (args.api_key or os.environ.get("POSTMAN_API_KEY", "")).strip(),
        "workspace_id":    (args.workspace_id or os.environ.get("POSTMAN_WORKSPACE_ID", "")).strip(),
        "collection_json": (args.collection_json or os.environ.get("POSTMAN_COLLECTION_JSON", "")).strip(),
        "cache_dir":       Path(args.cache_dir),
    }


CONFIG = resolve_config()
CONFIG["cache_dir"].mkdir(parents=True, exist_ok=True)

POSTMAN_BASE_URL  = "https://api.getpostman.com"
CACHE_TTL_SECONDS = 3600  # 1 jam

# ──────────────────────────────────────────────
# FastMCP Init
# ──────────────────────────────────────────────

mcp = FastMCP(
    name="PostmanContextAgent",
    instructions=(
        "Saya adalah Context Agent untuk Postman API Collection Suitmedia. "
        "Saya menyediakan API contract (endpoint, method, request body, response schema) "
        "berdasarkan kebutuhan fitur yang diberikan oleh GitLab Agent. "
        "Gunakan get_api_context_for_feature() sebagai tool utama dengan menyertakan "
        "deskripsi fitur dari GitLab issue."
    ),
)


# ══════════════════════════════════════════════
# HELPER: Cache
# ══════════════════════════════════════════════

def _cache_path(key: str) -> Path:
    return CONFIG["cache_dir"] / f"{re.sub(r'[^\w\-]', '_', key)}.json"

def _read_cache(key: str) -> Optional[Any]:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_cached_at", 0) > CACHE_TTL_SECONDS:
            return None
        return data.get("_payload")
    except Exception:
        return None

def _write_cache(key: str, payload: Any) -> None:
    try:
        _cache_path(key).write_text(
            json.dumps({"_cached_at": time.time(), "_payload": payload}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[CACHE WARN] Gagal simpan cache '{key}': {e}", file=sys.stderr)


# ══════════════════════════════════════════════
# HELPER: Postman API Client
# ══════════════════════════════════════════════

def _get_headers() -> dict:
    return {"X-Api-Key": CONFIG["api_key"], "Content-Type": "application/json"}

def _api_get(endpoint: str, cache_key: Optional[str] = None) -> tuple[bool, Any]:
    """GET ke Postman API dengan caching. Returns: (success, data)."""
    if cache_key:
        cached = _read_cache(cache_key)
        if cached is not None:
            return True, cached

    if not CONFIG["api_key"]:
        return False, "❌ POSTMAN_API_KEY tidak dikonfigurasi."

    try:
        url = f"{POSTMAN_BASE_URL}{endpoint}"
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=_get_headers())

        if response.status_code == 401:
            return False, "❌ API Key tidak valid atau sudah expired."
        if response.status_code == 403:
            return False, "❌ Akses ditolak. Pastikan API Key punya permission yang cukup."
        if response.status_code == 429:
            return False, "⚠️ Rate limit Postman API tercapai. Coba lagi dalam beberapa menit."
        if response.status_code != 200:
            return False, f"❌ Postman API error {response.status_code}: {response.text[:200]}"

        data = response.json()
        if cache_key:
            _write_cache(cache_key, data)
        return True, data

    except httpx.ConnectError:
        # Fallback ke cache lama (offline mode)
        if cache_key:
            old_cache = _cache_path(cache_key)
            if old_cache.exists():
                try:
                    payload = json.loads(old_cache.read_text()).get("_payload")
                    if payload:
                        print("[CACHE] Menggunakan cache lama (offline mode)", file=sys.stderr)
                        return True, payload
                except Exception:
                    pass
        return False, "❌ Tidak bisa terhubung ke Postman API. Periksa koneksi internet."
    except Exception as e:
        return False, f"❌ Error tidak terduga: {e}"


# ══════════════════════════════════════════════
# HELPER: Collection Parser
# ══════════════════════════════════════════════

def _load_local_collection(json_path: str) -> tuple[bool, Any]:
    """Load collection dari file JSON lokal (export Postman)."""
    path = Path(json_path)
    if not path.exists():
        return False, f"❌ File tidak ditemukan: {json_path}"
    try:
        return True, json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"❌ File JSON tidak valid: {e}"


def _extract_items_recursive(items: list, prefix: str = "") -> list[dict]:
    """Rekursif ekstrak semua request dari nested folder Postman."""
    results = []
    for item in items:
        name      = item.get("name", "Unknown")
        full_name = f"{prefix}/{name}" if prefix else name

        if "item" in item:
            results.extend(_extract_items_recursive(item["item"], full_name))
        elif "request" in item:
            req     = item["request"]
            url_obj = req.get("url", {})
            url     = url_obj.get("raw", "") if isinstance(url_obj, dict) else url_obj

            results.append({
                "name":        name,
                "folder_path": full_name,
                "method":      req.get("method", "GET").upper(),
                "url":         url,
                "description": req.get("description", ""),
                "_raw":        item,
            })
    return results


def _get_body_schema(request_raw: dict) -> dict:
    """Ekstrak body schema dari raw request item."""
    body = request_raw.get("request", {}).get("body", {})
    mode = body.get("mode", "")
    data = None

    if mode == "raw":
        try:
            data = json.loads(body.get("raw", ""))
        except Exception:
            data = body.get("raw", "")
    elif mode == "urlencoded":
        data = {i["key"]: i.get("value", "") for i in body.get("urlencoded", [])}
    elif mode == "formdata":
        data = {i["key"]: i.get("value", "") for i in body.get("formdata", [])}

    return {"mode": mode, "data": data}


def _get_response_examples(request_raw: dict) -> list[dict]:
    """Ekstrak contoh response dari request item."""
    examples = []
    for resp in request_raw.get("response", []):
        status = resp.get("code", 0)
        body   = resp.get("body", "")
        try:
            body_parsed = json.loads(body)
        except Exception:
            body_parsed = body
        examples.append({"name": resp.get("name", f"Response {status}"), "status": status, "body": body_parsed})
    return examples


def _load_all_endpoints() -> tuple[bool, list[dict], str]:
    """
    Load semua endpoint dari sumber yang dikonfigurasi.
    Returns: (success, all_requests, collection_name)
    """
    # Mode 1: Local JSON
    if CONFIG["collection_json"]:
        ok, data = _load_local_collection(CONFIG["collection_json"])
        if not ok:
            return False, [], str(data)
        col_name = data.get("info", {}).get("name", "Local Collection")
        items    = data.get("item", [])
        return True, _extract_items_recursive(items), col_name

    # Mode 2: Postman Cloud API
    if not CONFIG["api_key"]:
        return False, [], "❌ Tidak ada sumber data. Konfigurasi POSTMAN_API_KEY atau POSTMAN_COLLECTION_JSON."

    workspace_filter = f"?workspace={CONFIG['workspace_id']}" if CONFIG["workspace_id"] else ""
    ok, data = _api_get(f"/collections{workspace_filter}", cache_key="collections_list")
    if not ok:
        return False, [], str(data)

    all_reqs = []
    col_names = []
    for col in data.get("collections", [])[:10]:  # Batasi 10 collection
        cid  = col.get("uid", col.get("id"))
        name = col.get("name", cid)
        col_names.append(name)
        ok2, col_data = _api_get(f"/collections/{cid}", cache_key=f"collection_{cid}")
        if not ok2:
            continue
        reqs = _extract_items_recursive(col_data.get("collection", {}).get("item", []))
        for r in reqs:
            r["_collection"] = name
        all_reqs.extend(reqs)

    return True, all_reqs, ", ".join(col_names)


# ══════════════════════════════════════════════
# MCP TOOLS
# ══════════════════════════════════════════════

@tool
@mcp.tool()
@wrap_tool_call
def get_api_context_for_feature(
    feature_description: str,
    keywords: Optional[str] = None,
    collection_id: Optional[str] = None,
) -> str:
    """
    [TOOL UTAMA] Mencari dan mengembalikan API contract yang relevan
    untuk sebuah fitur berdasarkan deskripsi dari GitLab issue.

    Tool ini adalah pintu masuk utama yang digunakan oleh orchestrator
    setelah GitLab Agent mengekstrak requirement dari issue.

    Args:
        feature_description: Deskripsi fitur dari GitLab issue
                             (contoh: "Implementasi login dengan JWT token")
        keywords:            (Opsional) Kata kunci tambahan dipisah koma
                             (contoh: "login,auth,token")
        collection_id:       (Opsional) ID collection spesifik untuk Postman Cloud.
                             Kosongi untuk cari di semua collection.

    Returns:
        API contracts yang relevan: endpoint, method, request body,
        response schema, dan path parameters.
    """
    # Kumpulkan semua endpoint
    if collection_id and CONFIG["api_key"]:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return str(data)
        col  = data.get("collection", {})
        reqs = _extract_items_recursive(col.get("item", []))
        col_name = col.get("info", {}).get("name", collection_id)
    else:
        ok, reqs, col_name = _load_all_endpoints()
        if not ok:
            return col_name  # col_name berisi pesan error

    if not reqs:
        return "⚠️ Tidak ada endpoint ditemukan di collection yang dikonfigurasi."

    # Bangun query keywords dari feature_description + keywords tambahan
    base_keywords = re.split(r"[\s,./]+", feature_description.lower())
    if keywords:
        base_keywords += re.split(r"[\s,]+", keywords.lower())

    # Saring: hanya kata yang bermakna (≥3 karakter, bukan stop words)
    stop_words = {"dan", "the", "for", "with", "yang", "dari", "ke", "di", "dengan", "atau", "and", "or", "to"}
    search_terms = [w for w in base_keywords if len(w) >= 3 and w not in stop_words]

    if not search_terms:
        search_terms = [feature_description.lower()]

    # Score tiap endpoint berdasarkan relevansi
    scored: list[tuple[int, dict]] = []
    for req in reqs:
        haystack = " ".join([
            req["name"].lower(),
            req["url"].lower(),
            req["folder_path"].lower(),
            req.get("description", "").lower(),
        ])
        score = sum(1 for term in search_terms if term in haystack)
        if score > 0:
            scored.append((score, req))

    # Urutkan: score tertinggi dulu
    scored.sort(key=lambda x: -x[0])
    top_matches = [r for _, r in scored[:10]]

    if not top_matches:
        return (
            f"🔍 Tidak ada endpoint yang cocok untuk fitur: '{feature_description}'\n"
            f"   Keywords dicari: {', '.join(search_terms)}\n"
            f"   Collection    : {col_name}\n"
            f"   Total endpoint: {len(reqs)}\n\n"
            f"💡 Coba gunakan keywords yang lebih spesifik atau gunakan list_all_endpoints() untuk lihat semua."
        )

    # Format output sebagai API contract yang readable oleh AI
    method_icons = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}
    lines = [
        f"📋 API CONTRACT UNTUK FITUR: {feature_description}",
        f"   Collection: {col_name}",
        f"   Ditemukan : {len(top_matches)} endpoint relevan",
        f"{'═' * 65}",
    ]

    for req in top_matches:
        raw    = req["_raw"]
        req_   = raw.get("request", {})
        url_obj = req_.get("url", {})

        # URL & params
        url_raw = url_obj.get("raw", req["url"]) if isinstance(url_obj, dict) else req["url"]
        path_params = re.findall(r"\{([^}]+)\}", url_raw)
        query_params = [
            f"{q.get('key')}={q.get('value', '')}"
            for q in (url_obj.get("query", []) if isinstance(url_obj, dict) else [])
            if not q.get("disabled", False)
        ]

        # Headers (non-auth)
        headers = {
            h.get("key"): h.get("value")
            for h in req_.get("header", [])
            if not h.get("disabled", False) and h.get("key", "").lower() not in ("authorization",)
        }

        # Body
        body_schema = _get_body_schema(raw)

        # Response examples
        examples = _get_response_examples(raw)
        success_resp = next(
            (ex for ex in examples if 200 <= ex["status"] < 300),
            None
        )

        icon = method_icons.get(req["method"], "⚫")
        lines += [
            f"\n{icon} [{req['method']}] {req['name']}",
            f"   📁 Folder : {req['folder_path']}",
            f"   🌐 URL    : {url_raw}",
        ]

        if req.get("description"):
            lines.append(f"   📝 Desc   : {req['description'][:150]}")

        if path_params:
            lines.append(f"   🔑 Path   : {{{', '.join(path_params)}}}")

        if query_params:
            lines.append(f"   🔍 Query  : {' | '.join(query_params)}")

        if headers:
            lines.append(f"   📋 Headers: {json.dumps(headers, ensure_ascii=False)}")

        if body_schema["data"] is not None:
            body_str = json.dumps(body_schema["data"], indent=6, ensure_ascii=False)
            lines.append(f"   📦 Body ({body_schema['mode']}):\n{body_str}")

        if success_resp:
            resp_str = (
                json.dumps(success_resp["body"], indent=6, ensure_ascii=False)
                if isinstance(success_resp["body"], (dict, list))
                else str(success_resp["body"])
            )
            lines.append(f"   ✅ Response ({success_resp['status']}):\n{resp_str}")

    lines += [
        f"\n{'─' * 65}",
        f"💡 Gunakan get_endpoint_detail(endpoint_name) untuk detail tambahan.",
    ]
    return "\n".join(lines)


@tool
@mcp.tool()
@wrap_tool_call
def list_all_endpoints(folder_filter: Optional[str] = None) -> str:
    """
    Menampilkan semua endpoint yang tersedia dalam collection.
    Berguna untuk eksplorasi awal atau ketika fitur belum jelas endpoint-nya.

    Args:
        folder_filter: (Opsional) Filter hanya tampilkan endpoint dari folder tertentu
                       (contoh: "auth", "user", "payment")

    Returns:
        Daftar semua endpoint dikelompokkan per folder dengan method dan URL.
    """
    ok, reqs, col_name = _load_all_endpoints()
    if not ok:
        return col_name

    if not reqs:
        return "⚠️ Tidak ada endpoint ditemukan."

    # Filter per folder jika diminta
    if folder_filter:
        reqs = [r for r in reqs if folder_filter.lower() in r["folder_path"].lower()]
        if not reqs:
            return f"⚠️ Tidak ada endpoint di folder '{folder_filter}'."

    # Kelompokkan per folder
    by_folder: dict[str, list] = {}
    for req in reqs:
        folder = req["folder_path"].split("/")[0]
        by_folder.setdefault(folder, []).append(req)

    method_icons = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}
    lines = [
        f"📦 COLLECTION: {col_name}",
        f"   Total: {len(reqs)} endpoint | {len(by_folder)} folder\n",
    ]

    for folder, folder_reqs in by_folder.items():
        lines.append(f"📁 {folder} ({len(folder_reqs)} endpoint):")
        for req in folder_reqs:
            icon        = method_icons.get(req["method"], "⚫")
            url_display = re.sub(r"^\{\{[^}]+\}\}", "{{baseUrl}}", req["url"])
            lines.append(f"   {icon} [{req['method']:6}] {req['name']}")
            lines.append(f"          {url_display}")
        lines.append("")

    lines.append("💡 Tip: Gunakan get_api_context_for_feature(feature_description) untuk mencari endpoint relevan.")
    return "\n".join(lines)


@tool
@mcp.tool()
@wrap_tool_call
def get_endpoint_detail(endpoint_name: str, collection_id: Optional[str] = None) -> str:
    """
    Menampilkan detail lengkap sebuah endpoint: method, URL, headers, body, response, path params.

    Args:
        endpoint_name:  Nama endpoint (boleh sebagian, case-insensitive).
        collection_id:  (Opsional) ID collection spesifik untuk Postman Cloud.

    Returns:
        Detail lengkap request/response endpoint yang diminta.
    """
    if collection_id and CONFIG["api_key"]:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return str(data)
        reqs = _extract_items_recursive(data.get("collection", {}).get("item", []))
    else:
        ok, reqs, _ = _load_all_endpoints()
        if not ok:
            return reqs  # type: ignore[return-value]

    query   = endpoint_name.lower()
    matches = [r for r in reqs if query in r["name"].lower() or query in r["url"].lower()]

    if not matches:
        return (
            f"❌ Endpoint '{endpoint_name}' tidak ditemukan.\n"
            f"   Gunakan list_all_endpoints() untuk melihat semua endpoint yang tersedia."
        )
    if len(matches) > 5:
        names = "\n".join(f"   • {m['name']}" for m in matches[:10])
        return f"⚠️ Ditemukan {len(matches)} hasil untuk '{endpoint_name}':\n{names}\n\nSilakan perjelas nama endpoint."

    method_icons = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}
    output_parts = []

    for match in matches:
        raw     = match["_raw"]
        req_    = raw.get("request", {})
        url_obj = req_.get("url", {})

        url_raw     = url_obj.get("raw", match["url"]) if isinstance(url_obj, dict) else match["url"]
        path_params = re.findall(r"\{([^}]+)\}", url_raw)
        query_params = [
            f"{q.get('key')}={q.get('value', '')}"
            for q in (url_obj.get("query", []) if isinstance(url_obj, dict) else [])
            if not q.get("disabled", False)
        ]
        headers     = {h.get("key"): h.get("value") for h in req_.get("header", []) if not h.get("disabled", False)}
        body_schema = _get_body_schema(raw)
        examples    = _get_response_examples(raw)

        icon  = method_icons.get(match["method"], "⚫")
        lines = [
            f"{'═' * 60}",
            f"{icon} ENDPOINT: {match['name']}",
            f"{'─' * 60}",
            f"📍 Method : {match['method']}",
            f"🌐 URL    : {url_raw}",
            f"📁 Folder : {match['folder_path']}",
        ]

        if match.get("description"):
            lines.append(f"📝 Desc   : {match['description'][:300]}")
        if path_params:
            lines.append(f"\n🔑 Path Params : {{{', '.join(path_params)}}}")
        if query_params:
            lines.append(f"🔍 Query Params: {' | '.join(query_params)}")
        if headers:
            lines.append(f"\n📋 Headers:")
            for k, v in headers.items():
                lines.append(f"   • {k}: {v}")
        if body_schema["data"] is not None:
            lines.append(f"\n📦 Body ({body_schema['mode']}):")
            lines.append(json.dumps(body_schema["data"], indent=4, ensure_ascii=False))

        if examples:
            lines.append(f"\n📨 Response Examples:")
            status_icons = {2: "✅", 4: "❌", 5: "💥"}
            for ex in examples:
                icon_r   = status_icons.get(ex["status"] // 100, "❓")
                body_str = (
                    json.dumps(ex["body"], indent=4, ensure_ascii=False)
                    if isinstance(ex["body"], (dict, list)) else str(ex["body"])
                )
                lines += [f"  {icon_r} HTTP {ex['status']} — {ex['name']}", body_str]
        else:
            lines.append("\n⚠️ Tidak ada contoh response di Postman.")

        output_parts.append("\n".join(lines))

    return "\n\n".join(output_parts)


@tool
@mcp.tool()
@wrap_tool_call
def search_endpoint(query: str) -> str:
    """
    Mencari endpoint berdasarkan nama, URL, method, atau folder.
    Gunakan ini jika get_api_context_for_feature() tidak menemukan hasil yang tepat.

    Args:
        query: Kata kunci pencarian (misalnya: "login", "POST", "/users", "auth")

    Returns:
        Daftar endpoint yang cocok.
    """
    ok, reqs, col_name = _load_all_endpoints()
    if not ok:
        return col_name

    q       = query.lower()
    matches = [
        r for r in reqs
        if q in r["name"].lower() or q in r["url"].lower()
        or q in r["method"].lower() or q in r["folder_path"].lower()
    ]

    if not matches:
        return f"🔍 Tidak ada endpoint yang cocok dengan '{query}'."

    method_icons = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}
    lines = [
        f"🔍 Hasil: '{query}' — {len(matches)} endpoint ditemukan di {col_name}\n",
    ]

    for r in matches[:20]:
        icon        = method_icons.get(r["method"], "⚫")
        url_display = re.sub(r"^\{\{[^}]+\}\}", "{{baseUrl}}", r["url"])
        lines.append(f"  {icon} [{r['method']:6}] {r['name']}")
        lines.append(f"         Folder: {r['folder_path']}")
        lines.append(f"         URL   : {url_display}\n")

    if len(matches) > 20:
        lines.append(f"   ... dan {len(matches) - 20} hasil lainnya. Perjelas query.")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 2. Inisialisasi Agen (The API Analyst)
# ──────────────────────────────────────────────

class PostmanAPIAnalysis(BaseModel):
    """Skema hasil analisis API dari Postman Collection."""
    feature_summary: str = Field(description="Ringkasan fitur yang dianalisis.")
    relevant_endpoints: List[Dict[str, Any]] = Field(description="Daftar endpoint yang relevan (method, url, purpose).")
    api_contracts: List[Dict[str, Any]] = Field(description="Detail contract untuk setiap endpoint (headers, body schema, response).")
    missing_endpoints: List[str] = Field(description="Daftar fitur yang tidak ditemukan endpointnya di collection.")
    recommendations: Optional[str] = Field(description="Rekomendasi integrasi atau catatan tambahan.")

@mcp.tool()
def run_postman_analyst_agent(user_query: str) -> PostmanAPIAnalysis:
    """
    Menjalankan agen kompeten yang mengerti API Postman untuk memberikan contract yang tepat.
    """
    from langgraph.checkpoint.memory import MemorySaver

    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL"),
        temperature=0.0,
    )
    
    # Daftar tools yang sudah direfaktor ke standar LangChain
    tools = [
        get_api_context_for_feature,
        list_all_endpoints,
        get_endpoint_detail,
        search_endpoint
    ]
    
    # Instruksi sistem untuk Sang Analis API
    system_instructions = (
        "Anda adalah 'The API Analyst', spesialis dalam mendesain dan mendokumentasikan API contract.\n"
        "Tugas Anda adalah membantu developer menemukan endpoint yang paling sesuai dengan "
        "kebutuhan fitur mereka menggunakan Postman Collections.\n\n"
        "Berikan output yang teknis, mencakup URL, method, body, dan contoh response "
        "yang harus diikuti oleh tim developer."
    )
    
    # Setup Memory
    memory = MemorySaver()
    
    # Buat agen
    agent_executor = create_agent(
        llm, 
        tools, 
        system_prompt=system_instructions, 
        name="PostmanAnalyst",
        checkpointer=memory
    )
    
    print(f"\n📡 [Postman Agent] Analyzing API needs for: '{user_query}'...", file=sys.stderr)
    
    final_output = ""
    
    # Eksekusi dengan streaming
    config = {"configurable": {"thread_id": "postman_session_1"}}
    
    for chunk in agent_executor.stream(
        {"messages": [("human", user_query)]}, 
        config=config,
        stream_mode="updates"
    ):
        for node_name, node_update in chunk.items():
            print(f"📍 [Node: {node_name}] is processing...", file=sys.stderr)
            if "messages" in node_update:
                last_msg = node_update["messages"][-1]
                if hasattr(last_msg, 'content') and last_msg.content:
                    final_output = last_msg.content
                    
    print(f"✅ [Postman Agent] Analysis complete.", file=sys.stderr)
    
    # Konversi output Markdown dari agen ke Structured Output (Pydantic)
    print(f"📝 [Postman Agent] Structuring API analysis...", file=sys.stderr)
    llm_structured = llm.with_structured_output(PostmanAPIAnalysis)
    structured_result = llm_structured.invoke(final_output)
    
    return structured_result

# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    mode = (
        "Postman Cloud API" if CONFIG["api_key"]
        else f"Local JSON: {CONFIG['collection_json']}" if CONFIG["collection_json"]
        else "⚠️  TIDAK ADA SUMBER DATA"
    )
    api_key_preview = (CONFIG["api_key"][:20] + "...") if len(CONFIG["api_key"]) > 20 else "NOT SET"

    print(
        f"[Postman Context Agent] 🚀 Memulai MCP Server...\n"
        f"   Mode        : {mode}\n"
        f"   API Key     : {api_key_preview}\n"
        f"   Workspace   : {CONFIG['workspace_id'] or 'Semua workspace'}\n"
        f"   Cache Dir   : {CONFIG['cache_dir']}\n"
        f"   Cache TTL   : {CACHE_TTL_SECONDS // 60} menit\n"
        f"   Tools       : get_api_context_for_feature [UTAMA]\n"
        f"                 list_all_endpoints\n"
        f"                 get_endpoint_detail\n"
        f"                 search_endpoint\n",
        file=sys.stderr
    )

    if not CONFIG["api_key"] and not CONFIG["collection_json"]:
        print("❌ ERROR: POSTMAN_API_KEY atau POSTMAN_COLLECTION_JSON harus di-set!", file=sys.stderr)
        sys.exit(1)

    mcp.run(transport="stdio")