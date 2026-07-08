"""core.knowledge — pluggable knowledge source for LLM agents (RAG toggle).

Every LLM agent (attacker AND defender) receives a KnowledgeSource. Default is
PromptOnly (knowledge in the system prompt). RAGSource is REAL retrieval: offline-indexed
grounded corpus (corpus/<role>/<variant>/*.txt), dense top-k cosine retrieval over ollama
embeddings, injected into the USER message. The KnowledgeSource/LLMClient split is
unchanged (Lewis et al. canonical RAG) — only RAGSource is now real.

Offline + reproducible: corpus is embedded ONCE (disk-cached, content-hashed); embeddings
are deterministic (ollama same-text -> identical vector). No runtime external calls beyond
the local ollama server. augment() NEVER crashes the interface (degrades to no-op on error).
"""
from __future__ import annotations
import abc, glob, hashlib, json, logging, os, re, urllib.request
from pathlib import Path
from typing import List, Optional

import numpy as np

log = logging.getLogger("knowledge")

# module-level query-embedding cache (query strings repeat across units in one run)
_EMB_CACHE: dict = {}

# ── retrieval audit sink (per-turn chunk-id + score logging; opened by the runner) ──
# Records WHAT each augment() retrieved so RAG levels are auditable (Phase 6). Context
# (unit/cell/turn/role) is pulled from llm_client._LLM_CTX set by the runner.
_RETR_SINK: dict = {"fh": None}


def open_retrieval_log(path) -> None:
    close_retrieval_log()
    _RETR_SINK["fh"] = open(path, "a", encoding="utf-8")


def close_retrieval_log() -> None:
    fh = _RETR_SINK.get("fh")
    if fh is not None:
        try: fh.close()
        finally: _RETR_SINK["fh"] = None


def _emit_retrieval(variant, query, hits) -> None:
    fh = _RETR_SINK.get("fh")
    if fh is None:
        return
    try:
        from core.llm_client import _LLM_CTX
        ctx = dict(_LLM_CTX.get())
    except Exception:
        ctx = {}
    try:
        rec = {**ctx, "rag_corpus_variant": variant, "query": query, "hits": hits}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
    except Exception:
        pass   # auditing must never break a run


