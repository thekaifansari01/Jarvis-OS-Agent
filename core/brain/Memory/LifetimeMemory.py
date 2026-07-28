import os
import json
import uuid
import threading
from datetime import datetime
from pathlib import Path
import chromadb

from groq import Groq
from google import genai
from google.genai import types

from core.logger.logger import logger
from core.brain.config import GEMINI_API_KEY, GROQ_API_KEY, GEMINI_EMBEDDING_MODEL, EMBEDDING_DIM, GROQ_SUMMARY_MODEL

class LifetimeMemoryEngine:
    def __init__(self):
        self.db_path = Path("Data/jarvis_memory/lifetime_db")
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.google_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
        self.groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        
        try:
            self.chroma_client = chromadb.PersistentClient(path=str(self.db_path))
            self.ltm_collection = self.chroma_client.get_or_create_collection(name="jarvis_episodic_memory")
            logger.info("LTM ChromaDB Initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize LTM ChromaDB: {e}")

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
            logger.error(f"LTM Embedding error: {e}")
            return None

    def _generate_episode_summary(self, chat_logs, date_str):
        if not self.groq_client or not chat_logs:
            return None
            
        prompt = f"""Analyze this chat log from {date_str} and extract a dense, third-person factual summary.
        Focus ONLY on:
        1. Important facts the user shared (life events, ideas, preferences).
        2. Major tasks completed or decisions made.
        3. Ignore small talk, greetings, or generic system errors.

        Chat Log:
        {chat_logs}

        Format as a short paragraph. If nothing important happened, reply with EXACTLY "NO_IMPORTANT_DATA".
        """
        
        try:
            response = self.groq_client.chat.completions.create(
                model=GROQ_SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": "You are a memory consolidation AI. Extract only permanent, useful facts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            result = response.choices[0].message.content.strip()
            return None if result == "NO_IMPORTANT_DATA" else result
        except Exception as e:
            logger.error(f"LTM Summarization error: {e}")
            return None

    def archive_old_chats(self, chat_list, date_str=None):
        if not chat_list: return
        
        target_date = date_str or datetime.now().strftime('%Y-%m-%d')
        
        def _process_and_store():
            try:
                raw_text = "\n".join([f"{msg['role']}: {msg['message']}" for msg in chat_list])
                
                summary = self._generate_episode_summary(raw_text, target_date)
                
                if summary:
                    embedding = self.get_embedding(summary, "search_document")
                    if embedding:
                        doc_id = f"episode_{target_date}_{uuid.uuid4().hex[:8]}"
                        
                        self.ltm_collection.upsert(
                            ids=[doc_id],
                            embeddings=[embedding],
                            metadatas=[{"date": target_date, "type": "daily_summary"}],
                            documents=[f"Date: {target_date}\nMemory: {summary}"]
                        )
            except Exception as e:
                logger.error(f"Failed to archive LTM: {e}")

        threading.Thread(target=_process_and_store, daemon=True).start()

    def search_lifetime_memory(self, query, top_k=3):
        if not query or not query.strip(): 
            return "Observation: Query was empty."
            
        query_embedding = self.get_embedding(query, "search_query")
        
        if not query_embedding or self.ltm_collection.count() == 0: 
            return "Observation: No relevant past memories found in Lifetime Database."
            
        try:
            results = self.ltm_collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self.ltm_collection.count()),
                include=["documents", "metadatas"]
            )
            
            hits = []
            if results['documents'] and results['documents'][0]:
                for doc in results['documents'][0]:
                    hits.append(f"Past Record:\n{doc}")
            
            if hits:
                return "Observation: Found these records from Lifetime Memory:\n\n" + "\n\n".join(hits)
            else:
                return "Observation: Found nothing relevant in Lifetime Memory for this query."
                
        except Exception as e:
            return f"Observation: Lifetime Memory search failed due to error: {e}"

ltm_engine = LifetimeMemoryEngine()