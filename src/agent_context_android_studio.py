import sys
import os
import re
import argparse
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

# ──────────────────────────────────────────────
# Inisialisasi argumen & root directory
# ──────────────────────────────────────────────
def resolve_root_directory() -> Path:
    """
    Deteksi root directory secara otomatis:
    1. Dari argumen --root di command line
    2. Dari environment variable ANDROID_PROJECT_ROOT
    3. Dari current working directory
    """
    parser = argparse.ArgumentParser(
        description="Android Studio Context MCP Server",
        add_help=False  # Agar tidak konflik dengan MCP stdio
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Path ke root direktori proyek Android"
    )
    # Parse hanya argumen yang kita kenal, sisanya diabaikan
    args, _ = parser.parse_known_args()

    if args.root:
        root = Path(args.root).resolve()
    elif "ANDROID_PROJECT_ROOT" in os.environ:
        root = Path(os.environ["ANDROID_PROJECT_ROOT"]).resolve()
    else:
        root = Path.cwd().resolve()

    if not root.exists():
        print(f"[ERROR] Root directory tidak ditemukan: {root}", file=sys.stderr)
        sys.exit(1)

    return root


ROOT_DIR = resolve_root_directory()

# ──────────────────────────────────────────────
# Konstanta & konfigurasi
# ──────────────────────────────────────────────

# Ekstensi file teks yang diizinkan untuk dibaca
ALLOWED_EXTENSIONS = {
    ".kt",      # Kotlin
    ".java",    # Java
    ".xml",     # XML (layout, manifest, resource)
    ".gradle",  # Gradle build scripts
    ".kts",     # Kotlin Script (build.gradle.kts)
    ".properties",  # gradle.properties, local.properties
    ".json",    # JSON config
    ".md",      # Dokumentasi
    ".txt",     # Teks biasa
    ".pro",     # ProGuard rules
    ".toml",    # Version catalog (libs.versions.toml)
}

# Direktori yang harus dilewati saat scanning
SKIP_DIRS = {
    ".git", ".gradle", ".idea", "build",
    "node_modules", "__pycache__", ".DS_Store",
    "intermediates", "generated", "tmp", "cache",
}

MAX_FILE_SIZE_BYTES = 500_000   # 500 KB – batas baca file
MAX_SEARCH_RESULTS  = 50        # Batas hasil search per query
MAX_TREE_DEPTH      = 5         # Kedalaman maksimal pohon direktori

# ──────────────────────────────────────────────
# FastMCP initialization
# ──────────────────────────────────────────────
mcp = FastMCP(
    name="AndroidContextAgent",
    instructions=(
        "Saya adalah Context Agent untuk proyek Android. "
        f"Root proyek: {ROOT_DIR}. "
        "Gunakan tools saya untuk menjelajahi modul, membaca source code, "
        "mencari string/regex, melihat struktur proyek, dan menganalisis AndroidManifest."
    ),
)


# ══════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════

def _safe_relative(path: Path) -> str:
    """Konversi path absolut ke relatif dari ROOT_DIR."""
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def _is_allowed_file(path: Path) -> bool:
    """Cek apakah file boleh dibaca (berdasarkan ekstensi)."""
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def _is_text_readable(path: Path) -> bool:
    """Cek apakah file bisa dibaca sebagai teks (ukuran & ekstensi)."""
    if not _is_allowed_file(path):
        return False
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        return False
    return True


