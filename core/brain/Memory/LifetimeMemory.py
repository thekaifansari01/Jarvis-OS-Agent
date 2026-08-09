# LifetimeMemory.py
import os
import json
import threading
import networkx as nx
from datetime import datetime
from pathlib import Path
import re
from groq import Groq

from core.logger.logger import logger
from core.brain.config import GROQ_API_KEY, GROQ_FAST_MODEL

class LifetimeMemoryEngine:
    def __init__(self):
        self.db_path = Path("Data/jarvis_memory/lifetime_graph.json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.aliases_path = Path("Data/jarvis_memory/aliases.json")
        self.aliases_path.parent.mkdir(parents=True, exist_ok=True)
        self.groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.graph = nx.DiGraph()
        self._lock = threading.Lock()
        self._load_graph()
        self._load_aliases()

    def _load_graph(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.graph = nx.node_link_graph(data)
                logger.info("LTM GraphDB (NetworkX) Initialized.")
            except Exception as e:
                logger.error(f"Failed to load LTM Graph: {e}")
                self.graph = nx.DiGraph()
        else:
            self.graph = nx.DiGraph()

    def _save_graph(self):
        with self._lock:
            try:
                data = nx.node_link_data(self.graph)
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save LTM Graph: {e}")

    def _load_aliases(self):
        self.alias_to_canonical = {}
        if self.aliases_path.exists():
            try:
                with open(self.aliases_path, "r", encoding="utf-8") as f:
                    alias_map = json.load(f)
                for canonical, aliases in alias_map.items():
                    for alias in aliases:
                        self.alias_to_canonical[alias.lower()] = canonical
            except Exception as e:
                logger.error(f"Failed to load aliases: {e}")
                self.alias_to_canonical = {}
        else:
            default_aliases = {
                "bmw": ["car", "vehicle", "beemer"],
                "kaif": ["boss", "sir", "master"],
                "jarvis": ["ai", "assistant"]
            }
            try:
                with open(self.aliases_path, "w", encoding="utf-8") as f:
                    json.dump(default_aliases, f, indent=2)
                for canonical, aliases in default_aliases.items():
                    for alias in aliases:
                        self.alias_to_canonical[alias.lower()] = canonical
            except Exception:
                pass

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
            edge_data = self.graph.get_edge_data(src, tgt, default=None)
            if edge_data is not None and edge_data.get('relation') == rel:
                self.graph.edges[src, tgt]['weight'] = edge_data.get('weight', 1) + 1
                self.graph.edges[src, tgt]['last_seen'] = date_str
            else:
                self.graph.add_edge(src, tgt, relation=rel, date=date_str, weight=1, last_seen=date_str)
        self._save_graph()

    def _clean_json(self, raw_text):
        m = re.search(r'(\[.*\])', raw_text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return raw_text.strip()

    def _extract_triplets(self, text):
        if not self.groq_client or not text.strip():
            return []
        prompt = f'Extract knowledge graph triplets from the text. Return ONLY a JSON array of objects with keys: "source", "relation", "target". Keep entities short (1-2 words). Make relations UPPERCASE. Text: {text[:3000]}'
        try:
            res = self.groq_client.chat.completions.create(
                model=GROQ_FAST_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw = res.choices[0].message.content.strip()
            return json.loads(self._clean_json(raw))
        except Exception:
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

    def _expand_entities(self, entities):
        expanded = []
        for ent in entities:
            ent_lower = ent.lower()
            if ent_lower in self.alias_to_canonical:
                expanded.append(self.alias_to_canonical[ent_lower])
            else:
                expanded.append(ent)
        return expanded

    def search_lifetime_memory(self, query, top_k=3):
        if not query.strip():
            return "Observation: Query empty."
        entities = self._extract_entities_from_query(query)
        if not entities:
            return "Observation: No clear entities found in query."
        entities = self._expand_entities(entities)
        results = []
        today = datetime.now().date()
        with self._lock:
            nodes = {str(n).lower(): n for n in self.graph.nodes()}
            for ent in entities:
                ent_lower = str(ent).lower()
                matched_node = None
                for n_low, n_real in nodes.items():
                    if ent_lower in n_low or n_low in ent_lower:
                        matched_node = n_real
                        break
                if not matched_node:
                    continue
                for successor in self.graph.successors(matched_node):
                    edge = self.graph.edges[matched_node, successor]
                    rel = edge.get('relation', 'RELATES_TO')
                    weight = edge.get('weight', 1)
                    last_seen = edge.get('last_seen', edge.get('date', ''))
                    days_diff = 0
                    if last_seen:
                        try:
                            last_date = datetime.strptime(last_seen, "%Y-%m-%d").date()
                            days_diff = (today - last_date).days
                        except:
                            pass
                    adjusted_weight = weight * (0.5 if days_diff > 180 else 1.0)
                    results.append({
                        "text": f"[{matched_node}] --({rel})--> [{successor}]",
                        "weight": adjusted_weight
                    })
                for predecessor in self.graph.predecessors(matched_node):
                    edge = self.graph.edges[predecessor, matched_node]
                    rel = edge.get('relation', 'RELATES_TO')
                    weight = edge.get('weight', 1)
                    last_seen = edge.get('last_seen', edge.get('date', ''))
                    days_diff = 0
                    if last_seen:
                        try:
                            last_date = datetime.strptime(last_seen, "%Y-%m-%d").date()
                            days_diff = (today - last_date).days
                        except:
                            pass
                    adjusted_weight = weight * (0.5 if days_diff > 180 else 1.0)
                    results.append({
                        "text": f"[{predecessor}] --({rel})--> [{matched_node}]",
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
        res_str = "\n".join(unique[:15])
        return f"Observation: Found relations in Graph Memory:\n{res_str}"

    def _extract_entities_from_query(self, query):
        if not self.groq_client or not query.strip():
            return []
        prompt = f'Extract main entities (people, places, objects, concepts) from the query to search a knowledge graph. Return ONLY a JSON array of strings. Example: ["Rahul", "BMW"]. Query: {query}'
        try:
            res = self.groq_client.chat.completions.create(
                model=GROQ_FAST_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            raw = res.choices[0].message.content.strip()
            return json.loads(self._clean_json(raw))
        except Exception:
            return []

ltm_engine = LifetimeMemoryEngine()