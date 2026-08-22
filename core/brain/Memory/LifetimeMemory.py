import os
import json
import threading
import time
import networkx as nx
import numpy as np
from datetime import datetime
from pathlib import Path
import re
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
from core.logger.logger import logger

class LifetimeMemoryEngine:
    def __init__(self):
        self.db_path = Path("Data/jarvis_memory/lifetime_graph.json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph = nx.DiGraph()
        self._lock = threading.RLock()

        logger.info("⏳ Loading Semantic Embedding Model (BAAI/bge-small-en-v1.5) for LTM...")
        self.embedder = SentenceTransformer('BAAI/bge-small-en-v1.5')
        self.node_embeddings = {}
        self.metadata_embeddings = {}

        self._load_graph()
        self._start_auto_cleanup()

    def _compute_all_embeddings(self):
        nodes = list(self.graph.nodes())
        if nodes:
            embeddings = self.embedder.encode(nodes)
            for node, emb in zip(nodes, embeddings):
                self.node_embeddings[node] = emb

        for u, v, data in self.graph.edges(data=True):
            if 'metadata' in data and data['metadata'] and data['metadata'].get('source_message'):
                msg = data['metadata']['source_message']
                if msg and msg not in self.metadata_embeddings:
                    self.metadata_embeddings[msg] = self._get_embedding(msg)

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
            except Exception as e:
                logger.error(f"Error loading graph: {e}")
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
            except Exception as e:
                logger.error(f"Error saving graph: {e}")

    def _start_auto_cleanup(self):
        def cleanup_loop():
            while True:
                time.sleep(86400)
                self._archive_old_edges()
        threading.Thread(target=cleanup_loop, daemon=True).start()

    def _archive_old_edges(self):
        with self._lock:
            now = datetime.now()
            to_archive = []
            for u, v, data in self.graph.edges(data=True):
                last_seen = data.get('last_seen')
                if last_seen:
                    try:
                        last_date = datetime.strptime(last_seen, "%Y-%m-%d")
                        if (now - last_date).days > 180:
                            to_archive.append((u, v))
                    except Exception as e:
                        logger.error(f"Date parse error in archive: {e}")
            for u, v in to_archive:
                self.graph.edges[u, v]['archived'] = True
            if to_archive:
                self._save_graph()

    def record_triplet(self, source, relation, target, date_str=None, metadata=None, inverse=None):
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
                self.graph.edges[src, tgt]['count'] = edge_data.get('count', 1) + 1
                self.graph.edges[src, tgt]['last_seen'] = date_str
                if metadata:
                    self.graph.edges[src, tgt]['metadata'] = metadata
                if 'first_seen' not in edge_data:
                    self.graph.edges[src, tgt]['first_seen'] = date_str
                if 'archived' in self.graph.edges[src, tgt]:
                    del self.graph.edges[src, tgt]['archived']
            else:
                self.graph.add_edge(src, tgt, relation=rel, date=date_str, weight=1, count=1, first_seen=date_str, last_seen=date_str, metadata=metadata)

            if metadata and metadata.get('source_message'):
                msg = metadata['source_message']
                if msg not in self.metadata_embeddings:
                    self.metadata_embeddings[msg] = self._get_embedding(msg)

            if inverse:
                inv_rel = str(inverse.get("relation", "")).strip().upper()
                inv_tgt = str(inverse.get("target", "")).strip().title()
                if inv_rel and inv_tgt:
                    inv_edge_data = self.graph.get_edge_data(tgt, inv_tgt, default=None)
                    if inv_edge_data is not None and inv_edge_data.get('relation') == inv_rel:
                        self.graph.edges[tgt, inv_tgt]['weight'] = inv_edge_data.get('weight', 1) + 1
                        self.graph.edges[tgt, inv_tgt]['last_seen'] = date_str
                    else:
                        self.graph.add_edge(tgt, inv_tgt, relation=inv_rel, date=date_str, weight=1, count=1, first_seen=date_str, last_seen=date_str, metadata=metadata)

        self._save_graph()

    def search_lifetime_memory(self, queries, top_k=3, threshold=0.82):
        if not queries:
            return "Observation: Query empty."

        entities = []
        relations = []
        if isinstance(queries, str):
            entities = [queries.strip()]
        elif isinstance(queries, list):
            for q in queries:
                if isinstance(q, dict):
                    ent = q.get('entity', '')
                    if ent:
                        entities.append(str(ent).strip())
                    rel = q.get('relation', '')
                    if rel:
                        relations.append(str(rel).strip().lower())
                else:
                    if str(q).strip():
                        entities.append(str(q).strip())

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

                for msg, msg_emb in self.metadata_embeddings.items():
                    sim = 1 - cosine(ent_emb, msg_emb)
                    if sim >= threshold:
                        for u, v, data in self.graph.edges(data=True):
                            if data.get('metadata', {}).get('source_message') == msg:
                                if u not in matched_nodes:
                                    matched_nodes.append(u)
                                if v not in matched_nodes:
                                    matched_nodes.append(v)

                for u, v, data in self.graph.edges(data=True):
                    rel = data.get('relation', '')
                    match_found = False
                    if ent.lower() in rel.lower():
                        match_found = True
                    for r in relations:
                        if r in rel.lower():
                            match_found = True
                    if match_found:
                        if u not in matched_nodes:
                            matched_nodes.append(u)
                        if v not in matched_nodes:
                            matched_nodes.append(v)

                for matched_node in matched_nodes:
                    undirected_g = self.graph.to_undirected()
                    try:
                        neighbors_dict = nx.single_source_shortest_path_length(undirected_g, matched_node, cutoff=1)
                    except Exception as e:
                        logger.error(f"Shortest path calculation failed: {e}")
                        continue

                    subgraph = self.graph.subgraph(neighbors_dict.keys())

                    for u, v, data in subgraph.edges(data=True):
                        if data.get('archived', False):
                            continue
                        rel = data.get('relation', 'RELATES_TO')
                        weight = data.get('weight', 1)
                        count = data.get('count', 1)
                        last_seen = data.get('last_seen', data.get('date', ''))
                        metadata = data.get('metadata', {})
                        source_msg = metadata.get('source_message', '')

                        days_diff = 0
                        if last_seen:
                            try:
                                last_date = datetime.strptime(last_seen, "%Y-%m-%d").date()
                                days_diff = (today - last_date).days
                            except Exception:
                                pass

                        match_boost = 1.5 if (u in matched_nodes or v in matched_nodes) else 1.0

                        depth_u = neighbors_dict.get(u, 2)
                        depth_v = neighbors_dict.get(v, 2)
                        min_depth = min(depth_u, depth_v)
                        depth_penalty = 1.0 if min_depth == 0 else 0.8

                        time_penalty = 0.5 if days_diff > 180 else 1.0
                        count_boost = min(1.0 + (count - 1) * 0.1, 2.0)

                        adjusted_weight = weight * time_penalty * depth_penalty * match_boost * count_boost

                        res_text = f"[{u}] --({rel})--> [{v}]"
                        if source_msg:
                            res_text += f" (Context: {source_msg})"

                        results.append({
                            "text": res_text,
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