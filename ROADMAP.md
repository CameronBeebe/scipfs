# SciPFS Development Roadmap: Content-Aware IPFS Libraries

## Core Goal

Transform scipfs from a basic file-sharing tool into an intelligent library manager that understands and leverages the **content** of files stored on IPFS. The key differentiator will be an LLM-powered intelligence layer for semantic understanding, search, organization, and interoperability.

## Guiding Principles

- **Incremental Value:** Each phase and feature should deliver tangible benefits to users
- **Leverage Existing Strengths:** Build upon scipfs's current IPFS file handling, manifest management, and CLI structure
- **Modularity:** Design components (e.g., LLM interaction, text extraction) to be modular and replaceable
- **User Experience:** Keep the CLI intuitive and provide clear feedback, especially for new AI-driven features
- **Configuration over Hardcoding:** Allow users to configure LLM providers, API keys (via environment variables), and other preferences
- **Feasibility First:** Prioritize concrete, achievable steps over "pie-in-the-sky" ideas, with clear feasibility assessments

---

## Phase 0: Codebase Refinement & Robustness

**Priority:** Critical (Before Phase 1)
**Overall Feasibility:** High
**Goal:** Strengthen the existing codebase to ensure stability, maintainability, and easier extension for future LLM features.

### 0.1. Enhanced `IPFSClient` Robustness (`scipfs/ipfs.py`)
**Description:** Improve the reliability and error handling of IPFS interactions.
**Implementation Details:**
- **Standardized Go Helper Error Handling:** Ensure all interactions with `scipfs_go_helper` have consistent error parsing (JSON error messages from Go), propagate errors as custom `SciPFSException` subtypes, and provide clear logging.
- **Retry Mechanisms:** Implement basic retry logic with backoff for critical network-dependent IPFS operations (e.g., `publish_to_ipns`, `resolve_ipns_name`, `get_json`), especially for IPNS calls.
- **Go Helper Health Check:** Consider a dedicated `check_health()` method in `IPFSClient` (callable by `scipfs doctor`) to verify Go helper and daemon status.
**Feasibility:** High

### 0.2. `Library` Class Refinements (`scipfs/library.py`)
**Description:** Improve manifest management and the `add_file` process.
**Implementation Details:**
- **Manifest Versioning:** Introduce a `manifest_format_version` field (e.g., "1.0") within the manifest JSON itself. Update `_load_manifest` to check this version to handle future schema changes gracefully.
- **Clearer `_save_manifest()` Separation (Consideration):** Evaluate if `_save_manifest()` needs more granular internal methods for scenarios like partial metadata updates (more relevant for async tasks later, but good to review).
- **`add_file()` Transactionality & LLM Prep:** As `add_file` will be extended for text extraction and LLM processing, plan how to handle partial failures (e.g., file added to IPFS, but LLM step fails). The `llm_processing_status` field (planned for Phase 1) will be key here. Ensure the initial file addition remains robust.
**Feasibility:** High

### 0.3. Configuration Enhancements (`scipfs/config.py` & `scipfs/llm_config.py`)
**Description:** Improve configuration management.
**Implementation Details:**
- **Typed Configuration (Consideration):** For `scipfs/config.py` and `scipfs/llm_config.py`, explore using Pydantic or similar for loading, validating, and accessing config options, especially as complexity grows.
- **API Key Access Alignment:** Ensure `scipfs/config.py` (for user preferences like default provider/model) correctly interacts with `scipfs/llm_config.py` (which handles actual API key retrieval from env vars and provider-specifics).
**Feasibility:** Medium (Pydantic is an added dependency if used)

### 0.4. CLI Enhancements (`scipfs/cli.py`)
**Description:** Improve user experience and utility of the CLI.
**Implementation Details:**
- **`scipfs file-info` Command:** Implement a new command `scipfs file-info <library_name> <file_name>` to display all currently stored metadata for a specific file (CID, size, adder, timestamp, and future LLM metadata).
- **Consistent Output Styling:** Review and standardize CLI output for clarity and consistency, possibly using more of `click`'s styling features.
- **`--yes` Flag (Consideration):** For commands that might involve significant changes or costs (like future LLM calls), consider adding a `--yes` flag to bypass interactive confirmations.
**Feasibility:** High for `file-info` and styling; Medium for `--yes` flag logic if complex confirmations arise.

