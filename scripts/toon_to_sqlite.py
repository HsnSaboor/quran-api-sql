#!/usr/bin/env python3
"""
Convert Unified Toon Tafsirs to SQLite Databases.
Generates:
1. Per-Edition DBs: tafsirs/db/{slug}.db
2. Master DB: tafsirs/db/master.db
"""
import sqlite3
import os
import json
from pathlib import Path

# Config
SRC_DIR = Path("tafsirs")
OUT_DIR = Path("tafsirs/db")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Schema
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS ayahs (
    surah INTEGER,
    ayah INTEGER,
    text TEXT,
    PRIMARY KEY (surah, ayah)
);
"""

MASTER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS editions (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE,
    name TEXT,
    author TEXT,
    language TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS tafsir_content (
    edition_id INTEGER,
    surah_id INTEGER,
    ayah_id INTEGER,
    text TEXT,
    PRIMARY KEY (edition_id, surah_id, ayah_id),
    FOREIGN KEY (edition_id) REFERENCES editions(id)
);

CREATE INDEX IF NOT EXISTS idx_content_lookup ON tafsir_content(edition_id, surah_id, ayah_id);
"""

def init_db(path, schema):
    conn = sqlite3.connect(path)
    conn.isolation_level = None  # Autocommit mode to allow VACUUM
    conn.executescript(schema)
    # Optimizations for HTTP VFS
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("PRAGMA journal_mode = DELETE;")
    conn.execute("PRAGMA synchronous = OFF;")
    return conn

def parse_toon_file(path):
    meta = {}
    ayahs = {}
    
    with open(path, 'r', encoding='utf-8') as f:
        in_ayahs = False
        for line in f:
            line = line.strip()
            if not line: continue
            
            if line.startswith("meta:"):
                continue
            elif line.startswith("ayahs["):
                in_ayahs = True
                continue
            
            if not in_ayahs:
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            else:
                # 1:1,"text..."
                if "," in line:
                    try:
                        key, val = line.split(",", 1)
                        # Remove quotes if present (standard JSON string)
                        val = json.loads(val)
                        surah, ayah = map(int, key.split(":"))
                        ayahs[(surah, ayah)] = val
                    except:
                        pass
    return meta, ayahs

def main():
    print(f"CWD: {os.getcwd()}")
    print(f"OUT_DIR absolute: {OUT_DIR.resolve()}")
    print("=== Generating SQLite Databases ===")
    
    # 1. Initialize Master DB
    master_path = OUT_DIR / "master.db"
    if master_path.exists(): master_path.unlink()
    master_conn = init_db(master_path, MASTER_SCHEMA_SQL)
    
    files = sorted(list(SRC_DIR.glob("*.toon")))
    files = [f for f in files if f.name != "editions.toon"]
    
    edition_id_counter = 1
    
    for i, f in enumerate(files):
        print(f"[{i+1}/{len(files)}] Processing {f.name}...")
        meta, ayahs = parse_toon_file(f)
        
        slug = meta.get("id", f.stem)
        
        # A. Create Per-Edition DB
        db_path = OUT_DIR / f"{slug}.db"
        if db_path.exists(): db_path.unlink()
        
        conn = init_db(db_path, SCHEMA_SQL)
        
        conn.execute("BEGIN TRANSACTION")
        # Insert Metadata
        conn.executemany("INSERT INTO metadata (key, value) VALUES (?, ?)", list(meta.items()))
        
        # Insert Ayahs
        conn.executemany("INSERT INTO ayahs (surah, ayah, text) VALUES (?, ?, ?)", 
                         [(s, a, t) for (s, a), t in ayahs.items()])
        conn.execute("COMMIT")
        
        # Optimize & Close
        conn.execute("VACUUM;")
        conn.close()
        
        # B. Insert into Master DB
        master_conn.execute("BEGIN TRANSACTION")
        master_conn.execute(
            "INSERT INTO editions (id, slug, name, author, language, source) VALUES (?, ?, ?, ?, ?, ?)",
            (edition_id_counter, slug, meta.get("name"), meta.get("author"), meta.get("language"), meta.get("source"))
        )
        
        master_conn.executemany(
            "INSERT INTO tafsir_content (edition_id, surah_id, ayah_id, text) VALUES (?, ?, ?, ?)",
            [(edition_id_counter, s, a, t) for (s, a), t in ayahs.items()]
        )
        master_conn.execute("COMMIT")
        
        edition_id_counter += 1

    # Finalize Master DB
    print("Optimizing Master DB (this may take a while)...")
    master_conn.execute("VACUUM;")
    master_conn.close()
    
    print(f"\n=== SUCCESS ===")
    print(f"Generated {len(files)} individual DBs")
    print(f"Generated master.db at {master_path}")

if __name__ == "__main__":
    main()
