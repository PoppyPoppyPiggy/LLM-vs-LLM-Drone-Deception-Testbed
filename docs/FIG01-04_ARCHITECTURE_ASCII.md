# FIG 01–04 — Architecture (big-picture, data-flow labelled)

> Components say WHAT they do; every arrow says WHICH DATA passes; the evaluation figure says WHICH
> METRICS are checked and WHAT QUESTION each answers. MTD-free (GCS is a passive hub, no directive).

═══════════════════════════════════════════════════════════════════════════════
## fig_01 — SYSTEM MODEL  (who plays, what data flows between them)
═══════════════════════════════════════════════════════════════════════════════
```
   ┌─────────────────────────┐        action a_t  (probe / exploit)        ┌──────────────────────────┐
   │      ATTACKER LLM        │ ──────────────────────────────────────────▶│        FANET NODES        │
   │ decides the next move    │                                            │  2 real  +  2 honeydrones │
   │ along a kill-chain;      │◀────────────────────────────────────────── │  (identical on the wire)  │
   │ tries to breach REAL     │     wire response  (telemetry / banner /    │                           │
   │ nodes & exfiltrate intel │      intel — real OR faked)                 └───────┬──────────┬────────┘
   └─────────▲───────────────┘                                    fake surface │          │ real surface
             │                                                (crafted telemetry│          │(hardened; breach
             │ b^A ← μ                                          + subtle tells)  │          │ only on costly
             │ (attacker's belief                                    ┌──────────▼──────┐   │ exploit)
             │  tracks the observer)                                 │  DECEPTION LLM  │   │
             │                                                       │ (brain of each  │   │
             │                        (action , response)            │  honeydrone):   │   │
   ┌─────────┴───────────────┐   pair on the wire                    │ pick a deception│   │
   │    BELIEF OBSERVER       │◀──────────────────────────────────── │ skill to look   │   │
   │ neutral 3rd party: reads │                                       │ like a real UAV │   │
   │ the wire, estimates      │            μ  (belief the node        └─────────────────┘   │
   │ "how REAL does this look"│───────────▶  is real, 0–1)  ────────────────▶  WIN METRIC   │
   └──────────────────────────┘                                     win = μ_final > 0.5     │
                                                                                            │
   - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -│- - -
   EVALUATOR holds θ (which node is real vs honey) — used ONLY to score, never shown to any player. ◀┘
   ⇒ the attacker must INFER "decoy", it is never told.
```
**Reading it.** The attacker LLM and the honeydrones' Deception LLMs play a hidden-role game over an
indistinguishable wire; a neutral observer LLM converts each wire exchange into a belief μ that (i)
defines the defender's win and (ii) is fed back as the attacker's own belief b^A. The ground truth θ
lives only in the evaluator.

═══════════════════════════════════════════════════════════════════════════════
## fig_02 — ATTACKER LOOP  (what the attacker computes each turn, and what comes back)
═══════════════════════════════════════════════════════════════════════════════
```
     target state                 kill-chain                 chosen                 engagement
     (opaque id,        phase     phase                action  action                 result
      last response) ─────────▶  Recon→Intrusion  ─────────▶  1 of 7 moves  ─────────▶  ┌── REAL ──┐
                                 →Persistence→Theft          (recon / probe /          │ breach signal
                                                              exploit / leave)          │ + real intel
                                                                                        │ (only via costly
                                                                                        │  exploit)
                                                                                        └── HONEY ─┐
                                                                                        │ FAKE intel
                                                                                        │ + honey-tells
                                                                                        └──────────┘
                                                                                              │
     ┌────────────────────────────────────────────────────────────────────────────────────┘
     ▼
   update  ● suspicion ← honey-tells   (catches decoys)
           ● belief b^A ← observer μ   (how real it feels)
     │
     └────▶ next turn  (loop ×12, or disengage)     GOAL: damage real nodes  vs  lure GOAL: keep b^A high,
                                                                                    waste attacker effort on honey
```
**Reading it.** Each turn the attacker maps the situation to a kill-chain phase, picks one of seven
cost-weighted actions, and gets back either a real breach signal (only from costly exploits) or fake
intel plus tells from a honeydrone; it then revises suspicion (from tells) and belief (from μ).

