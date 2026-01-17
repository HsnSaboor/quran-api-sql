#!/usr/bin/env python3
"""
Quran Toon to SQLite Comprehensive Converter

Converts all toon files to SQLite databases optimized for HTTP Range Requests.
All output files are kept under 100MB for regular GitHub hosting.

Output Structure:
=================
/db/
  quran.db          - Uthmani text (1.6 MB)
  info.db           - Surah metadata (0.3 MB)
  tajweed.db        - Tajweed rules (3.4 MB)
  tajweed_glyphs.db - QPC v4 glyph codes (0.7 MB)
  mutashabihat.db   - Similar verses (0.1 MB)
  recitations.db    - Reciter metadata (0.01 MB)

/db/editions/
  index.db          - Edition metadata + chunk mapping (~0.1 MB)
  chunk_1.db        - Editions 1-60 translations (~95 MB)
  chunk_2.db        - Editions 61-120 translations (~95 MB)
  chunk_3.db        - Editions 121-180 translations (~95 MB)
  chunk_4.db        - Editions 181-240 translations (~95 MB)
  chunk_5.db        - Editions 241-294 translations (~95 MB)

/tafsirs/db/
  index.db          - Tafsir metadata (replaces master.db)
  {slug}.db         - Individual tafsir DBs (127 files, each <100MB)

HTTP Optimization:
- PRAGMA page_size = 4096 (optimal for Range Requests)
- PRAGMA journal_mode = DELETE
- VACUUM after creation
"""

import sqlite3
import os
import re
import json
from pathlib import Path
from datetime import datetime

# --- Configuration ---
TOON_REPO = Path("/home/saboor/code/quran-api-toon")
SQL_REPO = Path("/home/saboor/code/quran-api-sql")
DB_DIR = SQL_REPO / "db"
EDITIONS_DIR = DB_DIR / "editions"
TAFSIRS_DB_DIR = SQL_REPO / "tafsirs" / "db"

# Chunk size for editions (aim for ~45 editions per chunk to stay under 100MB)
EDITIONS_PER_CHUNK = 45

# Ensure output directories exist
DB_DIR.mkdir(parents=True, exist_ok=True)
EDITIONS_DIR.mkdir(parents=True, exist_ok=True)
TAFSIRS_DB_DIR.mkdir(parents=True, exist_ok=True)

# --- Utility Functions ---

def init_db(path, schema):
    """Initialize a database with HTTP-optimized settings."""
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    conn.isolation_level = None
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("PRAGMA journal_mode = DELETE;")
    conn.execute("PRAGMA synchronous = OFF;")
    conn.executescript(schema)
    return conn

def finalize_db(conn, path):
    """Optimize and close database."""
    print(f"  Optimizing {path.name}...")
    conn.execute("VACUUM;")
    conn.close()
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Created {path.name} ({size_mb:.2f} MB)")
    return size_mb

# --- Quran.toon Parser ---

def parse_quran_toon():
    """Parse quran.toon: c,v,text format."""
    quran_file = TOON_REPO / "quran.toon"
    ayahs = []

    with open(quran_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('quran['):
                continue

            match = re.match(r'\s*(\d+),(\d+),(.+)$', line)
            if match:
                surah = int(match.group(1))
                ayah = int(match.group(2))
                text = match.group(3).strip()
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]
                elif text.startswith('" ') and text.endswith('"'):
                    text = text[2:-1]
                ayahs.append((surah, ayah, text))

    return ayahs

def create_quran_db():
    """Create quran.db with Uthmani text."""
    print("\n=== Creating quran.db ===")

    schema = """
    CREATE TABLE ayahs (
        surah INTEGER,
        ayah INTEGER,
        text TEXT,
        PRIMARY KEY (surah, ayah)
    );
    CREATE INDEX idx_ayah_surah ON ayahs(surah);
    """

    db_path = DB_DIR / "quran.db"
    conn = init_db(db_path, schema)

    ayahs = parse_quran_toon()
    print(f"  Parsed {len(ayahs)} ayahs from quran.toon")

    conn.execute("BEGIN TRANSACTION")
    conn.executemany(
        "INSERT INTO ayahs (surah, ayah, text) VALUES (?, ?, ?)",
        ayahs
    )
    conn.execute("COMMIT")

    finalize_db(conn, db_path)

