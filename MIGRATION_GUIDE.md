# Quran SQL Database Architecture Guide

## Overview

This repository provides SQLite databases optimized for **HTTP Range Requests**, enabling "SQL-over-HTTP" - clients can query databases without downloading the entire file.

### Key Design Principles
- **All files under 100MB** - Compatible with regular GitHub (no LFS needed)
- **Minimal file count** - Chunked editions vs 294 individual files
- **Zero API Backend** - Databases served as static files from CDN
- **Instant Queries** - HTTP Range Requests fetch only needed bytes (~4KB per query)

---

## Database Catalog

### Core Databases (`/db/`)

| Database | Size | Description |
|----------|------|-------------|
| `quran.db` | 1.6 MB | Uthmani Arabic text (6,236 ayahs) |
| `info.db` | 0.3 MB | Surah metadata (names, juz, pages, manzil, ruku, maqra, sajda) |
| `tajweed.db` | 3.4 MB | Tajweed rules (59,844 character position markers) |
| `tajweed_glyphs.db` | 0.7 MB | QPC v4 font glyph codes per page |
| `mutashabihat.db` | 0.1 MB | Similar verses cross-references (814 entries) |
| `recitations.db` | 0.01 MB | Reciter metadata (27 reciters) |

### Editions (Translations) - `/db/editions/`

294 translations split into 7 chunks for GitHub compatibility:

| Database | Size | Contents |
|----------|------|----------|
| `index.db` | 0.07 MB | Edition metadata + chunk mapping |
| `chunk_1.db` | ~74 MB | Editions 1-45 |
| `chunk_2.db` | ~55 MB | Editions 46-90 |
| `chunk_3.db` | ~66 MB | Editions 91-135 |
| `chunk_4.db` | ~98 MB | Editions 136-180 |
| `chunk_5.db` | ~68 MB | Editions 181-225 |
| `chunk_6.db` | ~75 MB | Editions 226-270 |
| `chunk_7.db` | ~39 MB | Editions 271-294 |

**Client Usage:**
1. Query `index.db` to find edition metadata and `chunk_id`
2. Query `chunk_{chunk_id}.db` for translations using `edition_id`

### Tafsir Databases (`/tafsirs/db/`)

| Database | Size | Description |
|----------|------|-------------|
| `index.db` | 0.04 MB | Tafsir metadata (replaces master.db) |
| `{slug}.db` | 0.5-67 MB | 126 individual tafsir databases |

All tafsir files are under 100MB each.

---

## Database Schemas

### quran.db
```sql
CREATE TABLE ayahs (
    surah INTEGER,
    ayah INTEGER,
    text TEXT,
    PRIMARY KEY (surah, ayah)
);
```

### info.db
```sql
CREATE TABLE surahs (
    id INTEGER PRIMARY KEY,
    name TEXT,
    english_name TEXT,
    arabic_name TEXT,
    revelation TEXT,  -- "Mecca" or "Madina"
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
```

### editions/index.db
```sql
CREATE TABLE editions (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE,
    author TEXT,
    language TEXT,
    direction TEXT,  -- "ltr" or "rtl"
    source TEXT,
    note TEXT,
    chunk_id INTEGER  -- Which chunk file contains this edition
);
```

### editions/chunk_N.db
```sql
CREATE TABLE translations (
    edition_id INTEGER,
    surah INTEGER,
    ayah INTEGER,
    text TEXT,
    PRIMARY KEY (edition_id, surah, ayah)
);
```

### tajweed.db
```sql
CREATE TABLE rules (
    id INTEGER PRIMARY KEY,
    surah INTEGER,
    ayah INTEGER,
    start_pos INTEGER,  -- Character start position
    end_pos INTEGER,    -- Character end position
    rule_type TEXT      -- e.g., "ghunnah", "idgham_shafawi", "madda_normal"
);
```

