import os
import json
import threading
import time
import re
import networkx as nx
import numpy as np
from datetime import datetime
from pathlib import Path
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
from core.logger.logger import logger


SINGULAR_RELATIONS = {
    "LIVES_IN",
    "LOCATED_IN",
    "AGE",
    "HAS_AGE",
    "DOB",
    "DATE_OF_BIRTH",
    "FATHER",
    "MOTHER",
    "SPOUSE",
    "WORKS_AT",
    "WORKS_AS",
    "PROFESSION",
    "COLLEGE",
    "STUDIES_AT",
    "SCHOOL",
    "DEGREE",
    "CURRENT_PROJECT",
    "HAS_PHONE",
    "HAS_EMAIL",
    "LAPTOP",
    "USES_LAPTOP",
}

RELATION_STOP_TOKENS = {
    "HAS", "IS", "THE", "FOR", "WITH", "FROM", "IN", "AT", "TO", "OF", "ON", "BY",
    "WORKS", "LIVES", "STUDIES", "USES", "GOES", "PLAYS", "MAKES", "DOES", "HAVE"
}

OPPOSITE_RELATION_PAIRS = [
    ({"FATHER", "DAD"}, {"MOTHER", "MOM"}),
    ({"BROTHER"}, {"SISTER"}),
    ({"SON"}, {"DAUGHTER"}),
    ({"UNCLE"}, {"AUNT"}),
    ({"HUSBAND"}, {"WIFE"}),
    ({"LIKES", "LOVES", "PREFERS"}, {"DISLIKES", "HATES", "AVOIDS"}),
    ({"WORKS_AT"}, {"WORKS_AS"}),
]

PRESERVE_UPPER_ACRONYMS = {
    "AI", "ML", "DL", "LLM", "RAG", "API", "UI", "UX", "OS", "PC", "RAM",
    "SSD", "HDD", "CPU", "GPU", "BCA", "BSC", "MSC", "MBA", "BTECH", "MTECH",
    "HP", "DELL", "ASUS", "ACER", "USB", "SSH", "ADB", "CLI", "GUI", "SQL",
    "HTML", "CSS", "JS", "TS", "PHP", "CPP", "QT", "SEO", "URL", "PDF", "JSON"
}

SELF_ENTITY_ALIASES = {"user", "mai", "main", "mein", "me", "myself", "i", "self"}


