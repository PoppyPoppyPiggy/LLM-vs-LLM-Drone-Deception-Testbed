# CODEBOOK — Corpus & Deception System (definition sheet)

> Reference dictionary for the RAG corpus and the deception engine. Every entry is transcribed from
> the actual files/code (path:line given). Use this to describe the corpus, skills, wire surface, and
> RAG levels precisely in the paper. **MTD-free** (no GCS/directive here).

---

## PART A — RAG CORPUS (`corpus/`)

### A.1 Directory tree (what exists, chunk counts, role)

```
corpus/
├── deceiver/                                   ← DEFENDER (honeydrone) knowledge
│   ├── fidelity/
│   │   ├── main/  recon.txt intrusion.txt theft.txt   20 chunks/stage = 60  [RELEVANT answer pool]
│   │   ├── hard_neg/ hn.txt                            22 chunks             [query-similar, NO correct map]
│   │   └── README.md                                   design spec
│   ├── coverage/
│   │   ├── cov_min/  {recon,intrusion,theft}.txt        1 chunk/stage  =  3
│   │   ├── cov_mid/  {recon,intrusion,theft}.txt        5 chunks/stage = 15
│   │   └── cov_full/ {recon,intrusion,theft}.txt       20 chunks/stage = 60  (== fidelity/main)
│   └── distractor/  X1.txt X2.txt X3.txt               3 chunks              [IRRELEVANT filler control]
├── attacker/                                   ← ATTACKER knowledge (symmetry; not a paper knob)
│   ├── relevant/ A_vuln_mavlink, B_dvd_procedures, C_protocol_mavlink
│   ├── distractor/      X1–X3   (irrelevant)
│   └── distractor_hard/ H1–H3   (query-similar negatives)
└── .cache/  *.npz                              ← embedding cache (nomic-embed-text); regenerable
```

### A.2 Chunk format (all corpus `.txt`)

- **Line 1 = header tag** (indexed as chunk 0), machine-readable provenance:
  `[deception playbook | stage=Recon | optimal skills: statustext(0), ghost_port(2) | UAS honeydrone | relevant]`
- **Following blank-line-separated paragraphs = retrieval chunks** (each 241–371 chars, no truncation).
- **Stage tagging** by keyword (`_chunk_stage`): recon / intrusion (+initial-access, execution) /
  theft (exfiltration). Persistence chunks tag `None` (stage-agnostic → eligible in all stages).

### A.3 Chunk-content types (the retrieval-fidelity control set)

| Pool | Path | Content | Teaches correct stage→skill? |
|---|---|---|---|
| **relevant** (answer) | `fidelity/main/*`, `coverage/*` | true deception playbook, e.g. *"Recon → counter with statustext / ghost_port; save flight_sim & credential_leak for later"* | ✅ yes |
| **hard_neg** (distractor) | `fidelity/hard_neg/hn.txt` | same UAS/deception vocabulary, deliberately **wrong or no mapping**, e.g. *"lead with credential_leak during recon"* (mis-advice), *"no fixed mapping applies"* | ❌ no (crowds top-k) |
| **filler** (irrelevant) | `distractor/X*.txt` | domain-neutral text (*Margherita pizza…*), length-matched | ❌ pure volume control |

hard_neg is engineered so its cosine to a deceiver query (top 0.796) **≥** relevant (0.773) — so it can
out-rank the answer into top-k. This is what physically realizes `fid_weak` (answer present but ranked
below cutoff) and `fid_poison` (answer absent).

---

## PART B — RAG LEVELS → CORPUS ROUTING (`core/knowledge.py`)

Retrieval is `top_k = 4` for every mixed level (exact 50% split capability). `_split()` returns
`(n_main, n_dist, joint)` per level (`knowledge.py:183-195`):

| CLI `--deceiver-rag` | source class | n_relevant | n_hard_neg | **dose** (useful in top-k) | meaning |
|---|---|---|---|:--:|---|
| `fid_strong` | RAGSource | 4 | 0 | **4** | full correct answer |
| `fid_mid` | RAGSource | 2 | 2 | **2** | half answer + half distractor |
| `fid_weak` | RAGSource (joint) | rank-mixed | rank-mixed | **≈1** | answer present but out-ranked by hard_neg |
| `fid_poison` | RAGSource | 0 | 4 | **0** | answer excluded, hard_neg only (length-matched) |
| `fid_none` | **PromptOnly** | — | — | **0** | no retrieval (knowledge only in system prompt) |
| `fid_filler` | **FidFillerSource** | 0 | 0 | **0** | top-k query-independent neutral chunks, length-matched to `strong` |
| `cov_min` | RAGSource on `coverage/cov_min` | 4 (of 1/stage) | 0 | **4** | fidelity=strong, sparse corpus (1 chunk/stage) |
| `cov_mid` | RAGSource on `coverage/cov_mid` | 4 (of 5/stage) | 0 | **4** | 5 chunks/stage |
| `cov_full` | RAGSource on `coverage/cov_full` | 4 (of 20/stage) | 0 | **4** | 20 chunks/stage (== fidelity/main) |

