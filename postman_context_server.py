"""
Postman Context Agent - MCP Server
====================================
MCP Server untuk membaca Postman Collection secara dinamis.
Mendukung Postman Cloud API (online) dengan fallback ke cache lokal (offline).

Dirancang untuk Suitmedia - sebagai CTX 4 dalam Multi-Agent RAG Workflow.

Usage:
    python postman_context_server.py
    python postman_context_server.py --api-key YOUR_POSTMAN_API_KEY
    python postman_context_server.py --collection-json /path/to/collection.json

Environment Variables (alternatif argumen):
    POSTMAN_API_KEY         : API Key dari Postman
    POSTMAN_WORKSPACE_ID    : (opsional) filter workspace tertentu
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
from fastmcp import FastMCP

# ──────────────────────────────────────────────
# Argumen & Konfigurasi
# ──────────────────────────────────────────────

def resolve_config() -> dict:
    parser = argparse.ArgumentParser(
        description="Postman Context MCP Server",
        add_help=False
    )
    parser.add_argument("--api-key",         type=str, default=None)
    parser.add_argument("--workspace-id",    type=str, default=None)
    parser.add_argument("--collection-json", type=str, default=None)
    parser.add_argument("--cache-dir",       type=str, default="./postman_cache")
    args, _ = parser.parse_known_args()

    return {
        "api_key":         args.api_key         or os.environ.get("POSTMAN_API_KEY", ""),
        "workspace_id":    args.workspace_id     or os.environ.get("POSTMAN_WORKSPACE_ID", ""),
        "collection_json": args.collection_json  or os.environ.get("POSTMAN_COLLECTION_JSON", ""),
        "cache_dir":       Path(args.cache_dir),
    }


CONFIG = resolve_config()
CONFIG["cache_dir"].mkdir(parents=True, exist_ok=True)

POSTMAN_BASE_URL = "https://api.getpostman.com"
CACHE_TTL_SECONDS = 3600  # 1 jam

# ──────────────────────────────────────────────
# FastMCP Init
# ──────────────────────────────────────────────

mcp = FastMCP(
    name="PostmanContextAgent",
    instructions=(
        "Saya adalah Context Agent untuk Postman API Collection Suitmedia. "
        "Saya bisa menampilkan daftar collection, endpoint, detail request/response, "
        "environment variables, mencari endpoint, dan generate Retrofit interface Kotlin. "
        "Gunakan saya untuk memahami API contract sebelum menulis kode Android."
    ),
)


# ══════════════════════════════════════════════
# HELPER: Cache Management
# ══════════════════════════════════════════════

def _cache_path(key: str) -> Path:
    safe_key = re.sub(r"[^\w\-]", "_", key)
    return CONFIG["cache_dir"] / f"{safe_key}.json"


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
    path = _cache_path(key)
    try:
        path.write_text(
            json.dumps({"_cached_at": time.time(), "_payload": payload}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[CACHE WARN] Gagal simpan cache '{key}': {e}", file=sys.stderr)


# ══════════════════════════════════════════════
# HELPER: Postman API Client
# ══════════════════════════════════════════════

def _get_headers() -> dict:
    return {
        "X-Api-Key": CONFIG["api_key"],
        "Content-Type": "application/json",
    }


def _api_get(endpoint: str, cache_key: Optional[str] = None) -> tuple[bool, Any]:
    """
    GET ke Postman API dengan caching.
    Returns: (success: bool, data: Any)
    """
    if cache_key:
        cached = _read_cache(cache_key)
        if cached is not None:
            return True, cached

    if not CONFIG["api_key"]:
        return False, "❌ POSTMAN_API_KEY tidak dikonfigurasi. Gunakan --api-key atau set environment variable POSTMAN_API_KEY."

    try:
        url = f"{POSTMAN_BASE_URL}{endpoint}"
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=_get_headers())

        if response.status_code == 401:
            return False, "❌ API Key tidak valid atau sudah expired. Cek kembali POSTMAN_API_KEY Anda."
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
        # Fallback ke cache lama jika ada
        if cache_key:
            old_cache = _cache_path(cache_key)
            if old_cache.exists():
                try:
                    data = json.loads(old_cache.read_text())
                    payload = data.get("_payload")
                    if payload:
                        print("[CACHE] Menggunakan cache lama (offline mode)", file=sys.stderr)
                        return True, payload
                except Exception:
                    pass
        return False, "❌ Tidak bisa terhubung ke Postman API. Periksa koneksi internet Anda."
    except Exception as e:
        return False, f"❌ Error tidak terduga: {e}"


# ══════════════════════════════════════════════
# HELPER: Collection JSON Parser
# ══════════════════════════════════════════════

def _load_local_collection(json_path: str) -> tuple[bool, Any]:
    """Load collection dari file JSON lokal (export Postman)."""
    path = Path(json_path)
    if not path.exists():
        return False, f"❌ File tidak ditemukan: {json_path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return True, data
    except json.JSONDecodeError as e:
        return False, f"❌ File JSON tidak valid: {e}"


def _extract_items_recursive(items: list, prefix: str = "") -> list[dict]:
    """
    Rekursif ekstrak semua request dari nested folder Postman.
    """
    results = []
    for item in items:
        name = item.get("name", "Unknown")
        full_name = f"{prefix}/{name}" if prefix else name

        # Jika ini folder (punya sub-items)
        if "item" in item:
            results.extend(_extract_items_recursive(item["item"], full_name))
        # Jika ini request
        elif "request" in item:
            req = item["request"]
            method = req.get("method", "GET")
            url_obj = req.get("url", {})

            # Handle URL bisa string atau object
            if isinstance(url_obj, str):
                url = url_obj
            else:
                raw = url_obj.get("raw", "")
                url = raw

            results.append({
                "name":        name,
                "folder_path": full_name,
                "method":      method.upper(),
                "url":         url,
                "description": req.get("description", ""),
                "_raw":        item,
            })
    return results


def _get_body_schema(request_raw: dict) -> dict:
    """Ekstrak body schema dari raw request item."""
    req = request_raw.get("request", {})
    body = req.get("body", {})
    mode = body.get("mode", "")
    schema = {"mode": mode, "data": None}

    if mode == "raw":
        raw_content = body.get("raw", "")
        try:
            schema["data"] = json.loads(raw_content)
        except Exception:
            schema["data"] = raw_content
    elif mode == "urlencoded":
        schema["data"] = {
            item["key"]: item.get("value", "")
            for item in body.get("urlencoded", [])
        }
    elif mode == "formdata":
        schema["data"] = {
            item["key"]: item.get("value", "")
            for item in body.get("formdata", [])
        }

    return schema


def _get_response_examples(request_raw: dict) -> list[dict]:
    """Ekstrak contoh response dari request item."""
    responses = []
    for resp in request_raw.get("response", []):
        status = resp.get("code", 0)
        name   = resp.get("name", f"Response {status}")
        body   = resp.get("body", "")
        try:
            body_parsed = json.loads(body)
        except Exception:
            body_parsed = body

        responses.append({
            "name":   name,
            "status": status,
            "body":   body_parsed,
        })
    return responses


# ══════════════════════════════════════════════
# HELPER: Kotlin Code Generator
# ══════════════════════════════════════════════

def _to_camel_case(s: str) -> str:
    parts = re.split(r"[-_\s/]", s)
    return parts[0].lower() + "".join(p.title() for p in parts[1:])


def _to_pascal_case(s: str) -> str:
    parts = re.split(r"[-_\s/]", s)
    return "".join(p.title() for p in parts)


def _json_to_kotlin_data_class(obj: Any, class_name: str, indent: int = 0) -> list[str]:
    """Generate Kotlin data class dari JSON object."""
    lines = []
    pad = "    " * indent

    if not isinstance(obj, dict):
        return [f"{pad}// Cannot generate data class from non-object type"]

    lines.append(f"{pad}data class {class_name}(")
    nested_classes = []

    for i, (key, value) in enumerate(obj.items()):
        comma = "" if i == len(obj) - 1 else ","
        field_name = _to_camel_case(key)
        annotation = f'    @SerializedName("{key}") ' if key != field_name else "    "

        if value is None:
            lines.append(f'{pad}{annotation}val {field_name}: Any?{comma}')
        elif isinstance(value, bool):
            lines.append(f'{pad}{annotation}val {field_name}: Boolean{comma}')
        elif isinstance(value, int):
            lines.append(f'{pad}{annotation}val {field_name}: Int{comma}')
        elif isinstance(value, float):
            lines.append(f'{pad}{annotation}val {field_name}: Double{comma}')
        elif isinstance(value, str):
            lines.append(f'{pad}{annotation}val {field_name}: String{comma}')
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                nested_name = _to_pascal_case(key)
                lines.append(f'{pad}{annotation}val {field_name}: List<{nested_name}>{comma}')
                nested_classes.extend(_json_to_kotlin_data_class(value[0], nested_name, indent))
            else:
                lines.append(f'{pad}{annotation}val {field_name}: List<Any?>{comma}')
        elif isinstance(value, dict):
            nested_name = _to_pascal_case(key)
            lines.append(f'{pad}{annotation}val {field_name}: {nested_name}{comma}')
            nested_classes.extend(_json_to_kotlin_data_class(value, nested_name, indent))
        else:
            lines.append(f'{pad}{annotation}val {field_name}: Any?{comma}')

    lines.append(f"{pad})")
    lines.extend(nested_classes)
    return lines


def _extract_path_params(url: str) -> list[str]:
    return re.findall(r"\{([^}]+)\}", url)


def _clean_url_for_retrofit(url: str) -> str:
    """Bersihkan URL Postman menjadi Retrofit path."""
    # Hapus base URL / environment variable
    url = re.sub(r"^\{\{[^}]+\}\}", "", url)
    url = re.sub(r"^https?://[^/]+", "", url)
    # Bersihkan query string
    url = url.split("?")[0]
    # Retrofit pakai {param} bukan {{param}}
    url = re.sub(r"\{\{([^}]+)\}\}", r"{\1}", url)
    return url.strip("/")


# ══════════════════════════════════════════════
# MCP TOOLS
# ══════════════════════════════════════════════

@mcp.tool()
def list_collections() -> str:
    """
    Menampilkan semua Postman Collection yang tersedia.
    Menggunakan Postman Cloud API jika API Key tersedia,
    atau membaca dari file JSON lokal jika dikonfigurasi.

    Returns:
        Daftar collection beserta ID dan informasi dasarnya.
    """
    # Mode 1: Local JSON file
    if CONFIG["collection_json"]:
        ok, data = _load_local_collection(CONFIG["collection_json"])
        if not ok:
            return data
        col_info = data.get("info", {})
        items    = data.get("item", [])
        all_reqs = _extract_items_recursive(items)
        return (
            f"📦 COLLECTION (Local JSON)\n"
            f"   Nama    : {col_info.get('name', 'Unknown')}\n"
            f"   Schema  : {col_info.get('schema', 'N/A')}\n"
            f"   Total Request: {len(all_reqs)}\n\n"
            f"💡 Tip: Gunakan get_endpoints() untuk melihat detail endpoint."
        )

    # Mode 2: Postman Cloud API
    workspace_filter = f"?workspace={CONFIG['workspace_id']}" if CONFIG["workspace_id"] else ""
    ok, data = _api_get(f"/collections{workspace_filter}", cache_key="collections_list")
    if not ok:
        return data

    collections = data.get("collections", [])
    if not collections:
        return "⚠️ Tidak ada collection ditemukan di workspace Anda."

    lines = [
        f"📦 POSTMAN COLLECTIONS",
        f"   Total: {len(collections)} collection\n",
    ]
    for col in collections:
        lines.append(
            f"  • 📁 {col.get('name', 'Unknown')}\n"
            f"       ID  : {col.get('uid', col.get('id', 'N/A'))}\n"
            f"       Owner: {col.get('owner', 'N/A')}\n"
        )

    lines.append("\n💡 Tip: Salin ID collection lalu gunakan get_endpoints(collection_id) untuk melihat semua endpoint.")
    return "\n".join(lines)


@mcp.tool()
def get_endpoints(collection_id: str) -> str:
    """
    Menampilkan semua endpoint dalam satu Postman Collection.

    Args:
        collection_id: ID atau UID collection dari list_collections().
                       Jika menggunakan local JSON, isi dengan "local".

    Returns:
        Daftar endpoint dikelompokkan per folder/fitur, beserta method dan URL.
    """
    # Mode Local JSON
    if CONFIG["collection_json"] or collection_id.lower() == "local":
        json_path = CONFIG["collection_json"]
        if not json_path:
            return "❌ Tidak ada file JSON lokal yang dikonfigurasi."
        ok, data = _load_local_collection(json_path)
        if not ok:
            return data
        items    = data.get("item", [])
        all_reqs = _extract_items_recursive(items)
        col_name = data.get("info", {}).get("name", "Local Collection")
    else:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return data
        collection = data.get("collection", {})
        items      = collection.get("item", [])
        all_reqs   = _extract_items_recursive(items)
        col_name   = collection.get("info", {}).get("name", "Unknown")

    if not all_reqs:
        return f"⚠️ Tidak ada endpoint ditemukan di collection '{col_name}'."

    # Kelompokkan per folder
    by_folder: dict[str, list] = {}
    for req in all_reqs:
        parts  = req["folder_path"].split("/")
        folder = parts[0] if len(parts) > 1 else "📄 Root"
        by_folder.setdefault(folder, []).append(req)

    method_icons = {
        "GET": "🟢", "POST": "🟡", "PUT": "🔵",
        "PATCH": "🟠", "DELETE": "🔴", "HEAD": "⚪",
    }

    lines = [
        f"📦 COLLECTION: {col_name}",
        f"   Total endpoint: {len(all_reqs)}\n",
    ]

    for folder, reqs in by_folder.items():
        lines.append(f"📁 {folder} ({len(reqs)} endpoint):")
        for req in reqs:
            icon = method_icons.get(req["method"], "⚫")
            # Bersihkan URL untuk tampilan
            url_display = req["url"]
            url_display = re.sub(r"^\{\{[^}]+\}\}", "{{baseUrl}}", url_display)
            lines.append(f"   {icon} [{req['method']:6}] {req['name']}")
            lines.append(f"          {url_display}")
        lines.append("")

    lines.append("💡 Tip: Gunakan get_request_detail(collection_id, endpoint_name) untuk detail lengkap.")
    return "\n".join(lines)


@mcp.tool()
def get_request_detail(collection_id: str, endpoint_name: str) -> str:
    """
    Menampilkan detail lengkap sebuah endpoint: method, URL, headers, body, path params.

    Args:
        collection_id:  ID collection atau "local" untuk file JSON lokal.
        endpoint_name:  Nama endpoint (bisa sebagian, case-insensitive).

    Returns:
        Detail request lengkap termasuk headers, body schema, dan path parameters.
    """
    # Load data
    if CONFIG["collection_json"] or collection_id.lower() == "local":
        ok, data = _load_local_collection(CONFIG["collection_json"] or "")
        if not ok:
            return data
        items = data.get("item", [])
    else:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return data
        items = data.get("collection", {}).get("item", [])

    all_reqs = _extract_items_recursive(items)

    # Cari endpoint (fuzzy match)
    query   = endpoint_name.lower()
    matches = [r for r in all_reqs if query in r["name"].lower() or query in r["url"].lower()]

    if not matches:
        available = ", ".join(r["name"] for r in all_reqs[:10])
        return (
            f"❌ Endpoint '{endpoint_name}' tidak ditemukan.\n"
            f"   Tersedia (10 pertama): {available}\n"
            f"   Gunakan search_endpoint() untuk pencarian lebih akurat."
        )

    if len(matches) > 5:
        names = "\n".join(f"   • {m['name']}" for m in matches[:10])
        return f"⚠️ Ditemukan {len(matches)} hasil untuk '{endpoint_name}':\n{names}\n\nMohon perjelas nama endpoint."

    output_parts = []
    for match in matches:
        raw  = match["_raw"]
        req  = raw.get("request", {})
        url_obj = req.get("url", {})

        # URL & path params
        url_raw     = url_obj.get("raw", match["url"]) if isinstance(url_obj, dict) else match["url"]
        path_params = _extract_path_params(url_raw)
        query_params = []
        if isinstance(url_obj, dict):
            query_params = [
                f"{q.get('key')}={q.get('value', '')}"
                for q in url_obj.get("query", [])
                if not q.get("disabled", False)
            ]

        # Headers
        headers = {
            h.get("key"): h.get("value")
            for h in req.get("header", [])
            if not h.get("disabled", False)
        }

        # Body
        body_schema = _get_body_schema(raw)

        lines = [
            f"{'═' * 60}",
            f"🔌 ENDPOINT: {match['name']}",
            f"{'─' * 60}",
            f"📍 Method      : {match['method']}",
            f"🌐 URL         : {url_raw}",
            f"📁 Folder      : {match['folder_path']}",
        ]

        if match.get("description"):
            lines.append(f"📝 Description : {match['description'][:200]}")

        if path_params:
            lines.append(f"\n🔑 Path Params  :")
            for p in path_params:
                lines.append(f"   • {{{p}}}")

        if query_params:
            lines.append(f"\n🔍 Query Params :")
            for q in query_params:
                lines.append(f"   • {q}")

        if headers:
            lines.append(f"\n📋 Headers      :")
            for k, v in headers.items():
                lines.append(f"   • {k}: {v}")

        if body_schema["data"] is not None:
            lines.append(f"\n📦 Body ({body_schema['mode']}):")
            body_str = json.dumps(body_schema["data"], indent=4, ensure_ascii=False)
            lines.append(body_str)

        output_parts.append("\n".join(lines))

    return "\n\n".join(output_parts)


@mcp.tool()
def get_response_example(collection_id: str, endpoint_name: str) -> str:
    """
    Menampilkan contoh response (success & error) dari sebuah endpoint.

    Args:
        collection_id:  ID collection atau "local".
        endpoint_name:  Nama endpoint yang dicari.

    Returns:
        Contoh response JSON beserta status code.
    """
    if CONFIG["collection_json"] or collection_id.lower() == "local":
        ok, data = _load_local_collection(CONFIG["collection_json"] or "")
        if not ok:
            return data
        items = data.get("item", [])
    else:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return data
        items = data.get("collection", {}).get("item", [])

    all_reqs = _extract_items_recursive(items)
    query    = endpoint_name.lower()
    matches  = [r for r in all_reqs if query in r["name"].lower()]

    if not matches:
        return f"❌ Endpoint '{endpoint_name}' tidak ditemukan."

    match    = matches[0]
    examples = _get_response_examples(match["_raw"])

    if not examples:
        return (
            f"⚠️ Endpoint '{match['name']}' tidak memiliki contoh response.\n"
            f"   Tambahkan 'Example' di Postman untuk endpoint ini."
        )

    status_icons = {2: "✅", 4: "❌", 5: "💥"}
    lines = [f"📨 RESPONSE EXAMPLES: {match['name']}\n"]

    for ex in examples:
        status    = ex["status"]
        icon      = status_icons.get(status // 100, "❓")
        body_str  = json.dumps(ex["body"], indent=4, ensure_ascii=False) if isinstance(ex["body"], (dict, list)) else str(ex["body"])
        lines.extend([
            f"{'─' * 50}",
            f"{icon} {ex['name']} (HTTP {status})",
            f"{'─' * 50}",
            body_str,
            "",
        ])

    return "\n".join(lines)


@mcp.tool()
def search_endpoint(query: str, collection_id: Optional[str] = None) -> str:
    """
    Mencari endpoint berdasarkan nama, URL, atau method di semua atau satu collection.

    Args:
        query:         Kata kunci pencarian (nama endpoint, path URL, atau HTTP method).
        collection_id: (Opsional) ID collection spesifik. Jika None, cari di semua collection.

    Returns:
        Daftar endpoint yang cocok dengan pencarian.
    """
    all_reqs = []

    # Load dari local JSON
    if CONFIG["collection_json"]:
        ok, data = _load_local_collection(CONFIG["collection_json"])
        if ok:
            col_name = data.get("info", {}).get("name", "Local")
            items    = data.get("item", [])
            reqs     = _extract_items_recursive(items)
            for r in reqs:
                r["_collection"] = col_name
            all_reqs.extend(reqs)

    # Load dari Postman API
    elif CONFIG["api_key"]:
        if collection_id:
            col_ids = [collection_id]
        else:
            ok, data = _api_get("/collections", cache_key="collections_list")
            if not ok:
                return data
            col_ids = [c.get("uid", c.get("id")) for c in data.get("collections", [])]

        for cid in col_ids[:5]:  # Batasi 5 collection untuk performa
            ok, data = _api_get(f"/collections/{cid}", cache_key=f"collection_{cid}")
            if not ok:
                continue
            col = data.get("collection", {})
            col_name = col.get("info", {}).get("name", cid)
            reqs     = _extract_items_recursive(col.get("item", []))
            for r in reqs:
                r["_collection"] = col_name
            all_reqs.extend(reqs)
    else:
        return "❌ Tidak ada sumber data. Konfigurasi POSTMAN_API_KEY atau --collection-json."

    # Filter
    q       = query.lower()
    matches = [
        r for r in all_reqs
        if q in r["name"].lower()
        or q in r["url"].lower()
        or q in r["method"].lower()
        or q in r["folder_path"].lower()
    ]

    if not matches:
        return f"🔍 Tidak ada endpoint yang cocok dengan '{query}'."

    method_icons = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}
    lines = [
        f"🔍 Hasil pencarian: '{query}'",
        f"   Ditemukan: {len(matches)} endpoint\n",
    ]

    for r in matches[:20]:
        icon = method_icons.get(r["method"], "⚫")
        lines.append(f"  {icon} [{r['method']:6}] {r['name']}")
        lines.append(f"         Collection: {r.get('_collection', 'N/A')}")
        lines.append(f"         Path      : {r['folder_path']}")
        url_display = re.sub(r"^\{\{[^}]+\}\}", "{{baseUrl}}", r["url"])
        lines.append(f"         URL       : {url_display}\n")

    if len(matches) > 20:
        lines.append(f"   ... dan {len(matches) - 20} hasil lainnya. Perjelas query pencarian.")

    return "\n".join(lines)


@mcp.tool()
def get_environment_variables(environment_id: Optional[str] = None) -> str:
    """
    Menampilkan environment variables Postman (base URL, token, dll).
    Berguna untuk AI mengetahui konfigurasi API seperti base URL dan auth token.

    Args:
        environment_id: ID environment spesifik. Jika None, tampilkan semua environment.

    Returns:
        Daftar environment variables (nilai sensitif disensor).
    """
    if not CONFIG["api_key"]:
        # Coba baca dari collection local jika ada variable
        if CONFIG["collection_json"]:
            ok, data = _load_local_collection(CONFIG["collection_json"])
            if ok:
                variables = data.get("variable", [])
                if variables:
                    lines = ["🌐 COLLECTION VARIABLES (Local):\n"]
                    for v in variables:
                        key   = v.get("key", "")
                        value = v.get("value", "")
                        # Sensor nilai sensitif
                        if any(s in key.lower() for s in ["token", "secret", "password", "key", "auth"]):
                            value = "***HIDDEN***"
                        lines.append(f"   • {key} = {value}")
                    return "\n".join(lines)
        return "❌ POSTMAN_API_KEY diperlukan untuk mengakses environment variables cloud."

    if environment_id:
        ok, data = _api_get(f"/environments/{environment_id}", cache_key=f"env_{environment_id}")
        if not ok:
            return data

        env    = data.get("environment", {})
        values = env.get("values", [])
        lines  = [f"🌐 ENVIRONMENT: {env.get('name', 'Unknown')}\n"]
        for v in values:
            key   = v.get("key", "")
            value = v.get("value", "") if v.get("enabled", True) else "(disabled)"
            if any(s in key.lower() for s in ["token", "secret", "password", "key", "auth"]):
                value = "***HIDDEN***"
            lines.append(f"   • {key} = {value}")
        return "\n".join(lines)

    else:
        ok, data = _api_get("/environments", cache_key="environments_list")
        if not ok:
            return data

        envs = data.get("environments", [])
        if not envs:
            return "⚠️ Tidak ada environment ditemukan."

        lines = [f"🌐 ENVIRONMENTS ({len(envs)} tersedia):\n"]
        for env in envs:
            lines.append(f"   • {env.get('name', 'Unknown')} — ID: {env.get('uid', env.get('id', 'N/A'))}")
        lines.append("\n💡 Tip: Gunakan get_environment_variables(environment_id) untuk detail.")
        return "\n".join(lines)


@mcp.tool()
def generate_retrofit_interface(
    collection_id: str,
    endpoint_name: str,
    package_name: str = "com.suitmedia.data.remote.api"
) -> str:
    """
    Generate kode Kotlin Retrofit interface + Request/Response data class
    secara otomatis dari endpoint Postman.

    Args:
        collection_id:  ID collection atau "local".
        endpoint_name:  Nama endpoint yang ingin di-generate.
        package_name:   Package name Kotlin (default: com.suitmedia.data.remote.api).

    Returns:
        Kode Kotlin siap pakai: ApiService interface + data class Request & Response.
    """
    # Load data
    if CONFIG["collection_json"] or collection_id.lower() == "local":
        ok, data = _load_local_collection(CONFIG["collection_json"] or "")
        if not ok:
            return data
        items = data.get("item", [])
    else:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return data
        items = data.get("collection", {}).get("item", [])

    all_reqs = _extract_items_recursive(items)
    query    = endpoint_name.lower()
    matches  = [r for r in all_reqs if query in r["name"].lower()]

    if not matches:
        return f"❌ Endpoint '{endpoint_name}' tidak ditemukan."

    match = matches[0]
    raw   = match["_raw"]
    req   = raw.get("request", {})

    # Nama-nama class
    endpoint_pascal = _to_pascal_case(match["name"])
    func_name       = _to_camel_case(match["name"])
    method          = match["method"]

    # URL untuk Retrofit
    url_obj  = req.get("url", {})
    url_raw  = url_obj.get("raw", match["url"]) if isinstance(url_obj, dict) else match["url"]
    ret_path = _clean_url_for_retrofit(url_raw)
    path_params = _extract_path_params(ret_path)

    # Query params
    query_params_list = []
    if isinstance(url_obj, dict):
        query_params_list = [
            q.get("key") for q in url_obj.get("query", [])
            if not q.get("disabled", False) and q.get("key")
        ]

    # Body
    body_schema = _get_body_schema(raw)
    has_body    = body_schema["data"] is not None

    # Response examples
    examples = _get_response_examples(raw)
    success_response = next(
        (ex["body"] for ex in examples if 200 <= ex["status"] < 300 and isinstance(ex["body"], dict)),
        None
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Generate Kotlin code ──
    lines = [
        f"// ═══════════════════════════════════════════════════════════",
        f"// Generated by Postman Context Agent — {now}",
        f"// Endpoint : {match['name']}",
        f"// Source   : {match['folder_path']}",
        f"// ═══════════════════════════════════════════════════════════",
        f"",
        f"package {package_name}",
        f"",
        f"import com.google.gson.annotations.SerializedName",
        f"import retrofit2.Response",
        f"import retrofit2.http.*",
        f"",
    ]

    # ── Request Data Class ──
    if has_body and isinstance(body_schema["data"], dict):
        lines.append(f"// ── Request Body ──────────────────────────────────────────")
        lines.extend(_json_to_kotlin_data_class(body_schema["data"], f"{endpoint_pascal}Request"))
        lines.append("")

    # ── Response Data Class ──
    if success_response and isinstance(success_response, dict):
        lines.append(f"// ── Response Body ─────────────────────────────────────────")
        lines.extend(_json_to_kotlin_data_class(success_response, f"{endpoint_pascal}Response"))
        lines.append("")

    # ── Retrofit Interface ──
    lines.append(f"// ── Retrofit API Service ──────────────────────────────────")
    lines.append(f"interface {endpoint_pascal}ApiService {{")
    lines.append(f"")

    # Anotasi method
    lines.append(f'    @{method}("{ret_path}")')

    # Suspend function signature
    params = []
    for p in path_params:
        params.append(f'@Path("{p}") {_to_camel_case(p)}: String')
    for q in query_params_list:
        params.append(f'@Query("{q}") {_to_camel_case(q)}: String? = null')
    if has_body:
        params.append(f"@Body request: {endpoint_pascal}Request")

    param_str = ",\n        ".join(params)
    if params:
        return_type = f"{endpoint_pascal}Response" if success_response else "Any"
        lines.append(f"    suspend fun {func_name}(")
        lines.append(f"        {param_str}")
        lines.append(f"    ): Response<{return_type}>")
    else:
        return_type = f"{endpoint_pascal}Response" if success_response else "Any"
        lines.append(f"    suspend fun {func_name}(): Response<{return_type}>")

    lines.append(f"}}")
    lines.append(f"")
    lines.append(f"// ── Usage in Repository ───────────────────────────────────")
    
    # Pre-process param string di luar f-string untuk menghindari backslash error
    usage_params = []
    for p in params:
        # Ambil nama variabel sebelum titik dua (contoh: '@Path("id") id: String' -> '@Path("id") id')
        param_name_part = p.split(':')[0].strip() 
        if '@Body' in param_name_part:
            usage_params.append('request')
        elif '@Path' in param_name_part or '@Query' in param_name_part:
            # Ambil kata terakhir setelah spasi (contoh: '@Path("id") id' -> 'id')
            param_name = param_name_part.split(' ')[-1]
            usage_params.append(param_name)
        else:
            usage_params.append(param_name_part)
            
    usage_str = ", ".join(usage_params)

    lines.append(f"// val response = apiService.{func_name}({usage_str})")
    lines.append(f"// if (response.isSuccessful) {{ val data = response.body() }}")

    return "\n".join(lines)


@mcp.tool()
def get_collection_summary(collection_id: str) -> str:
    """
    Memberikan ringkasan lengkap sebuah collection: jumlah endpoint per folder,
    methods yang digunakan, dan statistik keseluruhan.
    Berguna untuk AI memahami scope API sebelum generate kode.

    Args:
        collection_id: ID collection atau "local".

    Returns:
        Ringkasan statistik collection.
    """
    if CONFIG["collection_json"] or collection_id.lower() == "local":
        ok, data = _load_local_collection(CONFIG["collection_json"] or "")
        if not ok:
            return data
        col_name = data.get("info", {}).get("name", "Local Collection")
        items    = data.get("item", [])
    else:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return data
        col      = data.get("collection", {})
        col_name = col.get("info", {}).get("name", "Unknown")
        items    = col.get("item", [])

    all_reqs = _extract_items_recursive(items)

    # Statistik
    by_method: dict[str, int] = {}
    by_folder: dict[str, int] = {}
    has_body_count   = 0
    has_example_count = 0

    for req in all_reqs:
        m = req["method"]
        by_method[m] = by_method.get(m, 0) + 1

        folder = req["folder_path"].split("/")[0]
        by_folder[folder] = by_folder.get(folder, 0) + 1

        if _get_body_schema(req["_raw"])["data"] is not None:
            has_body_count += 1
        if _get_response_examples(req["_raw"]):
            has_example_count += 1

    method_icons = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}
    lines = [
        f"📊 COLLECTION SUMMARY: {col_name}",
        f"{'═' * 50}",
        f"",
        f"📈 Total Endpoint   : {len(all_reqs)}",
        f"📝 Punya Body       : {has_body_count}",
        f"💡 Punya Examples   : {has_example_count}",
        f"",
        f"📋 Per HTTP Method:",
    ]
    for method, count in sorted(by_method.items()):
        icon = method_icons.get(method, "⚫")
        bar  = "█" * count
        lines.append(f"   {icon} {method:6} : {count:3} {bar}")

    lines.append(f"\n📁 Per Folder/Fitur:")
    for folder, count in sorted(by_folder.items(), key=lambda x: -x[1]):
        lines.append(f"   • {folder:<30} {count} endpoint")

    lines.append(f"\n💡 Gunakan get_endpoints('{collection_id}') untuk detail per endpoint.")
    return "\n".join(lines)


# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    mode = "Postman Cloud API" if CONFIG["api_key"] else (
        f"Local JSON: {CONFIG['collection_json']}" if CONFIG["collection_json"]
        else "⚠️  TIDAK ADA SUMBER DATA (set --api-key atau --collection-json)"
    )
    print(
        f"[Postman Context Agent] 🚀 Memulai MCP Server...\n"
        f"   Mode        : {mode}\n"
        f"   Workspace   : {CONFIG['workspace_id'] or 'Semua workspace'}\n"
        f"   Cache Dir   : {CONFIG['cache_dir']}\n"
        f"   Cache TTL   : {CACHE_TTL_SECONDS // 60} menit\n"
        f"   Tools       : list_collections, get_endpoints, get_request_detail,\n"
        f"                 get_response_example, search_endpoint,\n"
        f"                 get_environment_variables, generate_retrofit_interface,\n"
        f"                 get_collection_summary\n",
        file=sys.stderr
    )
    mcp.run(transport="stdio")