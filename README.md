# LLM-vs-LLM Honeydrone Deception on a FANET (testbed)

A simulated **model-and-simulation (M&S) testbed** where an **Attacker LLM** and a **Deception LLM**
(the brain of a honeydrone) compete on a Flying Ad-hoc Network (FANET). The attacker tries to breach
real mission drones; the honeydrones try to keep the attacker fooled (engaged on decoys). We measure,
as standard LLM-evaluation axes, **who wins (win-rate from the attacker's recovered belief)** against
**decision-token cost**, across four knobs: attacker capability, multi-agent structure, and RAG
(retrieval fidelity & coverage).

> **Scope / ethics.** Everything here is **simulated and abstracted** (no real MAVLink crypto, RF, or
> exploits; "credentials" surfaced to the attacker are fake decoy artifacts). The attacker-side
> kill-chain is a research abstraction, not a usable exploit. Released for reproducible security
> research only.

## Key result (strict-rescored, win-rate primary)
- **Capacity** — a larger Attacker LLM wins more (defender win 0.77 → 0.46 as attacker scales 0.5B→14B; attacker identification rises, pooled d≈1.16, n=32/cell). *Attacker buys advantage with tokens.*
- **Structure (2×2)** — single-sided multi helps that side (SM 0.780 / MS 0.309), but **both-multi (MM 0.434) is a near-tie at worst token-efficiency** (def_tokens 239 vs 116 at SS) — an arms-race that wastes compute.
- **RAG fidelity** — relevant retrieval lifts the defender almost for free (win 0.73 → 0.90 across the dose at ~constant tokens; best win/1k). Win-rate dose-response Pearson r≈0.95; selection-quality (strict) OLS β=0.094 [0.069,0.118], R²=0.316.
- **RAG coverage** — graded (not saturated): more kill-chain coverage → higher win (cov_min 0.51 → cov_full 0.73).
- *Dropped as non-informative/artifacts:* diversion, survival, raw (non-strict) deception-quality.

## Install
```bash
pip install -r requirements.txt          # numpy, matplotlib, PyYAML  (Python 3.10+)
# External: a local Ollama server (https://ollama.com) with the models:
ollama serve &
ollama pull qwen2.5:0.5b qwen2.5:1.5b qwen2.5:7b qwen2.5:14b nomic-embed-text
```

## Run one cell
```bash
python3 run.py --deceiver-rag fid_strong --deceiver-skillset 5 --prompt-stage-hint off \
   --max-turns 12 --routing sweep --deception visible \
   --model-attacker qwen2.5:7b --seeds 0,1,2,3 --episodes 1 --tag demo
```
Knobs: `--model-attacker` (capacity) · `--{attacker,deceiver}-structure single|multi` (structure) ·
`--deceiver-rag {none,fid_poison,fid_weak,fid_mid,fid_strong,cov_min,cov_mid,cov_full,fid_filler}` (RAG).

## Reproduce figures
```bash
cd figures_py
python3 paper_figures.py    # the 4 result figures from results_cells.csv -> ../figures/
```
Outputs PNG/PDF/SVG for `fig_06`–`fig_09` (paper Figures 5–8: capacity, retrieval, structure,
efficiency). Shared IEEE style in `figures_py/ieee_style.py` (serif, brick/teal palette, column widths).

## Repository layout
```
run.py            episode loop entry             episode.py        one-episode game loop
core/agents/      attacker · deception · observer LLM agents
core/deception/   skills · wire surface · suspicion
core/knowledge.py RAG (fidelity/main ⊕ hard_neg, coverage tiers)   core/belief/convex.py  belief μ update
core/staging/     kill-chain phase model         eval/             metrics (win-rate, strict deception-quality)
fanet/            FANET: nodes · star topology · routing · mobility
config/default.yaml   single source of knobs     corpus/           RAG corpus (deceiver playbook + hard negatives, attacker)
results_cells.csv · results_episodes.csv   reported data (single source of truth: 21 cells / 800 episodes)
figures_py/       ieee_style.py + paper_figures.py  →  figures/ (pre-rendered fig_06..09, PNG/PDF/SVG)
METRICS_FULL.md   per-cell metric dump (21 cells × mean±95%CI)
docs/             architecture (ASCII flow + Mermaid) + corpus deception codebook
```
> **Out of scope.** The GCS *coordinate-directive* / moving-target-defense (MTD) extension is not
> part of this release: it is disabled in every reported run and its code is not included here.
Metrics: **win-rate** = fraction of engaged honeydrones with recovered belief μ_final > 0.5;
**cost** = role completion-tokens. Regime for all reported runs: `max_turns=12`, `routing=sweep`,
5-skill engine, `prompt_stage_hint=off`, fallback-free, seed-paired.

## License
MIT (see `LICENSE`).
