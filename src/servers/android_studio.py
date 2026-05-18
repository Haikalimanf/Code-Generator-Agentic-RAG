import re
import argparse
import logging
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from langchain_core.tools import tool

from src.config.settings import settings
from src.models.schemas import AndroidArchitectureAnalysis
from src.utils.error_handler import wrap_tool_call
from src.utils.llm_factory import create_llm, create_agent_with_memory, execute_agent_and_structure

logger = logging.getLogger("android_server")


def _resolve_root_directory() -> Path:
    parser = argparse.ArgumentParser(description="Android Studio Context MCP Server", add_help=False)
    parser.add_argument("--root", type=str, default=None)
    args, _ = parser.parse_known_args()

    if args.root:
        root = Path(args.root).resolve()
    elif settings.android_project_root:
        root = Path(settings.android_project_root).resolve()
    else:
        root = Path.cwd().resolve()

    if not root.exists():
        logger.error("Root directory tidak ditemukan: %s", root)
        raise SystemExit(1)
    return root


ROOT_DIR = _resolve_root_directory()

ALLOWED_EXTENSIONS = {
    ".kt", ".java", ".xml", ".gradle", ".kts", ".properties",
    ".json", ".md", ".txt", ".pro", ".toml",
}

SKIP_DIRS = {
    ".git", ".gradle", ".idea", "build",
    "node_modules", "__pycache__", ".DS_Store",
    "intermediates", "generated", "tmp", "cache",
}

MAX_FILE_SIZE_BYTES = 500_000
MAX_SEARCH_RESULTS = 50
MAX_TREE_DEPTH = 5

mcp = FastMCP(
    name="AndroidContextAgent",
    instructions=(
        "Saya adalah Context Agent untuk proyek Android. "
        f"Root proyek: {ROOT_DIR}. "
        "Gunakan tools saya untuk menjelajahi modul, membaca source code, "
        "mencari string/regex, melihat struktur proyek, dan menganalisis AndroidManifest."
    ),
)


def _safe_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _is_allowed_file(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def _is_text_readable(path: Path) -> bool:
    if not _is_allowed_file(path):
        return False
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        return False
    return True


def _read_file_safe(path: Path) -> str:
    for encoding in ["utf-8", "cp1252", "latin-1"]:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, PermissionError) as e:
            if isinstance(e, PermissionError):
                return f"[ERROR] Akses ditolak: {e}"
            continue
    return "[ERROR] Tidak bisa membaca file: encoding tidak dikenali."


def _log_usage(tool_name: str, output: str):
    if not output:
        return
    char_count = len(output)
    est_tokens = char_count // 4
    logger.info("Tool '%s' output: %d chars (~%d tokens)", tool_name, char_count, est_tokens)


@tool
@mcp.tool()
@wrap_tool_call
def list_android_modules() -> str:
    """
    Menelusuri seluruh direktori proyek untuk menemukan modul Android.

    Returns:
        Daftar modul beserta path relatifnya dari root proyek.
    """
    modules = []

    for gradle_file in sorted(ROOT_DIR.rglob("build.gradle*")):
        parts = gradle_file.parts
        if any(skip in parts for skip in SKIP_DIRS):
            continue

        module_dir = gradle_file.parent
        rel_path = _safe_relative(module_dir)

        module_type = "root" if module_dir == ROOT_DIR else "module"
        has_src = (module_dir / "src").is_dir()
        has_manifest = any(module_dir.rglob("AndroidManifest.xml"))

        modules.append({
            "name": module_dir.name,
            "path": rel_path,
            "type": module_type,
            "has_src": has_src,
            "has_manifest": has_manifest,
            "gradle_file": gradle_file.name,
        })

    if not modules:
        return f"Tidak ada modul ditemukan di: {ROOT_DIR}"

    lines = [
        f"Android Modules - Root: {ROOT_DIR.name}",
        f"Ditemukan {len(modules)} modul:",
        "-" * 60,
    ]
    for m in modules:
        src = "src+" if m["has_src"] else "src-"
        mnf = "mnf+" if m["has_manifest"] else "mnf-"
        lines.append(f"  [{m['type'][:1].upper()}] {m['name']:<15} | {src} | {mnf} | {m['path']}")

    result = "\n".join(lines)
    _log_usage("list_android_modules", result)
    return result


