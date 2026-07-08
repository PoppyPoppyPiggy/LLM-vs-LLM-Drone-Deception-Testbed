# ARCHITECTURE — clean ASCII flows (논문 figure 변환용)

4장 분리·세로 flow. 박스 폭 일관, 화살표 중앙정렬. Attacker=공격, Deception=허니드론 두뇌, "Deceiver" 미사용.

═════════════════════════════════════════════════════════════
## A. FANET ENVIRONMENT (배경 무대)
═════════════════════════════════════════════════════════════
```
                          ┌──────────┐
                          │   GCS    │   star hub
                          └────┬─────┘
          ┌──────────┬─────────┼─────────┬──────────┐    star links
          │          │         │         │          │
     ┌────▼───┐ ┌────▼───┐     │    ┌────▼────┐ ┌───▼─────┐
     │ real_0 │ │ real_1 │     │    │ honey_0 │ │ honey_1 │
     │ θ=real │ │ θ=real │     │    │ θ=honey │ │ θ=honey │
     │protect │ │protect │     │    │+DEC LLM │ │+DEC LLM │
     └────────┘ └────────┘     │    └────┬────┘ └────┬────┘
                               │         └─────┬─────┘  range ≤150m
                          ┌────▼───────────────▼────┐
                          │   ATTACKER LLM           │
                          │   Qwen2.5  0.5–14B       │
                          └──────────────────────────┘

  nodes: 1 GCS · 2 real · 2 honey(Deception LLM 7B) · 1 attacker
  star · static · MAVLink wire · real↔honey WIRE-INDISTINCT · θ = eval-only
  (fanet/{nodes,topology,routing,mobility} · config/default.yaml)
```

═════════════════════════════════════════════════════════════
## B. ATTACK FLOW (공격자, per-turn 순서)
═════════════════════════════════════════════════════════════
```
         ┌────────────────────────────────────────┐
         │  ATTACKER LLM   Qwen2.5 0.5–14B          │
         │  single | multi (recon→exploit, 2 calls) │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ ① observe target  (opaque id, θ hidden)  │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ ② detect kill-chain phase                │
         │    Recon → Intrusion → Persist → Theft   │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ ③ select action  a_idx                   │
         │    7 actions (cost 0.5 … 4)              │
         └─────────────────────┬───────────────────┘
                               ▼
                          ┌────────────┐
                     ┌────┤ ④ target ? ├────┐
                 REAL│    └────────────┘    │HONEY
                     ▼                      ▼
         ┌────────────────────┐  ┌────────────────────────┐
         │ breach / intel     │  │ engages honeydrone      │
         │ (attacker goal)    │  │ → DEFENSE FLOW (C)      │
         └─────────┬──────────┘  └───────────┬────────────┘
                   └────────────┬─────────────┘
                                ▼
         ┌────────────────────────────────────────┐
         │ ⑤ receive wire → update belief b, susp   │
         └─────────────────────┬───────────────────┘
                               │   loop × max_turns = 12
                               └──────────────▲  (back to ①)
  core/agents/{attacker,attacker_team} · core/staging/phase · core/deception/{skills,surface}
```

═════════════════════════════════════════════════════════════
## C. DEFENSE FLOW (Deception LLM = 허니드론, per-engagement 순서)
═════════════════════════════════════════════════════════════
```
         ┌────────────────────────────────────────┐
         │  attacker action observed (on honey)     │
         │  (stage, action, P_real)                 │
         └─────────────────────┬───────────────────┘
                               ▼
         ╔════════════════════════════════════════╗
         ║ ① RAG retrieve        (knowledge.py)     ║
         ║    query → embed → top_k = 4             ║
         ║    main(relevant) ⊕ hard_neg(distractor) ║
         ║    → rel_dose      ★ fidelity / coverage ║
         ╚═════════════════════╤════════════════════╝
                               ▼
         ┌────────────────────────────────────────┐
         │ ② DECEPTION LLM  select skill_idx (5)    │
         │    single: Tactical                      │
         │    multi : Orchestr→Checker→Log→Persona  │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ ③ honey_response(action, skill)          │
         │    fake telemetry/intel + tells(flags)   │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ → raises belief μ  (attacker stays fooled)│
         └────────────────────────────────────────┘
  core/agents/{defender,defender/multi,tactical} · core/deception/{skills,surface,suspicion}
```

═════════════════════════════════════════════════════════════
## D. RESULTS PIPELINE (결과 도출 순서)
═════════════════════════════════════════════════════════════
```
         ┌────────────────────────────────────────┐
         │ KNOBS                                    │
         │  ① capacity (attacker size)              │
         │  ② structure (single/multi, 양측)        │
         │  ③ RAG (fidelity / coverage)             │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ run.py → episode loop × max12 (sweep)    │
         │   ATTACK flow (B)  ⇄  DEFENSE flow (C)   │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ Belief Observer  (per turn)              │
         │   μ ← (1−w)·μ + w·μ̂                       │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ episode metrics  (θ-aware)               │
         │   win = honey μ_final > 0.5              │
         │   strict deception-quality · cost=tokens │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ aggregate (n=16/32, fallback-free,paired)│
         │   strict rescore + correlation           │
         └─────────────────────┬───────────────────┘
                               ▼
         ┌────────────────────────────────────────┐
         │ FIGURES                                  │
         │   win-rate × token cost (dominance)      │
         │   dose-response · arms-race 2×2          │
         └────────────────────────────────────────┘
  run.py · episode.py · core/belief/convex · eval/{metrics,continuous} · dominance_figures.py
```

═════════════════════════════════════════════════════════════
본문 배치: **A(무대)** 먼저 → **B·C(공격/방어 flow, 나란히 대칭)** → **D(결과 도출, 방법↔결과 연결)**.
각 ①②③④⑤ 번호는 TikZ 이식 시 그대로 노드 라벨로 유지(캡션에서 모듈 경로 참조).
```
