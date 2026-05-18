import re
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

import httpx
import sys 

from fastmcp import FastMCP
from langchain_core.tools import tool

from src.config.settings import settings
from src.models.schemas import PostmanAPIAnalysis
from src.utils.error_handler import wrap_tool_call
from src.utils.llm_factory import create_llm, create_agent_with_memory, execute_agent_and_structure

logger = logging.getLogger("postman_server")

POSTMAN_BASE_URL = "https://api.getpostman.com"

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


def _resolve_config() -> dict:
    parser = argparse.ArgumentParser(description="Postman Context MCP Server", add_help=False)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--workspace-id", type=str, default=None)
    parser.add_argument("--collection-json", type=str, default=None)
    args, _ = parser.parse_known_args()

    return {
        "api_key": (args.api_key or settings.postman_api_key),
        "workspace_id": (args.workspace_id or settings.postman_workspace_id),
        "collection_json": (args.collection_json or settings.postman_collection_json),
        "cache_dir": settings.postman_cache_dir,
    }


CONFIG = _resolve_config()
CONFIG["cache_dir"].mkdir(parents=True, exist_ok=True)


def _cache_path(key: str) -> Path:
    safe_key = re.sub(r'[^\w\-]', '_', key)
    return CONFIG["cache_dir"] / f"{safe_key}.json"


def _read_cache(key: str) -> Optional[Any]:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("_cached_at", 0) > settings.postman_cache_ttl:
            return None
        return data.get("_payload")
    except Exception:
        return None


