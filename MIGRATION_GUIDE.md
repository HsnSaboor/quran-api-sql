# Quran App Migration & Architecture Guide

## 1. Core Architecture Strategy: "SQLite-First"

Instead of managing 700,000+ text files, the entire application will rely on **SQLite** databases served via CDN. This enables:
1. **Instant Web Access:** Using HTTP Range Requests (fetching only the needed bytes).
2. **Native Performance:** Direct file access on mobile.
3. **Zero-API Backend:** The "API" is just the hosted SQLite file on jsDelivr.

---

## 2. Database Schema

### A. `quran.db` (Core Text & Metadata)
Contains the Uthmani text, simple translations, and structural metadata. Small (~10MB), downloaded fully.

```sql
CREATE TABLE surahs (
  id INTEGER PRIMARY KEY,
  name_simple TEXT,
  name_arabic TEXT,
  verse_count INTEGER
);

CREATE TABLE ayahs (
  id INTEGER PRIMARY KEY, -- 1 to 6236
  surah_id INTEGER,
  ayah_number INTEGER,
  text_uthmani TEXT,
  FOREIGN KEY(surah_id) REFERENCES surahs(id)
);
```

### B. `tafsirs.db` (The Massive Archive)
Contains all 125+ Tafsirs. Large (~1.5GB), streamed on Web, downloaded on demand on Mobile.

```sql
CREATE TABLE editions (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE,       -- e.g., 'en-ibn-kathir'
  name TEXT,
  author TEXT,
  language TEXT,
  source TEXT,
  direction TEXT
);

CREATE TABLE tafsir_content (
  edition_id INTEGER,
  surah_id INTEGER,
  ayah_id INTEGER,
  text TEXT,              -- The actual HTML/Text content
  PRIMARY KEY (edition_id, surah_id, ayah_id),
  FOREIGN KEY (edition_id) REFERENCES editions(id)
);

-- Indexes for speed
CREATE INDEX idx_tafsir_lookup ON tafsir_content(edition_id, surah_id, ayah_id);
```

---

## 3. Technology Stack

### Web (Browser / PWA)
- **Library:** [`wa-sqlite`](https://github.com/rhashimoto/wa-sqlite)
  - **Why:** Faster than `sql.js`, supports Asyncify, enables VFS.
- **VFS Driver:** [`wa-sqlite` HTTP VFS](https://github.com/rhashimoto/wa-sqlite/tree/master/src/examples)
  - **Why:** Allows querying a remote DB file without downloading it.
- **State Management:** TanStack Query (React Query)

### Mobile (Native)
- **Library:** [`op-sqlite`](https://github.com/OP-Engineering/op-sqlite) or [`react-native-quick-sqlite`](https://github.com/margelo/react-native-quick-sqlite)
  - **Why:** Direct C++ bindings to SQLite. 10x faster than standard bridges.
- **FS Access:** `expo-file-system`
  - **Why:** Downloading the `.db` files from CDN to local storage.

---

## 4. API Endpoints (Static Files)

**Base URL:** `https://cdn.jsdelivr.net/gh/{user}/{repo}@{version}/`

| Resource | Endpoint | Format | Usage |
| :--- | :--- | :--- | :--- |
| **Tafsir Index** | `/tafsirs/editions.toon` | JSON/Toon | List available resources |
| **Per-Edition DB** | `/tafsirs/db/{slug}.db` | SQLite (10-50MB) | Mobile Download & Web Reading |
| **Master DB** | `/tafsirs/db/master.db` | SQLite (1.5GB) | Web Global Search (Streaming) |

---

## 5. Migration Guide (Toon -> SQLite)

### Step 1: Generate Databases
Run the script `scripts/toon_to_sqlite.py` (to be created):
1. Iterates through `tafsirs/*.toon`.
2. Creates a per-edition DB (`tafsirs/db/{id}.db`).
   - Optimizations: `PRAGMA page_size=4096; VACUUM;`.
3. Merges all into `tafsirs/db/master.db` (optional).

### Step 2: Optimization for Web Streaming
To allow "streaming" SQL queries from the web, the DB needs specific optimizations:
```sql
PRAGMA journal_mode = DELETE;
PRAGMA page_size = 4096;  -- Optimal for HTTP requests
VACUUM;
```

### Step 3: Web Implementation Strategy
**"Lazy VFS" Pattern:**
1. **Default:** Load the specific `edition.db` (~15MB) into IndexedDB (IDB-VFS). This is fast and persistent.
2. **Search:** Mount the `master.db` (1.5GB) via HTTP-VFS for "Global Search" (search across all tafsirs).

**How HTTP Streaming Works (Magic Byte Ranges):**
The client developer does **not** calculate ranges manually. The `wa-sqlite` VFS driver handles it:
1. **SQLite Engine:** Requests "Page 42".
2. **VFS Driver:** Calculates offset `42 * 4096`.
3. **Browser:** Sends `Range: bytes=172032-176128`.
4. **CDN:** Returns just that 4KB chunk.

### Step 4: Mobile Implementation Strategy
**"Download & Cache" Pattern:**
1. **Check:** If `local_tafsirs/{id}.db` exists.
2. **Download:** If not, fetch `https://cdn.../tafsirs/db/{id}.db`.
3. **Query:** Open via `react-native-quick-sqlite`.

---

## 6. Developer Workflow
1. **Add new Tafsir:** Add `.toon` file -> Run `toon_to_sqlite.py` -> Upload `.db`.
2. **Update Metadata:** Edit `editions.toon` -> Re-run script.