### 0.5. Enhanced Logging
**Description:** Improve logging for better debugging and monitoring.
**Implementation Details:**
- **Structured Logging (Consideration):** Explore outputting log entries in a structured format (e.g., JSON) for easier parsing by log management tools, especially for complex operations or background tasks.
- **Contextual Logging:** Ensure log messages include relevant context (e.g., library name, file name, operation type) to facilitate easier tracing of operations.
**Feasibility:** Medium

### 0.6. Go Helper Refinements (`scipfs_go_wrapper.go`)
**Description:** Ensure robustness of the Go helper component.
**Implementation Details:**
- **Input Sanitization/Validation:** Review and ensure robust handling of all inputs received from the Python layer (file paths, CIDs, key names).
- **Structured JSON Error Reporting:** Verify that all error paths in the Go helper return well-formed JSON error messages to `stderr`, allowing `scipfs/ipfs.py` to parse them reliably and consistently.
**Feasibility:** High

---

## Phase 1: Foundational LLM Integration & Content Processing

**Priority:** High  
**Overall Feasibility:** High - Relies on well-established Python libraries and standard API integrations
**Developer Notes:**
- A separate `scipfs/llm_config.py` will be created to manage LLM provider details (API key env vars, default models) and global LLM call parameters (max tokens, temperature, etc.), keeping it distinct from `scipfs/config.py` which handles user/library settings.
- Skeletons for `scipfs/text_extractor.py` and `scipfs/llm_utils.py` will be created as starting points.
- The library manifest structure will require significant updates (see 1.5) to store new metadata like `extracted_text_cid`, `summary`, `tags`, and processing status.
- A `manifest_format_version` field should be added to the manifest to help manage schema changes over time.

### 1.1. Configuration for LLM API Keys & Provider Choice

**Description:** Securely manage LLM API keys and allow users to choose their preferred LLM provider and model.
**Developer Note:** API Key management and provider choice will be handled by the new `scipfs/llm_config.py`. The main `scipfs/config.py` might store user *preferences* for default provider/model, which `llm_utils.py` would then use in conjunction with `llm_config.py`.

#### Implementation Details

**Files:** `scipfs/config.py` (for user preferences), `scipfs/llm_config.py` (new, for provider details & API key access), `scipfs/cli.py`

**Python Functionality:**

- `SciPFSConfig` class in `config.py`:
  - Methods to set/get user's preferred LLM provider and model (e.g., `set_user_default_llm_provider`, `get_user_default_llm_model`). These preferences are stored in `~/.scipfs/config.json`.
- `GlobalLLMConfig` class in `llm_config.py` (new):
  - Manages a list of known LLM providers (e.g., OpenAI, Anthropic).
  - For each provider, defines how to get the API key (e.g., from `SCIPFS_OPENAI_API_KEY`).
  - Stores default models for each provider, and global defaults for LLM call parameters (max_tokens, temperature).
  - Provides methods like `get_api_key(provider_name)`, `get_model_for_task(provider_name, task_type)`.
- New CLI commands in `cli.py` using `click`:
  - `scipfs config set default_llm_provider <openai|anthropic|custom_url>`
  - `scipfs config set default_llm_model <model_name_or_identifier>` (perhaps per provider)
  - `scipfs config get default_llm_provider`
  - `scipfs config get default_llm_model`

**Data:** API keys remain in environment variables. `~/.scipfs/config.json` stores provider choice and model.

**LLM Integration:** Indirect; sets up credentials.

#### Acceptance Criteria

- User can set/get LLM provider and model
- SciPFS accesses API keys from environment variables
- Keys NOT in config file/logs

**Feasibility:** High - Standard config and environment variable handling

### 1.2. Text Extraction from Files

**Description:** Extract plain text content from uploaded files.

#### Implementation Details

**Files:** `scipfs/text_extractor.py` (new - skeleton created), `scipfs/library.py`