@tool
@mcp.tool()
@wrap_tool_call
def read_source_file(path: str) -> str:
    """
    Membaca isi file source code Android secara aman.

    Args:
        path: Path ke file, bisa relatif dari root proyek atau absolut
    """
    target = Path(path)
    if not target.is_absolute():
        target = ROOT_DIR / path
    target = target.resolve()

    try:
        target.relative_to(ROOT_DIR)
    except ValueError:
        return f"DITOLAK: Path '{path}' berada di luar root proyek ({ROOT_DIR})."

    if not target.exists():
        return f"File tidak ditemukan: {path}"

    if not target.is_file():
        return f"'{path}' bukan file (mungkin direktori)."

    if not _is_allowed_file(target):
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return f"Ekstensi '{target.suffix}' tidak diizinkan. Diperbolehkan: {allowed}"

    size = target.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        size_kb = size // 1024
        return f"File terlalu besar ({size_kb} KB). Batas maksimal: {MAX_FILE_SIZE_BYTES // 1024} KB."

    content = _read_file_safe(target)
    rel_path = _safe_relative(target)
    line_count = content.count("\n") + 1

    header = (
        f"FILE: {rel_path}\n"
        f"  Ukuran: {size:,} bytes | Baris: {line_count:,}\n"
        f"{'─' * 60}\n"
    )
    result = header + content
    _log_usage("read_source_file", result)
    return result