**Tajweed Rule Types:**
- `ghunnah`, `idgham_ghunnah`, `idgham_wo_ghunnah`
- `idgham_shafawi`, `idgham_mutajanisayn`, `idgham_mutaqaribayn`
- `ikhafa`, `ikhafa_shafawi`, `iqlab`
- `laam_shamsiyah`, `ham_wasl`
- `madda_normal`, `madda_necessary`, `madda_obligatory`, `madda_permissible`
- `qalaqah`, `slnt`

### tajweed_glyphs.db
```sql
CREATE TABLE glyphs (
    page INTEGER,       -- Mushaf page (1-604)
    surah INTEGER,
    ayah INTEGER,
    glyph_text TEXT,    -- Pipe-separated QPC v4 glyph codes
    PRIMARY KEY (page, surah, ayah)
);
```

### tafsirs/db/index.db
```sql
CREATE TABLE tafsirs (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE,
    name TEXT,
    author TEXT,
    language TEXT,
    source TEXT,
    ayah_count INTEGER,
    file_size_bytes INTEGER
);
```

### tafsirs/db/{slug}.db
```sql
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE ayahs (
    surah INTEGER,
    ayah INTEGER,
    text TEXT,
    PRIMARY KEY (surah, ayah)
);
```

---

## HTTP Range Request Implementation

### How It Works

1. SQLite engine requests "Page 42"
2. VFS driver calculates byte offset: `42 × 4096`
3. Browser sends: `Range: bytes=172032-176128`
4. CDN returns just that 4KB chunk
5. User gets instant query results

### Technology Stack

**Web (Browser/PWA):**
- [`wa-sqlite`](https://github.com/rhashimoto/wa-sqlite) with HTTP VFS
- Enables querying remote SQLite files without full download

**Mobile (React Native):**
- [`op-sqlite`](https://github.com/OP-Engineering/op-sqlite) or `react-native-quick-sqlite`
- Download databases to local storage, query natively

---

## Query Examples

### Get Surah Al-Fatiha
```sql
-- From quran.db
SELECT * FROM ayahs WHERE surah = 1;
```

### Get English Translation (Chunked Approach)
```sql
-- Step 1: Query index.db to find edition
SELECT id, chunk_id FROM editions WHERE slug = 'eng-sahih';
-- Returns: id=75, chunk_id=2

-- Step 2: Query chunk_2.db
SELECT text FROM translations
WHERE edition_id = 75 AND surah = 2 AND ayah = 255;
```

### Get Tajweed Rules for an Ayah
```sql
-- From tajweed.db
SELECT start_pos, end_pos, rule_type
FROM rules
WHERE surah = 1 AND ayah = 1;
```

### Get Page 1 Glyph Codes
```sql
-- From tajweed_glyphs.db
SELECT * FROM glyphs WHERE page = 1;
```

### Get All Ayahs in Juz 30
```sql
-- Cross-database query (client-side join)
-- 1. From info.db: get surah/ayah for juz 30
SELECT surah, ayah FROM verse_info WHERE juz = 30;

-- 2. From quran.db: get text for those ayahs
SELECT text FROM ayahs WHERE surah = ? AND ayah = ?;
```

### List Available Tafsirs
```sql
-- From tafsirs/db/index.db
SELECT slug, name, language, ayah_count
FROM tafsirs
ORDER BY language, name;
```

---

## Conversion Script

To regenerate databases from source `.toon` files:

```bash
cd /path/to/quran-api-sql
python3 scripts/convert_all_to_sql.py
```

This creates all databases with HTTP-optimized settings:
- `PRAGMA page_size = 4096`
- `PRAGMA journal_mode = DELETE`
- `VACUUM` for minimal size

---

## File Size Summary

| Category | Files | Total Size | Max File |
|----------|-------|------------|----------|
| Core DBs | 6 | ~6 MB | 3.4 MB |
| Edition chunks | 8 | ~475 MB | 98 MB |
| Tafsir DBs | 127 | ~1.3 GB | 67 MB |

**All files under 100MB** ✅ - No Git LFS required!