def _embed(text: str, url: str, model: str) -> np.ndarray:
    key = (model, text)
    if key in _EMB_CACHE:
        return _EMB_CACHE[key]
    req = urllib.request.Request(
        url.rstrip("/") + "/api/embeddings",
        data=json.dumps({"model": model, "prompt": text}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        v = np.asarray(json.load(r)["embedding"], dtype=np.float32)
    n = float(np.linalg.norm(v)) or 1.0
    v = v / n
    _EMB_CACHE[key] = v
    return v


class KnowledgeSource(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def augment(self, prompt: str, query: str) -> str:
        """Return `prompt` possibly augmented with retrieved context for `query`."""
        ...


class PromptOnly(KnowledgeSource):
    """No retrieval — knowledge lives entirely in the hard-coded prompt (RAG off)."""
    name = "prompt_only"

    def augment(self, prompt: str, query: str) -> str:
        return prompt


# kill-chain stage of a chunk, by the earliest stage keyword in its body (corpus is stage-paragraphed)
_STAGE_KEYS = [("recon", ("reconnaissance", "recon")),
               ("intrusion", ("intrusion", "initial access", "execution")),
               ("theft", ("exfiltration", "theft"))]


def _chunk_stage(text: str) -> Optional[str]:
    low = text.lower()
    best = (10 ** 9, None)
    for stage, kws in _STAGE_KEYS:
        pos = min((low.find(k) for k in kws if low.find(k) >= 0), default=-1)
        if pos >= 0 and pos < best[0]:
            best = (pos, stage)
    return best[1]


def _query_stage(query: str) -> Optional[str]:
    """Map the 'stage=<word>' token in a query to a canonical chunk stage (Persistence->intrusion)."""
    m = re.search(r"stage=(\w+)", query, re.I)
    if not m:
        return None
    s = m.group(1).lower()
    if s.startswith("recon"):
        return "recon"
    if s.startswith("intrus") or s.startswith("persist") or s in ("execution",):
        return "intrusion"
    if s.startswith("theft") or s.startswith("exfil"):
        return "theft"
    return None


def _load_embed(corpus_dir: str, embed_url: str, model: str, cache_dir: Optional[str]):
    """Load *.txt -> paragraph chunks (inject text + body-only embed text) and embed (disk-cached).
    [provenance] header kept for INJECTION but EXCLUDED from the embedding. Each chunk gets a
    kill-chain stage tag (for stage-gated retrieval). Returns (chunks, sources, mat, stages)."""
    chunks: List[str] = []; sources: List[str] = []; embed_texts: List[str] = []; stages: List = []
    files = sorted(glob.glob(os.path.join(corpus_dir, "*.txt")))
    for f in files:
        raw = Path(f).read_text(encoding="utf-8").strip()
        lines = raw.split("\n", 1)
        header = lines[0] if lines and lines[0].startswith("[") else ""
        body = lines[1].strip() if (header and len(lines) > 1) else raw
        for para in re.split(r"\n\s*\n", body):
            para = para.strip()
            if len(para) >= 40:
                chunks.append((header + "\n" + para).strip() if header else para)
                embed_texts.append(para)
                sources.append(f"{Path(f).stem}#{len(sources)}")
                stages.append(_chunk_stage(para))
    if not chunks:
        raise FileNotFoundError(f"no corpus chunks in {corpus_dir}")
    h = hashlib.sha256(("||".join(embed_texts) + model + "v2body").encode()).hexdigest()[:16]
    cache = Path(cache_dir) / f"{h}.npz" if cache_dir else None
    if cache and cache.exists():
        mat = np.load(cache)["mat"]
    else:
        mat = np.stack([_embed(t, embed_url, model) for t in embed_texts])
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True); np.savez(cache, mat=mat)
    return chunks, sources, mat, stages


class RAGSource(KnowledgeSource):
    """Real retrieval: dense cosine top-k over an offline-embedded grounded corpus, with a
    FIDELITY knob. fidelity='strong' = precise top-k from the relevant corpus; fidelity='weak'
    = `distractor_frac` of the top-k slots filled from a fixed distractor pool (mismatched
    retrieval). Query is built from the agent STATE by the caller."""
    name = "rag"

    def __init__(self, corpus_dir: str, embed_url: str, model: str, top_k: int = 3,
                 cache_dir: Optional[str] = None, inject_chars: int = 600,
                 fidelity: str = "strong", distractor_dir: Optional[str] = None,
                 distractor_frac: float = 0.5):
        self.top_k = top_k; self.embed_url = embed_url; self.model = model
        self.inject_chars = inject_chars; self.fidelity = fidelity
        self._distractor_frac_legacy = distractor_frac
        n_main, n_dist, joint = self._split()
        self.last_hits: List[dict] = []
        self.mat = self.dmat = None
        self.ok = False
        self.stages: List = []; self.dstages: List = []
        try:
            self.chunks, self.sources, self.mat, self.stages = _load_embed(corpus_dir, embed_url, model, cache_dir)
            if (n_dist > 0 or joint) and distractor_dir:          # poison/mid/weak need the negative pool
                self.dchunks, self.dsources, self.dmat, self.dstages = _load_embed(distractor_dir, embed_url, model, cache_dir)
            self.ok = True
            log.info("rag_source_ready", extra={"dir": corpus_dir, "chunks": len(self.chunks),
                                                 "fidelity": fidelity})
        except Exception as e:
            log.warning("rag init failed (%s) -> no-op augmentation", str(e)[:120]); self.ok = False

    def _split(self):
        """(n_main, n_dist, joint) from fidelity. PRESENCE/RELEVANCE 5-point + legacy + coverage."""
        f = self.fidelity; k = self.top_k
        if f in ("fid_strong", "strong") or str(f).startswith("cov_"):
            return (k, 0, False)                 # full relevant (coverage = strong on its corpus)
        if f == "fid_mid":
            return (k // 2, k - k // 2, False)   # half answer + half hard_neg (top_k=4 -> 2+2)
        if f == "fid_poison":
            return (0, k, False)                 # length-matched control: hard_neg only, answer excluded
        if f == "fid_weak":
            return (0, 0, True)                  # joint rank main∪hard_neg: answer present but out-ranked
        if str(f).startswith("weak"):            # legacy weak/weak_easy/weak_hard
            nd = round(k * self._distractor_frac_legacy); return (k - nd, nd, False)
        return (k, 0, False)

    def _gate(self, query):
        """stage-gated relevant pool indices (same-stage + stage-agnostic None); full pool fallback."""
        qstage = _query_stage(query)
        pool = [i for i in range(len(self.chunks))
                if (qstage is None or self.stages[i] == qstage or self.stages[i] is None)]
        return pool or list(range(len(self.chunks)))

    def augment(self, prompt: str, query: str) -> str:
        if not self.ok or not query:
            return prompt
        try:
            q = _embed(query, self.embed_url, self.model)
            n_main, n_dist, joint = self._split()
            sims = self.mat @ q
            pool = self._gate(query)
            hits: List[dict] = []; refs: List[str] = []
            if joint and self.dmat is not None:
                # fid_weak: rank stage-gated answer pool ∪ ALL hard_neg jointly; answer exists but
                # competitive hard negatives crowd the top-k (retrieval-failure, not answer-absent).
                dsims = self.dmat @ q
                merged = ([(float(sims[i]), "relevant", i) for i in pool] +
                          [(float(dsims[j]), "distractor", j) for j in range(len(self.dchunks))])
                for sc, kind, k_ in sorted(merged, key=lambda t: -t[0])[:self.top_k]:
                    if kind == "relevant":
                        hits.append({"chunk_id": int(k_), "source": self.sources[k_], "kind": "relevant",
                                     "stage": self.stages[k_], "score": round(sc, 4)})
                        refs.append(self.chunks[k_][: self.inject_chars])
                    else:
                        hits.append({"chunk_id": int(k_), "source": self.dsources[k_], "kind": "distractor",
                                     "score": round(sc, 4)})
                        refs.append(self.dchunks[k_][: self.inject_chars])
            else:
                idx = sorted(pool, key=lambda i: -sims[i])[:n_main]
                hits += [{"chunk_id": int(i), "source": self.sources[i], "kind": "relevant",
                          "stage": self.stages[i], "score": round(float(sims[i]), 4)} for i in idx]
                refs += [self.chunks[i][: self.inject_chars] for i in idx]
                if n_dist > 0 and self.dmat is not None:
                    didx = np.argsort(-(self.dmat @ q))[:n_dist]
                    hits += [{"chunk_id": int(i), "source": self.dsources[i], "kind": "distractor",
                              "score": round(float((self.dmat @ q)[i]), 4)} for i in didx]
                    refs += [self.dchunks[i][: self.inject_chars] for i in didx]
            self.last_hits = hits
            _emit_retrieval(self.fidelity, query, hits)
            ctx = "\n".join(f"[ref] {r}" for r in refs)
            return f"{prompt}\n\nRetrieved references (top-{self.top_k}, fidelity={self.fidelity}):\n{ctx}"
        except Exception as e:
            log.warning("rag augment failed (%s) -> no-op", str(e)[:100]); return prompt


def _load_text_chunks(corpus_dir: str) -> List[str]:
    """Paragraph chunks (with header) WITHOUT embedding — for length-control filler."""
    out: List[str] = []
    for f in sorted(glob.glob(os.path.join(corpus_dir, "*.txt"))):
        raw = Path(f).read_text(encoding="utf-8").strip()
        lines = raw.split("\n", 1)
        header = lines[0] if lines and lines[0].startswith("[") else ""
        body = lines[1].strip() if (header and len(lines) > 1) else raw
        for para in re.split(r"\n\s*\n", body):
            para = para.strip()
            if len(para) >= 40:
                out.append((header + "\n" + para).strip() if header else para)
    return out


class FillerSource(KnowledgeSource):
    """LENGTH control (reflection 3): inject a FIXED block of irrelevant text matched in volume to
    `strong` (top_k chunks × inject_chars) but NOT retrieved (query-independent). Isolates whether a
    RAG effect is CONTENT or just prompt LENGTH/token-volume."""
    name = "filler"

    def __init__(self, distractor_dir: str, top_k: int = 3, inject_chars: int = 600):
        self.top_k = top_k; self.inject_chars = inject_chars
        self.chunks = _load_text_chunks(distractor_dir)
        self.ok = bool(self.chunks)
        self.last_hits = [{"source": "filler", "kind": "filler"}]

    def augment(self, prompt: str, query: str) -> str:
        if not self.ok:
            return prompt
        # length-match `strong` (~top_k chunks of real content). Distractor paragraphs are short,
        # so PAD each ref by repeating the pool to ~per_ref chars (≈ a relevant chunk's length).
        per_ref = 450
        pool = "  ".join(self.chunks)
        refs = []
        for i in range(self.top_k):
            seg = (pool * ((per_ref // max(1, len(pool))) + 1))[i * per_ref: i * per_ref + per_ref]
            if len(seg) < per_ref:
                seg = (seg + "  " + pool)[: per_ref]
            refs.append(seg.strip())
        ctx = "\n".join(f"[ref] {r}" for r in refs)
        return f"{prompt}\n\nRetrieved references (top-{self.top_k}, fidelity=filler):\n{ctx}"


class FidFillerSource(KnowledgeSource):
    """fid_filler (Phase 1.5 length⊥relevance control): inject top_k QUERY-INDEPENDENT, domain-neutral
    chunks whose per-ref length is matched (±10%) to fid_strong's injected relevant chunks. Isolates
    length/priming from relevance. Content = neutral distractor pool (cooking/general text)."""
    name = "fid_filler"

    def __init__(self, neutral_dir: str, strong_dir: str, top_k: int = 3, inject_chars: int = 600):
        self.top_k = top_k; self.inject_chars = inject_chars; self.ok = False
        neutral = _load_text_chunks(neutral_dir); strong = _load_text_chunks(strong_dir)
        if not neutral or not strong:
            log.warning("fid_filler: empty neutral/strong corpus -> no-op"); return
        slen = [min(len(c), inject_chars) for c in strong]        # strong's injected per-chunk lengths
        target = round(sum(slen) / len(slen))                     # match filler refs to this (mean)
        pool = "  ".join(neutral); refs = []
        for i in range(top_k):
            seg = (pool * ((target // max(1, len(pool))) + 2))[i * target: i * target + target]
            if len(seg) < target:
                seg = (seg + "  " + pool)[:target]
            refs.append(seg.strip())
        self.refs = refs
        # ★length-control asserts (spec STEP 2): chunk count + mean length matched to strong.
        mean_f = sum(len(r) for r in refs) / len(refs)
        assert abs(len(refs) - min(top_k, len(strong))) <= 1, \
            f"fid_filler/strong chunk-count mismatch ({len(refs)} vs {min(top_k, len(strong))})"
        assert abs(mean_f - target) / target <= 0.10, \
            f"fid_filler/strong length mismatch (filler {round(mean_f)} vs strong {target} chars, >10%)"
        self.ok = True
        self.last_hits = [{"source": "fid_filler", "kind": "filler"} for _ in range(top_k)]
        log.info("fid_filler ready", extra={"top_k": top_k, "ref_chars": target})

    def augment(self, prompt: str, query: str) -> str:
        if not self.ok:
            return prompt
        ctx = "\n".join(f"[ref] {r}" for r in self.refs)        # query-INDEPENDENT (relevance=0 by design)
        return f"{prompt}\n\nRetrieved references (top-{self.top_k}, fidelity=fid_filler):\n{ctx}"


def make_knowledge(fidelity: str, role: Optional[str] = None, corpus_root: Optional[str] = None,
                   embed_url: Optional[str] = None, model: Optional[str] = None,
                   top_k: int = 3, extended: bool = False) -> KnowledgeSource:
    """Redesigned fidelity routing (legacy strong/weak*/tier* REMOVED). Valid values:
      none/fid_none -> PromptOnly; filler -> FillerSource(distractor); fid_filler -> FidFillerSource;
      fid_{poison,weak,mid,strong} -> RAGSource(fidelity/main + fidelity/hard_neg, top_k=4);
      cov_{min,mid,full} -> RAGSource(coverage/<lvl>, top_k=4).
    Unknown fidelity -> ValueError (no silent fall-through). `extended` is vestigial (engine 5/10 is
    selected via deceiver.extended_skills in build_agents, not via corpus here).
    Missing role/corpus/embed -> PromptOnly (warn) so a bad config can't crash the run."""
    if fidelity in ("none", "fid_none"):
        return PromptOnly()
    if fidelity == "filler" and role and corpus_root:        # length control (no embedding needed)
        return FillerSource(os.path.join(corpus_root, role, "distractor"), top_k=top_k)
    if fidelity == "fid_filler" and role and corpus_root:     # length⊥relevance control (neutral, len-matched to new main)
        return FidFillerSource(os.path.join(corpus_root, role, "distractor"),
                               os.path.join(corpus_root, role, "fidelity", "main"), top_k=4)
    if not (role and corpus_root and embed_url and model):
        log.warning("rag requested but role/corpus/embed unset -> PromptOnly"); return PromptOnly()
    # Redesigned corpus: separated PRESENCE/RELEVANCE (5-point fidelity) + coverage axis.
    #   fid_strong=fidelity/main only; fid_mid=main+hard_neg; fid_poison=hard_neg only (answer excluded);
    #   fid_weak=joint rank (answer present, out-ranked); cov_*=coverage/<lvl> (strong on that corpus).
    FID5 = {"fid_strong", "fid_weak", "fid_mid", "fid_poison"}
    COV = {"cov_min", "cov_mid", "cov_full"}
    if fidelity in FID5 or fidelity in COV:
        main_dir = (os.path.join(corpus_root, role, "coverage", fidelity) if fidelity in COV
                    else os.path.join(corpus_root, role, "fidelity", "main"))
        return RAGSource(main_dir, embed_url, model, top_k=4,         # top_k=4 -> exact 50% split (C2 fix)
                         cache_dir=os.path.join(corpus_root, ".cache"), fidelity=fidelity,
                         distractor_dir=os.path.join(corpus_root, role, "fidelity", "hard_neg"))
    # ★ NO silent fall-through: legacy fidelity wiring (strong/weak/weak_easy/weak_hard/tier1/tier2 ->
    # relevant_5/relevant/relevant_L1/_L2 + distractor_hard) was REMOVED. An unknown value must raise,
    # not route to the old small corpus at top_k=3 (which used to fail silently).
    raise ValueError(
        f"unknown fidelity='{fidelity}' (legacy removed; use "
        "none/fid_none, fid_poison, fid_weak, fid_mid, fid_strong, cov_min, cov_mid, cov_full, "
        "filler, fid_filler)")
