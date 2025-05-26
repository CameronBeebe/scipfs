# SciPFS Development Roadmap: Content-Aware IPFS Libraries

## Core Goal
Transform scipfs from a basic file-sharing tool into an intelligent library manager that understands and leverages the *content* of files stored on IPFS. The key differentiator will be an LLM-powered intelligence layer for semantic understanding, search, organization, and interoperability.

## Guiding Principles
*   **Incremental Value:** Each phase and feature should deliver tangible benefits to users.
*   **Leverage Existing Strengths:** Build upon scipfs's current IPFS file handling, manifest management, and CLI structure.
*   **Modularity:** Design components (e.g., LLM interaction, text extraction) to be modular and replaceable.
*   **User Experience:** Keep the CLI intuitive and provide clear feedback, especially for new AI-driven features.
*   **Configuration over Hardcoding:** Allow users to configure LLM providers, API keys (via environment variables), and other preferences.
*   **Feasibility First:** Prioritize concrete, achievable steps over "pie-in-the-sky" ideas, with clear feasibility assessments.

---

## Phase 1: Foundational LLM Integration & Content Processing

**Priority: High** - This phase lays the groundwork for all subsequent intelligent features.
**Overall Feasibility: High** - Relies on well-established Python libraries and standard API integrations.

**1.1. Configuration for LLM API Keys & Provider Choice**
    *   **Description:** Securely manage LLM API keys and allow users to choose their preferred LLM provider and model.
    *   **Implementation Details:**
        *   **Files:** `scipfs/config.py`, `scipfs/cli.py`
        *   **Python Functionality:**
            *   `SciPFSConfig` class in `config.py`:
                ```python
                # scipfs/config.py (pseudocode)
                class SciPFSConfig:
                    def __init__(self, config_path):
                        self.config_path = config_path
                        self.data = self._load_config() # loads from ~/.scipfs/config.json

                    def get_api_key(self, provider_name: str) -> Optional[str]:
                        env_var_name = f"SCIPFS_{provider_name.upper()}_API_KEY"
                        return os.environ.get(env_var_name)

                    def set_llm_provider(self, provider: str):
                        self.data['llm_provider'] = provider
                        self._save_config()

                    def get_llm_provider(self) -> Optional[str]:
                        return self.data.get('llm_provider')

                    def set_llm_model(self, model: str):
                        self.data['llm_model'] = model
                        self._save_config()
                    
                    def get_llm_model(self) -> Optional[str]:
                        return self.data.get('llm_model')
                    # ... load/save methods ...
                ```
            *   New CLI commands in `cli.py` using `click`:
                *   `scipfs config set llm_provider <openai|anthropic|custom_url>`
                *   `scipfs config set llm_model <model_name_or_identifier>`
                *   `scipfs config get llm_provider`
                *   `scipfs config get llm_model`
        *   **Data:** API keys remain in environment variables. `~/.scipfs/config.json` stores provider choice and model.
        *   **LLM Integration:** Indirect; sets up credentials.
    *   **Acceptance Criteria:**
        *   User can set/get LLM provider and model.
        *   SciPFS accesses API keys from environment variables.
        *   Keys NOT in config file/logs.
    *   **Feasibility: High** - Standard config and environment variable handling.

**1.2. Text Extraction from Files**
    *   **Description:** Extract plain text content from uploaded files.
    *   **Implementation Details:**
        *   **Files:** `scipfs/text_extractor.py` (new), `scipfs/library.py`
        *   **Python Functionality:**
            *   `text_extractor.py`:
                ```python
                # scipfs/text_extractor.py (pseudocode)
                from pathlib import Path
                import PyPDF2 # Example for PDF
                # import python-docx, openpyxl, etc.

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
                            logger.warning(f"Unsupported file type for text extraction: {file_path.suffix}")
                            return None
                    except Exception as e:
                        logger.error(f"Error extracting text from {file_path}: {e}")
                        return None
                ```
            *   `library.py`: `Library.add_file()` calls `extract_text()`.
        *   **Data Strategy (Option B preferred for scalability):**
            1.  Extract text.
            2.  If text is substantial, save as `original_filename_extracted.txt`.
            3.  Add this text file to IPFS: `extracted_text_cid = ipfs_client.add_file(extracted_text_path)`.
            4.  Store `extracted_text_cid` in the manifest.
            5.  If text is very small (e.g. < 1KB), consider storing directly in manifest `extracted_text_short` for quick access, but still prefer `extracted_text_cid` for consistency.
        *   **LLM Integration:** None directly.
    *   **Acceptance Criteria:**
        *   Text extracted from PDF, TXT, DOCX.
        *   `extracted_text_cid` (or short text) stored in manifest.
    *   **Feasibility: High** for common formats; Medium for very broad format support (might need Tika).