═══════════════════════════════════════════════════════════════════════════════
## fig_03 — HONEYDRONE DEFENSE  (the deception pipeline + where the 3 study knobs enter)
═══════════════════════════════════════════════════════════════════════════════
```
   attacker action
   (+ stage)
        │
        ▼
   ┌───────────────────────┐   retrieved snippets     ┌────────────────────────┐   skill choice
   │  RETRIEVE knowledge   │  (0–4 USEFUL playbook  ─▶│   DECEPTION LLM         │  (which of 5
   │  how to act this stage│   chunks, rest noise)    │  choose a deception     │   deception skills)
   └───────────────────────┘                          │  skill for this action  │       │
        ▲                                              └────────────────────────┘       │
        │  ◀── KNOB ③ RETRIEVAL                             ▲                            ▼
        │      fidelity: how USEFUL the chunks are          │ ◀── KNOB ② STRUCTURE   ┌────────────────────┐
        │      coverage: how BROAD the corpus is            │   single = 1 reasoner  │  WIRE SURFACE      │
        │                                                   │   multi  = reasoner +  │  turn (action,skill)│
        │                                                   │           checker      │  into what the      │
        │                                                   │                        │  attacker sees      │
        │                                                   │                        └─────────┬──────────┘
        │                                                   │        good skill → convincing    │
        │                                                   │        fake intel, few tells      │
        │  KNOB ① CAPACITY sits on the ATTACKER side ───────┘        bad  skill → obvious tells  │
        │  (bigger attacker model = better decoy detection)                                     ▼
        │                                                              observer reads wire ─▶ μ stays HIGH
        └──────────────────────────────────────────────────────────  tells ─▶ attacker suspicion RISES
```
**Reading it.** When the attacker hits a honeydrone, retrieval supplies stage-appropriate playbook
snippets (KNOB③), the Deception LLM — alone or as a reasoner+checker team (KNOB②) — picks a skill, and a
surface layer turns it into fake telemetry/intel plus tells; good choices keep μ high, bad ones leak tells
that raise the attacker's suspicion. Attacker model size is the third knob (KNOB①), set on the attack side.

═══════════════════════════════════════════════════════════════════════════════
## fig_04 — EVALUATION  (which metrics are read, and what each one checks)
═══════════════════════════════════════════════════════════════════════════════
```
   RUN one episode per knob setting  ─────▶  collect signals at 3 timescales
        (attack ⇄ defense, 12 turns)
                                             ┌──────────────────────────────────────────────────────────┐
   PER TURN   ─────────────────────────────▶│ μ_t  belief the engaged node is real (observer)            │
                                             └──────────────────────────────────────────────────────────┘
                                             ┌──────────── metric ──────────────┬──── question it answers ─┐
   PER EPISODE ────────────────────────────▶│ WIN = μ_final > 0.5               │ did the decoy stay unmasked?
                                             │ IDENTIFICATION rate               │ did the attacker call it a decoy?
                                             │ STRICT deception-quality          │ did the LLM pick the RIGHT skill?
                                             │ DIVERSION (effort on honey)       │ was the attacker pulled off real?
                                             │ REAL breach / real-intel          │ did real assets actually get hit?
                                             │ TOKENS  def / atk  (+ ARC cost)   │ how much compute did it cost?
                                             └───────────────────────────────────┴──────────────────────────┘
                                             ┌──────────────────────────────────────────────────────────┐
   ACROSS 800 EPISODES ────────────────────▶│ win-rate + 95% CI ;  dose-response (retrieval → win)       │
   (n=32 / 64, fallback-free, seed-paired)  │ effect size (capacity, d) ;  win × token-cost frontier     │
                                             └──────────────────────────────────────────────────────────┘
                                             ┌──────────────────────────────────────────────────────────┐
   VALIDITY CHECK ─────────────────────────▶│ does μ track TRUTH?  real-vs-honey μ separation, AUROC     │
                                             │ (θ-blind: proves the belief metric isn't arbitrary)        │
                                             └──────────────────────────────────────────────────────────┘
        │
        ▼
   REPORTED FIGURES:  capacity ↓win ↑id · retrieval dose-response · structure 2×2 arms-race ·
                      cost frontier · forest · artifact (raw vs strict) · construct validity
```
**Reading it.** Every episode is read at three timescales — the per-turn belief μ, a bundle of
per-episode metrics (each answering one question: unmasked? identified? right skill? diverted? real damage?
at what cost?), and cross-episode aggregates (win-rate + CI, dose-response, effect size, cost frontier) —
plus a θ-blind validity check that the belief actually separates real from honey nodes.

───────────────────────────────────────────────────────────────────────────────
Placement: fig_01 (system) → fig_02 + fig_03 side-by-side (attack vs defense) → fig_04 (evaluation,
bridges into the result figures fig_06–09).
```
