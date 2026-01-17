# Quran SQL Database Architecture Guide

## Overview

This repository provides SQLite databases optimized for **HTTP Range Requests**, enabling "SQL-over-HTTP" - clients can query databases without downloading the entire file.

### Key Benefits
- **Zero API Backend**: Databases served as static files from CDN
- **Instant Queries**: HTTP Range Requests fetch only needed bytes (~4KB per query)
- **Massive Compression**: 700,000+ files → ~10 databases
- **Native Performance**: Direct SQLite on mobile apps

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
| `editions.db`* | 475 MB | All 294 translations combined |

*Large files require CDN hosting with Range Request support

### Tafsir Databases (`/tafsirs/db/`)

| Pattern | Count | Size Range | Description |
|---------|-------|------------|-------------|
| `{slug}.db` | 127 | 0.5-67 MB | Individual tafsir databases |
| `master.db`* | 1 | 1.5 GB | All tafsirs combined (for global search) |

*Large files require CDN hosting with Range Request support

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

### editions.db
```sql
CREATE TABLE editions (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE,
    author TEXT,
    language TEXT,
    direction TEXT,  -- "ltr" or "rtl"
    source TEXT,
    note TEXT
);

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

The `glyph_text` contains pipe-separated (`|`) glyph codes where each segment = one word. Use with QPC v4 fonts.

### mutashabihat.db
```sql
CREATE TABLE similarities (
    id INTEGER PRIMARY KEY,
    source_ref TEXT,     -- e.g., "2:23:15-17"
    similar_refs TEXT    -- Semicolon-separated refs
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

### Technology Stack

**Web (Browser/PWA):**
- [`wa-sqlite`](https://github.com/rhashimoto/wa-sqlite) with HTTP VFS
- Enables querying remote SQLite files without full download

**Mobile (React Native):**
- [`op-sqlite`](https://github.com/OP-Engineering/op-sqlite) or `react-native-quick-sqlite`
- Download databases to local storage, query natively

### How It Works

1. SQLite engine requests "Page 42"
2. VFS driver calculates byte offset: `42 × 4096`
3. Browser sends: `Range: bytes=172032-176128`
4. CDN returns just that 4KB chunk
5. User gets instant query results

### CDN Setup

Host databases on a CDN with CORS and Range Request support:

```
Base URL: https://cdn.example.com/quran-sql/
         /db/quran.db
         /db/info.db
         /db/tajweed.db
         /tafsirs/db/{slug}.db
```

---

## Query Examples

### Get Surah Al-Fatiha
```sql
SELECT * FROM ayahs WHERE surah = 1;
```

### Get English Translation
```sql
SELECT t.text
FROM translations t
JOIN editions e ON t.edition_id = e.id
WHERE e.slug = 'eng-sahih' AND t.surah = 2 AND t.ayah = 255;
```

### Get Tajweed Rules for an Ayah
```sql
SELECT start_pos, end_pos, rule_type
FROM rules
WHERE surah = 1 AND ayah = 1;
```

### Get Page 1 Glyph Codes
```sql
SELECT * FROM glyphs WHERE page = 1;
```

### Get All Ayahs in Juz 30
```sql
SELECT q.surah, q.ayah, q.text
FROM ayahs q
JOIN verse_info v ON q.surah = v.surah AND q.ayah = v.ayah
WHERE v.juz = 30;
```

---

## Conversion Script

To regenerate databases from source `.toon` files:

```bash
cd /path/to/quran-api-sql
python3 scripts/convert_all_to_sql.py
```

This creates all databases in `/db/` with HTTP-optimized settings:
- `PRAGMA page_size = 4096`
- `PRAGMA journal_mode = DELETE`
- `VACUUM` for minimal size

---

## File Size Reference

| Database | Regular Git | Requires |
|----------|-------------|----------|
| quran.db | ✅ | - |
| info.db | ✅ | - |
| tajweed.db | ✅ | - |
| tajweed_glyphs.db | ✅ | - |
| mutashabihat.db | ✅ | - |
| recitations.db | ✅ | - |
| editions.db | ❌ | LFS or CDN |
| tafsirs/db/*.db | ✅* | - |
| tafsirs/db/master.db | ❌ | LFS or CDN |

*Individual tafsir DBs are under 100MB each