**1.3. LLM-Powered Content Summarization**
    *   **Description:** Generate a concise summary of the file's content.
    *   **Implementation Details:**
        *   **Files:** `scipfs/llm_utils.py` (new), `scipfs/library.py`
        *   **Python Functionality:**
            *   `llm_utils.py`:
                ```python
                # scipfs/llm_utils.py (pseudocode)
                # import openai, anthropic
                class LLMClient:
                    def __init__(self, config: SciPFSConfig):
                        self.provider = config.get_llm_provider()
                        self.model = config.get_llm_model()
                        self.api_key = config.get_api_key(self.provider)
                        # Initialize actual client (e.g., openai.OpenAI(api_key=self.api_key))

                    def summarize(self, text: str, max_tokens: int = 150) -> Optional[str]:
                        if not self.api_key: return None
                        prompt = f"Summarize the following text in about {max_tokens//4} words:

{text}" # Rough estimate
                        # Make API call using self.client, handle retries/errors
                        # response = self.client.chat.completions.create(...)
                        # return response.choices[0].message.content
                        pass
                ```
            *   `library.py`: In `Library.add_file()`, after getting text (from CID or direct), call `llm_client.summarize()`.
        *   **Data:** Store summary in manifest: `file_entry["summary"] = "..."`.
        *   **LLM Integration:** Direct API calls. Use cost-effective models (e.g., `gpt-4o-mini`, `claude-3-haiku`). Truncate long texts before sending to LLM to manage token limits/costs if full text CID isn't used.
    *   **Acceptance Criteria:**
        *   Summary generated and stored. Concise and relevant.
    *   **Feasibility: High** - Standard LLM API interaction.

**1.4. LLM-Powered Keyword/Tag Generation**
    *   **Description:** Automatically generate relevant keywords/tags.
    *   **Implementation Details:**
        *   **Files:** `scipfs/llm_utils.py`, `scipfs/library.py`
        *   **Python Functionality:**
            *   `llm_utils.py`: `LLMClient.generate_tags(text: str, num_tags: int = 5) -> Optional[List[str]]`
                *   Prompt: `"Extract the {num_tags} most relevant keywords or tags from this text. Return as a JSON list of strings. Example: ["tag1", "tag2"] Text: {text}"`
                *   Parse JSON response.
        *   **Data:** Store tags in manifest: `file_entry["tags"] = ["keyword1", ...]`.
    *   **Acceptance Criteria:**
        *   Relevant tags generated and stored as a list.
    *   **Feasibility: High**.

**1.5. Manifest Structure & CLI Updates for New Metadata**
    *   **Description:** Update manifest and CLI for new metadata.
    *   **Implementation Details:**
        *   **Files:** `scipfs/library.py`, `scipfs/cli.py`
        *   **Updated Manifest Structure (example entry in `files` dict):**
            ```json
            "example.pdf": {
                "cid": "QmOriginal...",
                "size": 12345,
                "added_by": "user_x",
                "added_timestamp": 1678886400,
                "original_file_type": ".pdf",
                "extracted_text_cid": "QmText...", // If text stored on IPFS
                // "extracted_text_short": "Brief text...", // If very short
                "summary": "This document discusses advanced techniques...",
                "tags": ["ai", "decentralization", "ipfs"],
                "llm_processing_status": "completed", // "pending", "failed: [error_msg]"
                "bibtex_cid": "QmBibtex..." // To be added in Phase 2
            }
            ```
        *   `cli.py`:
            *   `scipfs list <library_name> [--show-summaries] [--show-tags]`
            *   `scipfs file-info <library_name> <file_name>` (displays all metadata)
    *   **Acceptance Criteria:**
        *   Manifest correctly stores/loads all new fields.
        *   CLI displays new metadata.
    *   **Feasibility: High**.

---

## Phase 2: Enhanced Discovery, Interoperability & Advanced Storage

**Priority: Medium-High** - Focus on making libraries more useful and integrated.
**Overall Feasibility: Medium** - Some features introduce more complexity or external dependencies.