class LifetimeMemoryEngine:
    def __init__(self):
        self.db_path = Path("Data/jarvis_memory/lifetime_graph.json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph = nx.MultiDiGraph()
        self._lock = threading.RLock()
        self._embed_lock = threading.RLock()

        logger.info("Loading Semantic Embedding Model (BAAI/bge-small-en-v1.5) for LTM...")
        self.embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
        self.node_embeddings = {}
        self.relation_embeddings = {}

        self._load_graph()
        self._start_auto_cleanup()

    def _normalize_entity(self, raw_entity: str) -> str:
        s = str(raw_entity or "").strip()
        if not s:
            return ""
        low = s.lower()
        if low in SELF_ENTITY_ALIASES:
            return "User"
        if "@" in s and " " not in s:
            return low
        if "://" in s or s.startswith("/") or "\\" in s:
            return s
        if " " not in s and ("_" in s or any(ch.isdigit() for ch in s) or (not s.islower() and not s.isupper())):
            return s

        words = s.split()
        norm_words = []
        for w in words:
            w_clean = re.sub(r"[^A-Za-z0-9]", "", w)
            if w_clean.upper() in PRESERVE_UPPER_ACRONYMS:
                norm_words.append(w.upper())
            elif any(ch.isdigit() for ch in w) or (not w.islower() and not w.isupper()):
                norm_words.append(w)
            else:
                norm_words.append(w.capitalize())
        res = " ".join(norm_words)

        with self._lock:
            for existing_node in self.graph.nodes():
                if existing_node.lower() == res.lower():
                    return existing_node
        return res

    @staticmethod
    def _are_relations_opposite(rel_a: str, rel_b: str) -> bool:
        a_clean = rel_a.upper().strip()
        b_clean = rel_b.upper().strip()
        a_tokens = set(a_clean.split("_")) | {a_clean}
        b_tokens = set(b_clean.split("_")) | {b_clean}
        for group_1, group_2 in OPPOSITE_RELATION_PAIRS:
            if (a_tokens & group_1 and b_tokens & group_2) or (a_tokens & group_2 and b_tokens & group_1):
                return True
        return False

    def _compute_all_embeddings(self):
        nodes = list(self.graph.nodes())
        if nodes:
            with self._embed_lock:
                embeddings = self.embedder.encode(
                    nodes, normalize_embeddings=True, show_progress_bar=False
                )
            for node, emb in zip(nodes, embeddings):
                self.node_embeddings[node] = emb

        unique_relations = set()
        for u, v, data in self.graph.edges(data=True):
            if "relation" in data and data["relation"]:
                unique_relations.add(str(data["relation"]).upper())

        if unique_relations:
            rel_list = list(unique_relations)
            with self._embed_lock:
                rel_embeddings = self.embedder.encode(
                    [r.replace("_", " ") for r in rel_list],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            for rel, emb in zip(rel_list, rel_embeddings):
                self.relation_embeddings[rel] = emb

    def _get_embedding(self, text: str):
        with self._embed_lock:
            return self.embedder.encode(
                [str(text)], normalize_embeddings=True, show_progress_bar=False
            )[0]

    def embed(self, texts, is_query=False):
        if texts is None:
            return None
        single = isinstance(texts, str)
        if single:
            texts = [texts]
        if not texts:
            return [] if not single else None

        prefix = "Represent this sentence for searching relevant passages: "
        processed = []
        for t in texts:
            if t is None or not str(t).strip():
                processed.append(" ")
            elif is_query:
                processed.append(prefix + str(t))
            else:
                processed.append(str(t))

        try:
            with self._embed_lock:
                embeddings = self.embedder.encode(
                    processed,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=32,
                )
            if single:
                return embeddings[0].tolist()
            return [e.tolist() for e in embeddings]
        except Exception as e:
            logger.error(f"LTM embed failed: {e}")
            return None

    @staticmethod
    def _is_token_match(query_str: str, target_str: str) -> bool:
        q_clean = query_str.strip().lower()
        t_clean = target_str.strip().lower()
        if not q_clean or not t_clean:
            return False
        if q_clean == t_clean:
            return True
        q_tokens = {tok for tok in re.findall(r"\w+", q_clean) if len(tok) >= 3}
        t_tokens = {tok for tok in re.findall(r"\w+", t_clean) if len(tok) >= 3}
        if not q_tokens or not t_tokens:
            return False
        if q_tokens == t_tokens:
            return True
        overlap = len(q_tokens & t_tokens)
        union = len(q_tokens | t_tokens)
        if overlap > 0 and (overlap / union) >= 0.75:
            return True
        return False

    def _relation_matches(self, edge_rel: str, requested_rel: str, threshold: float = 0.80) -> bool:
        if not requested_rel:
            return True
        e_rel = (edge_rel or "").strip().upper()
        r_rel = (requested_rel or "").strip().upper()
        if not e_rel:
            return False
        if e_rel == r_rel:
            return True
        if self._are_relations_opposite(e_rel, r_rel):
            return False

        e_tokens = {t for t in e_rel.split("_") if len(t) >= 3 and t not in RELATION_STOP_TOKENS}
        r_tokens = {t for t in re.split(r"[_\s]+", r_rel) if len(t) >= 3 and t not in RELATION_STOP_TOKENS}
        if e_tokens and r_tokens and e_tokens == r_tokens:
            return True

        try:
            e_emb = self.relation_embeddings.get(e_rel)
            if e_emb is None:
                e_emb = self._get_embedding(e_rel.replace("_", " "))
                self.relation_embeddings[e_rel] = e_emb
            r_emb = self.relation_embeddings.get(r_rel)
            if r_emb is None:
                r_emb = self._get_embedding(r_rel.replace("_", " "))
                self.relation_embeddings[r_rel] = r_emb
            sim = 1.0 - float(cosine(e_emb, r_emb))
            return sim >= threshold
        except Exception:
            return False

    def get_all_node_names(self, limit=100):
        with self._lock:
            nodes = sorted(self.graph.degree, key=lambda x: x[1], reverse=True)
            return [n[0] for n in nodes[:limit]]

    def get_all_relations(self, limit=50):
        with self._lock:
            relations = set()
            for u, v, data in self.graph.edges(data=True):
                if not data.get("archived", False) and "relation" in data:
                    relations.add(data["relation"])
            return list(relations)[:limit]

    def _deduplicate_relation(self, rel, threshold=0.88):
        if not rel:
            return rel
        rel = re.sub(r"\s+", "_", rel.upper().strip())

        with self._lock:
            if rel in self.relation_embeddings or rel in SINGULAR_RELATIONS:
                if rel not in self.relation_embeddings:
                    self.relation_embeddings[rel] = self._get_embedding(rel.replace("_", " "))
                return rel

            rel_emb = self._get_embedding(rel.replace("_", " "))
            best_match = None
            best_sim = -1.0

            for ex_rel, ex_emb in self.relation_embeddings.items():
                if self._are_relations_opposite(rel, ex_rel):
                    continue
                sim = 1.0 - float(cosine(rel_emb, ex_emb))
                if sim > best_sim:
                    best_sim = sim
                    best_match = ex_rel

            if best_match and best_sim >= threshold:
                logger.info(f"LTM Semantic Deduplication: Merged '{rel}' -> '{best_match}' (Sim: {best_sim:.2f})")
                return best_match

            self.relation_embeddings[rel] = rel_emb
            return rel

    def _load_graph(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loaded_g = nx.node_link_graph(data)
                if isinstance(loaded_g, nx.MultiDiGraph):
                    self.graph = loaded_g
                else:
                    self.graph = nx.MultiDiGraph()
                    for n, n_data in loaded_g.nodes(data=True):
                        self.graph.add_node(n, **(n_data or {}))
                    for u, v, e_data in loaded_g.edges(data=True):
                        rel_key = str((e_data or {}).get("relation", "RELATES_TO")).upper()
                        self.graph.add_edge(u, v, key=rel_key, **(e_data or {}))
            except Exception as e:
                logger.error(f"Error loading graph: {e}")
                self.graph = nx.MultiDiGraph()
        else:
            self.graph = nx.MultiDiGraph()
        self._compute_all_embeddings()

    def _save_graph(self):
        with self._lock:
            try:
                tmp_path = self.db_path.with_suffix(".json.tmp")
                data = nx.node_link_data(self.graph)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.db_path)
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
            archived_any = False
            for u, v, k, data in self.graph.edges(keys=True, data=True):
                if data.get("archived", False):
                    continue
                last_seen = data.get("last_seen")
                if last_seen:
                    try:
                        last_date = datetime.strptime(last_seen, "%Y-%m-%d")
                        if (now - last_date).days > 180:
                            data["archived"] = True
                            archived_any = True
                    except Exception as e:
                        logger.error(f"Date parse error in archive: {e}")
            if archived_any:
                self._save_graph()

    def _upsert_single_edge(self, src: str, rel: str, tgt: str, date_str: str, metadata=None, inverse_of: str = None):
        if self.graph.has_edge(src, tgt, key="HAS_RELATION") and rel != "HAS_RELATION":
            self.graph.remove_edge(src, tgt, key="HAS_RELATION")

        if self.graph.has_edge(src, tgt, key=rel):
            edge_data = self.graph.edges[src, tgt, rel]
            edge_data["weight"] = edge_data.get("weight", 1) + 1
            edge_data["count"] = edge_data.get("count", 1) + 1
            edge_data["last_seen"] = date_str
            if metadata:
                edge_data["metadata"] = metadata
            if inverse_of:
                edge_data["inverse_of"] = inverse_of
            if "first_seen" not in edge_data:
                edge_data["first_seen"] = date_str
            edge_data.pop("archived", None)
        else:
            edge_attrs = {
                "relation": rel,
                "date": date_str,
                "weight": 1,
                "count": 1,
                "first_seen": date_str,
                "last_seen": date_str,
                "metadata": metadata,
            }
            if inverse_of:
                edge_attrs["inverse_of"] = inverse_of
            self.graph.add_edge(src, tgt, key=rel, **edge_attrs)

    def record_triplet(
        self,
        source,
        relation,
        target,
        date_str=None,
        metadata=None,
        inverse=None,
        is_singular: bool = False,
    ):
        if not source or not relation or not target:
            return

        src = self._normalize_entity(source)
        tgt = self._normalize_entity(target)
        rel = self._deduplicate_relation(str(relation).strip())

        if not src or not rel or not tgt or src.lower() == tgt.lower():
            return

        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        singular_flag = bool(is_singular or rel in SINGULAR_RELATIONS)

        with self._lock:
            if src not in self.node_embeddings:
                self.node_embeddings[src] = self._get_embedding(src)
            if tgt not in self.node_embeddings:
                self.node_embeddings[tgt] = self._get_embedding(tgt)

            if singular_flag and self.graph.has_node(src):
                for _, old_tgt, old_key, old_data in list(self.graph.out_edges(src, keys=True, data=True)):
                    if old_tgt != tgt and old_data.get("relation") == rel and not old_data.get("archived", False):
                        old_data["archived"] = True
                        logger.info(
                            f"LTM Conflict Resolved: Archived outdated [{src}] --({rel})--> [{old_tgt}] in favor of [{tgt}]"
                        )
                        if self.graph.has_node(old_tgt):
                            for _, inv_v, inv_k, inv_data in list(self.graph.out_edges(old_tgt, keys=True, data=True)):
                                if inv_v == src and not inv_data.get("archived", False):
                                    if inv_data.get("inverse_of") == rel or len(self.graph[old_tgt][src]) == 1:
                                        inv_data["archived"] = True

            self._upsert_single_edge(src, rel, tgt, date_str, metadata=metadata)

            if inverse and isinstance(inverse, dict):
                inv_tgt_raw = inverse.get("target") or src
                inv_tgt = self._normalize_entity(inv_tgt_raw)
                inv_rel = self._deduplicate_relation(str(inverse.get("relation", "")).strip())

                if inv_rel and inv_tgt and tgt.lower() != inv_tgt.lower():
                    if inv_tgt not in self.node_embeddings:
                        self.node_embeddings[inv_tgt] = self._get_embedding(inv_tgt)
                    self._upsert_single_edge(
                        tgt,
                        inv_rel,
                        inv_tgt,
                        date_str,
                        metadata=metadata,
                        inverse_of=rel,
                    )

        self._save_graph()

    def _find_matching_nodes(self, entity_str: str, threshold: float = 0.85):
        ent_clean = self._normalize_entity(entity_str)
        if not ent_clean:
            return []

        if ent_clean in self.graph.nodes():
            return [ent_clean]

        ent_emb = self._get_embedding(ent_clean)
        matched = []

        for node, node_emb in self.node_embeddings.items():
            if node.lower() == ent_clean.lower():
                return [node]
            if self._is_token_match(ent_clean, node):
                matched.append((node, 0.99))
                continue
            sim = 1.0 - float(cosine(ent_emb, node_emb))
            if sim >= threshold:
                matched.append((node, sim))

        matched.sort(key=lambda x: x[1], reverse=True)
        return [m[0] for m in matched[:3]]

    def search_lifetime_memory(self, queries, top_k=5, threshold=0.85):
        if not queries:
            return "Observation: Query empty."

        query_items = []
        if isinstance(queries, str):
            query_items.append({"entity": queries.strip(), "relation": ""})
        elif isinstance(queries, list):
            for q in queries:
                if isinstance(q, dict):
                    ent = str(q.get("entity") or "").strip()
                    rel = str(q.get("relation") or "").strip()
                    if ent or rel:
                        query_items.append({"entity": ent, "relation": rel})
                elif str(q).strip():
                    query_items.append({"entity": str(q).strip(), "relation": ""})

        if not query_items:
            return "Observation: No clear entities provided."

        has_non_user_entity = any(
            self._normalize_entity(item["entity"]) != "User" and item["entity"] != ""
            for item in query_items
        )

        results = []
        today = datetime.now().date()

        with self._lock:
            for item in query_items:
                ent = item["entity"]
                req_rel = item["relation"]
                norm_ent = self._normalize_entity(ent) if ent else ""

                if norm_ent == "User" and not req_rel and has_non_user_entity:
                    continue

                matched_nodes = self._find_matching_nodes(ent, threshold=threshold) if ent else []
                candidate_edges = []

                if matched_nodes:
                    for m_node in matched_nodes:
                        for u, v, data in self.graph.out_edges(m_node, data=True):
                            candidate_edges.append((u, v, data))
                        for u, v, data in self.graph.in_edges(m_node, data=True):
                            candidate_edges.append((u, v, data))
                elif not ent and req_rel:
                    for u, v, data in self.graph.edges(data=True):
                        candidate_edges.append((u, v, data))
                elif ent and not req_rel:
                    for u, v, data in self.graph.edges(data=True):
                        if self._relation_matches(data.get("relation", ""), ent, threshold=0.82):
                            candidate_edges.append((u, v, data))

                for u, v, data in candidate_edges:
                    if data.get("archived", False):
                        continue

                    edge_rel = data.get("relation", "RELATES_TO")

                    if req_rel and not self._relation_matches(edge_rel, req_rel, threshold=0.80):
                        continue

                    weight = float(data.get("weight", 1))
                    count = int(data.get("count", 1))
                    last_seen = data.get("last_seen", data.get("date", ""))
                    metadata = data.get("metadata") or {}
                    source_msg = metadata.get("source_message", "")

                    days_diff = 0
                    if last_seen:
                        try:
                            last_date = datetime.strptime(last_seen, "%Y-%m-%d").date()
                            days_diff = (today - last_date).days
                        except Exception:
                            pass

                    time_penalty = 0.5 if days_diff > 180 else 1.0
                    count_boost = min(1.0 + (count - 1) * 0.15, 2.0)
                    rel_boost = 2.0 if (req_rel and self._relation_matches(edge_rel, req_rel, threshold=0.84)) else 1.0

                    adjusted_weight = weight * time_penalty * count_boost * rel_boost

                    res_text = f"[{u}] --({edge_rel})--> [{v}]"
                    if source_msg:
                        res_text += f" (Context: {source_msg})"

                    results.append({
                        "text": res_text,
                        "weight": adjusted_weight,
                    })

        if not results:
            return "Observation: Found nothing in Graph Memory for these entities/relations."

        results.sort(key=lambda x: x["weight"], reverse=True)
        unique = []
        seen = set()
        for r in results:
            if r["text"] not in seen:
                seen.add(r["text"])
                unique.append(r["text"])

        max_items = 8 if len(query_items) == 1 else 12
        res_str = "\n".join(unique[:max_items])
        return f"Observation: Found relations in Graph Memory:\n{res_str}"


ltm_engine = LifetimeMemoryEngine()