**Python Functionality:**

- `text_extractor.py`:

```python
# scipfs/text_extractor.py (pseudocode)
from pathlib import Path
from typing import Optional
import PyPDF2  # Example for PDF
# import python-docx, openpyxl, etc.
# import logging

def extract_text(file_path: Path) -> Optional[str]:
    try:
        if file_path.suffix == '.pdf':
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                return "".join(page.extract_text() for page in reader.pages if page.extract_text())
        elif file_path.suffix == '.txt' or file_path.suffix == '.md':
            return file_path.read_text()
        # Add more handlers for .docx, .pptx, .xlsx
        else:
            # logger.warning(f"Unsupported file type for text extraction: {file_path.suffix}")
            return None
    except Exception as e:
        # logger.error(f"Error extracting text from {file_path}: {e}")
        return None
```

- `library.py`: `Library.add_file()` calls `extract_text()`

**Data Strategy (Option B preferred for scalability):**

1. Extract text
2. If text is substantial, save as `original_filename_extracted.txt`
3. Add this text file to IPFS: `extracted_text_cid = ipfs_client.add_file(extracted_text_path)`
4. Store `extracted_text_cid` in the manifest
5. If text is very small (e.g. < 1KB), consider storing directly in manifest `extracted_text_short` for quick access, but still prefer `extracted_text_cid` for consistency

**LLM Integration:** None directly

#### Acceptance Criteria

- Text extracted from PDF, TXT, DOCX
- `extracted_text_cid` (or short text) stored in manifest

**Feasibility:** High for common formats; Medium for very broad format support (might need Tika)

### 1.3. LLM-Powered Content Summarization

**Description:** Generate a concise summary of the file's content.

#### Implementation Details

**Files:** `scipfs/llm_utils.py` (new - skeleton created), `scipfs/library.py`, `scipfs/llm_config.py` (used by `llm_utils.py`)

**Python Functionality:**

- `llm_utils.py`:

```python
# scipfs/llm_utils.py (pseudocode)
# import openai, anthropic
# from .config import SciPFSConfig
from typing import Optional

class LLMClient:
    def __init__(self, config: SciPFSConfig):
        self.provider = config.get_llm_provider()
        self.model = config.get_llm_model()
        self.api_key = config.get_api_key(self.provider)
        # Initialize actual client

    def summarize(self, text: str, max_tokens_summary: int = 150) -> Optional[str]:
        if not self.api_key or not self.client: 
            return None
        
        prompt = f"""Summarize the following text concisely (around {max_tokens_summary // 4}-{max_tokens_summary // 3} words):

{text}"""
        
        # Make API call using self.client, handle retries/errors
        # Example for OpenAI:
        # response = self.client.chat.completions.create(
        #     model=self.model,
        #     messages=[{"role": "user", "content": prompt}],
        #     max_tokens=max_tokens_summary
        # )
        # return response.choices[0].message.content
        return "Placeholder summary"  # Placeholder
```

- `library.py`: In `Library.add_file()`, after getting text (from CID or direct), call `llm_client.summarize()`

**Data:** Store summary in manifest: `file_entry["summary"] = "..."`

**LLM Integration:** Direct API calls. Use cost-effective models (e.g., `gpt-4o-mini`, `claude-3-haiku`). Truncate long texts before sending to LLM to manage token limits/costs if full text CID isn't used.

#### Acceptance Criteria

- Summary generated and stored
- Concise and relevant

**Feasibility:** High - Standard LLM API interaction

### 1.4. LLM-Powered Keyword/Tag Generation

**Description:** Automatically generate relevant keywords/tags.

#### Implementation Details

**Files:** `scipfs/llm_utils.py`, `scipfs/library.py`

**Python Functionality:**

- `llm_utils.py`: `LLMClient.generate_tags(text: str, num_tags: int = 5) -> Optional[list[str]]`:
  - Prompt: `f"Extract the {num_tags} most relevant keywords or tags from this text. Return as a JSON list of strings. Example: [\"tag1\", \"tag2\"] Text: {text}"`
  - Parse JSON response

