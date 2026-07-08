# ARCHITECTURE — Mermaid (논문 figure용, 렌더 가능)

각 코드블록을 mermaid.live · VS Code(Markdown Preview Mermaid) · GitHub에서 **벡터 그림으로 바로 렌더** → SVG 추출 후 IEEE figure로.
색: Attacker=brick(빨강) · Deception=teal(초록) · 중립(FANET/GCS/real/Observer)=gray. "Deceiver" 미사용.

---

## FIG A — FANET ENVIRONMENT (배경 무대)
> 물리 토폴로지: 1 GCS · 2 real · 2 honey(Deception LLM 탑재) · 1 attacker. star/static/150m. real↔honey wire 구분불가.

```mermaid
graph TD
  classDef atk fill:#F5D9D9,stroke:#A32D2D,stroke-width:1.5px,color:#000
  classDef dec fill:#D6EBE3,stroke:#1F6E56,stroke-width:1.5px,color:#000
  classDef neu fill:#ECECEC,stroke:#777,stroke-width:1.2px,color:#000

  GCS["GCS (star hub)"]:::neu
  R0["real drone 0<br/>θ=real · protected"]:::neu
  R1["real drone 1<br/>θ=real · protected"]:::neu
  H0["honeydrone 0<br/>θ=honey · Deception LLM 7B"]:::dec
  H1["honeydrone 1<br/>θ=honey · Deception LLM 7B"]:::dec
  ATK["Attacker LLM<br/>Qwen2.5 0.5–14B"]:::atk

  GCS --- R0
  GCS --- R1
  GCS --- H0
  GCS --- H1
  ATK -. "range ≤150m (MAVLink, no GCS link)" .- H0
  ATK -. "real↔honey WIRE-INDISTINCT" .- R0
  ATK -. .- H1

  %% fanet/{nodes,topology=star,routing=shortest_path,mobility=static} · config/default.yaml
```

---

## FIG B — ATTACK FLOW (공격자, per-turn 순서)
> Attacker LLM이 kill-chain을 따라 행동을 고르는 흐름. single=1 LLM, multi=recon-analyst→exploit-operator.

```mermaid
flowchart TD
  classDef atk fill:#F5D9D9,stroke:#A32D2D,stroke-width:1.5px,color:#000
  classDef neu fill:#ECECEC,stroke:#777,color:#000

  A0["① observe target state<br/>(opaque id, θ hidden)"]:::neu
  A1["② detect kill-chain phase<br/>Recon→Intrusion→Persistence→Theft"]:::atk
  A2["③ Attacker LLM select_action<br/>single: 1 call · multi: recon→exploit (2 calls)"]:::atk
  A3["④ emit action a_idx + target<br/>7 actions (cost 0.5–4)"]:::atk
  A4{"⑤ target type?"}:::neu
  A5["REAL → goal: breach/intel<br/>(win on costly exploit 1/3/4)"]:::neu
  A6["HONEY → engages decoy<br/>(unknowingly → Defense flow)"]:::dec
  A7["⑥ receive wire response<br/>update own belief b, suspicion"]:::atk

  A0 --> A1 --> A2 --> A3 --> A4
  A4 -->|real| A5
  A4 -->|honey| A6
  A5 --> A7
  A6 --> A7
  A7 -. "next turn (loop ×max_turns=12)" .-> A0

  classDef dec fill:#D6EBE3,stroke:#1F6E56,color:#000
  %% core/agents/{attacker,attacker_team}:select_action · core/staging/phase · core/deception/{skills,surface}
```

---

## FIG C — DEFENSE FLOW (Deception LLM, per-engagement 순서)
> 허니드론 두뇌가 공격 행동을 받아 belief μ를 높게 유지하는 흐름. ①RAG→②skill→③wire.

```mermaid
flowchart TD
  classDef dec fill:#D6EBE3,stroke:#1F6E56,stroke-width:1.5px,color:#000
  classDef rag fill:#EAF5F0,stroke:#1F6E56,stroke-dasharray:4 2,color:#000
  classDef neu fill:#ECECEC,stroke:#777,color:#000

  D0["attacker action observed<br/>(stage, action, P_real)"]:::neu
  subgraph RAG["① RAG retrieve  (core/knowledge.py)"]
    direction TB
    G1["query → embed → top_k=4"]:::rag
    G2["pool = fidelity/main (relevant)<br/>⊕ fidelity/hard_neg (distractor)"]:::rag
    G3["rel_dose = #relevant in top_k<br/>★ fidelity / coverage knob"]:::rag
    G1 --> G2 --> G3
  end
  D1["② select skill_idx (5-skill)<br/>single: Tactical · multi: Orchestr→Checker→Log→Persona"]:::dec
  D2["③ honey_response(action, skill)<br/>fake telemetry/intel + tells(flags)"]:::dec
  D3["→ raises belief μ<br/>(attacker stays fooled)"]:::dec

  D0 --> RAG --> D1 --> D2 --> D3
  %% core/agents/{defender,defender/multi,tactical} · core/deception/{skills,surface,suspicion}
```

---

## FIG D — RESULTS PIPELINE (결과 도출 순서)
> 노브 → 에피소드 루프 → per-turn belief/cost → 에피소드 지표 → 집계 → figure.

```mermaid
flowchart LR
  classDef knob fill:#FFF3D6,stroke:#BA7517,color:#000
  classDef proc fill:#ECECEC,stroke:#777,color:#000
  classDef out fill:#E6E9F5,stroke:#3A4BA0,color:#000

  K["KNOBS<br/>① capacity (attacker size)<br/>② structure (single/multi, 양측)<br/>③ RAG (fidelity/coverage)"]:::knob
  R["run.py → episode loop<br/>×max_turns=12, sweep<br/>(Attack flow ⇄ Defense flow)"]:::proc
  O["Belief Observer per turn<br/>μ ← (1−w)μ + w·μ̂"]:::proc
  M["episode metrics (θ-aware)<br/>win = honey μ_final>0.5<br/>strict deception-quality<br/>cost = completion tokens"]:::proc
  AGG["aggregate (n=16/32, fallback-free, seed-paired)<br/>+ strict rescore + correlation"]:::proc
  F["FIGURES<br/>win-rate × token cost (dominance)<br/>dose-response · arms-race 2×2"]:::out

  K --> R --> O --> M --> AGG --> F
  %% run.py · episode.py · core/belief/convex · eval/{metrics,continuous} · dominance_figures.py
```

---

## 렌더 / 이식 노트
- **렌더**: mermaid.live 붙여넣기 → Export SVG/PNG. 또는 VS Code "Markdown Preview Mermaid Support". GitHub은 ```mermaid 자동 렌더.
- **IEEE 이식**: SVG를 그대로 vector figure로 쓰거나, 배치 확정 후 TikZ로 옮김(노드/엣지가 단순해 직역 쉬움).
- **4장 역할**: A=무대(배경), B=공격 순서, C=방어 순서, D=결과 도출 — 본문에서 A 먼저, B·C 나란히(대칭), D는 방법/결과 연결부.
- 색 classDef(atk/dec/neu)는 4장 공통 → 일관성 유지.