**2.1. Basic Semantic Search (LLM-based, no vector DB)**
    *   **Description:** Search within a library based on semantic meaning.
    *   **Implementation Details:**
        *   **Files:** `scipfs/search.py` (new), `scipfs/cli.py`, `scipfs/llm_utils.py`
        *   **Python Functionality:**
            *   `search.py`: `semantic_search_library(library: Library, query: str, llm_client: LLMClient) -> List[Dict]`
                *   Algorithm:
                    1. For each file in `library.manifest["files"]`:
                        a. Get its `summary`. If summary is short, consider fetching full text from `extracted_text_cid` (if LLM context allows and cost is acceptable).
                        b. Use `llm_client.check_semantic_relevance(text_to_check, query)`
            *   `llm_utils.py`: `LLMClient.check_semantic_relevance(text_content: str, query: str) -> Tuple[float, str]`
                *   Prompt: `"Rate the semantic relevance of the following text to the query: '{query}'. Provide a score from 0.0 (not relevant) to 1.0 (highly relevant), followed by a comma, then a brief justification. Example: 0.85,The text directly addresses the core concepts of the query. Text: {text_content}"`
                *   Parse score and justification.
                *   Return `(score, justification)`.
            *   Collect files with score > threshold (e.g., 0.5), rank by score.
        *   `cli.py`: `scipfs search <library_name> "<search_query>"`
    *   **Acceptance Criteria:**
        *   Returns relevant files ranked by semantic score.
    *   **Feasibility: Medium** - LLM calls for each file can be slow/costly for large libraries. Good for MVP search.

**2.2. Advanced Metadata Filtering**
    *   **Description:** Enhance `list` and `search` with metadata filters.
    *   **Implementation Details:**
        *   **Files:** `scipfs/cli.py`
        *   **Python Functionality:**
            *   Add `click` options to `list` and `search`: `--tag <t>`, `--added-by <user>`, `--file-type <.pdf>`.
            *   Implement filtering logic in `cli.py` before displaying/processing results.
                ```python
                # scipfs/cli.py (pseudocode for filtering)
                def filter_files(files_metadata: List[Dict], tags: List[str], added_by: str, file_type: str) -> List[Dict]:
                    filtered = files_metadata
                    if tags:
                        filtered = [f for f in filtered if all(tag in f.get("tags", []) for tag in tags)] # AND logic
                    if added_by:
                        filtered = [f for f in filtered if f.get("added_by") == added_by]
                    # ... and so on
                    return filtered
                ```
    *   **Acceptance Criteria:**
        *   Users can filter by tags, user, file type.
    *   **Feasibility: High**.

**2.3. BibTeX Integration (Generation & Management)**
    *   **Description:** Generate and manage `.bib` entries for files, especially academic papers.
    *   **Implementation Details:**
        *   **Files:** `scipfs/bibtex_utils.py` (new), `scipfs/llm_utils.py`, `scipfs/library.py`
        *   **Python Functionality:**
            *   `llm_utils.py`: `LLMClient.extract_bibtex(text_content: str) -> Optional[str]`
                *   Prompt: `"Extract bibliographic information from the following text and format it as a BibTeX entry. If it's not an academic paper or no clear info, return 'None'. Text: {text_content}"`
                *   Alternatively, for known PDFs, try to extract DOI and use an external API (e.g., CrossRef `https://api.crossref.org/works/{DOI}/transform/application/x-bibtex`) if LLM calls are too unreliable for this.
            *   `bibtex_utils.py`:
                *   `generate_bib_entry_for_file(file_metadata: dict, text_content: str, llm_client: LLMClient) -> Optional[str]`
                *   `compile_library_bibtex(library: Library) -> str` (compiles all entries into one string)
            *   `library.py`:
                *   During `add_file`, attempt to generate a BibTeX entry.
                *   Store the BibTeX string directly in manifest `file_entry["bibtex_entry"] = "..."` OR add the entry as `filename.bib` to IPFS and store `file_entry["bibtex_cid"] = "QmBib..."`. Storing as separate CID is cleaner.
                *   When a library manifest is updated, potentially update a library-wide `.bib` file (e.g., `library_name.bib`) on IPFS, storing its CID in the main manifest: `manifest["library_bib_cid"] = "Qm..."`.
            *   `cli.py`:
                *   `scipfs get-bibtex <library_name> [file_name]` (gets entry for file or whole library)
                *   `scipfs export-library-bib <library_name> <output_path.bib>`
    *   **Acceptance Criteria:**
        *   BibTeX entries generated for suitable files.
        *   Library-wide `.bib` file can be exported.
    *   **Feasibility: Medium** - LLM extraction can be hit-or-miss; DOI lookup is more reliable but needs network access and DOI presence. Managing library-wide bib file consistency needs care.