**Data:** Store tags in manifest: `file_entry["tags"] = ["keyword1", ...]`

#### Acceptance Criteria

- Relevant tags generated and stored as a list

**Feasibility:** High

### 1.5. Manifest Structure & CLI Updates for New Metadata

**Description:** Update manifest and CLI for new metadata.
**Developer Note:** The manifest structure needs to accommodate CIDs for extracted text, summaries, tags, processing status, and potentially which LLM was used. A `manifest_format_version` field should be added.

#### Implementation Details

**Files:** `scipfs/library.py`, `scipfs/cli.py`

**Updated Manifest Structure (example entry in `files` dict):**

```json
{
    "example.pdf": {
        "cid": "QmOriginal...",
        "size": 12345,
        "added_by": "user_x",
        "added_timestamp": 1678886400,
        "original_file_type": ".pdf",
        "extracted_text_cid": "QmText...",
        "summary": "This document discusses advanced techniques...",
        "tags": ["ai", "decentralization", "ipfs"],
        "llm_processing_status": "completed", // e.g., "pending", "failed_extraction", "failed_summary"
        "llm_provider_info": {"provider": "openai", "model": "gpt-4o-mini"}, // Optional: record what generated the content
        "bibtex_cid": "QmBibtex..."
    }
}
```

**Overall Manifest Structure:**
```json
{
    "manifest_format_version": "1.1", // Or similar semantic version
    "name": "my_library",
    "ipns_name": "/ipns/...",
    "ipns_key_name": "my_library",
    "latest_manifest_cid": "QmCurrentManifest...",
    "files": {
        // ... file entries as above ...
    }
}
```

**CLI Updates:**

- `scipfs list <library_name> [--show-summaries] [--show-tags]`
- `scipfs file-info <library_name> <file_name>` (displays all metadata)

#### Acceptance Criteria

- Manifest correctly stores/loads all new fields
- CLI displays new metadata

**Feasibility:** High

---

## Phase 2: Enhanced Discovery, Interoperability & Advanced Storage

**Priority:** Medium-High - Focus on making libraries more useful and integrated  
**Overall Feasibility:** Medium - Some features introduce more complexity or external dependencies

### 2.1. Basic Semantic Search (LLM-based, no vector DB)

**Description:** Search within a library based on semantic meaning.

#### Implementation Details

**Files:** `scipfs/search.py` (new), `scipfs/cli.py`, `scipfs/llm_utils.py`

**Python Functionality:**

- `search.py`: `semantic_search_library(library: Library, query: str, llm_client: LLMClient) -> list[dict]`:

**Algorithm:**
1. Initialize `results = []`
2. For each `file_name, file_meta` in `library.manifest["files"].items()`:
   - `text_to_check = file_meta.get("summary")` (Or fetch full text from `extracted_text_cid` if needed and feasible)
   - If `text_to_check`:
     - `score, justification = llm_client.check_semantic_relevance(text_to_check, query)`
     - If `score > RELEVANCE_THRESHOLD` (e.g., 0.5):
       - `results.append({"file_name": file_name, "score": score, "justification": justification, "metadata": file_meta})`
3. Sort `results` by `score` descending
4. Return `results`

- `llm_utils.py`: `LLMClient.check_semantic_relevance(text_content: str, query: str) -> tuple[float, str]`:
  - Prompt: `f"Rate the semantic relevance of the following text to the query: '{query}'. Provide a score from 0.0 (not relevant) to 1.0 (highly relevant), followed by a comma, then a brief justification. Example: 0.85,The text directly addresses the core concepts of the query. Text: {text_content}"`
  - Parse score and justification
  - Return `(score, justification)`

- `cli.py`: `scipfs search <library_name> "<search_query>"`

#### Acceptance Criteria

- Returns relevant files ranked by semantic score

**Feasibility:** Medium - LLM calls for each file can be slow/costly for large libraries. Good for MVP search.

### 2.2. Advanced Metadata Filtering

**Description:** Enhance `list` and `search` with metadata filters.

#### Implementation Details

**Files:** `scipfs/cli.py`

**Python Functionality:**