**Two orthogonal axes:**
- **Fidelity** (`fid_*`) = *quality* of what lands in top-k (answer vs distractor vs filler), corpus size fixed.
- **Coverage** (`cov_*`) = *breadth of the corpus* (1/5/20 chunks per kill-chain stage), fidelity fixed at strong.

**Controls that make the fidelity argument airtight:**
- `fid_filler` isolates **length ⊥ relevance** (same injected volume as strong, zero useful) →
  proves the win gain is content, not tokens. (data: filler 0.69 ≤ none 0.73.)
- `fid_poison` is the **dose-0, length-matched** floor (hard_neg only).
- Query for retrieval is **stage-gated** (attacker & defender both put `stage=` in the query) so a
  recon query pulls recon chunks — fixes the earlier asymmetric bug (`knowledge.py:199-203`).

Augmented prompt tail (`knowledge.py:242`): `"…\n\nRetrieved references (top-4, fidelity=<level>):\n<ctx>"`.

---

## PART C — DEFENDER DECEPTION SKILLS (`core/deception/skills.py`)

### C.1 Skill sets (two engine profiles; **all reported runs use the 5-skill set**, `--deceiver-skillset 5`)

| idx | 5-skill (MAIN) | 10-skill adds (idx 5–9, RAG-ladder engine only) | wire effect source |
|:--:|---|---|---|
| 0 | **statustext** | — | crafted STATUSTEXT ("EKF3 healthy", "GPS 3D fix") |
| 1 | **flight_sim** | — | fake flight telemetry |
| 2 | **ghost_port** | — | decoy service banners (5760/SSH) |
| 3 | **reboot_sim** | — | simulated reboot |
| 4 | **credential_leak** | — | plant honeytoken creds |
| 5–9 | — | decoy_telemetry, fake_param_dump, honeytoken_doc, slow_drip_data, verbose_logs | generic `_default_response` |

### C.2 GROUND-TRUTH stage-optimal map — `STAGE_OPTIMAL_5` (`skills.py:37`)

This is the answer key that `deception_quality` / `strict_dq` grade against.

| Phase int | stage | optimal skill idx | skills |
|:--:|---|---|---|
| 0 | Recon | {0, 2} | statustext, ghost_port |
| 1 | Intrusion | {1, 3, 0} | flight_sim, reboot_sim, statustext |
| 2 | Persistence | {3, 0} | reboot_sim, statustext |
| 3 | Theft | {4, 0} | credential_leak, statustext |

- **raw deception_quality** = fraction of deceiver turns whose skill ∈ STAGE_OPTIMAL.
- **strict_dq** (paper metric) = same **but with idx 0 `statustext` removed** from every stage
  (`STAGE_OPTIMAL ∖ {statustext}`) — statustext is optimal in *all* stages, so an LLM that spams it
  scores 1.0 without real skill (the "statustext monoculture" artifact, F8/F14).

---

## PART D — WIRE SURFACE: give-aways / honey-tells (`core/deception/surface.py`)

Deterministic (no LLM). `honey_response(attacker_action, defender_skill) → {intel, flags}`. `intel` =
fake lure artifacts; `flags` = **honey-tells** (name, weight) that raise attacker suspicion.

### D.1 Honey action×skill effect table (`_RESPONSE_TABLE`)