def _write_cache(key: str, payload: Any) -> None:
    try:
        _cache_path(key).write_text(
            json.dumps({"_cached_at": time.time(), "_payload": payload}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Gagal simpan cache '%s': %s", key, e)


def _get_headers() -> dict:
    return {"X-Api-Key": CONFIG["api_key"], "Content-Type": "application/json"}


def _api_get(endpoint: str, cache_key: Optional[str] = None) -> tuple[bool, Any]:
    if cache_key:
        cached = _read_cache(cache_key)
        if cached is not None:
            return True, cached

    if not CONFIG["api_key"]:
        return False, "POSTMAN_API_KEY tidak dikonfigurasi."

    try:
        url = f"{POSTMAN_BASE_URL}{endpoint}"
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=_get_headers())

        if response.status_code == 401:
            return False, "API Key tidak valid atau sudah expired."
        if response.status_code == 403:
            return False, "Akses ditolak. Pastikan API Key punya permission yang cukup."
        if response.status_code == 429:
            return False, "Rate limit Postman API tercapai. Coba lagi dalam beberapa menit."
        if response.status_code != 200:
            return False, f"Postman API error {response.status_code}: {response.text[:200]}"

        data = response.json()
        if cache_key:
            _write_cache(cache_key, data)
        return True, data

    except httpx.ConnectError:
        if cache_key:
            old_cache = _cache_path(cache_key)
            if old_cache.exists():
                try:
                    payload = json.loads(old_cache.read_text()).get("_payload")
                    if payload:
                        logger.info("Menggunakan cache lama (offline mode)")
                        return True, payload
                except Exception:
                    pass
        return False, "Tidak bisa terhubung ke Postman API. Periksa koneksi internet."
    except Exception as e:
        return False, f"Error tidak terduga: {e}"


def _load_local_collection(json_path: str) -> tuple[bool, Any]:
    path = Path(json_path)
    if not path.exists():
        return False, f"File tidak ditemukan: {json_path}"
    try:
        return True, json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"File JSON tidak valid: {e}"


def _extract_items_recursive(items: list, prefix: str = "") -> list[dict]:
    results = []
    for item in items:
        name = item.get("name", "Unknown")
        full_name = f"{prefix}/{name}" if prefix else name

        if "item" in item:
            results.extend(_extract_items_recursive(item["item"], full_name))
        elif "request" in item:
            req = item["request"]
            url_obj = req.get("url", {})
            url = url_obj.get("raw", "") if isinstance(url_obj, dict) else url_obj

            results.append({
                "name": name,
                "folder_path": full_name,
                "method": req.get("method", "GET").upper(),
                "url": url,
                "description": req.get("description", ""),
                "_raw": item,
            })
    return results


def _get_body_schema(request_raw: dict) -> dict:
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
    examples = []
    for resp in request_raw.get("response", []):
        status = resp.get("code", 0)
        body = resp.get("body", "")
        try:
            body_parsed = json.loads(body)
        except Exception:
            body_parsed = body
        examples.append({"name": resp.get("name", f"Response {status}"), "status": status, "body": body_parsed})
    return examples


def _load_all_endpoints() -> tuple[bool, list[dict], str]:
    if CONFIG["collection_json"]:
        ok, data = _load_local_collection(CONFIG["collection_json"])
        if not ok:
            return False, [], str(data)
        col_name = data.get("info", {}).get("name", "Local Collection")
        items = data.get("item", [])
        return True, _extract_items_recursive(items), col_name

    if not CONFIG["api_key"]:
        return False, [], "Tidak ada sumber data. Konfigurasi POSTMAN_API_KEY atau POSTMAN_COLLECTION_JSON."

    workspace_filter = f"?workspace={CONFIG['workspace_id']}" if CONFIG["workspace_id"] else ""
    ok, data = _api_get(f"/collections{workspace_filter}", cache_key="collections_list")
    if not ok:
        return False, [], str(data)

    all_reqs = []
    col_names = []
    for col in data.get("collections", [])[:10]:
        cid = col.get("uid", col.get("id"))
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


METHOD_ICONS = {"GET": "🟢", "POST": "🟡", "PUT": "🔵", "PATCH": "🟠", "DELETE": "🔴"}


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

    Args:
        feature_description: Deskripsi fitur dari GitLab issue
        keywords: Kata kunci tambahan dipisah koma
        collection_id: ID collection spesifik untuk Postman Cloud
    """
    if collection_id and CONFIG["api_key"]:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return str(data)
        col = data.get("collection", {})
        reqs = _extract_items_recursive(col.get("item", []))
        col_name = col.get("info", {}).get("name", collection_id)
    else:
        ok, reqs, col_name = _load_all_endpoints()
        if not ok:
            return col_name

    if not reqs:
        return "Tidak ada endpoint ditemukan di collection yang dikonfigurasi."

    base_keywords = re.split(r"[\s,./]+", feature_description.lower())
    if keywords:
        base_keywords += re.split(r"[\s,]+", keywords.lower())

    stop_words = {"dan", "the", "for", "with", "yang", "dari", "ke", "di", "dengan", "atau", "and", "or", "to"}
    search_terms = [w for w in base_keywords if len(w) >= 3 and w not in stop_words]

    if not search_terms:
        search_terms = [feature_description.lower()]

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

    scored.sort(key=lambda x: -x[0])
    top_matches = [r for _, r in scored[:10]]

    if not top_matches:
        return (
            f"Tidak ada endpoint yang cocok untuk fitur: '{feature_description}'\n"
            f"Keywords dicari: {', '.join(search_terms)}\n"
            f"Collection: {col_name}\n"
            f"Total endpoint: {len(reqs)}"
        )

    lines = [
        f"API CONTRACT UNTUK FITUR: {feature_description}",
        f"Collection: {col_name}",
        f"Ditemukan: {len(top_matches)} endpoint relevan",
        "=" * 65,
    ]

    for req in top_matches:
        raw = req["_raw"]
        req_ = raw.get("request", {})
        url_obj = req_.get("url", {})

        url_raw = url_obj.get("raw", req["url"]) if isinstance(url_obj, dict) else req["url"]
        path_params = re.findall(r"\{([^}]+)\}", str(url_raw or ""))
        query_params = [
            f"{q.get('key')}={q.get('value', '')}"
            for q in (url_obj.get("query", []) if isinstance(url_obj, dict) else [])
            if not q.get("disabled", False)
        ]

        headers = {
            h.get("key"): h.get("value")
            for h in req_.get("header", [])
            if not h.get("disabled", False) and h.get("key", "").lower() not in ("authorization",)
        }

        body_schema = _get_body_schema(raw)
        examples = _get_response_examples(raw)
        success_resp = next(
            (ex for ex in examples if 200 <= ex["status"] < 300),
            None,
        )

        icon = METHOD_ICONS.get(req["method"], "⚫")
        lines += [
            f"\n{icon} [{req['method']}] {req['name']}",
            f"  Folder: {req['folder_path']}",
            f"  URL: {url_raw}",
        ]

        if req.get("description"):
            lines.append(f"  Desc: {req['description'][:150]}")

        if path_params:
            lines.append(f"  Path: {{{', '.join(path_params)}}}")

        if query_params:
            lines.append(f"  Query: {' | '.join(query_params)}")

        if headers:
            lines.append(f"  Headers: {json.dumps(headers, ensure_ascii=False)}")

        if body_schema["data"] is not None:
            body_str = json.dumps(body_schema["data"], indent=6, ensure_ascii=False)
            lines.append(f"  Body ({body_schema['mode']}):\n{body_str}")

        if success_resp:
            resp_str = (
                json.dumps(success_resp["body"], indent=6, ensure_ascii=False)
                if isinstance(success_resp["body"], (dict, list))
                else str(success_resp["body"])
            )
            lines.append(f"  Response ({success_resp['status']}):\n{resp_str}")

    lines += [
        f"\n{'─' * 65}",
        "Gunakan get_endpoint_detail(endpoint_name) untuk detail tambahan.",
    ]
    return "\n".join(lines)


@tool
@mcp.tool()
@wrap_tool_call
def list_all_endpoints(folder_filter: Optional[str] = None) -> str:
    """
    Menampilkan semua endpoint yang tersedia dalam collection.

    Args:
        folder_filter: Filter hanya tampilkan endpoint dari folder tertentu
    """
    ok, reqs, col_name = _load_all_endpoints()
    if not ok:
        return col_name

    if not reqs:
        return "Tidak ada endpoint ditemukan."

    if folder_filter:
        reqs = [r for r in reqs if folder_filter.lower() in r["folder_path"].lower()]
        if not reqs:
            return f"Tidak ada endpoint di folder '{folder_filter}'."

    by_folder: dict[str, list] = {}
    for req in reqs:
        folder = req["folder_path"].split("/")[0]
        by_folder.setdefault(folder, []).append(req)

    lines = [
        f"COLLECTION: {col_name}",
        f"Total: {len(reqs)} endpoint | {len(by_folder)} folder\n",
    ]

    for folder, folder_reqs in by_folder.items():
        lines.append(f"[{folder}] ({len(folder_reqs)} endpoint):")
        for req in folder_reqs:
            icon = METHOD_ICONS.get(req["method"], "⚫")
            url_display = re.sub(r"^\{\{[^}]+\}\}", "{{baseUrl}}", req["url"])
            lines.append(f"  {icon} [{req['method']:6}] {req['name']}")
            lines.append(f"          {url_display}")
        lines.append("")

    return "\n".join(lines)


@tool
@mcp.tool()
@wrap_tool_call
def get_endpoint_detail(endpoint_name: str, collection_id: Optional[str] = None) -> str:
    """
    Menampilkan detail lengkap sebuah endpoint.

    Args:
        endpoint_name: Nama endpoint (boleh sebagian, case-insensitive)
        collection_id: ID collection spesifik untuk Postman Cloud
    """
    if collection_id and CONFIG["api_key"]:
        ok, data = _api_get(f"/collections/{collection_id}", cache_key=f"collection_{collection_id}")
        if not ok:
            return str(data)
        reqs = _extract_items_recursive(data.get("collection", {}).get("item", []))
    else:
        ok, reqs, _ = _load_all_endpoints()
        if not ok:
            return "Gagal memuat endpoints."

    query = endpoint_name.lower()
    matches = [r for r in reqs if query in r["name"].lower() or query in r["url"].lower()]

    if not matches:
        return f"Endpoint '{endpoint_name}' tidak ditemukan. Gunakan list_all_endpoints() untuk melihat semua."
    if len(matches) > 5:
        names = "\n".join(f"  - {m['name']}" for m in matches[:10])
        return f"Ditemukan {len(matches)} hasil untuk '{endpoint_name}':\n{names}\n\nSilakan perjelas nama endpoint."

    output_parts = []
    for match in matches:
        raw = match["_raw"]
        req_ = raw.get("request", {})
        url_obj = req_.get("url", {})

        url_raw = url_obj.get("raw", match["url"]) if isinstance(url_obj, dict) else match["url"]
        path_params = re.findall(r"\{([^}]+)\}", str(url_raw or ""))
        query_params = [
            f"{q.get('key')}={q.get('value', '')}"
            for q in (url_obj.get("query", []) if isinstance(url_obj, dict) else [])
            if not q.get("disabled", False)
        ]
        headers = {h.get("key"): h.get("value") for h in req_.get("header", []) if not h.get("disabled", False)}
        body_schema = _get_body_schema(raw)
        examples = _get_response_examples(raw)

        icon = METHOD_ICONS.get(match["method"], "⚫")
        lines = [
            "=" * 60,
            f"{icon} ENDPOINT: {match['name']}",
            "-" * 60,
            f"Method: {match['method']}",
            f"URL: {url_raw}",
            f"Folder: {match['folder_path']}",
        ]

        if match.get("description"):
            lines.append(f"Desc: {match['description'][:300]}")
        if path_params:
            lines.append(f"\nPath Params: {{{', '.join(path_params)}}}")
        if query_params:
            lines.append(f"Query Params: {' | '.join(query_params)}")
        if headers:
            lines.append(f"\nHeaders:")
            for k, v in headers.items():
                lines.append(f"  - {k}: {v}")
        if body_schema["data"] is not None:
            lines.append(f"\nBody ({body_schema['mode']}):")
            lines.append(json.dumps(body_schema["data"], indent=4, ensure_ascii=False))

        if examples:
            lines.append(f"\nResponse Examples:")
            status_icons = {2: "OK", 4: "ERR", 5: "FAIL"}
            for ex in examples:
                body_str = (
                    json.dumps(ex["body"], indent=4, ensure_ascii=False)
                    if isinstance(ex["body"], (dict, list)) else str(ex["body"])
                )
                lines += [f"  HTTP {ex['status']} - {ex['name']}", body_str]
        else:
            lines.append("\nTidak ada contoh response di Postman.")

        output_parts.append("\n".join(lines))

    return "\n\n".join(output_parts)


@tool
@mcp.tool()
@wrap_tool_call
def search_endpoint(query: str) -> str:
    """
    Mencari endpoint berdasarkan nama, URL, method, atau folder.

    Args:
        query: Kata kunci pencarian
    """
    ok, reqs, col_name = _load_all_endpoints()
    if not ok:
        return col_name

    q = query.lower()
    matches = [
        r for r in reqs
        if q in r["name"].lower() or q in r["url"].lower()
        or q in r["method"].lower() or q in r["folder_path"].lower()
    ]

    if not matches:
        return f"Tidak ada endpoint yang cocok dengan '{query}'."

    lines = [
        f"Hasil: '{query}' - {len(matches)} endpoint ditemukan di {col_name}\n",
    ]

    for r in matches[:20]:
        icon = METHOD_ICONS.get(r["method"], "⚫")
        url_display = re.sub(r"^\{\{[^}]+\}\}", "{{baseUrl}}", r["url"])
        lines.append(f"  {icon} [{r['method']:6}] {r['name']}")
        lines.append(f"         Folder: {r['folder_path']}")
        lines.append(f"         URL: {url_display}\n")

    if len(matches) > 20:
        lines.append(f"  ... dan {len(matches) - 20} hasil lainnya. Perjelas query.")

    return "\n".join(lines)


SYSTEM_PROMPT_POSTMAN = (
    "Anda adalah 'The API Analyst', spesialis dalam mendesain dan mendokumentasikan API contract.\n"
    "Tugas Anda adalah membantu developer menemukan endpoint yang paling sesuai dengan "
    "kebutuhan fitur mereka menggunakan Postman Collections.\n\n"
    "Berikan output yang teknis, mencakup URL, method, body, dan contoh response "
    "yang harus diikuti oleh tim developer."
)


@mcp.tool()
def run_postman_analyst_agent(user_query: str) -> PostmanAPIAnalysis:
    """
    Menjalankan agen kompeten yang mengerti API Postman untuk memberikan contract yang tepat.
    """
    llm = create_llm(temperature=0.0)

    tools = [
        get_api_context_for_feature,
        list_all_endpoints,
        get_endpoint_detail,
        search_endpoint,
    ]

    agent_executor, agent_config = create_agent_with_memory(
        llm=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT_POSTMAN,
        agent_name="PostmanAnalyst",
    )

    return execute_agent_and_structure(
        agent_executor=agent_executor,
        agent_config=agent_config,
        user_input=user_query,
        llm=llm,
        output_schema=PostmanAPIAnalysis,
        agent_label="PostmanAnalyst",
    )


if __name__ == "__main__":
    mode = (
        "Postman Cloud API" if CONFIG["api_key"]
        else f"Local JSON: {CONFIG['collection_json']}" if CONFIG["collection_json"]
        else "TIDAK ADA SUMBER DATA"
    )
    logger.info("Starting MCP Server | Mode: %s", mode)

    if not CONFIG["api_key"] and not CONFIG["collection_json"]:
        logger.error("POSTMAN_API_KEY atau POSTMAN_COLLECTION_JSON harus di-set!")
        sys.exit(1)

    mcp.run(transport="stdio")