- Add `click` options to `list` and `search`: `--tag <t>`, `--added-by <user>`, `--file-type <.pdf>`
- Implement filtering logic in `cli.py` before displaying/processing results:

```python
# scipfs/cli.py (pseudocode for filtering)
def filter_files(files_metadata_list: list[dict], tags: list[str] = None, added_by: str = None, file_type: str = None) -> list[dict]:
    filtered = files_metadata_list
    if tags:
        # Assuming file_meta['tags'] is a list of strings
        filtered = [fm for fm in filtered if all(tag in fm.get("tags", []) for tag in tags)]
    if added_by:
        filtered = [fm for fm in filtered if fm.get("added_by") == added_by]
    if file_type:
        # Assuming file_meta['original_file_type'] stores the extension like '.pdf'
        normalized_file_type = file_type if file_type.startswith('.') else '.' + file_type
        filtered = [fm for fm in filtered if fm.get("original_file_type") == normalized_file_type]
    return filtered
```

#### Acceptance Criteria

- Users can filter by tags, user, file type

**Feasibility:** High

### 2.3. BibTeX Integration (Generation & Management)

**Description:** Generate and manage `.bib` entries for files, especially academic papers.

#### Implementation Details

**Files:** `scipfs/bibtex_utils.py` (new), `scipfs/llm_utils.py`, `scipfs/library.py`

**Python Functionality:**

- `llm_utils.py`: `LLMClient.extract_bibtex_from_text(text_content: str) -> Optional[str]`:
  - Prompt: `f"Extract bibliographic information from the following text and format it as a valid BibTeX entry. If it's not an academic paper or no clear info, return only the string 'None'. Text: {text_content}"`
  - Alternative (more robust if DOI present): `extract_doi_from_text(text_content: str) -> Optional[str]` using regex, then use an external API (e.g., CrossRef `https://api.crossref.org/works/{DOI}/transform/application/x-bibtex`)

- `bibtex_utils.py`:
  - `generate_bib_entry_for_file(file_metadata: dict, text_content_or_cid: str, llm_client: LLMClient, ipfs_client) -> Optional[str]` (decides to use LLM or DOI)
  - `compile_library_bibtex(library: Library, ipfs_client) -> str` (fetches individual BibTeX CIDs or entries and compiles them)

- `library.py`:
  - During `add_file`, attempt to generate a BibTeX entry
  - Store the BibTeX entry as `filename.bib` to IPFS and store its CID: `file_entry["bibtex_cid"] = "QmBib..."`
  - Update library manifest: `manifest["library_bib_cid"] = "Qm..."` (CID of a file containing all BibTeX entries for the library)

- `cli.py`:
  - `scipfs get-bibtex <library_name> [file_name]`
  - `scipfs export-library-bib <library_name> <output_path.bib>`

#### Acceptance Criteria

- BibTeX entries generated for suitable files and CIDs stored
- Library-wide `.bib` file can be compiled and exported

**Feasibility:** Medium - LLM extraction reliability is a concern. DOI lookup is better but requires DOI. Managing consistency of the library-wide BibTeX file needs careful implementation.

### 2.4. Initial Model Context Protocol (MCP) Integration

**Description:** Enable scipfs to expose some functionality as an MCP tool and/or consume other MCP tools.

#### Implementation Details

**Files:** `scipfs/mcp_adapter.py` (new)

**Python Functionality:**

- Research Python MCP libraries

**Use Case 1 (Expose scipfs functionality):**
- Define MCP tool schemas for:
  - `add_file_to_scipfs_library` (inputs: library_name, file_path_or_cid, user_info; outputs: status, new_manifest_cid)
  - `search_scipfs_library` (inputs: library_name, search_query; outputs: list_of_results)
- Implement an MCP server endpoint (e.g., using FastAPI or a simpler HTTP server if MCP libraries support it) that calls underlying `scipfs` library functions

**Use Case 2 (Consume external MCP tool - example):**
- `Library.add_file` could call an external MCP tool for specialized OCR if local extraction fails badly

**LLM Integration:** LLMs acting as agents could call scipfs MCP tools

#### Acceptance Criteria

- scipfs can register and respond as an MCP tool for at least one function (e.g., search)

