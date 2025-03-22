### Database Schema

The project uses **SQLite** to implement the database schema for the web crawler and indexer. Below is an explanation of the schema design, including tables and their purposes, along with how they support the system's functionality:

---

#### **1. `webpages` Table (Forward Index)**
This table stores **metadata for each crawled webpage**, acting as a **forward index** (URL → document properties).  
**Schema Definition**:
```sql
CREATE TABLE IF NOT EXISTS webpages (
    url TEXT PRIMARY KEY,
    title TEXT,
    date TEXT,
    size INTEGER,
    body_keywords TEXT,
    parent_links TEXT,
    child_links TEXT,
    is_start INTEGER
);
```

**Columns**:
- **`url`**: Unique identifier for the webpage (primary key).
- **`title`**: Title of the webpage.
- **`date`**: Last modified date (stored as ISO-formatted string).
- **`size`**: Size of the webpage in bytes.
- **`body_keywords`**: Comma-separated string of keywords and their frequencies (e.g., `"apple:3,banana:2"`).
- **`parent_links`**: Comma-separated list of URLs linking to this page.
- **`child_links`**: Comma-separated list of URLs this page links to.
- **`is_start`**: Boolean flag (`1`/`0`) indicating if this is the starting URL of the crawl.

**Purpose**:
- Stores all crawled webpages with their metadata.
- Tracks the **link graph** (parent/child relationships).
- Maintains **keyword frequency** in the body for indexing.

---

#### **2. `inverted_index` Table (Inverted Index)**
This table implements the **inverted index** (keyword → list of documents containing the keyword). There are **two separate databases** for clarity:
- **`body_inverted_index.db`**: For body keywords.
- **`title_inverted_index.db`**: For title keywords.

**Schema Definition**:
```sql
CREATE TABLE IF NOT EXISTS inverted_index (
    keyword TEXT PRIMARY KEY,
    postings TEXT
);
```

**Columns**:
- **`keyword`**: Keywords (e.g., "appl" for "apple").
- **`postings`**: Serialized postings list for the keyword. Each entry is formatted as:
  ```
  "url:tf:tf-idf,url:tf:tf-idf,..."
  ```
  Example: `"https://example.com:3:0.5678,https://test.com:2:0.3456"`.

**Purpose**:
- Maps keywords to documents (URLs) where they appear.
- Stores **TF-IDF scores** for ranking search results.

---

#### **3. Key Design Choices**
1. **No Page IDs or Word IDs**:
   - **URLs** are used directly as document identifiers instead of numeric IDs. This simplifies the schema but may impact performance for very large datasets.
   - **Keywords** are stored as strings without numeric IDs, leveraging SQLite’s text indexing.

2. **Serialized Data Storage**:
   - **`body_keywords`**, **`parent_links`**, **`child_links`**, and **`postings`** are stored as comma-separated strings. This avoids complex join operations but requires parsing when querying.
   - Example: `body_keywords` stores `"apple:3,banana:2"` instead of a separate table for term frequencies.

3. **Separate Databases for Body/Title Indexes**:
   - **`body_inverted_index.db`** and **`title_inverted_index.db`** are separate databases to distinguish between body and title keywords. This allows independent management and querying of each index.

4. **TF-IDF Storage**:
   - TF-IDF scores are precomputed and stored in the inverted index. This avoids real-time computation during search, improving query performance.

---

#### **4. Supporting Tables and Functions**
- **`is_start` Flag**: Identifies the starting URL of the crawl, enabling resumption of crawling from the same point.
- **`date` Field**: Tracks the last modified time of pages to avoid re-crawling unchanged pages.
- **`load_stopwords` Function**: Loads a list of stop words to filter out common words (e.g., "the", "and").