**2.4. Initial Model Context Protocol (MCP) Integration**
    *   **Description:** Enable scipfs to expose some functionality as an MCP tool and/or consume other MCP tools.
    *   **Implementation Details:**
        *   **Files:** `scipfs/mcp_adapter.py` (new)
        *   **Python Functionality:**
            *   Research Python MCP libraries (e.g., from `modelcontextprotocol` GitHub).
            *   **Use Case 1 (Expose scipfs functionality):**
                *   Define MCP tool schemas for:
                    *   `add_file_to_scipfs_library` (input: library_name, file_path/CID, user_info; output: status, manifest_cid)
                    *   `search_scipfs_library` (input: library_name, query; output: results_list)
                *   Implement an MCP server endpoint (e.g., using FastAPI) within scipfs or as a separate process that calls scipfs CLI/library functions.
            *   **Use Case 2 (Consume external MCP tool):**
                *   Example: If an external MCP tool provides advanced OCR for difficult PDFs.
                *   `Library.add_file` could, for certain files, call out to this MCP tool.
        *   **LLM Integration:** LLMs acting as agents could call scipfs MCP tools.
    *   **Acceptance Criteria:**
        *   scipfs can successfully register and respond as an MCP tool for `add_file` or `search`.
        *   (Optional) scipfs can successfully call a simple external MCP tool.
    *   **Feasibility: Medium** - Depends on maturity of Python MCP libraries and complexity of chosen use case. Starting with exposing 1-2 simple scipfs functions via MCP is achievable.

**2.5. Filecoin Integration Exploration (for Archival/Persistence)**
    *   **Description:** Explore options for long-term persistence of library CIDs using Filecoin.
    *   **Implementation Details:**
        *   **Research Phase:**
            *   Investigate Filecoin storage providers and deal-making mechanisms (e.g., web3.storage, estuary.tech, or direct interaction with brokers/miners if simpler APIs exist).
            *   Evaluate Python libraries for Filecoin interaction.
        *   **Potential Integration Points:**
            *   `scipfs pin --archive <library_name> [file_name|--all]`: Command to initiate a storage deal on Filecoin for the CIDs.
            *   This might involve using an MCP tool that brokers Filecoin deals, or a direct API integration.
            *   Store deal IDs/status in the manifest: `file_entry["filecoin_deals"] = [{"deal_id": "...", "provider": "...", "status": "active"}]`.
    *   **Acceptance Criteria (for exploration):**
        *   Clear understanding of at least one viable pathway to make Filecoin storage deals for scipfs CIDs.
        *   Prototype of making a deal for a single CID using a chosen service/library.
    *   **Feasibility: Medium to Hard** - Filecoin deal mechanisms can be complex. Relying on services like web3.storage can simplify this significantly (High feasibility if using such a service). Direct deal-making is harder.

---

## Phase 3: Advanced Features & Ecosystem Maturity

**Priority: Medium-Low** - Explore once core content intelligence and key integrations are solid.
**Overall Feasibility: Medium** - Features here are more complex or rely on a larger user base.

**3.1. Vector Embeddings for Scalable Semantic Search**
    *   **Description:** Implement vector embeddings for faster, more scalable semantic search.
    *   **Implementation Details:**
        *   **LLM Integration:** Use embedding models (OpenAI `text-embedding-3-small`, Sentence Transformers).
        *   **Python Functionality:**
            *   `Library.add_file()`: Generate embedding for summary or full text.
            *   Store embeddings:
                *   Option A: In the manifest (if vector size and number of files are small).
                *   Option B: Separate local vector DB (FAISS, ChromaDB in local file mode) per library, store path/CID to DB in manifest.
            *   `search.py`: `vector_search_library(library, query_embedding)`.
    *   **Acceptance Criteria:**
        *   Semantic search uses vector similarity.
        *   Noticeable performance improvement for large libraries.
    *   **Feasibility: Medium** - Adds dependency on vector DB and embedding generation pipeline.

**3.2. Asynchronous Processing for LLM Tasks**
    *   **Description:** Offload time-consuming LLM operations to a background queue.
    *   **Implementation Details:**
        *   Use Python's `asyncio` and `concurrent.futures`, or a simple file-based/SQLite queue.
        *   `scipfs add --no-wait`: Quickly adds file, queues LLM tasks. `llm_processing_status` becomes "pending".
        *   `scipfs process-queue <library_name>` or a background worker.
    *   **Acceptance Criteria:**
        *   `scipfs add --no-wait` returns quickly.
        *   Tasks processed in background; status updated in manifest.
    *   **Feasibility: Medium**.

