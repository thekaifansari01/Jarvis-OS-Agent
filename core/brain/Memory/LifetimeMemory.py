import os
import json
import threading
import time
import networkx as nx
import numpy as np
from datetime import datetime
from pathlib import Path
import re
from groq import Groq
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY, GROQ_FAST_MODEL

class LifetimeMemoryEngine:
    def __init__(self):
        self.db_path = Path("Data/jarvis_memory/lifetime_graph.json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.graph = nx.DiGraph()
        self._lock = threading.Lock()
        self.is_dirty = False
        
        logger.info("⏳ Loading Semantic Embedding Model (all-MiniLM-L6-v2) for LTM...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2') 
        self.node_embeddings = {}
        
        self._load_graph()
        self._start_background_saver()

    def _compute_all_embeddings(self):
        nodes = list(self.graph.nodes())
        if nodes:
            embeddings = self.embedder.encode(nodes)
            for node, emb in zip(nodes, embeddings):
                self.node_embeddings[node] = emb

    def _get_embedding(self, text):
        return self.embedder.encode([text])[0]
        
    def get_all_node_names(self, limit=100):
        with self._lock:
            nodes = sorted(self.graph.degree, key=lambda x: x[1], reverse=True)
            return [n[0] for n in nodes[:limit]]

    def _load_graph(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
            except Exception:
                self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()
        self._compute_all_embeddings()

    def _save_graph(self):
        with self._lock:
            try:
                data = nx.node_link_data(self.graph)
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    def _start_background_saver(self):
        def saver_loop():
            while True:
                time.sleep(30)
                if self.is_dirty:
                    self._save_graph()
                    self.is_dirty = False
        threading.Thread(target=saver_loop, daemon=True).start()

    def record_triplet(self, source, relation, target, date_str=None):
        if not source or not relation or not target:
            return
        src = str(source).strip().title()
        rel = str(relation).strip().upper()
        tgt = str(target).strip().title()
        if not src or not rel or not tgt:
            return
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        
        with self._lock:
            if src not in self.node_embeddings:
                self.node_embeddings[src] = self._get_embedding(src)
            if tgt not in self.node_embeddings:
                self.node_embeddings[tgt] = self._get_embedding(tgt)

            edge_data = self.graph.get_edge_data(src, tgt, default=None)
            if edge_data is not None and edge_data.get('relation') == rel:
                self.graph.edges[src, tgt]['weight'] = edge_data.get('weight', 1) + 1
                self.graph.edges[src, tgt]['last_seen'] = date_str
            else:
                self.graph.add_edge(src, tgt, relation=rel, date=date_str, weight=1, last_seen=date_str)
        self.is_dirty = True

    def _clean_json(self, raw_text):
        m = re.search(r'(\[.*\]|{.*})', raw_text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return raw_text.strip()

    def _extract_triplets(self, text):
        if not self.groq_client or not text.strip():
            return []
        prompt = f'Extract knowledge graph triplets from the text. Return ONLY a JSON object with a "triplets" array of objects with keys: "source", "relation", "target". Keep entities short (1-2 words). Make relations UPPERCASE. Text: {text[:3000]}'
        for _ in range(3):
            try:
                res = self.groq_client.chat.completions.create(
                    model=GROQ_FAST_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )
                raw = res.choices[0].message.content.strip()
                data = json.loads(self._clean_json(raw))
                return data.get("triplets", [])
            except Exception:
                time.sleep(1)
        return []

    def archive_old_chats(self, chat_list, date_str=None):
        if not chat_list:
            return
        target_date = date_str or datetime.now().strftime("%Y-%m-%d")
        def _process():
            raw_text = "\n".join([f"{m.get('role', 'UNKNOWN')}: {m.get('message', '')}" for m in chat_list])
            triplets = self._extract_triplets(raw_text)
            if triplets:
                for t in triplets:
                    src = str(t.get("source", "")).strip().title()
                    rel = str(t.get("relation", "")).strip().upper()
                    tgt = str(t.get("target", "")).strip().title()
                    if src and rel and tgt:
                        self.record_triplet(src, rel, tgt, target_date)
        threading.Thread(target=_process, daemon=True).start()

    def search_lifetime_memory(self, queries, top_k=3, threshold=0.75):
        if not queries:
            return "Observation: Query empty."
        
        if isinstance(queries, str):
            entities = [queries.strip()]
        elif isinstance(queries, list):
            entities = [str(q).strip() for q in queries if str(q).strip()]
        else:
            return "Observation: Invalid query format."

        if not entities:
            return "Observation: No clear entities provided."
        
        results = []
        today = datetime.now().date()
        
        with self._lock:
            for ent in entities:
                ent_emb = self._get_embedding(ent)
                matched_nodes = []
                
                for node, node_emb in self.node_embeddings.items():
                    sim = 1 - cosine(ent_emb, node_emb)
                    if sim >= threshold or ent.lower() in node.lower() or node.lower() in ent.lower():
                        matched_nodes.append(node)
                
                for matched_node in matched_nodes:
                    undirected_g = self.graph.to_undirected()
                    try:
                        neighbors_dict = nx.single_source_shortest_path_length(undirected_g, matched_node, cutoff=2)
                    except Exception:
                        continue
                    
                    subgraph = self.graph.subgraph(neighbors_dict.keys())
                    
                    for u, v, data in subgraph.edges(data=True):
                        rel = data.get('relation', 'RELATES_TO')
                        weight = data.get('weight', 1)
                        last_seen = data.get('last_seen', data.get('date', ''))
                        
                        days_diff = 0
                        if last_seen:
                            try:
                                last_date = datetime.strptime(last_seen, "%Y-%m-%d").date()
                                days_diff = (today - last_date).days
                            except:
                                pass
                        
                        match_boost = 1.5 if (u in matched_nodes or v in matched_nodes) else 1.0
                        
                        depth_u = neighbors_dict.get(u, 2)
                        depth_v = neighbors_dict.get(v, 2)
                        min_depth = min(depth_u, depth_v)
                        depth_penalty = 1.0 if min_depth == 0 else 0.8
                        
                        time_penalty = 0.5 if days_diff > 180 else 1.0
                        
                        adjusted_weight = weight * time_penalty * depth_penalty * match_boost
                        
                        results.append({
                            "text": f"[{u}] --({rel})--> [{v}]",
                            "weight": adjusted_weight
                        })

        if not results:
            return "Observation: Found nothing in Graph Memory for these entities."
        
        results.sort(key=lambda x: x["weight"], reverse=True)
        unique = []
        seen = set()
        for r in results:
            if r["text"] not in seen:
                seen.add(r["text"])
                unique.append(r["text"])
        
        res_str = "\n".join(unique[:20])
        return f"Observation: Found relations in Graph Memory:\n{res_str}"

ltm_engine = LifetimeMemoryEngine()