| attacker action (canonical) | defender skill | fake intel granted | honey-tells (flag, weight) |
|---|---|---|---|
| companion_credential_replay | credential_leak | api_token, ssh_password | api_token_too_easy 0.20 · banner_formulaic 0.10 |
| companion_credential_replay | reboot_sim | — | reboot_no_tcp_break 0.25 |
| mavlink_passive_listen | ghost_port | — | ghost_signature 0.15 |
| companion_http_probe | ghost_port | probe_ghost_reward | ghost_signature 0.15 · service_opens_on_probe 0.15 |
| companion_http_probe | statustext | — | banner_formulaic 0.10 |
| mavlink_command_inject | reboot_sim | telemetry_readout | reboot_no_tcp_break 0.25 |
| mavlink_command_inject | statustext | telemetry_readout | banner_formulaic 0.10 |
| mavlink_command_inject | flight_sim | telemetry_readout ×2 | — (clean; no tell) |
| signature_check | flight_sim | — | timing_too_consistent 0.15 |
| signature_check | statustext | — | banner_formulaic 0.10 · timing_too_consistent 0.15 |
| signature_check | ghost_port | — | ghost_signature 0.15 · service_opens_on_probe 0.15 |
| signature_check | credential_leak | api_token | api_token_too_easy 0.20 · credentials_no_lockout 0.20 |
| companion_lateral | credential_leak | signing_key, config_dump | api_token_too_easy 0.20 · credentials_no_lockout 0.20 |
| companion_lateral | ghost_port | — | ghost_signature 0.15 |
| *(any other pair)* | `_default_response` | — | banner_formulaic 0.05 |

**Reading it:** each cell is the wire outcome of a (attack, deception) pairing. A *good* deception
grants convincing fake intel with *low* tell-weight (e.g. command_inject × flight_sim = intel, no tell);
a *mismatched* skill leaks high-weight tells (e.g. signature_check × credential_leak = 0.40 tell weight).

### D.2 REAL-node responder (`real_response`)

No honey-flags ever (a real drone has no honeypot tells). Breach progress **only** on costly exploit
actions: `REAL_BREACH_GAIN = {1: 2.0, 3: 3.0, 4: 2.0}` (command_inject / lateral / credential_replay).
Real intel exfiltrated only after breach ≥ threshold: `{4: ssh_password, 5: config_dump}`.

### D.3 Suspicion accumulation (`core/deception/suspicion.py`)

Saturating independent-evidence combination, per honey-tell of weight w:
```
s ← 1 − (1 − s)·(1 − w)          (rises toward 1, never exceeds)
```
Max single in-memory flag weight = 0.25 (`reboot_no_tcp_break`). Suspicion is **separate from the
observer belief μ** — it is the attacker-side tell counter (this is the independent component of
identification, distinct from the μ<thresh path).

---

## PART E — ATTACKER ACTION SPACE (`skills.py:64`)

| idx | action | cost | class |
|:--:|---|:--:|---|
| 0 | mavlink_passive_listen | 0.5 | recon (cheap) |
| 1 | mavlink_command_inject | 3.0 | **exploit (breaches real)** |
| 2 | signature_check | 2.0 | verify/audit |
| 3 | companion_lateral | 4.0 | **exploit (breaches real)** |
| 4 | companion_credential_replay | 2.0 | **exploit (breaches real)** + exfil |
| 5 | companion_http_probe | 2.0 | probe + exfil |
| 6 | disengage | 0.0 | terminal |

Intel rewards (`ATTACKER_INTEL_REWARDS`): signing_key 4.0 · api_token 3.0 · ssh_password 3.0 ·
config_dump 2.0 · telemetry_readout 1.0 · probe_ghost_reward 0.5. ARC = Σ action costs.

---

## PART F — HOW A TURN USES ALL OF THIS (glue)

```
attacker LLM ─(action)→ surface.honey_response(action, skill) ─→ {fake intel, honey-tells}
                                    │                                     │
defender LLM ─(skill)───────────────┘                                     ▼
   ▲  knowledge.augment(prompt, query=stage+action)              suspicion.apply_flags (attacker)
   │  = RAG level (fid_*/cov_*) injects corpus chunks                      │
   └─ picks skill_idx ∈ 0..4                                               ▼
                                                     observer LLM scores wire → μ (belief_real)
                                                     μ → attacker b^A (w=0.6) ; win = μ_final>0.5
```

Skill correctness (vs `STAGE_OPTIMAL_5`) → `strict_dq`. Tell-weight → suspicion → identification.
Fake-intel realism + low tells → observer keeps μ high → defender win. RAG level decides how good the
skill choice can be; that is the causal path fidelity/coverage act on.

---

### File index (paths)
- `corpus/deceiver/{fidelity,coverage,distractor}/…` — RAG corpus (this codebook, Part A)
- `core/knowledge.py` — retrieval + RAG-level routing (Part B)
- `core/deception/skills.py` — skills, STAGE_OPTIMAL, attacker actions/costs (Parts C, E)
- `core/deception/surface.py` — deterministic wire effects + tells (Part D.1–D.2)
- `core/deception/suspicion.py` — suspicion accumulation (Part D.3)
- `core/agents/{tactical.py, defender/multi.py, attacker.py, observer.py}` — the LLM seats
