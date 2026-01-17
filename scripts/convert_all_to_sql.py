#!/usr/bin/env python3
"""
Quran Toon to SQLite Comprehensive Converter

Converts all toon files to SQLite databases optimized for HTTP Range Requests.
This enables SQL-over-HTTP using libraries like wa-sqlite with HTTP VFS.

Data Types:
1. quran.db - Core Quran text with surah/ayah structure
2. editions.db - All 294+ translations in one DB with per-edition tables
3. tajweed.db - Tajweed rules per ayah (character position-based)
4. tajweed_glyphs.db - QPC v4 font glyph codes per page/verse
5. mutashabihat.db - Similar verses cross-references
6. recitations.db - Reciter metadata
7. info.db - Surah metadata (names, revelation, juz, pages, etc.)
8. tafsirs/db/*.db - Already converted (127 files)

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

# Ensure output directories exist
DB_DIR.mkdir(parents=True, exist_ok=True)

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

            # Format: "  1,1,text" or "  1,2,\"text\""
            match = re.match(r'\s*(\d+),(\d+),(.+)$', line)
            if match:
                surah = int(match.group(1))
                ayah = int(match.group(2))
                text = match.group(3).strip()
                # Remove surrounding quotes if present
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
                # Save previous surah
                if current_surah:
                    current_surah['verses'] = verses
                    surahs.append(current_surah)
                current_surah = {'chapter': int(line.split(':')[1].strip())}
                verses = []
                in_verses = False
            elif line.strip().startswith('name:') and 'current_surah' in dir():
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
                # verse,line,juz,manzil,page,ruku,maqra,sajda
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

        # Don't forget last surah
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

# --- Editions Parser ---

def parse_editions_toon():
    """Parse editions.toon for edition metadata."""
    editions_file = TOON_REPO / "editions.toon"
    editions = []

    with open(editions_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('meta:') or line.startswith('editions['):
                continue

            # Parse CSV-like: id,author,lang,dir,src,note
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

def create_editions_db():
    """Create editions.db with all translations."""
    print("\n=== Creating editions.db ===")

    schema = """
    CREATE TABLE editions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE,
        author TEXT,
        language TEXT,
        direction TEXT,
        source TEXT,
        note TEXT
    );

    CREATE TABLE translations (
        edition_id INTEGER,
        surah INTEGER,
        ayah INTEGER,
        text TEXT,
        PRIMARY KEY (edition_id, surah, ayah),
        FOREIGN KEY (edition_id) REFERENCES editions(id)
    );

    CREATE INDEX idx_trans_edition ON translations(edition_id);
    CREATE INDEX idx_trans_surah ON translations(surah);
    """

    db_path = DB_DIR / "editions.db"
    conn = init_db(db_path, schema)

    editions = parse_editions_toon()
    print(f"  Found {len(editions)} editions in metadata")

    conn.execute("BEGIN TRANSACTION")

    # Insert edition metadata
    for ed in editions:
        conn.execute(
            "INSERT INTO editions (slug, author, language, direction, source, note) VALUES (?, ?, ?, ?, ?, ?)",
            (ed['id'], ed['author'], ed['language'], ed['direction'], ed['source'], ed['note'])
        )

    conn.execute("COMMIT")

    # Process each edition's toon file
    editions_dir = TOON_REPO / "editions"
    processed = 0

    for ed in editions:
        toon_file = editions_dir / f"{ed['id']}.toon"
        if not toon_file.exists():
            continue

        # Get edition_id
        cursor = conn.execute("SELECT id FROM editions WHERE slug = ?", (ed['id'],))
        row = cursor.fetchone()
        if not row:
            continue
        edition_id = row[0]

        ayahs = parse_edition_toon_file(toon_file)

        if ayahs:
            conn.execute("BEGIN TRANSACTION")
            conn.executemany(
                "INSERT INTO translations (edition_id, surah, ayah, text) VALUES (?, ?, ?, ?)",
                [(edition_id, s, a, t) for s, a, t in ayahs]
            )
            conn.execute("COMMIT")

        processed += 1
        if processed % 50 == 0:
            print(f"  Processed {processed} editions...")

    print(f"  Total: {processed} editions processed")
    finalize_db(conn, db_path)

# --- Tajweed Parser ---

def parse_tajweed_toon():
    """Parse tajweed.toon for tajweed rules."""
    tajweed_file = TOON_REPO / "tajweed.toon"
    rules = []
    current_ayah = None

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
                # start,end,rule_type
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

            # Format: "id","source_ref","refs"
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

# --- Tajweed Glyphs Parser (QPC v4) ---

def parse_tajweed_glyphs():
    """Parse tajweed_glyphs/*.toon for QPC v4 glyph codes by page."""
    glyphs_dir = TOON_REPO / "quran" / "tajweed_glyphs"
    all_glyphs = []

    # 604 pages in Mushaf
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

                # Format: c,v,"glyph1|glyph2|..."
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

            # Format: id,name,style,verses
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

# --- Main ---

def main():
    print("=" * 60)
    print("Quran Toon to SQLite Converter")
    print(f"Source: {TOON_REPO}")
    print(f"Output: {DB_DIR}")
    print("=" * 60)

    start_time = datetime.now()

    # Convert all data types
    create_quran_db()
    create_info_db()
    create_editions_db()
    create_tajweed_db()
    create_tajweed_glyphs_db()
    create_mutashabihat_db()
    create_recitations_db()

    # Summary
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("CONVERSION COMPLETE")
    print(f"Time: {elapsed.total_seconds():.1f} seconds")
    print("\nGenerated Databases:")

    total_size = 0
    for db_file in sorted(DB_DIR.glob("*.db")):
        size_mb = db_file.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"  {db_file.name}: {size_mb:.2f} MB")

    print(f"\nTotal: {total_size:.2f} MB")
    print("\nNote: Tafsirs are already converted in tafsirs/db/")
    print("=" * 60)

if __name__ == "__main__":
    main()