**Feasibility:** Medium - Depends on Python MCP library maturity. Exposing simple functions is a good start.

### 2.5. Filecoin Integration Exploration (for Archival/Persistence)

**Description:** Explore options for long-term persistence of library CIDs using Filecoin.

#### Implementation Details

**Research Phase:**
- Investigate services like web3.storage, estuary.tech, Lighthouse.storage which simplify Filecoin deals
- Evaluate their Python client libraries

**Potential Integration:**
- New CLI command: `scipfs archive <library_name> [file_name|--all] [--provider <web3.storage|lighthouse|etc.>]`
- The command would use the chosen service's API to upload the file/CID and initiate storage deals
- Store deal IDs/status in the manifest: `file_entry["filecoin_deals"] = [{"service": "web3.storage", "deal_id": "...", "status": "active"}]`

#### Acceptance Criteria (for exploration & initial integration)

- Successful archival of a file's CID from scipfs to Filecoin via at least one third-party service
- Storage deal information is retrievable and can be noted in the manifest

**Feasibility:** Medium (if using an abstraction service like web3.storage, whose APIs are generally straightforward). Direct Filecoin deal-making is Hard.

---

## Phase 3: Advanced Features & Ecosystem Maturity

**Priority:** Medium-Low - Explore once core content intelligence and key integrations are solid  
**Overall Feasibility:** Medium - Features here are more complex or rely on a larger user base

### 3.1. Vector Embeddings for Scalable Semantic Search

**Description:** Implement vector embeddings for faster, more scalable semantic search.

#### Implementation Details

**LLM Integration:** Use embedding models (OpenAI `text-embedding-3-small`, Sentence Transformers like `all-MiniLM-L6-v2`)

**Python Functionality:**

- `Library.add_file()`: Generate embedding for summary or fetched full text (from `extracted_text_cid`)
- `llm_utils.py`: `LLMClient.generate_embedding(text: str) -> Optional[list[float]]`

**Storage:**
- Embeddings stored in a separate file per library (e.g., `library_name_embeddings.json` or a small local vector DB file like FAISS index or ChromaDB collection)
- The manifest for the library could point to the CID of this embeddings file if it's also stored on IPFS

- `search.py`: `vector_search_library(library, query: str, llm_client: LLMClient, top_k: int = 5)`:
  1. Generate embedding for the `query` using `llm_client.generate_embedding(query)`
  2. Load the library's embeddings
  3. Perform cosine similarity search against all file embeddings
  4. Return top_k results

#### Acceptance Criteria

- Semantic search uses vector similarity
- Performance improvement for large libraries

**Feasibility:** Medium - Adds dependency on embedding models and vector similarity calculations. Managing embedding stores requires care.

### 3.2. Asynchronous Processing for LLM Tasks

**Description:** Offload time-consuming LLM operations to a background queue.

#### Implementation Details

- Use Python's `asyncio` and `concurrent.futures.ThreadPoolExecutor` for I/O-bound LLM calls
- `scipfs add --no-wait` (or make async default):
  - Quickly adds file to IPFS, creates basic manifest entry with `llm_processing_status: "pending"`
  - Schedules LLM tasks (summary, tags, bibtex, embeddings) to run asynchronously
  - These tasks, upon completion, update the manifest (requiring a re-pin and re-publish of the manifest). This re-publish step is critical and needs robust handling
- New CLI command: `scipfs status <library_name>` could show processing status of files

#### Acceptance Criteria

- `scipfs add` returns more quickly for LLM-intensive operations
- LLM tasks complete in the background and update the manifest correctly

**Feasibility:** Medium - Managing manifest updates from async tasks and ensuring IPNS republishing is consistent can be complex.

### 3.3. Library Discovery and Recommendation

**Description:** Help users discover new scipfs libraries or get recommendations.

#### Implementation Ideas & Feasibility

**Option A: Curated Registry (Feasibility: High for MVP)**
- A well-known public IPNS key hosts a JSON file: `{"libraries": [{"name": "lib1", "ipns_name": "/ipns/xxx", "description": "...", "tags": [...]}, ...]}`
- Library creators can submit PRs to a Git repo managing this JSON file
- `scipfs discover [--tag <tag>]` fetches and searches this list

