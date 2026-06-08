import os
import json
import hashlib
import re
import threading
from datetime import datetime
from pathlib import Path
import chromadb
import platform

from google import genai
from google.genai import types 
from core.brain.config import GEMINI_API_KEY 
from core.logger.logger import logger

from core.brain.config import (
    GEMINI_EMBEDDING_MODEL, EMBEDDING_DIM
)

from tools.workspace.workspace import workspace 

class RagEngine:
    def __init__(self):
        self.vault_path = workspace.vault_dir
        self.creations_path = workspace.creations_dir
        
        self.db_path = Path("Data/jarvis_memory/rag_chroma_db")
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.file_hashes_file = Path("Data/jarvis_memory/rag_hashes.json")
        
        self.file_hashes = self._load_json(self.file_hashes_file, {})
        
        self.google_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
        
        self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
        self.rag_collection = self.chroma_client.get_or_create_collection(name="jarvis_vault_docs")
        
        threading.Thread(target=self._index_vault_files, daemon=True).start()

    def _load_json(self, file_path, default):
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
            return default
        except: return default
    
    def _save_json(self, file_path, data):
        try:
            with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)
        except: pass

    def get_embedding(self, text, input_type="search_document"):
        if not text or not text.strip() or not self.google_client: return None
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

    def _smart_chunk_text(self, text, file_extension=".txt", max_chars=15000):
        """
        🔥 UPGRADE 1: Code-Aware Smart Chunker.
        Does not blindy cut Python/JS files. Splits them by functions and classes.
        Uses 15000 characters for Gemini's massive 256K context window.
        """
        if file_extension in ['.py', '.js']:
            chunks = re.split(r'(?m)^(?=def |class )', text)
            valid_chunks = []
            current = ""
            for chunk in chunks:
                if len(current) + len(chunk) < max_chars * 1.5:
                    current += chunk
                else:
                    if current: valid_chunks.append(current.strip())
                    current = chunk
            if current: valid_chunks.append(current.strip())
            return valid_chunks if valid_chunks else [text]
        
        paragraphs = text.split('\n\n')
        chunks, current_chunk = [], ""
        for p in paragraphs:
            if len(current_chunk) + len(p) < max_chars: 
                current_chunk += p + "\n\n"
            else:
                if current_chunk: chunks.append(current_chunk.strip())
                current_chunk = p + "\n\n"
        if current_chunk: chunks.append(current_chunk.strip())
        return chunks if chunks else [text]

    def _get_file_hash(self, file_path):
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f: hasher.update(f.read())
        return hasher.hexdigest()

    def _index_vault_files(self):
        supported_extensions = ['.txt', '.md', '.json', '.py', '.js', '.csv']
        new_hashes, updated = {}, False
        
        folders_to_index = [self.vault_path, self.creations_path]
        
        for current_folder in folders_to_index:
            for root, _, files in os.walk(current_folder):
                for file_name in files:
                    ext = Path(file_name).suffix.lower()
                    if ext in supported_extensions:
                        file_path = Path(root) / file_name
                        file_hash = self._get_file_hash(file_path)
                        new_hashes[str(file_path)] = file_hash
                        
                        if self.file_hashes.get(str(file_path)) == file_hash: continue 
                            
                        logger.info(f"📚 Indexing to RAG Brain: {file_name}...")
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                if ext in ['.py', '.js']:
                                    lines = f.readlines()
                                    content = "".join([f"Line {idx+1}: {line}" for idx, line in enumerate(lines)])
                                else:
                                    content = f.read()
                                    
                                if not content.strip(): continue
                                
                                for i, chunk in enumerate(self._smart_chunk_text(content, ext)):
                                    embedding = self.get_embedding(chunk, "search_document")
                                    if embedding:
                                        self.rag_collection.upsert(
                                            ids=[f"{file_name}_chunk_{i}"],
                                            embeddings=[embedding],
                                            metadatas=[{"file_name": file_name}],
                                            documents=[chunk]
                                        )
                                updated = True
                        except Exception as e: 
                            logger.error(f"Error indexing file {file_name}: {e}")
        
        if updated or len(new_hashes) != len(self.file_hashes):
            self.file_hashes = new_hashes
            self._save_json(self.file_hashes_file, self.file_hashes)
            logger.info("✅ Jarvis Workspace & Vault Indexing complete.")

    def search_vault(self, query, top_k=15, distance_threshold=1.5):
        if not query or not query.strip(): return []
        query_embedding = self.get_embedding(query, "search_query")
        if not query_embedding or self.rag_collection.count() == 0: return []
        
        results = self.rag_collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.rag_collection.count()),
            include=["documents", "metadatas", "distances"]
        )
        hits = []
        if results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                dist = results['distances'][0][i] if 'distances' in results and results['distances'] else 0
                if dist <= distance_threshold:
                    hits.append({
                        "file_path": results['metadatas'][0][i]['file_name'],
                        "content": results['documents'][0][i]
                    })
        return hits

rag_engine = RagEngine()