# --- Info.toon Parser (Surah Metadata) ---

def parse_info_toon():
    """Parse info.toon for surah metadata."""
    info_file = TOON_REPO / "info.toon"
    surahs = []
    current_surah = {}
    in_verses = False
    verses = []

    with open(info_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()

            if line.strip().startswith('- chapter:'):
                if current_surah:
                    current_surah['verses'] = verses
                    surahs.append(current_surah)
                current_surah = {'chapter': int(line.split(':')[1].strip())}
                verses = []
                in_verses = False
            elif line.strip().startswith('name:') and current_surah:
                current_surah['name'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('englishname:'):
                current_surah['englishname'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('arabicname:'):
                current_surah['arabicname'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('revelation:'):
                current_surah['revelation'] = line.split(':', 1)[1].strip()
            elif line.strip().startswith('verses['):
                in_verses = True
            elif in_verses and re.match(r'\s+\d+,', line):
                parts = line.strip().split(',')
                if len(parts) >= 8:
                    verses.append({
                        'verse': int(parts[0]),
                        'line': int(parts[1]),
                        'juz': int(parts[2]),
                        'manzil': int(parts[3]),
                        'page': int(parts[4]),
                        'ruku': int(parts[5]),
                        'maqra': int(parts[6]),
                        'sajda': parts[7].lower() == 'true'
                    })

        if current_surah:
            current_surah['verses'] = verses
            surahs.append(current_surah)

    return surahs

def create_info_db():
    """Create info.db with surah metadata and verse details."""
    print("\n=== Creating info.db ===")

    schema = """
    CREATE TABLE surahs (
        id INTEGER PRIMARY KEY,
        name TEXT,
        english_name TEXT,
        arabic_name TEXT,
        revelation TEXT,
        verse_count INTEGER
    );

    CREATE TABLE verse_info (
        surah INTEGER,
        ayah INTEGER,
        line INTEGER,
        juz INTEGER,
        manzil INTEGER,
        page INTEGER,
        ruku INTEGER,
        maqra INTEGER,
        sajda BOOLEAN,
        PRIMARY KEY (surah, ayah)
    );

    CREATE INDEX idx_verse_juz ON verse_info(juz);
    CREATE INDEX idx_verse_page ON verse_info(page);
    """

    db_path = DB_DIR / "info.db"
    conn = init_db(db_path, schema)

    surahs = parse_info_toon()
    print(f"  Parsed {len(surahs)} surahs from info.toon")

    conn.execute("BEGIN TRANSACTION")

    for s in surahs:
        conn.execute(
            "INSERT INTO surahs (id, name, english_name, arabic_name, revelation, verse_count) VALUES (?, ?, ?, ?, ?, ?)",
            (s.get('chapter'), s.get('name'), s.get('englishname'), s.get('arabicname'),
             s.get('revelation'), len(s.get('verses', [])))
        )

        for v in s.get('verses', []):
            conn.execute(
                "INSERT INTO verse_info VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (s['chapter'], v['verse'], v['line'], v['juz'], v['manzil'],
                 v['page'], v['ruku'], v['maqra'], v['sajda'])
            )

    conn.execute("COMMIT")
    finalize_db(conn, db_path)

# --- Editions Parser (Chunked) ---

def parse_editions_toon():
    """Parse editions.toon for edition metadata."""
    editions_file = TOON_REPO / "editions.toon"
    editions = []

    with open(editions_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('meta:') or line.startswith('editions['):
                continue

            parts = []
            current = ""
            in_quotes = False
            for char in line:
                if char == '"':
                    in_quotes = not in_quotes
                elif char == ',' and not in_quotes:
                    parts.append(current.strip().strip('"'))
                    current = ""
                else:
                    current += char
            parts.append(current.strip().strip('"'))

            if len(parts) >= 4:
                editions.append({
                    'id': parts[0],
                    'author': parts[1] if len(parts) > 1 else '',
                    'language': parts[2] if len(parts) > 2 else '',
                    'direction': parts[3] if len(parts) > 3 else 'ltr',
                    'source': parts[4] if len(parts) > 4 else '',
                    'note': parts[5] if len(parts) > 5 else ''
                })

    return editions

def parse_edition_toon_file(path):
    """Parse a single edition .toon file."""
    ayahs = []

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('quran['):
                continue

            match = re.match(r'\s*(\d+),(\d+),(.+)$', line)
            if match:
                surah = int(match.group(1))
                ayah = int(match.group(2))
                text = match.group(3).strip()
                if text.startswith('"') and text.endswith('"'):
                    text = text[1:-1]
                ayahs.append((surah, ayah, text))

    return ayahs

def create_editions_chunked():
    """Create chunked edition databases (each under 100MB)."""
    print("\n=== Creating Editions (Chunked) ===")

    editions = parse_editions_toon()
    print(f"  Found {len(editions)} editions in metadata")

    # Calculate chunks
    num_chunks = (len(editions) + EDITIONS_PER_CHUNK - 1) // EDITIONS_PER_CHUNK
    print(f"  Splitting into {num_chunks} chunks (~{EDITIONS_PER_CHUNK} editions each)")

    # --- Create Index DB ---
    index_schema = """
    CREATE TABLE editions (
        id INTEGER PRIMARY KEY,
        slug TEXT UNIQUE,
        author TEXT,
        language TEXT,
        direction TEXT,
        source TEXT,
        note TEXT,
        chunk_id INTEGER
    );
    CREATE INDEX idx_editions_lang ON editions(language);
    CREATE INDEX idx_editions_chunk ON editions(chunk_id);
    """

    index_path = EDITIONS_DIR / "index.db"
    index_conn = init_db(index_path, index_schema)

    # --- Create Chunk DBs ---
    chunk_schema = """
    CREATE TABLE translations (
        edition_id INTEGER,
        surah INTEGER,
        ayah INTEGER,
        text TEXT,
        PRIMARY KEY (edition_id, surah, ayah)
    );
    CREATE INDEX idx_trans_edition ON translations(edition_id);
    CREATE INDEX idx_trans_surah ON translations(surah);
    """

    editions_dir_toon = TOON_REPO / "editions"

    # Process in chunks
    for chunk_id in range(1, num_chunks + 1):
        start_idx = (chunk_id - 1) * EDITIONS_PER_CHUNK
        end_idx = min(chunk_id * EDITIONS_PER_CHUNK, len(editions))
        chunk_editions = editions[start_idx:end_idx]

        print(f"\n  Chunk {chunk_id}: editions {start_idx + 1} to {end_idx}")

        chunk_path = EDITIONS_DIR / f"chunk_{chunk_id}.db"
        chunk_conn = init_db(chunk_path, chunk_schema)

        for i, ed in enumerate(chunk_editions):
            edition_id = start_idx + i + 1  # 1-based global ID

            # Add to index with chunk mapping
            index_conn.execute(
                "INSERT INTO editions (id, slug, author, language, direction, source, note, chunk_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (edition_id, ed['id'], ed['author'], ed['language'], ed['direction'], ed['source'], ed['note'], chunk_id)
            )

            # Parse and add translations to chunk
            toon_file = editions_dir_toon / f"{ed['id']}.toon"
            if not toon_file.exists():
                continue

            ayahs = parse_edition_toon_file(toon_file)
            if ayahs:
                chunk_conn.execute("BEGIN TRANSACTION")
                chunk_conn.executemany(
                    "INSERT INTO translations (edition_id, surah, ayah, text) VALUES (?, ?, ?, ?)",
                    [(edition_id, s, a, t) for s, a, t in ayahs]
                )
                chunk_conn.execute("COMMIT")

        size = finalize_db(chunk_conn, chunk_path)
        if size > 100:
            print(f"  WARNING: Chunk {chunk_id} exceeds 100MB ({size:.2f} MB)")

    finalize_db(index_conn, index_path)

# --- Tajweed Parser ---

def parse_tajweed_toon():
    """Parse tajweed.toon for tajweed rules."""
    tajweed_file = TOON_REPO / "tajweed.toon"
    rules = []
    current_ayah = None
    surah = 0

    with open(tajweed_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()

            if line.strip().startswith('- c:'):
                surah = int(line.split(':')[1].strip())
            elif line.strip().startswith('v:'):
                ayah = int(line.split(':')[1].strip())
                current_ayah = (surah, ayah)
            elif line.strip().startswith('rules['):
                continue
            elif current_ayah and re.match(r'\s+\d+,\d+,\w+', line):
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    rules.append({
                        'surah': current_ayah[0],
                        'ayah': current_ayah[1],
                        'start': int(parts[0]),
                        'end': int(parts[1]),
                        'rule': parts[2]
                    })

    return rules

def create_tajweed_db():
    """Create tajweed.db with tajweed rules."""
    print("\n=== Creating tajweed.db ===")

    schema = """
    CREATE TABLE rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        surah INTEGER,
        ayah INTEGER,
        start_pos INTEGER,
        end_pos INTEGER,
        rule_type TEXT
    );

    CREATE INDEX idx_tajweed_ayah ON rules(surah, ayah);
    CREATE INDEX idx_tajweed_rule ON rules(rule_type);
    """

    db_path = DB_DIR / "tajweed.db"
    conn = init_db(db_path, schema)

    rules = parse_tajweed_toon()
    print(f"  Parsed {len(rules)} tajweed rules")

    conn.execute("BEGIN TRANSACTION")
    conn.executemany(
        "INSERT INTO rules (surah, ayah, start_pos, end_pos, rule_type) VALUES (?, ?, ?, ?, ?)",
        [(r['surah'], r['ayah'], r['start'], r['end'], r['rule']) for r in rules]
    )
    conn.execute("COMMIT")

    finalize_db(conn, db_path)

# --- Tajweed Glyphs Parser (QPC v4) ---

def parse_tajweed_glyphs():
    """Parse tajweed_glyphs/*.toon for QPC v4 glyph codes by page."""
    glyphs_dir = TOON_REPO / "quran" / "tajweed_glyphs"
    all_glyphs = []

    for page_file in sorted(glyphs_dir.glob("*.toon")):
        try:
            page_num = int(page_file.stem)
        except ValueError:
            continue

        with open(page_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('glyphs['):
                    continue

                match = re.match(r'(\d+),(\d+),"(.+)"', line)
                if match:
                    all_glyphs.append({
                        'page': page_num,
                        'surah': int(match.group(1)),
                        'ayah': int(match.group(2)),
                        'glyphs': match.group(3)
                    })

    return all_glyphs

def create_tajweed_glyphs_db():
    """Create tajweed_glyphs.db with QPC v4 glyph codes per page/verse."""
    print("\n=== Creating tajweed_glyphs.db ===")

    schema = """
    CREATE TABLE glyphs (
        page INTEGER,
        surah INTEGER,
        ayah INTEGER,
        glyph_text TEXT,
        PRIMARY KEY (page, surah, ayah)
    );

    CREATE INDEX idx_glyphs_page ON glyphs(page);
    CREATE INDEX idx_glyphs_surah ON glyphs(surah, ayah);
    """

    db_path = DB_DIR / "tajweed_glyphs.db"
    conn = init_db(db_path, schema)

    glyphs = parse_tajweed_glyphs()
    print(f"  Parsed {len(glyphs)} glyph entries from 604 pages")

    conn.execute("BEGIN TRANSACTION")
    conn.executemany(
        "INSERT INTO glyphs (page, surah, ayah, glyph_text) VALUES (?, ?, ?, ?)",
        [(g['page'], g['surah'], g['ayah'], g['glyphs']) for g in glyphs]
    )
    conn.execute("COMMIT")

    finalize_db(conn, db_path)

# --- Mutashabihat Parser ---

def parse_mutashabihat_toon():
    """Parse mutashabihat/data.toon for similar verses."""
    data_file = TOON_REPO / "mutashabihat" / "data.toon"
    entries = []

    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('['):
                continue

            match = re.match(r'"(\d+)","([^"]+)","([^"]+)"', line)
            if match:
                entries.append({
                    'id': int(match.group(1)),
                    'source': match.group(2),
                    'refs': match.group(3)
                })

    return entries

def create_mutashabihat_db():
    """Create mutashabihat.db with similar verse cross-references."""
    print("\n=== Creating mutashabihat.db ===")

    schema = """
    CREATE TABLE similarities (
        id INTEGER PRIMARY KEY,
        source_ref TEXT,
        similar_refs TEXT
    );

    CREATE INDEX idx_similar_source ON similarities(source_ref);
    """

    db_path = DB_DIR / "mutashabihat.db"
    conn = init_db(db_path, schema)

    entries = parse_mutashabihat_toon()
    print(f"  Parsed {len(entries)} similarity entries")

    conn.execute("BEGIN TRANSACTION")
    conn.executemany(
        "INSERT INTO similarities (id, source_ref, similar_refs) VALUES (?, ?, ?)",
        [(e['id'], e['source'], e['refs']) for e in entries]
    )
    conn.execute("COMMIT")

    finalize_db(conn, db_path)

# --- Recitations Parser ---

def parse_recitations_toon():
    """Parse recitations.toon for reciter metadata."""
    rec_file = TOON_REPO / "recitations.toon"
    reciters = []

    with open(rec_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('meta:') or line.startswith('reciters['):
                continue

            match = re.match(r'(\d+),([^,]+),([^,]*),(\d+)', line)
            if match:
                reciters.append({
                    'id': int(match.group(1)),
                    'name': match.group(2),
                    'style': match.group(3) or None,
                    'verses': int(match.group(4))
                })

    return reciters

def create_recitations_db():
    """Create recitations.db with reciter metadata."""
    print("\n=== Creating recitations.db ===")

    schema = """
    CREATE TABLE reciters (
        id INTEGER PRIMARY KEY,
        name TEXT,
        style TEXT,
        verse_count INTEGER
    );
    """

    db_path = DB_DIR / "recitations.db"
    conn = init_db(db_path, schema)

    reciters = parse_recitations_toon()
    print(f"  Parsed {len(reciters)} reciters")

    conn.execute("BEGIN TRANSACTION")
    conn.executemany(
        "INSERT INTO reciters (id, name, style, verse_count) VALUES (?, ?, ?, ?)",
        [(r['id'], r['name'], r['style'], r['verses']) for r in reciters]
    )
    conn.execute("COMMIT")

    finalize_db(conn, db_path)

# --- Tafsirs Index ---

def create_tafsirs_index():
    """Create tafsirs/db/index.db with metadata for all tafsirs (replaces master.db)."""
    print("\n=== Creating tafsirs/db/index.db ===")

    schema = """
    CREATE TABLE tafsirs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE,
        name TEXT,
        author TEXT,
        language TEXT,
        source TEXT,
        ayah_count INTEGER,
        file_size_bytes INTEGER
    );
    CREATE INDEX idx_tafsirs_lang ON tafsirs(language);
    """

    index_path = TAFSIRS_DB_DIR / "index.db"
    conn = init_db(index_path, schema)

    # Scan existing tafsir DBs
    tafsir_dbs = sorted(TAFSIRS_DB_DIR.glob("*.db"))
    tafsir_dbs = [f for f in tafsir_dbs if f.name not in ('index.db', 'master.db')]

    print(f"  Found {len(tafsir_dbs)} tafsir databases")

    conn.execute("BEGIN TRANSACTION")

    for db_file in tafsir_dbs:
        slug = db_file.stem
        file_size = db_file.stat().st_size

        # Read metadata from the tafsir DB
        try:
            tafsir_conn = sqlite3.connect(str(db_file))
            cursor = tafsir_conn.execute("SELECT COUNT(*) FROM ayahs")
            ayah_count = cursor.fetchone()[0]

            # Try to get metadata
            try:
                cursor = tafsir_conn.execute("SELECT value FROM metadata WHERE key = 'name'")
                row = cursor.fetchone()
                name = row[0] if row else slug
            except:
                name = slug

            try:
                cursor = tafsir_conn.execute("SELECT value FROM metadata WHERE key = 'author'")
                row = cursor.fetchone()
                author = row[0] if row else None
            except:
                author = None

            try:
                cursor = tafsir_conn.execute("SELECT value FROM metadata WHERE key = 'language'")
                row = cursor.fetchone()
                language = row[0] if row else None
            except:
                language = None

            try:
                cursor = tafsir_conn.execute("SELECT value FROM metadata WHERE key = 'source'")
                row = cursor.fetchone()
                source = row[0] if row else None
            except:
                source = None

            tafsir_conn.close()

            conn.execute(
                "INSERT INTO tafsirs (slug, name, author, language, source, ayah_count, file_size_bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (slug, name, author, language, source, ayah_count, file_size)
            )
        except Exception as e:
            print(f"    Warning: Could not read {slug}: {e}")

    conn.execute("COMMIT")
    finalize_db(conn, index_path)

# --- Main ---

def main():
    print("=" * 60)
    print("Quran Toon to SQLite Converter (Sub-100MB Files)")
    print(f"Source: {TOON_REPO}")
    print(f"Output: {DB_DIR}")
    print("=" * 60)

    start_time = datetime.now()

    # Convert all data types
    create_quran_db()
    create_info_db()
    create_editions_chunked()  # Chunked editions
    create_tajweed_db()
    create_tajweed_glyphs_db()
    create_mutashabihat_db()
    create_recitations_db()
    create_tafsirs_index()  # Index instead of master.db

    # Summary
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("CONVERSION COMPLETE")
    print(f"Time: {elapsed.total_seconds():.1f} seconds")
    print("\nGenerated Databases:")

    total_size = 0
    max_size = 0

    # Core DBs
    for db_file in sorted(DB_DIR.glob("*.db")):
        size_mb = db_file.stat().st_size / (1024 * 1024)
        total_size += size_mb
        max_size = max(max_size, size_mb)
        print(f"  {db_file.name}: {size_mb:.2f} MB")

    # Edition chunks
    for db_file in sorted(EDITIONS_DIR.glob("*.db")):
        size_mb = db_file.stat().st_size / (1024 * 1024)
        total_size += size_mb
        max_size = max(max_size, size_mb)
        print(f"  editions/{db_file.name}: {size_mb:.2f} MB")

    # Tafsirs index
    index_file = TAFSIRS_DB_DIR / "index.db"
    if index_file.exists():
        size_mb = index_file.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"  tafsirs/db/index.db: {size_mb:.2f} MB")

    print(f"\nTotal new DBs: {total_size:.2f} MB")
    print(f"Max file size: {max_size:.2f} MB")

    if max_size > 100:
        print("\n⚠️  WARNING: Some files exceed 100MB!")
    else:
        print("\n✅ All files under 100MB - ready for GitHub!")

    print("=" * 60)

if __name__ == "__main__":
    main()