**Option B: Decentralized Publishing via PubSub (Feasibility: Medium to Hard)**
- `scipfs publish-library <library_name>`: Publishes a small JSON object `{name, ipns_name, description, tags}` to a well-known IPFS PubSub topic
- `scipfs discover` subscribes to this topic for a short period or queries a caching service that listens to the topic
- Requires nodes to be online and discoverable; spam is a concern

**Option C: LLM-based Matching (Feasibility: Medium, builds on A or B)**
- User: `scipfs discover --interest "quantum computing papers"`
- Fetches library descriptions (from A or B), uses LLM to match interest

**Manifest field for discovery:** Add `manifest["description"]` and `manifest["public_tags"]` to be filled by library owner

**Initial Steps:** Implement Option A with self-description fields in the manifest

**Feasibility:** Varies. Curated list is High. Decentralized pub/sub is Harder.

### 3.4. Content-Aware Recommendations (within a library)

**Description:** Suggest "similar files" within the *same* library.

#### Implementation Details

- If vector embeddings exist: `scipfs recommend <library_name> <file_name>` finds files with N closest embeddings to the target file's embedding
- If only LLM-based semantic relevance: Iterate through other files, using `check_semantic_relevance` between target file's summary and other files' summaries

**Feasibility:** Medium - Depends on having efficient similarity measures (embeddings are better here)

---

## Technology Stack & Key Libraries

### Core Technologies
- **Core:** Python 3.8+
- **CLI:** `click`
- **IPFS Interaction:** Existing `scipfs_go_helper`
- **Configuration/Serialization:** Python's `json` module

### Text Processing & LLM Integration
- **Text Extraction:** `PyPDF2`, `python-docx`, `openpyxl`. (Consider `tika-python` for broader/more robust support later if needed)
- **LLM Clients:** `openai`, `anthropic` Python libraries
- **BibTeX:** Potentially `bibtexparser` for parsing if consuming BibTeX, `requests` for DOI lookups

### Future/Advanced Features
- **Vector DB:** `faiss-cpu`, `chromadb` (local file-based modes)
- **Async:** `asyncio`, `concurrent.futures.ThreadPoolExecutor`
- **MCP:** Libraries from `modelcontextprotocol` org (once mature)
- **Filecoin Archival:** Client libraries for services like `web3.storage`, `lighthouse-storage.python`

---

## Release Milestones

### v0.2.0: "Intelligent Ingest MVP"
**Features:** 1.1, 1.2, 1.3, 1.4, 1.5 (Core LLM config, text extraction for PDF/TXT, summarization, tagging, manifest updates)  
**Goal:** Files added to scipfs are automatically processed for basic content understanding  
**Feasibility:** High

### v0.3.0: "Enhanced Discovery & Scholarly Features"
**Features:** 2.1 (Basic Semantic Search), 2.2 (Metadata Filtering), 2.3 (BibTeX Integration - initial version, DOI lookup preferred, LLM as fallback)  
**Goal:** Users can search semantically, filter effectively, and manage academic references  
**Feasibility:** Medium-High

### v0.4.0: "Interoperability & Archival Options"
**Features:** 2.4 (Initial MCP Integration - expose 1-2 scipfs tools), 2.5 (Filecoin Archival - via service like web3.storage)  
**Goal:** scipfs starts interacting with the broader ecosystem and offers robust storage solutions  
**Feasibility:** Medium

### v0.5.0+: "Scalability & Ecosystem Maturity"
**Features:** 3.1 (Vector Embeddings for Search), 3.2 (Async Processing for LLM tasks), 3.3 (Library Discovery - Curated Registry MVP), 3.4 (Content Recommendations within library)  
**Goal:** Improve performance, UX for large ops, and enable wider library discovery  
**Feasibility:** Medium to Hard (for some parts like decentralized discovery)

---

This roadmap provides a structured approach to evolving scipfs into a uniquely valuable tool. Prioritization will be reviewed based on development progress and user feedback. 