import os
import json
import hashlib
import threading
import time
from pathlib import Path
from datetime import datetime
import chromadb
from google import genai
from google.genai import types
from rank_bm25 import BM25Okapi

from core.brain.config import (
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    EMBEDDING_DIM,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    RAG_RECENCY_BOOST
)
from core.logger.logger import logger
from core.brain.Indexer.config_store import config_store
from core.brain.Indexer.walker import FileWalker
from core.brain.Indexer.filters import FilterEngine


class RagEngine:
    def __init__(self):
        self.db_path = Path("Data/jarvis_memory/rag_chroma_db")
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.file_hashes_file = Path("Data/jarvis_memory/rag_hashes.json")
        self.default_marker_file = Path("Data/jarvis_memory/.default_folder_added")

        self.filter_engine = FilterEngine(config_store.load_filters())
        self.walker = FileWalker(self.filter_engine)

        self.file_hashes = self._load_json(self.file_hashes_file, {})
        self.google_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

        self.db_lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.hash_lock = threading.Lock()
        self.index_lock = threading.Lock()
        self.bm25_lock = threading.RLock()

        self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
        self.rag_collection = self.chroma_client.get_or_create_collection(
            name="jarvis_knowledge_index"
        )

        self._all_documents_cache = None
        self._all_metadatas_cache = None
        self._all_ids_cache = None
        self._bm25_index = None
        self._corpus_tokens = None

        self._pause_event = threading.Event()
        self._pause_event.set()
        self._shutdown_flag = False
        self._indexing_thread = None

        self._status = {
            "state": "idle",
            "current_folder": "",
            "files_total": 0,
            "files_done": 0,
            "chunks_done": 0,
            "started_at": "",
            "last_completed": "",
            "last_error": ""
        }

        self._ensure_default_folders()
        self._ensure_schema_compatibility()
        logger.info("RAG Engine initialized with knowledge indexer.")

        self._indexing_thread = threading.Thread(target=self._initial_index, daemon=True)
        self._indexing_thread.start()

    def _load_json(self, file_path, default):
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return default
        except Exception as e:
            logger.warning(f"RAG hashes load failed: {e}")
            return default

    def _save_json(self, file_path, data):
        try:
            tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, file_path)
        except Exception as e:
            logger.error(f"RAG hashes save failed: {e}")

    def _set_status(self, **kwargs):
        with self.status_lock:
            self._status.update(kwargs)

    def _get_status_snapshot(self):
        with self.status_lock:
            return dict(self._status)

    def get_status(self):
        return self._get_status_snapshot()

    def get_progress(self):
        snap = self._get_status_snapshot()
        total = snap["files_total"]
        done = snap["files_done"]
        percent = round((done / total * 100), 2) if total > 0 else 0.0
        return {
            "state": snap["state"],
            "current_folder": snap["current_folder"],
            "files_total": total,
            "files_done": done,
            "chunks_done": snap["chunks_done"],
            "percent": percent,
            "started_at": snap["started_at"],
            "last_completed": snap["last_completed"],
            "last_error": snap["last_error"]
        }

    def _ensure_default_folders(self):
        folders = config_store.load_folders()
        if folders:
            return
        if self.default_marker_file.exists():
            return
        default_path = str(Path.home() / "Documents")
        if os.path.exists(default_path):
            folders = [{
                "path": str(Path(default_path).resolve()),
                "added_at": datetime.now().isoformat(),
                "last_indexed": "",
                "is_default": True,
                "enabled": True
            }]
            config_store.save_folders(folders)
            try:
                self.default_marker_file.parent.mkdir(parents=True, exist_ok=True)
                self.default_marker_file.touch()
            except Exception:
                pass
            logger.info(f"RAG indexer initialized with default folder: {default_path}")
        else:
            logger.warning("RAG indexer: default Documents folder not found.")

    def _ensure_schema_compatibility(self):
        try:
            with self.db_lock:
                sample = self.rag_collection.get(limit=1)
            metas = sample.get("metadatas") or []
            if not metas:
                return
            first_meta = metas[0]
            if not isinstance(first_meta, dict):
                self._purge_for_migration("metadata malformed")
                return
            if "file_id" not in first_meta:
                logger.warning("RAG schema migration: old chunks detected (missing 'file_id'). Clearing index for clean rebuild.")
                self._purge_for_migration("missing file_id")
        except Exception as e:
            logger.warning(f"RAG schema check failed: {e}")

    def _purge_for_migration(self, reason):
        try:
            with self.db_lock:
                all_ids = self.rag_collection.get().get("ids", []) or []
                if all_ids:
                    self.rag_collection.delete(ids=all_ids)
            with self.hash_lock:
                self.file_hashes = {}
                self._save_json(self.file_hashes_file, self.file_hashes)
            logger.info(f"RAG migration purge complete: {reason}. Files will re-index on next scan.")
        except Exception as e:
            logger.error(f"RAG migration purge failed: {e}")

    def _normalize_task_type(self, input_type):
        if input_type == "search_query":
            return "RETRIEVAL_QUERY"
        return "RETRIEVAL_DOCUMENT"

    def get_embedding(self, text, input_type="search_document"):
        if not text or not text.strip() or not self.google_client:
            return None
        max_chars = max(RAG_CHUNK_SIZE, 2000)
        truncated = text[:max_chars] if len(text) > max_chars else text
        task_type = self._normalize_task_type(input_type)

        for attempt in range(3):
            try:
                response = self.google_client.models.embed_content(
                    model=GEMINI_EMBEDDING_MODEL,
                    contents=truncated,
                    config=types.EmbedContentConfig(
                        output_dimensionality=EMBEDDING_DIM,
                        task_type=task_type
                    )
                )
                return response.embeddings[0].values
            except Exception as e:
                err_msg = str(e).lower()
                if "task_type" in err_msg and attempt == 0:
                    try:
                        response = self.google_client.models.embed_content(
                            model=GEMINI_EMBEDDING_MODEL,
                            contents=truncated,
                            config=types.EmbedContentConfig(
                                output_dimensionality=EMBEDDING_DIM
                            )
                        )
                        return response.embeddings[0].values
                    except Exception as e2:
                        logger.warning(f"RAG embedding (no task_type) attempt {attempt + 1} failed: {e2}")
                else:
                    logger.warning(f"RAG embedding attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        logger.error("RAG embedding failed after retries.")
        return None

    def _recursive_chunk_text(self, text, file_extension=".txt"):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        chunk_size = RAG_CHUNK_SIZE
        overlap = RAG_CHUNK_OVERLAP

        code_extensions = [
            ".py", ".js", ".ts", ".java", ".cpp", ".c",
            ".cs", ".go", ".rs", ".rb", ".php"
        ]

        if file_extension in code_extensions:
            lines = text.splitlines(keepends=True)
            chunks = []
            current = []
            current_len = 0
            for line in lines:
                line_len = len(line)
                if current_len + line_len > chunk_size and current:
                    chunks.append("".join(current))
                    overlap_lines = []
                    overlap_len = 0
                    for l in reversed(current):
                        if overlap_len + len(l) <= overlap:
                            overlap_lines.insert(0, l)
                            overlap_len += len(l)
                        else:
                            break
                    current = overlap_lines
                    current_len = overlap_len
                current.append(line)
                current_len += line_len
            if current:
                chunks.append("".join(current))
            return chunks if chunks else [text]

        paragraphs = text.split("\n\n")
        chunks = []
        current = []
        current_len = 0
        for p in paragraphs:
            p_len = len(p) + 2
            if current_len + p_len > chunk_size and current:
                chunks.append("\n\n".join(current))
                overlap_paras = []
                overlap_len = 0
                for par in reversed(current):
                    if overlap_len + len(par) + 2 <= overlap:
                        overlap_paras.insert(0, par)
                        overlap_len += len(par) + 2
                    else:
                        break
                current = overlap_paras
                current_len = overlap_len
            current.append(p)
            current_len += p_len
        if current:
            chunks.append("\n\n".join(current))
        return chunks if chunks else [text]

    def _get_file_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                hasher.update(block)
        return hasher.hexdigest()

    def _get_file_id(self, file_path):
        try:
            normalized = str(Path(file_path).resolve())
        except Exception:
            normalized = str(file_path)
        if os.name == "nt":
            normalized = normalized.lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def _is_under_folder(self, file_path, folder_path):
        try:
            fp = Path(file_path).resolve()
            fp_dir = Path(folder_path).resolve()
            try:
                return fp.is_relative_to(fp_dir)
            except AttributeError:
                return fp == fp_dir or fp_dir in fp.parents
        except Exception:
            return False

    def _initial_index(self):
        time.sleep(3)
        if self._shutdown_flag:
            return
        self._index_all_folders()

    def _index_all_folders(self):
        if self._shutdown_flag:
            return

        self.index_lock.acquire()
        try:
            folders = config_store.load_folders()
            enabled_folders = [f for f in folders if f.get("enabled", True)]

            if not enabled_folders:
                logger.info("RAG indexer: no enabled folders to index.")
                return

            self._set_status(
                state="scanning",
                started_at=datetime.now().isoformat(),
                files_total=0,
                files_done=0,
                chunks_done=0,
                last_error=""
            )

            all_files = []
            for folder in enabled_folders:
                folder_path = folder["path"]
                if not os.path.exists(folder_path):
                    logger.warning(f"RAG indexer: folder missing, skipping: {folder_path}")
                    continue
                for file_path in self.walker.walk_folder(folder_path):
                    all_files.append((str(file_path), folder_path))

            self._set_status(files_total=len(all_files))
            logger.info(f"RAG indexer: {len(all_files)} files discovered across {len(enabled_folders)} folders.")

            current_hashes = {}
            files_done = 0
            chunks_done = 0

            for file_path, root_folder in all_files:
                if self._shutdown_flag:
                    break
                if not self._pause_event.is_set():
                    self._pause_event.wait()
                    if self._shutdown_flag:
                        break

                try:
                    file_hash = self._get_file_hash(file_path)
                except Exception as e:
                    logger.warning(f"RAG indexer: hash failed for {file_path}: {e}")
                    files_done += 1
                    self._set_status(files_done=files_done)
                    continue

                if self.file_hashes.get(file_path) == file_hash:
                    current_hashes[file_path] = file_hash
                    files_done += 1
                    self._set_status(files_done=files_done)
                    continue

                success, added = self._process_file(file_path, root_folder, file_hash)
                if success:
                    current_hashes[file_path] = file_hash
                    chunks_done += added
                files_done += 1
                self._set_status(files_done=files_done, chunks_done=chunks_done)

            stale_files = set(self.file_hashes.keys()) - set(current_hashes.keys())
            if stale_files:
                self._remove_chunks_for_files(stale_files)
                logger.info(f"RAG indexer: removed {len(stale_files)} stale files from index.")

            with self.hash_lock:
                self.file_hashes = current_hashes
                self._save_json(self.file_hashes_file, self.file_hashes)

            self._rebuild_bm25_cache()

            self._set_status(
                state="idle",
                current_folder="",
                last_completed=datetime.now().isoformat()
            )
            logger.info("RAG indexer: full indexing complete.")

        except Exception as e:
            logger.error(f"RAG indexer: full indexing failed: {e}")
            self._set_status(state="error", last_error=str(e))
        finally:
            self.index_lock.release()

    def _process_file(self, file_path, root_folder, file_hash):
        try:
            ext = Path(file_path).suffix.lower()
            code_extensions = [
                ".py", ".js", ".ts", ".java", ".cpp", ".c",
                ".cs", ".go", ".rs", ".rb", ".php"
            ]

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                if ext in code_extensions:
                    lines = f.readlines()
                    content = "".join(
                        [f"Line {idx + 1}: {line}" for idx, line in enumerate(lines)]
                    )
                else:
                    content = f.read()

            if not content.strip():
                return True, 0

            mod_time = os.path.getmtime(file_path)
            mod_date = datetime.fromtimestamp(mod_time).isoformat()
            file_size = os.path.getsize(file_path)

            chunks = self._recursive_chunk_text(content, ext)
            file_id = self._get_file_id(file_path)

            batch_ids = []
            batch_embeddings = []
            batch_metadatas = []
            batch_documents = []
            failed_chunks = 0

            for i, chunk in enumerate(chunks):
                embedding = self.get_embedding(chunk, "search_document")
                if embedding:
                    batch_ids.append(f"{file_id}_{file_hash}_{i}")
                    batch_embeddings.append(embedding)
                    batch_metadatas.append({
                        "file_id": file_id,
                        "file_name": Path(file_path).name,
                        "file_path": file_path,
                        "root_folder": root_folder,
                        "modified": mod_date,
                        "file_size": file_size
                    })
                    batch_documents.append(chunk)
                else:
                    failed_chunks += 1

            if failed_chunks > 0:
                logger.error(f"RAG index partial failure for {file_path}: {failed_chunks}/{len(chunks)} chunks failed embedding.")
                return False, 0

            if not batch_ids:
                return True, 0

            old_ids = []
            try:
                with self.db_lock:
                    existing = self.rag_collection.get(where={"file_path": file_path})
                if existing and existing.get("ids"):
                    old_ids = existing["ids"]
            except Exception as e:
                logger.warning(f"RAG existing chunk fetch failed for {file_path}: {e}")

            with self.db_lock:
                self.rag_collection.upsert(
                    ids=batch_ids,
                    embeddings=batch_embeddings,
                    metadatas=batch_metadatas,
                    documents=batch_documents
                )

            new_id_set = set(batch_ids)
            stale_ids = [oid for oid in old_ids if oid not in new_id_set]
            if stale_ids:
                try:
                    with self.db_lock:
                        self.rag_collection.delete(ids=stale_ids)
                except Exception as e:
                    logger.warning(f"RAG stale chunk cleanup failed for {file_path}: {e}")

            logger.info(f"RAG indexed: {Path(file_path).name} ({len(batch_ids)} chunks)")
            return True, len(batch_ids)

        except Exception as e:
            logger.error(f"RAG file index failed for {file_path}: {e}")
            return False, 0

    def _remove_chunks_for_file(self, file_path):
        try:
            with self.db_lock:
                self.rag_collection.delete(where={"file_path": file_path})
        except Exception as e:
            logger.warning(f"RAG chunk cleanup failed for {file_path}: {e}")

    def _remove_chunks_for_files(self, file_paths):
        for fp in file_paths:
            self._remove_chunks_for_file(fp)

    def _remove_chunks_for_folder(self, folder_path):
        try:
            with self.db_lock:
                self.rag_collection.delete(where={"root_folder": folder_path})
        except Exception as e:
            logger.warning(f"RAG folder cleanup failed for {folder_path}: {e}")

    def _tokenize(self, text):
        return [t for t in text.lower().split() if t]

    def _rebuild_bm25_cache(self):
        try:
            with self.db_lock:
                all_data = self.rag_collection.get()

            documents = all_data.get("documents") or []
            metadatas = all_data.get("metadatas") or []
            ids = all_data.get("ids") or []

            if not documents:
                self._all_documents_cache = None
                self._all_metadatas_cache = None
                self._all_ids_cache = None
                self._bm25_index = None
                self._corpus_tokens = None
                logger.info("RAG BM25 cache cleared (empty collection).")
                return

            valid_docs = []
            valid_metas = []
            valid_ids = []
            for i, doc in enumerate(documents):
                if not doc:
                    continue
                if i >= len(metadatas):
                    continue
                meta = metadatas[i]
                if not isinstance(meta, dict):
                    continue
                if i >= len(ids):
                    continue
                doc_id = ids[i]
                if not doc_id:
                    continue
                valid_docs.append(doc)
                valid_metas.append(meta)
                valid_ids.append(doc_id)

            if not valid_docs:
                self._all_documents_cache = None
                self._all_metadatas_cache = None
                self._all_ids_cache = None
                self._bm25_index = None
                self._corpus_tokens = None
                logger.info("RAG BM25 cache cleared (no valid entries).")
                return

            self._all_documents_cache = valid_docs
            self._all_metadatas_cache = valid_metas
            self._all_ids_cache = valid_ids

            tokenized_corpus = [self._tokenize(doc) for doc in valid_docs]
            self._bm25_index = BM25Okapi(tokenized_corpus)
            self._corpus_tokens = tokenized_corpus

            logger.info(f"RAG BM25 cache rebuilt: {len(valid_docs)} chunks loaded.")
        except Exception as e:
            logger.error(f"RAG BM25 cache rebuild failed: {e}")
            self._bm25_index = None
            self._all_documents_cache = None
            self._all_metadatas_cache = None
            self._all_ids_cache = None

    def _rebuild_bm25_cache_if_needed(self):
        with self.bm25_lock:
            if self._bm25_index is None:
                self._rebuild_bm25_cache()

    def _reciprocal_rank_fusion(self, results_list, k=60):
        scores = {}
        for results in results_list:
            if not results:
                continue
            for rank, item in enumerate(results):
                if not isinstance(item, dict):
                    continue
                doc_id = item.get("id")
                if not doc_id:
                    continue
                meta = item.get("meta")
                if not isinstance(meta, dict):
                    continue
                if doc_id not in scores:
                    scores[doc_id] = {
                        "doc": item.get("doc", "") or "",
                        "meta": meta,
                        "score": 0.0
                    }
                scores[doc_id]["score"] += 1.0 / (k + rank + 1)
        return sorted(scores.values(), key=lambda x: x["score"], reverse=True)

    def search_vault(self, query, top_k=RAG_TOP_K, folder_filter=None):
        if isinstance(query, list):
            query = " ".join(str(q) for q in query if q)
        elif not isinstance(query, str):
            query = str(query) if query else ""
        query = query.strip()
        if not query:
            return []

        try:
            query_embedding = self.get_embedding(query, "search_query")
            if not query_embedding:
                return self._fallback_keyword_search(query, top_k, folder_filter)

            where_clause = {"root_folder": folder_filter} if folder_filter else None

            with self.db_lock:
                if where_clause:
                    vector_results = self.rag_collection.query(
                        query_embeddings=[query_embedding],
                        n_results=top_k * 2,
                        where=where_clause,
                        include=["documents", "metadatas", "distances", "ids"]
                    )
                else:
                    vector_results = self.rag_collection.query(
                        query_embeddings=[query_embedding],
                        n_results=top_k * 2,
                        include=["documents", "metadatas", "distances", "ids"]
                    )

            vector_items = []
            try:
                ids_batch = vector_results.get("ids") or []
                docs_batch = vector_results.get("documents") or []
                metas_batch = vector_results.get("metadatas") or []
                ids_list = ids_batch[0] if ids_batch and len(ids_batch) > 0 else []
                docs_list = docs_batch[0] if docs_batch and len(docs_batch) > 0 else []
                metas_list = metas_batch[0] if metas_batch and len(metas_batch) > 0 else []
                if ids_list:
                    for i, doc_id in enumerate(ids_list):
                        if not doc_id:
                            continue
                        doc = docs_list[i] if i < len(docs_list) else ""
                        meta = metas_list[i] if i < len(metas_list) else None
                        if not isinstance(meta, dict):
                            continue
                        vector_items.append({
                            "id": doc_id,
                            "doc": doc if doc else "",
                            "meta": meta
                        })
            except Exception as e:
                logger.warning(f"RAG vector result parsing failed: {e}")
                vector_items = []

            self._rebuild_bm25_cache_if_needed()
            bm25_items = []
            if self._bm25_index and self._all_metadatas_cache and self._all_ids_cache and self._all_documents_cache:
                tokenized_query = self._tokenize(query)
                if tokenized_query:
                    try:
                        bm25_scores = self._bm25_index.get_scores(tokenized_query)
                        sorted_indices = sorted(
                            range(len(bm25_scores)),
                            key=lambda i: bm25_scores[i],
                            reverse=True
                        )
                        taken = 0
                        for idx in sorted_indices:
                            if taken >= top_k * 2:
                                break
                            if bm25_scores[idx] == 0:
                                continue
                            if idx >= len(self._all_metadatas_cache):
                                continue
                            if idx >= len(self._all_ids_cache):
                                continue
                            if idx >= len(self._all_documents_cache):
                                continue
                            meta = self._all_metadatas_cache[idx]
                            doc_id = self._all_ids_cache[idx]
                            doc = self._all_documents_cache[idx]
                            if not isinstance(meta, dict) or not doc_id:
                                continue
                            if where_clause and meta.get("root_folder") != folder_filter:
                                continue
                            bm25_items.append({
                                "id": doc_id,
                                "doc": doc if doc else "",
                                "meta": meta
                            })
                            taken += 1
                    except Exception as e:
                        logger.warning(f"RAG BM25 ranking failed: {e}")
                        bm25_items = []

            fused = self._reciprocal_rank_fusion([vector_items, bm25_items])

            file_map = {}
            for item in fused[:top_k * 3]:
                meta = item.get("meta") or {}
                if not isinstance(meta, dict):
                    continue
                fpath = meta.get("file_path", "")
                if not fpath:
                    continue
                item_id = item.get("id")
                if not item_id:
                    continue
                if fpath not in file_map:
                    file_map[fpath] = {
                        "file_name": meta.get("file_name", ""),
                        "file_path": fpath,
                        "root_folder": meta.get("root_folder", ""),
                        "chunks_map": {},
                        "modified": meta.get("modified", ""),
                        "file_size": meta.get("file_size", 0)
                    }
                file_map[fpath]["chunks_map"][item_id] = item.get("doc", "") or ""

            final_results = []
            for fpath, data in file_map.items():
                try:
                    with self.db_lock:
                        all_chunks = self.rag_collection.get(where={"file_path": fpath})
                except Exception:
                    all_chunks = {"documents": []}

                total_chunks = len(all_chunks["documents"]) if all_chunks.get("documents") else 0
                unique_chunks = list(data["chunks_map"].values())
                content = "\n\n".join(unique_chunks)
                file_size_bytes = data["file_size"] if data["file_size"] else 0
                is_complete = total_chunks > 0 and len(unique_chunks) >= total_chunks

                final_results.append({
                    "file_name": data["file_name"],
                    "file_path": fpath,
                    "root_folder": data["root_folder"],
                    "file_size_bytes": file_size_bytes,
                    "total_chunks": total_chunks,
                    "chunks_found": len(unique_chunks),
                    "is_complete": is_complete,
                    "modified": data["modified"],
                    "content": content
                })

            if final_results:
                final_results.sort(key=lambda x: self._recency_boost(x), reverse=True)
                logger.info(f"RAG hybrid search: {len(final_results)} files matched.")
                return final_results[:top_k]

            return self._fallback_keyword_search(query, top_k, folder_filter)

        except Exception as e:
            logger.error(f"RAG search failed: {e}")
            return self._fallback_keyword_search(query, top_k, folder_filter)

    def _recency_boost(self, file_result):
        try:
            mod_str = file_result.get("modified", "")
            if mod_str:
                mod_date = datetime.fromisoformat(mod_str)
                now = datetime.now()
                if mod_date > now:
                    return 1.0 + RAG_RECENCY_BOOST
                days_old = (now - mod_date).days
                if days_old < 0:
                    days_old = 0
                boost = max(0, 1 - (days_old / 365)) * RAG_RECENCY_BOOST
                return boost + 1
        except Exception:
            pass
        return 1.0

    def _fallback_keyword_search(self, query, top_k, folder_filter=None):
        try:
            with self.db_lock:
                results = self.rag_collection.get()

            documents = results.get("documents") or []
            metadatas = results.get("metadatas") or []
            ids = results.get("ids") or []

            if not documents:
                return []

            query_tokens = set(self._tokenize(query))
            if not query_tokens:
                return []

            file_map = {}
            for i, doc in enumerate(documents):
                if not doc:
                    continue
                if i >= len(metadatas):
                    continue
                meta = metadatas[i]
                if not isinstance(meta, dict):
                    continue
                if folder_filter and meta.get("root_folder") != folder_filter:
                    continue
                fpath = meta.get("file_path", "")
                if not fpath:
                    continue
                if fpath not in file_map:
                    file_map[fpath] = {
                        "file_name": meta.get("file_name", ""),
                        "file_path": fpath,
                        "root_folder": meta.get("root_folder", ""),
                        "chunks_map": {},
                        "modified": meta.get("modified", ""),
                        "file_size": meta.get("file_size", 0)
                    }
                if i < len(ids) and ids[i]:
                    doc_id = ids[i]
                else:
                    doc_id = f"{fpath}_{i}"
                file_map[fpath]["chunks_map"][doc_id] = doc

            matched = []
            for fpath, data in file_map.items():
                combined = " ".join(data["chunks_map"].values()).lower()
                score = sum(1 for tok in query_tokens if tok in combined)
                if score > 0:
                    matched.append((fpath, score))

            if not matched:
                return []

            matched.sort(key=lambda x: x[1], reverse=True)

            final_results = []
            for fpath, _ in matched[:top_k]:
                data = file_map[fpath]
                unique_chunks = list(data["chunks_map"].values())
                total_chunks = len(unique_chunks)
                content = "\n\n".join(unique_chunks)
                file_size_bytes = data["file_size"] if data["file_size"] else 0
                final_results.append({
                    "file_name": data["file_name"],
                    "file_path": fpath,
                    "root_folder": data["root_folder"],
                    "file_size_bytes": file_size_bytes,
                    "total_chunks": total_chunks,
                    "chunks_found": total_chunks,
                    "is_complete": True,
                    "modified": data["modified"],
                    "content": content
                })

            final_results.sort(key=lambda x: self._recency_boost(x), reverse=True)
            logger.info(f"RAG fallback keyword search: {len(final_results)} files matched.")
            return final_results

        except Exception as e:
            logger.error(f"RAG fallback search failed: {e}")
            return []

    def add_folder(self, folder_path, is_default=False):
        try:
            resolved = str(Path(folder_path).expanduser().resolve())
        except Exception as e:
            logger.error(f"RAG add folder: path resolve failed: {e}")
            return {"success": False, "error": "Invalid path."}

        if not os.path.exists(resolved):
            logger.warning(f"RAG add folder: not found: {resolved}")
            return {"success": False, "error": "Folder does not exist."}

        if not os.path.isdir(resolved):
            logger.warning(f"RAG add folder: not a directory: {resolved}")
            return {"success": False, "error": "Path is not a folder."}

        if self.filter_engine.is_system_path(resolved):
            logger.warning(f"RAG add folder: system path blocked: {resolved}")
            return {"success": False, "error": "System folders cannot be indexed."}

        if self.filter_engine.is_sensitive_path(resolved):
            logger.warning(f"RAG add folder: sensitive path blocked: {resolved}")
            return {"success": False, "error": "Sensitive folders cannot be indexed."}

        folders = config_store.load_folders()
        resolved_cmp = resolved.lower() if os.name == "nt" else resolved
        for f in folders:
            existing_cmp = f["path"].lower() if os.name == "nt" else f["path"]
            if existing_cmp == resolved_cmp:
                logger.info(f"RAG add folder: already indexed: {resolved}")
                return {"success": False, "error": "Folder already indexed."}

        folders.append({
            "path": resolved,
            "added_at": datetime.now().isoformat(),
            "last_indexed": "",
            "is_default": is_default,
            "enabled": True
        })
        config_store.save_folders(folders)
        logger.info(f"RAG add folder: registered: {resolved}")

        threading.Thread(
            target=self.reindex_folder,
            args=(resolved,),
            daemon=True
        ).start()

        return {"success": True, "path": resolved}

    def remove_folder(self, folder_path):
        try:
            resolved = str(Path(folder_path).expanduser().resolve())
        except Exception as e:
            logger.error(f"RAG remove folder: path resolve failed: {e}")
            return {"success": False, "error": "Invalid path."}

        folders = config_store.load_folders()
        new_folders = [f for f in folders if f["path"] != resolved]

        if len(new_folders) == len(folders):
            logger.warning(f"RAG remove folder: not registered: {resolved}")
            return {"success": False, "error": "Folder not registered."}

        config_store.save_folders(new_folders)
        self._remove_chunks_for_folder(resolved)

        with self.hash_lock:
            self.file_hashes = {
                k: v for k, v in self.file_hashes.items()
                if not self._is_under_folder(k, resolved)
            }
            self._save_json(self.file_hashes_file, self.file_hashes)

        self._rebuild_bm25_cache()
        logger.info(f"RAG remove folder: complete: {resolved}")
        return {"success": True, "path": resolved}

    def list_folders(self):
        folders = config_store.load_folders()
        result = []
        for f in folders:
            stats = self.get_folder_stats(f["path"])
            result.append({
                "path": f["path"],
                "added_at": f.get("added_at", ""),
                "last_indexed": f.get("last_indexed", ""),
                "is_default": f.get("is_default", False),
                "enabled": f.get("enabled", True),
                "file_count": stats["file_count"],
                "chunk_count": stats["chunk_count"]
            })
        return result

    def get_folder_stats(self, folder_path):
        try:
            resolved = str(Path(folder_path).expanduser().resolve())
        except Exception:
            return {"file_count": 0, "chunk_count": 0}

        try:
            with self.db_lock:
                data = self.rag_collection.get(where={"root_folder": resolved})

            files = set()
            if data and data.get("metadatas"):
                for meta in data["metadatas"]:
                    files.add(meta.get("file_path"))

            return {
                "file_count": len(files),
                "chunk_count": len(data["ids"]) if data and data.get("ids") else 0
            }
        except Exception as e:
            logger.warning(f"RAG folder stats failed for {resolved}: {e}")
            return {"file_count": 0, "chunk_count": 0}

    def reindex_folder(self, folder_path):
        try:
            resolved = str(Path(folder_path).expanduser().resolve())
        except Exception as e:
            logger.error(f"RAG reindex: path resolve failed: {e}")
            return {"success": False, "error": "Invalid path."}

        self.index_lock.acquire()
        try:
            folders = config_store.load_folders()
            target = next((f for f in folders if f["path"] == resolved), None)
            if not target:
                logger.warning(f"RAG reindex: folder not registered: {resolved}")
                return {"success": False, "error": "Folder not registered."}

            logger.info(f"RAG reindex: starting for {resolved}")
            self._remove_chunks_for_folder(resolved)

            with self.hash_lock:
                self.file_hashes = {
                    k: v for k, v in self.file_hashes.items()
                    if not self._is_under_folder(k, resolved)
                }

            self._set_status(
                state="scanning",
                current_folder=resolved,
                started_at=datetime.now().isoformat(),
                files_total=0,
                files_done=0,
                chunks_done=0,
                last_error=""
            )

            files = list(self.walker.walk_folder(resolved))
            self._set_status(files_total=len(files))

            files_done = 0
            chunks_done = 0

            for file_path in files:
                if self._shutdown_flag:
                    break
                if not self._pause_event.is_set():
                    self._pause_event.wait()
                    if self._shutdown_flag:
                        break

                try:
                    file_hash = self._get_file_hash(str(file_path))
                except Exception as e:
                    logger.warning(f"RAG reindex hash failed: {file_path}: {e}")
                    files_done += 1
                    self._set_status(files_done=files_done)
                    continue

                success, added = self._process_file(str(file_path), resolved, file_hash)
                if success:
                    with self.hash_lock:
                        self.file_hashes[str(file_path)] = file_hash
                    chunks_done += added
                files_done += 1
                self._set_status(files_done=files_done, chunks_done=chunks_done)

            with self.hash_lock:
                self._save_json(self.file_hashes_file, self.file_hashes)

            self._rebuild_bm25_cache()

            for f in folders:
                if f["path"] == resolved:
                    f["last_indexed"] = datetime.now().isoformat()
            config_store.save_folders(folders)

            self._set_status(
                state="idle",
                current_folder="",
                last_completed=datetime.now().isoformat()
            )
            logger.info(f"RAG reindex: complete for {resolved}")
            return {"success": True, "path": resolved, "chunks_added": chunks_done}

        except Exception as e:
            logger.error(f"RAG reindex failed for {resolved}: {e}")
            self._set_status(state="error", last_error=str(e))
            return {"success": False, "error": str(e)}
        finally:
            self.index_lock.release()

    def pause_indexing(self):
        self._pause_event.clear()
        self._set_status(state="paused")
        logger.info("RAG indexer: paused.")
        return {"success": True}

    def resume_indexing(self):
        snap = self._get_status_snapshot()
        self._pause_event.set()
        if snap.get("state") == "paused":
            self._set_status(state="scanning")
        logger.info("RAG indexer: resumed.")
        return {"success": True}

    def get_filters(self):
        return config_store.load_filters()

    def update_filters(self, filters_dict):
        try:
            config_store.save_filters(filters_dict)
            self.filter_engine.reload(filters_dict)
            logger.info("RAG indexer: filters updated.")
            return {"success": True}
        except Exception as e:
            logger.error(f"RAG filters update failed: {e}")
            return {"success": False, "error": str(e)}

    def purge_all(self):
        self.index_lock.acquire()
        try:
            with self.db_lock:
                all_ids = self.rag_collection.get().get("ids", [])
                if all_ids:
                    self.rag_collection.delete(ids=all_ids)

            with self.hash_lock:
                self.file_hashes = {}
                self._save_json(self.file_hashes_file, self.file_hashes)

            self._rebuild_bm25_cache()
            self._set_status(
                state="idle",
                current_folder="",
                files_total=0,
                files_done=0,
                chunks_done=0
            )
            logger.info("RAG indexer: full purge complete.")
            return {"success": True}
        except Exception as e:
            logger.error(f"RAG purge failed: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.index_lock.release()

    def purge_folder(self, folder_path):
        try:
            resolved = str(Path(folder_path).expanduser().resolve())
        except Exception as e:
            logger.error(f"RAG purge folder: path resolve failed: {e}")
            return {"success": False, "error": "Invalid path."}

        self.index_lock.acquire()
        try:
            self._remove_chunks_for_folder(resolved)

            with self.hash_lock:
                self.file_hashes = {
                    k: v for k, v in self.file_hashes.items()
                    if not self._is_under_folder(k, resolved)
                }
                self._save_json(self.file_hashes_file, self.file_hashes)

            self._rebuild_bm25_cache()
            logger.info(f"RAG indexer: folder purge complete: {resolved}")
            return {"success": True, "path": resolved}
        finally:
            self.index_lock.release()

    def get_indexed_folders_summary(self):
        folders = config_store.load_folders()
        if not folders:
            return "No folders indexed."
        names = []
        for f in folders:
            if f.get("enabled", True):
                names.append(Path(f["path"]).name)
        snap = self._get_status_snapshot()
        return (
            f"Folders: {', '.join(names)} | "
            f"State: {snap['state']} | "
            f"Files: {snap['files_total']} | "
            f"Chunks: {snap['chunks_done']}"
        )

    def shutdown(self):
        self._shutdown_flag = True
        self._pause_event.set()
        try:
            if self._indexing_thread and self._indexing_thread.is_alive():
                self._indexing_thread.join(timeout=10)
        except Exception as e:
            logger.warning(f"RAG shutdown: thread join warning: {e}")
        try:
            with self.hash_lock:
                self._save_json(self.file_hashes_file, self.file_hashes)
        except Exception as e:
            logger.warning(f"RAG shutdown: hash save failed: {e}")
        logger.info("RAG indexer: shutdown complete.")


rag_engine = RagEngine()