@tool
@mcp.tool()
@wrap_tool_call
def search_code(query: str, use_regex: bool = False, file_extension: Optional[str] = None) -> str:
    """
    Mencari string atau pola regex di seluruh folder src/ proyek.

    Args:
        query: String atau pola regex yang dicari
        use_regex: Jika True, query diperlakukan sebagai regex
        file_extension: Filter hanya ekstensi tertentu
    """
    if not query.strip():
        return "Query pencarian tidak boleh kosong."

    try:
        if use_regex:
            pattern = re.compile(query, re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
    except re.error as e:
        return f"Regex tidak valid: {e}"

    search_dirs = []
    for src_dir in ROOT_DIR.rglob("src"):
        if src_dir.is_dir() and not any(s in src_dir.parts for s in SKIP_DIRS):
            search_dirs.append(src_dir)

    if not search_dirs:
        search_dirs = [ROOT_DIR]

    results = []
    total_hits = 0
    files_scanned = 0

    for search_dir in search_dirs:
        for file_path in sorted(search_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if any(s in file_path.parts for s in SKIP_DIRS):
                continue
            if not _is_allowed_file(file_path):
                continue
            if file_extension and file_path.suffix.lower() != file_extension.lower():
                continue
            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue

            files_scanned += 1
            content = _read_file_safe(file_path)
            lines = content.splitlines()

            file_matches = []
            for i, line in enumerate(lines):
                if pattern.search(line):
                    ctx_start = max(0, i - 1)
                    ctx_end = min(len(lines), i + 2)
                    context = []
                    for j in range(ctx_start, ctx_end):
                        prefix = ">>> " if j == i else "    "
                        context.append(f"  {prefix}{j+1:4d}: {lines[j]}")

                    file_matches.append("\n".join(context))
                    total_hits += 1

                    if total_hits >= MAX_SEARCH_RESULTS:
                        break

            if file_matches:
                rel = _safe_relative(file_path)
                results.append(f"\n{rel} ({len(file_matches)} hits):\n" + "\n---\n".join(file_matches))

            if total_hits >= MAX_SEARCH_RESULTS:
                break
        if total_hits >= MAX_SEARCH_RESULTS:
            break

    mode = "REGEX" if use_regex else "STRING"
    ext_filter = f" | Ekstensi: {file_extension}" if file_extension else ""
    header = (
        f"Pencarian [{mode}]: \"{query}\"{ext_filter}\n"
        f"  File diperiksa: {files_scanned} | Total hits: {total_hits}"
        + (" (dibatasi)" if total_hits >= MAX_SEARCH_RESULTS else "")
        + "\n" + "=" * 60
    )

    if not results:
        return header + "\n\nTidak ada hasil yang cocok."

    result = header + "".join(results)
    _log_usage("search_code", result)
    return result


@tool
@mcp.tool()
@wrap_tool_call
def get_project_structure(max_depth: int = 3, show_all: bool = False) -> str:
    """
    Memberikan gambaran pohon struktur folder proyek Android.

    Args:
        max_depth: Kedalaman maksimal pohon yang ditampilkan
        show_all: Jika True, tampilkan juga direktori yang biasa diskip
    """
    max_depth = max(1, min(max_depth, MAX_TREE_DEPTH + 2))

    def build_tree_custom(directory: Path, depth: int = 0) -> list[str]:
        if depth > max_depth:
            return []

        lines = []
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return [f"{'  ' * depth}[AKSES DITOLAK]"]

        for entry in entries:
            indent = "  " * depth
            if entry.is_dir():
                is_skip = entry.name in SKIP_DIRS
                if is_skip and not show_all:
                    lines.append(f"{indent}[DIR] {entry.name}/ (auto-skip)")
                    continue
                skip_label = " (!)" if is_skip else ""
                lines.append(f"{indent}[DIR] {entry.name}/{skip_label}")
                lines.extend(build_tree_custom(entry, depth + 1))
            else:
                lines.append(f"{indent}  {entry.name}")

        return lines

    tree_lines = build_tree_custom(ROOT_DIR)

    header = (
        f"STRUKTUR PROYEK ANDROID\n"
        f"  Root: {ROOT_DIR}\n"
        f"  Depth: {max_depth} | Show-all: {show_all}\n"
        f"{'=' * 60}\n"
        f"{ROOT_DIR.name}/  <- ROOT\n"
    )

    result = header + "\n".join(tree_lines)
    _log_usage("get_project_structure", result)
    return result


@tool
@mcp.tool()
@wrap_tool_call
def analyze_manifest(module_path: Optional[str] = None) -> str:
    """
    Membaca dan menganalisis AndroidManifest.xml secara otomatis.

    Args:
        module_path: Path relatif ke modul spesifik (contoh: "app")
    """
    if module_path:
        search_root = ROOT_DIR / module_path
        if not search_root.exists():
            return f"Modul tidak ditemukan: {module_path}"
        manifest_files = list(search_root.rglob("AndroidManifest.xml"))
    else:
        manifest_files = [
            f for f in ROOT_DIR.rglob("AndroidManifest.xml")
            if not any(skip in f.parts for skip in SKIP_DIRS)
        ]

    if not manifest_files:
        loc = f"modul '{module_path}'" if module_path else "proyek"
        return f"AndroidManifest.xml tidak ditemukan di {loc}."

    output_parts = []

    for manifest_path in sorted(manifest_files):
        rel_path = _safe_relative(manifest_path)
        content = _read_file_safe(manifest_path)

        pkg_match = re.search(r'package\s*=\s*"([^"]+)"', content)
        package = pkg_match.group(1) if pkg_match else "Tidak ditemukan"

        app_label = re.search(r'android:label\s*=\s*"([^"]+)"', content)
        label = app_label.group(1) if app_label else "(dari resources)"

        find_all = lambda tag_pattern: re.findall(tag_pattern, content)

        activities = find_all(r'<activity[^>]*android:name\s*=\s*"([^"]+)"')
        services = find_all(r'<service[^>]*android:name\s*=\s*"([^"]+)"')
        receivers = find_all(r'<receiver[^>]*android:name\s*=\s*"([^"]+)"')
        providers = find_all(r'<provider[^>]*android:name\s*=\s*"([^"]+)"')
        permissions = find_all(r'<uses-permission[^>]*android:name\s*=\s*"([^"]+)"')
        features = find_all(r'<uses-feature[^>]*android:name\s*=\s*"([^"]+)"')

        min_sdk = re.search(r'android:minSdkVersion\s*=\s*"([^"]+)"', content)
        target_sdk = re.search(r'android:targetSdkVersion\s*=\s*"([^"]+)"', content)

        has_internet = "android.permission.INTERNET" in content

        summary = [
            f"\n{'=' * 60}",
            f"MANIFEST: {rel_path}",
            f"{'-' * 60}",
            f"Package: {package}",
            f"App Label: {label}",
            f"Min SDK: {min_sdk.group(1) if min_sdk else 'N/A'}",
            f"Target SDK: {target_sdk.group(1) if target_sdk else 'N/A'}",
            f"Internet: {'Ya' if has_internet else 'Tidak'}",
            f"",
            f"Activities ({len(activities)}):",
        ]
        for a in activities:
            summary.append(f"  - {a}")

        if services:
            summary.append(f"\nServices ({len(services)}):")
            for s in services:
                summary.append(f"  - {s}")

        if receivers:
            summary.append(f"\nReceivers ({len(receivers)}):")
            for r in receivers:
                summary.append(f"  - {r}")

        if providers:
            summary.append(f"\nProviders ({len(providers)}):")
            for p in providers:
                summary.append(f"  - {p}")

        if permissions:
            summary.append(f"\nPermissions ({len(permissions)}):")
            for perm in permissions:
                summary.append(f"  - {perm}")

        if features:
            summary.append(f"\nFeatures ({len(features)}):")
            for feat in features:
                summary.append(f"  - {feat}")

        output_parts.append("\n".join(summary))

    result = "\n".join(output_parts)
    _log_usage("analyze_manifest", result)
    return result


@tool
@mcp.tool()
@wrap_tool_call
def list_files_in_module(module_path: str, extension: Optional[str] = None) -> str:
    """
    Menampilkan semua file source dalam satu modul Android.

    Args:
        module_path: Path relatif ke modul (contoh: "app", "core/network")
        extension: Filter berdasarkan ekstensi
    """
    target = (ROOT_DIR / module_path).resolve()

    try:
        target.relative_to(ROOT_DIR)
    except ValueError:
        return f"Path '{module_path}' berada di luar root proyek."

    if not target.exists():
        return f"Direktori tidak ditemukan: {module_path}"

    if not target.is_dir():
        return f"'{module_path}' bukan direktori."

    files_by_type: dict[str, list[str]] = {}

    for file_path in sorted(target.rglob("*")):
        if not file_path.is_file():
            continue
        if any(s in file_path.parts for s in SKIP_DIRS):
            continue
        if not _is_allowed_file(file_path):
            continue
        if extension and file_path.suffix.lower() != extension.lower():
            continue

        ext = file_path.suffix.lower() or "other"
        rel = _safe_relative(file_path)
        files_by_type.setdefault(ext, []).append(rel)

    if not files_by_type:
        ext_info = f" dengan ekstensi '{extension}'" if extension else ""
        return f"Tidak ada file{ext_info} ditemukan di: {module_path}"

    total = sum(len(v) for v in files_by_type.values())
    lines = [
        f"MODUL: {module_path}",
        f"  Total file: {total}\n",
    ]

    ext_order = [".kt", ".java", ".xml", ".gradle", ".kts", ".properties", ".toml"]
    all_exts = ext_order + sorted(k for k in files_by_type if k not in ext_order)

    for ext_key in all_exts:
        if ext_key not in files_by_type:
            continue
        ext_files = files_by_type[ext_key]
        lines.append(f"{ext_key.upper()} ({len(ext_files)} file):")
        for f in ext_files:
            lines.append(f"  {f}")
        lines.append("")

    result = "\n".join(lines)
    _log_usage("list_files_in_module", result)
    return result


@tool
@mcp.tool()
@wrap_tool_call
def get_gradle_dependencies(module_path: str = "app") -> str:
    """
    Membaca dan mengekstrak daftar dependencies dari file build.gradle.

    Args:
        module_path: Path relatif ke modul (default: "app")
    """
    target = ROOT_DIR / module_path

    gradle_file = None
    for name in ("build.gradle.kts", "build.gradle"):
        candidate = target / name
        if candidate.exists():
            gradle_file = candidate
            break

    if not gradle_file:
        return (
            f"File build.gradle tidak ditemukan di: {module_path}\n"
            f"  Coba gunakan list_android_modules() untuk melihat modul yang tersedia."
        )

    content = _read_file_safe(gradle_file)

    dep_patterns = [
        r'(implementation|api|testImplementation|androidTestImplementation|'
        r'compileOnly|runtimeOnly|kapt|ksp|debugImplementation|releaseImplementation)'
        r'\s+["\']([^"\']+)["\']',
        r'(implementation|api|testImplementation|androidTestImplementation|'
        r'compileOnly|runtimeOnly|kapt|ksp|debugImplementation|releaseImplementation)'
        r'\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ]

    deps_by_config: dict[str, list[str]] = {}
    seen = set()

    for pattern in dep_patterns:
        for match in re.finditer(pattern, content):
            config = match.group(1)
            dep = match.group(2)
            key = (config, dep)
            if key not in seen:
                seen.add(key)
                deps_by_config.setdefault(config, []).append(dep)

    if not deps_by_config:
        return (
            f"Tidak ada dependency terdeteksi di {gradle_file.name}.\n"
            f"  (Mungkin menggunakan Version Catalog atau format tidak standar)\n\n"
            f"ISI FILE:\n{'-' * 40}\n{content}"
        )

    total = sum(len(v) for v in deps_by_config.values())
    lines = [
        f"DEPENDENCIES: {_safe_relative(gradle_file)}",
        f"  Total: {total} dependency\n",
    ]

    priority = [
        "implementation", "api", "kapt", "ksp",
        "debugImplementation", "releaseImplementation",
        "testImplementation", "androidTestImplementation",
        "compileOnly", "runtimeOnly",
    ]
    all_configs = priority + sorted(k for k in deps_by_config if k not in priority)

    for cfg in all_configs:
        if cfg not in deps_by_config:
            continue
        lines.append(f"{cfg} ({len(deps_by_config[cfg])}):")
        for dep in sorted(deps_by_config[cfg]):
            lines.append(f"  - {dep}")
        lines.append("")

    result = "\n".join(lines)
    _log_usage("get_gradle_dependencies", result)
    return result


SYSTEM_PROMPT_ANDROID = (
    "Anda adalah 'The Architect', ahli arsitektur Android senior.\n"
    f"Anda memiliki akses ke proyek Android yang berlokasi di: {ROOT_DIR}\n\n"
    "Tugas Anda adalah membantu developer memahami struktur, alur data, dan "
    "arsitektur kode dalam proyek ini menggunakan tools yang tersedia.\n"
    "Berikan jawaban yang mendalam, tunjukkan file yang relevan, dan jelaskan "
    "bagaimana komponen saling berinteraksi.\n\n"
    "Gunakan tools secara efisien. Jangan membaca terlalu banyak file sekaligus jika tidak perlu."
)


@mcp.tool()
def run_android_architect_agent(user_query: str) -> AndroidArchitectureAnalysis:
    """
    Menjalankan agen kompeten yang mengerti arsitektur Android untuk menganalisis proyek.
    """
    llm = create_llm(temperature=0.0)

    tools = [
        list_android_modules,
        read_source_file,
        search_code,
        get_project_structure,
        analyze_manifest,
        list_files_in_module,
        get_gradle_dependencies,
    ]

    agent_executor, agent_config = create_agent_with_memory(
        llm=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT_ANDROID,
        agent_name="AndroidArchitect",
    )

    return execute_agent_and_structure(
        agent_executor=agent_executor,
        agent_config=agent_config,
        user_input=user_query,
        llm=llm,
        output_schema=AndroidArchitectureAnalysis,
        agent_label="AndroidArchitect",
    )


if __name__ == "__main__":
    logger.info("Starting MCP Server | Root: %s", ROOT_DIR)
    mcp.run(transport="stdio")