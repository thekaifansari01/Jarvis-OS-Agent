# RagEngine.py
import os
import json
import hashlib
import threading
from pathlib import Path
import time
from datetime import datetime
import chromadb
from google import genai
from google.genai import types
from rank_bm25 import BM25Okapi
import re

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

class RagEngine:
    def __init__(self):
        self.rag_path = Path.home() / "Documents" / "Jarvis" / "RAG"
        self.rag_path.mkdir(parents=True, exist_ok=True)

        self.db_path = Path("Data/jarvis_memory/rag_chroma_db")
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.file_hashes_file = Path("Data/jarvis_memory/rag_hashes.json")

        self.file_hashes = self._load_json(self.file_hashes_file, {})
        self.google_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

        # [NEW]: Thread lock to prevent ChromaDB Access Violations on Windows
        self.db_lock = threading.Lock()

        self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
        self.rag_collection = self.chroma_client.get_or_create_collection(name="jarvis_vault_docs")

        self._all_documents_cache = None
        self._all_metadatas_cache = None
        self._all_ids_cache = None
        self._bm25_index = None
        self._corpus_tokens = None

        threading.Thread(target=self._index_vault_files, daemon=True).start()

    def _load_json(self, file_path, default):
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return default
        except:
            return default

    def _save_json(self, file_path, data):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def get_embedding(self, text, input_type="search_document"):
        if not text or not text.strip() or not self.google_client:
            return None
        try:
            truncated = text[:2000] if len(text) > 2000 else text
            response = self.google_client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=truncated,
                config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)
            )
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"RAG Embedding error: {e}")
            return None

    def _recursive_chunk_text(self, text, file_extension=".txt"):
        chunk_size = RAG_CHUNK_SIZE
        overlap = RAG_CHUNK_OVERLAP

        if file_extension in ['.py', '.js']:
            lines = text.splitlines(keepends=True)
            chunks = []
            current = []
            current_len = 0
            for line in lines:
                line_len = len(line)
                if current_len + line_len > chunk_size and current:
                    chunks.append(''.join(current))
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
                chunks.append(''.join(current))
            return chunks if chunks else [text]

        paragraphs = text.split('\n\n')
        chunks = []
        current = []
        current_len = 0
        for p in paragraphs:
            p_len = len(p) + 2
            if current_len + p_len > chunk_size and current:
                chunks.append('\n\n'.join(current))
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
            chunks.append('\n\n'.join(current))
        return chunks if chunks else [text]

    def _get_file_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def _index_vault_files(self):
        supported_extensions = ['.txt', '.md', '.json', '.py', '.js', '.csv']
        new_hashes, updated = {}, False
        folders_to_index = [self.rag_path]

        for current_folder in folders_to_index:
            for root, _, files in os.walk(current_folder):
                for file_name in files:
                    ext = Path(file_name).suffix.lower()
                    if ext in supported_extensions:
                        file_path = Path(root) / file_name
                        file_hash = self._get_file_hash(file_path)
                        new_hashes[str(file_path)] = file_hash

                        if self.file_hashes.get(str(file_path)) == file_hash:
                            continue

                        logger.info(f"📚 Indexing to RAG Brain: {file_name}...")
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                if ext in ['.py', '.js']:
                                    lines = f.readlines()
                                    content = "".join([f"Line {idx+1}: {line}" for idx, line in enumerate(lines)])
                                else:
                                    content = f.read()

                                if not content.strip():
                                    continue

                                mod_time = os.path.getmtime(file_path)
                                mod_date = datetime.fromtimestamp(mod_time).isoformat()
                                file_size = os.path.getsize(file_path)

                                chunks = self._recursive_chunk_text(content, ext)
                                
                                # [NEW] Batch data to avoid repeated slow upsert loops
                                batch_ids = []
                                batch_embeddings = []
                                batch_metadatas = []
                                batch_documents = []

                                for i, chunk in enumerate(chunks):
                                    embedding = self.get_embedding(chunk, "search_document")
                                    if embedding:
                                        batch_ids.append(f"{file_name}_chunk_{i}")
                                        batch_embeddings.append(embedding)
                                        batch_metadatas.append({
                                            "file_name": file_name,
                                            "file_path": str(file_path),
                                            "modified": mod_date,
                                            "file_size": file_size
                                        })
                                        batch_documents.append(chunk)

                                if batch_ids:
                                    # [NEW] Lock the database thread during upsert to prevent Access Violation
                                    with self.db_lock:
                                        self.rag_collection.upsert(
                                            ids=batch_ids,
                                            embeddings=batch_embeddings,
                                            metadatas=batch_metadatas,
                                            documents=batch_documents
                                        )
                                updated = True
                        except Exception as e:
                            logger.error(f"Error indexing file {file_name}: {e}")

        if updated or len(new_hashes) != len(self.file_hashes):
            self.file_hashes = new_hashes
            self._save_json(self.file_hashes_file, self.file_hashes)
            self._rebuild_bm25_cache()
            logger.info("✅ Jarvis RAG Folder Indexing complete.")

    def _rebuild_bm25_cache(self):
        try:
            # Apply Lock
            with self.db_lock:
                all_data = self.rag_collection.get()
                
            if not all_data['documents']:
                self._all_documents_cache = None
                self._bm25_index = None
                return
            self._all_documents_cache = all_data['documents']
            self._all_metadatas_cache = all_data['metadatas']
            self._all_ids_cache = all_data['ids']

            tokenized_corpus = [doc.lower().split() for doc in all_data['documents']]
            self._bm25_index = BM25Okapi(tokenized_corpus)
            self._corpus_tokens = tokenized_corpus
        except Exception as e:
            logger.error(f"BM25 cache rebuild failed: {e}")
            self._bm25_index = None

    def _reciprocal_rank_fusion(self, results_list, k=60):
        scores = {}
        for results in results_list:
            for rank, item in enumerate(results):
                doc_id = item['id']
                if doc_id not in scores:
                    scores[doc_id] = {
                        'doc': item['doc'],
                        'meta': item['meta'],
                        'score': 0.0,
                        'rank_sum': 0
                    }
                scores[doc_id]['score'] += 1.0 / (k + rank + 1)
                scores[doc_id]['rank_sum'] += rank
        sorted_items = sorted(scores.values(), key=lambda x: x['score'], reverse=True)
        return sorted_items

    def search_vault(self, query, top_k=RAG_TOP_K):
        if not query or not query.strip():
            return []

        try:
            query_embedding = self.get_embedding(query, "search_query")
            if not query_embedding:
                return self._fallback_keyword_search(query, top_k)

            # Apply Lock
            with self.db_lock:
                vector_results = self.rag_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k * 2,
                    include=["documents", "metadatas", "distances"]
                )

            vector_items = []
            if vector_results['documents'] and vector_results['documents'][0]:
                for i, doc in enumerate(vector_results['documents'][0]):
                    meta = vector_results['metadatas'][0][i]
                    doc_id = f"{meta['file_name']}_{i}"  # approximate
                    vector_items.append({
                        'id': doc_id,
                        'doc': doc,
                        'meta': meta,
                        'rank': i
                    })

            self._rebuild_bm25_cache_if_needed()
            bm25_items = []
            if self._bm25_index:
                tokenized_query = query.lower().split()
                bm25_scores = self._bm25_index.get_scores(tokenized_query)
                sorted_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:top_k*2]
                for idx in sorted_indices:
                    if bm25_scores[idx] == 0:
                        continue
                    doc_id = self._all_ids_cache[idx]
                    bm25_items.append({
                        'id': doc_id,
                        'doc': self._all_documents_cache[idx],
                        'meta': self._all_metadatas_cache[idx],
                        'rank': idx
                    })

            fused = self._reciprocal_rank_fusion([vector_items, bm25_items])

            file_map = {}
            for item in fused[:top_k]:
                fname = item['meta']['file_name']
                fpath = item['meta']['file_path']
                if fname not in file_map:
                    file_map[fname] = {
                        "file_name": fname,
                        "file_path": fpath,
                        "chunks": [],
                        "modified": item['meta'].get('modified', ''),
                        "file_size": item['meta'].get('file_size', 0)
                    }
                file_map[fname]["chunks"].append(item['doc'])

            final_results = []
            for fname, data in file_map.items():
                # Apply Lock
                with self.db_lock:
                    all_chunks = self.rag_collection.get(where={"file_name": fname})
                    
                total_chunks = len(all_chunks['documents']) if all_chunks['documents'] else 0
                content = "\n\n".join(data["chunks"])
                file_size_bytes = data['file_size'] if data['file_size'] else 0
                is_complete = (len(data["chunks"]) >= total_chunks)
                final_results.append({
                    "file_name": fname,
                    "file_path": data["file_path"],
                    "file_size_bytes": file_size_bytes,
                    "total_chunks": total_chunks,
                    "chunks_found": len(data["chunks"]),
                    "is_complete": is_complete,
                    "content": content
                })

            if final_results:
                final_results.sort(key=lambda x: self._recency_boost(x), reverse=True)
                logger.info(f"📁 Hybrid search found {len(final_results)} files")
                return final_results

            return self._fallback_keyword_search(query, top_k)

        except Exception as e:
            logger.error(f"❌ RAG search error: {e}")
            return self._fallback_keyword_search(query, top_k)

    def _recency_boost(self, file_result):
        try:
            mod_str = file_result.get('modified', '')
            if mod_str:
                mod_date = datetime.fromisoformat(mod_str)
                days_old = (datetime.now() - mod_date).days
                boost = max(0, 1 - (days_old / 365)) * RAG_RECENCY_BOOST
                return boost + 1
        except:
            pass
        return 1.0

    def _rebuild_bm25_cache_if_needed(self):
        if self._bm25_index is None:
            self._rebuild_bm25_cache()

    def _fallback_keyword_search(self, query, top_k):
        try:
            # Apply Lock
            with self.db_lock:
                results = self.rag_collection.get()
                
            if not results['documents']:
                return []
            file_map = {}
            for i, doc in enumerate(results['documents']):
                fname = results['metadatas'][i]['file_name']
                fpath = results['metadatas'][i]['file_path']
                if fname not in file_map:
                    file_map[fname] = {
                        "file_name": fname,
                        "file_path": fpath,
                        "chunks": [],
                        "modified": results['metadatas'][i].get('modified', ''),
                        "file_size": results['metadatas'][i].get('file_size', 0)
                    }
                file_map[fname]["chunks"].append(doc)
            query_lower = query.lower()
            matched = []
            for fname, data in file_map.items():
                for chunk in data["chunks"]:
                    if query_lower in chunk.lower():
                        matched.append(fname)
                        break
            if not matched:
                return []
            final_results = []
            for fname in matched[:top_k]:
                data = file_map[fname]
                total_chunks = len(data["chunks"])
                content = "\n\n".join(data["chunks"])
                file_size_bytes = data['file_size'] if data['file_size'] else 0
                final_results.append({
                    "file_name": fname,
                    "file_path": data["file_path"],
                    "file_size_bytes": file_size_bytes,
                    "total_chunks": total_chunks,
                    "chunks_found": total_chunks,
                    "is_complete": True,
                    "content": content
                })
            return final_results
        except Exception as e:
            logger.error(f"Fallback search error: {e}")
            return []

rag_engine = RagEngine()