**3.3. Library Discovery and Recommendation**
    *   **Description:** Help users discover new scipfs libraries or get recommendations.
    *   **Implementation Ideas & Feasibility:**
        *   **Option A: Curated/Community Lists (Feasibility: High for MVP)**
            *   Users/community maintain a well-known IPNS name or a Git repo with a list of public scipfs library IPNS names and their descriptions/tags.
            *   `scipfs discover --from <URL/IPNS_curated_list>`
        *   **Option B: Decentralized Registry (Feasibility: Medium to Hard)**
            *   When a library is made public (new command: `scipfs publish-library-globally <library_name>`), its manifest CID (or a summary of it containing name, description, tags) is published to a shared DHT or a dedicated pub/sub topic.
            *   `scipfs discover [--tag <tag>]` would query this decentralized registry. This is complex to make robust and scalable.
        *   **Option C: LLM-based Matching (Feasibility: Medium, builds on A or B)**
            *   User provides interests: `scipfs discover --interest "quantum computing papers"`
            *   scipfs fetches descriptions from a list (Option A) or registry (Option B).
            *   Uses an LLM to match user interest to library descriptions/tags.
        *   **Recommendation (within scipfs ecosystem):** If a user frequently accesses libraries with tag "X", scipfs could (opt-in) note this and suggest other public libraries with tag "X".
    *   **Initial Steps:** Start with Option A. The critical part is having a way for library creators to *describe* their library (name, short description, tags) in their own manifest, which can then be shared.
    *   **Feasibility: Varies by approach.** A simple curated list is easy. Decentralized discovery is hard.

**3.4. Content-Aware Recommendations (within a library)**
    *   **Description:** Suggest "similar files" within the *same* library.
    *   **Implementation Details:**
        *   If vector embeddings: Find files with cosine similar embeddings.
        *   If LLM-based search: `scipfs recommend <library_name> <file_name>` could find top N files semantically similar to the given file's summary/text.
    *   **Feasibility: Medium** (depends on having embeddings or efficient semantic comparison).

---

## Technology Stack & Key Libraries (Summary)
*   **Core:** Python 3.8+
*   **CLI:** `click`
*   **IPFS Interaction:** Existing `scipfs_go_helper`
*   **Text Extraction:** `PyPDF2`, `python-docx`, `openpyxl`. (Consider `tika-python` for broader support later)
*   **LLM Clients:** `openai`, `anthropic` Python libraries.
*   **BibTeX:** Standard library for parsing if needed, direct string formatting, or external APIs.
*   **Configuration/Serialization:** Python's `json` module.
*   **(Future) Vector DB:** `faiss-cpu`, `chromadb`.
*   **(Future) Async:** `asyncio`, `concurrent.futures`, `APScheduler` or `Celery` (if heavy duty).
*   **(Future) MCP:** Libraries from `modelcontextprotocol` org.
*   **(Future) Filecoin:** `web3.storage` client, `python-filecoin-api` wrappers (if any mature ones exist for direct interaction).

## Release Milestones (Tentative - Adjusted for Prioritization)

*   **v0.2.0: "Intelligent Ingest MVP"**
    *   Features: 1.1, 1.2, 1.3, 1.4, 1.5 (Core LLM config, text extraction for PDF/TXT, summarization, tagging, manifest updates)
    *   Goal: Files added to scipfs are automatically processed for basic content understanding.
    *   **Feasibility: High**

*   **v0.3.0: "Enhanced Discovery & Scholarly Features"**
    *   Features: 2.1 (Basic Semantic Search), 2.2 (Metadata Filtering), 2.3 (BibTeX Integration - initial version)
    *   Goal: Users can search semantically, filter effectively, and manage academic references.
    *   **Feasibility: Medium-High**

*   **v0.4.0: "Interoperability & Advanced Storage Options"**
    *   Features: 2.4 (Initial MCP Integration - expose scipfs tools), 2.5 (Filecoin Integration - via service like web3.storage initially)
    *   Goal: scipfs starts interacting with the broader ecosystem and offers robust storage solutions.
    *   **Feasibility: Medium**

*   **v0.5.0+: "Scalability & Ecosystem Maturity"**
    *   Features: 3.1 (Vector Embeddings for Search), 3.2 (Async Processing), 3.3 (Library Discovery - curated list + LLM matching), 3.4 (Content Recommendations)
    *   Goal: Improve performance, UX for large ops, and enable wider library discovery.
    *   **Feasibility: Medium to Hard (for some parts like decentralized discovery)**

This roadmap provides a structured approach to evolving scipfs into a uniquely valuable tool. Prioritization will be reviewed based on development progress and user feedback. 