def _read_file_safe(path: Path) -> str:
    """Baca file dengan penanganan error encoding."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return "[ERROR] Tidak bisa membaca file: encoding tidak dikenali."

# ══════════════════════════════════════════════
# MCP TOOLS
# ══════════════════════════════════════════════

@mcp.tool()
def list_android_modules() -> str:
    """
    Menelusuri seluruh direktori proyek untuk menemukan modul Android.
    Modul diidentifikasi sebagai folder yang mengandung file 'build.gradle'
    atau 'build.gradle.kts'.

    Returns:
        Daftar modul beserta path relatifnya dari root proyek.
    """
    modules = []

    for gradle_file in sorted(ROOT_DIR.rglob("build.gradle*")):
        # Lewati direktori build & generated
        parts = gradle_file.parts
        if any(skip in parts for skip in SKIP_DIRS):
            continue

        module_dir = gradle_file.parent
        rel_path    = _safe_relative(module_dir)

        # Deteksi tipe modul
        module_type = "root" if module_dir == ROOT_DIR else "module"
        has_src     = (module_dir / "src").is_dir()
        has_manifest = any(module_dir.rglob("AndroidManifest.xml"))

        modules.append({
            "name":          module_dir.name,
            "path":          rel_path,
            "type":          module_type,
            "has_src":       has_src,
            "has_manifest":  has_manifest,
            "gradle_file":   gradle_file.name,
        })

    if not modules:
        return (
            f"⚠️  Tidak ada modul ditemukan di: {ROOT_DIR}\n"
            "Pastikan Anda menjalankan server dari root proyek Android."
        )

    lines = [
        f"🤖 Android Context Agent — Root: {ROOT_DIR}",
        f"📦 Ditemukan {len(modules)} modul:\n",
    ]
    for m in modules:
        src_icon      = "✅" if m["has_src"]      else "❌"
        manifest_icon = "✅" if m["has_manifest"] else "❌"
        lines.append(
            f"  • [{m['type'].upper()}] {m['name']}\n"
            f"    Path     : {m['path']}\n"
            f"    Gradle   : {m['gradle_file']}\n"
            f"    src/     : {src_icon}   AndroidManifest: {manifest_icon}\n"
        )

    return "\n".join(lines)


@mcp.tool()
def read_source_file(path: str) -> str:
    """
    Membaca isi file source code Android secara aman.

    Hanya file dengan ekstensi yang diizinkan yang bisa dibaca:
    .kt, .java, .xml, .gradle, .kts, .properties, .json, .md, .txt, .pro, .toml

    Args:
        path: Path ke file, bisa relatif dari root proyek atau absolut.
              Contoh: "app/src/main/java/com/example/MainActivity.kt"

    Returns:
        Isi file lengkap beserta informasi metadata.
    """
    # Resolve path
    target = Path(path)
    if not target.is_absolute():
        target = ROOT_DIR / path
    target = target.resolve()

    # Keamanan: pastikan file masih di dalam ROOT_DIR
    try:
        target.relative_to(ROOT_DIR)
    except ValueError:
        return f"❌ DITOLAK: Path '{path}' berada di luar root proyek ({ROOT_DIR})."

    # Validasi keberadaan file
    if not target.exists():
        return f"❌ File tidak ditemukan: {path}\n   Path lengkap: {target}"

    if not target.is_file():
        return f"❌ '{path}' bukan file (mungkin direktori)."

    # Validasi ekstensi
    if not _is_allowed_file(target):
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return (
            f"❌ Ekstensi '{target.suffix}' tidak diizinkan.\n"
            f"   Ekstensi yang diizinkan: {allowed}"
        )

    # Validasi ukuran
    size = target.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        size_kb = size // 1024
        return (
            f"❌ File terlalu besar ({size_kb} KB). "
            f"Batas maksimal: {MAX_FILE_SIZE_BYTES // 1024} KB.\n"
            f"   Gunakan search_code() untuk mencari bagian spesifik."
        )

    # Baca file
    content = _read_file_safe(target)
    rel_path = _safe_relative(target)
    line_count = content.count("\n") + 1

    header = (
        f"📄 FILE: {rel_path}\n"
        f"   Ukuran : {size:,} bytes  |  Baris: {line_count:,}\n"
        f"{'─' * 60}\n"
    )
    return header + content


@mcp.tool()
def search_code(query: str, use_regex: bool = False, file_extension: Optional[str] = None) -> str:
    """
    Mencari string atau pola regex di seluruh folder src/ proyek.

    Args:
        query:          String atau pola regex yang dicari.
        use_regex:      Jika True, query diperlakukan sebagai regex. Default: False.
        file_extension: Filter hanya ekstensi tertentu, contoh: ".kt" atau ".xml".
                        Jika None, semua file yang diizinkan akan dicari.

    Returns:
        Daftar file dan baris yang cocok, termasuk konteks 1 baris sebelum/sesudah.
    """
    if not query.strip():
        return "❌ Query pencarian tidak boleh kosong."

    # Kompilasi pattern
    try:
        if use_regex:
            pattern = re.compile(query, re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(query), re.IGNORECASE)
    except re.error as e:
        return f"❌ Regex tidak valid: {e}"

    # Tentukan direktori pencarian (prioritas: src/, fallback: seluruh ROOT)
    search_dirs = []
    for src_dir in ROOT_DIR.rglob("src"):
        if src_dir.is_dir() and not any(s in src_dir.parts for s in SKIP_DIRS):
            search_dirs.append(src_dir)

    if not search_dirs:
        search_dirs = [ROOT_DIR]

    results      = []
    total_hits   = 0
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
            lines   = content.splitlines()

            file_matches = []
            for i, line in enumerate(lines):
                if pattern.search(line):
                    # Konteks: 1 baris sebelum & sesudah
                    ctx_start = max(0, i - 1)
                    ctx_end   = min(len(lines), i + 2)
                    context   = []
                    for j in range(ctx_start, ctx_end):
                        prefix = ">>> " if j == i else "    "
                        context.append(f"  {prefix}{j+1:4d}: {lines[j]}")

                    file_matches.append("\n".join(context))
                    total_hits += 1

                    if total_hits >= MAX_SEARCH_RESULTS:
                        break

            if file_matches:
                rel = _safe_relative(file_path)
                results.append(f"\n📁 {rel} ({len(file_matches)} hits):\n" + "\n---\n".join(file_matches))

            if total_hits >= MAX_SEARCH_RESULTS:
                break

        if total_hits >= MAX_SEARCH_RESULTS:
            break

    # Ringkasan
    mode = "REGEX" if use_regex else "STRING"
    ext_filter = f" | Ekstensi: {file_extension}" if file_extension else ""
    header = (
        f"🔍 Pencarian [{mode}]: \"{query}\"{ext_filter}\n"
        f"   File diperiksa: {files_scanned}  |  Total hits: {total_hits}"
        + (" (dibatasi)" if total_hits >= MAX_SEARCH_RESULTS else "")
        + "\n" + "═" * 60
    )

    if not results:
        return header + "\n\n✅ Tidak ada hasil yang cocok."

    return header + "".join(results)


@mcp.tool()
def get_project_structure(max_depth: int = 4, show_all: bool = False) -> str:
    """
    Memberikan gambaran pohon struktur folder proyek Android.
    Membantu AI memahami letak res/, manifests/, java/, kotlin/.

    Args:
        max_depth:  Kedalaman maksimal pohon yang ditampilkan (default: 4).
        show_all:   Jika True, tampilkan juga direktori yang biasa diskip
                    (build/, .gradle/, dll). Default: False.

    Returns:
        Representasi pohon direktori proyek.
    """
    max_depth = max(1, min(max_depth, MAX_TREE_DEPTH + 2))

    def build_tree_custom(directory: Path, depth: int = 0) -> list[str]:
        if depth > max_depth:
            return []

        lines = []
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower())
            )
        except PermissionError:
            return [f"{'  ' * depth}[AKSES DITOLAK]"]

        for entry in entries:
            indent = "  " * depth
            if entry.is_dir():
                is_skip = entry.name in SKIP_DIRS
                if is_skip and not show_all:
                    lines.append(f"{indent}📁 {entry.name}/ ⏭️ (auto-skip)")
                    continue
                skip_label = " ⚠️" if is_skip else ""
                lines.append(f"{indent}📁 {entry.name}/{skip_label}")
                lines.extend(build_tree_custom(entry, depth + 1))
            else:
                icon = "📄"
                if entry.suffix == ".kt":    icon = "🟣"
                elif entry.suffix == ".java": icon = "☕"
                elif entry.suffix == ".xml":  icon = "📋"
                elif entry.suffix in (".gradle", ".kts"): icon = "🐘"
                elif entry.name == "AndroidManifest.xml": icon = "📜"
                lines.append(f"{indent}{icon} {entry.name}")

        return lines

    tree_lines = build_tree_custom(ROOT_DIR)

    legend = (
        "\n📌 LEGENDA:\n"
        "  🟣 .kt (Kotlin)  ☕ .java  📋 .xml  🐘 .gradle/.kts\n"
        "  📁 Direktori     ⏭️  Auto-skip (build artifacts)\n"
    )

    header = (
        f"🗂️  STRUKTUR PROYEK ANDROID\n"
        f"   Root    : {ROOT_DIR}\n"
        f"   Depth   : {max_depth}  |  Show-all: {show_all}\n"
        f"{'═' * 60}\n"
        f"📁 {ROOT_DIR.name}/  ← ROOT\n"
    )

    return header + "\n".join(tree_lines) + legend


@mcp.tool()
def analyze_manifest(module_path: Optional[str] = None) -> str:
    """
    Membaca dan menganalisis AndroidManifest.xml secara otomatis.
    Mengekstrak informasi penting: package name, activities, services,
    permissions, providers, dan konfigurasi aplikasi.

    Args:
        module_path: Path relatif ke modul spesifik (contoh: "app").
                     Jika None, akan mencari semua manifest di proyek.

    Returns:
        Isi AndroidManifest.xml beserta ringkasan analisis.
    """
    manifests = []

    if module_path:
        # Cari manifest di modul spesifik
        search_root = ROOT_DIR / module_path
        if not search_root.exists():
            return f"❌ Modul tidak ditemukan: {module_path}"
        manifest_files = list(search_root.rglob("AndroidManifest.xml"))
    else:
        # Cari semua manifest, kecuali di folder build/
        manifest_files = [
            f for f in ROOT_DIR.rglob("AndroidManifest.xml")
            if not any(skip in f.parts for skip in SKIP_DIRS)
        ]

    if not manifest_files:
        loc = f"modul '{module_path}'" if module_path else "proyek"
        return (
            f"⚠️  AndroidManifest.xml tidak ditemukan di {loc}.\n"
            f"   Pastikan ini adalah proyek Android yang valid."
        )

    output_parts = []

    for manifest_path in sorted(manifest_files):
        rel_path = _safe_relative(manifest_path)
        content  = _read_file_safe(manifest_path)

        # ── Parsing manual ringan untuk ringkasan ──
        def find_all(tag_pattern: str) -> list[str]:
            return re.findall(tag_pattern, content)

        # Package name
        pkg_match = re.search(r'package\s*=\s*"([^"]+)"', content)
        package   = pkg_match.group(1) if pkg_match else "Tidak ditemukan"

        # Application ID / label
        app_label = re.search(r'android:label\s*=\s*"([^"]+)"', content)
        label     = app_label.group(1) if app_label else "(dari resources)"

        # Komponen
        activities  = find_all(r'<activity[^>]*android:name\s*=\s*"([^"]+)"')
        services    = find_all(r'<service[^>]*android:name\s*=\s*"([^"]+)"')
        receivers   = find_all(r'<receiver[^>]*android:name\s*=\s*"([^"]+)"')
        providers   = find_all(r'<provider[^>]*android:name\s*=\s*"([^"]+)"')
        permissions = find_all(r'<uses-permission[^>]*android:name\s*=\s*"([^"]+)"')
        features    = find_all(r'<uses-feature[^>]*android:name\s*=\s*"([^"]+)"')

        # Min & Target SDK
        min_sdk    = re.search(r'android:minSdkVersion\s*=\s*"([^"]+)"', content)
        target_sdk = re.search(r'android:targetSdkVersion\s*=\s*"([^"]+)"', content)

        # Internet permission check
        has_internet = "android.permission.INTERNET" in content

        # Ringkasan
        summary = [
            f"\n{'═' * 60}",
            f"📜 MANIFEST: {rel_path}",
            f"{'─' * 60}",
            f"📦 Package       : {package}",
            f"🏷️  App Label     : {label}",
            f"📱 Min SDK        : {min_sdk.group(1) if min_sdk else 'N/A'}",
            f"🎯 Target SDK     : {target_sdk.group(1) if target_sdk else 'N/A'}",
            f"🌐 Internet       : {'✅ Ya' if has_internet else '❌ Tidak'}",
            f"",
            f"🏃 Activities    ({len(activities)}):",
        ]
        for a in activities:
            summary.append(f"     • {a}")

        if services:
            summary.append(f"\n⚙️  Services      ({len(services)}):")
            for s in services:
                summary.append(f"     • {s}")

        if receivers:
            summary.append(f"\n📡 Receivers     ({len(receivers)}):")
            for r in receivers:
                summary.append(f"     • {r}")

        if providers:
            summary.append(f"\n🗄️  Providers     ({len(providers)}):")
            for p in providers:
                summary.append(f"     • {p}")

        if permissions:
            summary.append(f"\n🔐 Permissions   ({len(permissions)}):")
            for perm in permissions:
                summary.append(f"     • {perm}")

        if features:
            summary.append(f"\n🔧 Features      ({len(features)}):")
            for feat in features:
                summary.append(f"     • {feat}")

        summary.extend([
            f"\n{'─' * 60}",
            "📄 ISI FILE LENGKAP:",
            f"{'─' * 60}",
            content,
        ])

        output_parts.append("\n".join(summary))

    header = (
        f"🤖 Analisis AndroidManifest.xml\n"
        f"   Ditemukan: {len(manifests)} file manifest\n"
    )
    return header + "\n".join(output_parts)


@mcp.tool()
def list_files_in_module(module_path: str, extension: Optional[str] = None) -> str:
    """
    Menampilkan semua file source dalam satu modul Android.

    Args:
        module_path: Path relatif ke modul (contoh: "app", "core/network").
        extension:   Filter berdasarkan ekstensi (contoh: ".kt", ".xml").
                     Jika None, tampilkan semua file yang diizinkan.

    Returns:
        Daftar file beserta path relatifnya.
    """
    target = (ROOT_DIR / module_path).resolve()

    try:
        target.relative_to(ROOT_DIR)
    except ValueError:
        return f"❌ Path '{module_path}' berada di luar root proyek."

    if not target.exists():
        return f"❌ Direktori tidak ditemukan: {module_path}"

    if not target.is_dir():
        return f"❌ '{module_path}' bukan direktori."

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
        return f"⚠️  Tidak ada file{ext_info} ditemukan di: {module_path}"

    total = sum(len(v) for v in files_by_type.values())
    lines = [
        f"📦 MODUL: {module_path}",
        f"   Total file: {total}\n",
    ]

    ext_order = [".kt", ".java", ".xml", ".gradle", ".kts", ".properties", ".toml"]
    all_exts  = ext_order + sorted(k for k in files_by_type if k not in ext_order)

    for ext_key in all_exts:
        if ext_key not in files_by_type:
            continue
        ext_files = files_by_type[ext_key]
        icons = {".kt": "🟣", ".java": "☕", ".xml": "📋", ".gradle": "🐘", ".kts": "🐘"}
        icon  = icons.get(ext_key, "📄")
        lines.append(f"{icon} {ext_key.upper()} ({len(ext_files)} file):")
        for f in ext_files:
            lines.append(f"   {f}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_gradle_dependencies(module_path: str = "app") -> str:
    """
    Membaca dan mengekstrak daftar dependencies dari file build.gradle
    atau build.gradle.kts pada modul tertentu.

    Args:
        module_path: Path relatif ke modul (default: "app").

    Returns:
        Daftar dependencies yang ditemukan beserta konfigurasinya.
    """
    target = ROOT_DIR / module_path

    # Cari file gradle (prioritaskan .kts)
    gradle_file = None
    for name in ("build.gradle.kts", "build.gradle"):
        candidate = target / name
        if candidate.exists():
            gradle_file = candidate
            break

    if not gradle_file:
        return (
            f"❌ File build.gradle tidak ditemukan di: {module_path}\n"
            f"   Coba gunakan list_android_modules() untuk melihat modul yang tersedia."
        )

    content = _read_file_safe(gradle_file)

    # Pattern untuk berbagai gaya dependencies
    dep_patterns = [
        # Groovy: implementation "group:artifact:version"
        r'(implementation|api|testImplementation|androidTestImplementation|'
        r'compileOnly|runtimeOnly|kapt|ksp|debugImplementation|releaseImplementation)'
        r'\s+["\']([^"\']+)["\']',
        # Kotlin DSL: implementation("group:artifact:version")
        r'(implementation|api|testImplementation|androidTestImplementation|'
        r'compileOnly|runtimeOnly|kapt|ksp|debugImplementation|releaseImplementation)'
        r'\s*\(\s*["\']([^"\']+)["\']\s*\)',
    ]

    deps_by_config: dict[str, list[str]] = {}
    seen = set()

    for pattern in dep_patterns:
        for match in re.finditer(pattern, content):
            config = match.group(1)
            dep    = match.group(2)
            key    = (config, dep)
            if key not in seen:
                seen.add(key)
                deps_by_config.setdefault(config, []).append(dep)

    if not deps_by_config:
        return (
            f"⚠️  Tidak ada dependency terdeteksi di {gradle_file.name}.\n"
            f"   (Mungkin menggunakan Version Catalog atau format tidak standar)\n\n"
            f"📄 ISI FILE:\n{'─'*40}\n{content}"
        )

    total = sum(len(v) for v in deps_by_config.values())
    lines = [
        f"🐘 DEPENDENCIES: {_safe_relative(gradle_file)}",
        f"   Total: {total} dependency\n",
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
        lines.append(f"📌 {cfg} ({len(deps_by_config[cfg])}):")
        for dep in sorted(deps_by_config[cfg]):
            lines.append(f"   • {dep}")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════
if __name__ == "__main__":
    print(
        f"[Android Context Agent] 🚀 Memulai MCP Server...\n"
        f"   Root Proyek : {ROOT_DIR}\n"
        f"   Mode        : stdio\n"
        f"   Tools       : list_android_modules, read_source_file, search_code,\n"
        f"                 get_project_structure, analyze_manifest,\n"
        f"                 list_files_in_module, get_gradle_dependencies\n",
        file=sys.stderr
    )
    mcp.run(transport="stdio")