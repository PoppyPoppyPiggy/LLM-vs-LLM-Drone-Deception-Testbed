# Deceiver RAG corpus — redesigned (Phase 2 draft)

Resolves DIAG_rag_corpus A1 (tiny corpus) / A2 (coverage stage gaps) / B2 (weak kept answer).
Stage tagging via `_chunk_stage` keywords: recon / intrusion(+initial access,execution) / theft(exfiltration).
Persistence chunks tag as None (stage-agnostic) → eligible in all stages; persist queries map→intrusion.

## Structure
```
fidelity/
  main/        recon.txt intrusion.txt theft.txt   — 20 chunks/stage = 60 (relevant; = coverage/cov_full)
  hard_neg/    hn.txt                               — 22 query-similar negatives, NO correct stage→skill map
coverage/
  cov_min/     1 chunk/stage  = 3    (all 3 stages, sparse)
  cov_mid/     5 chunks/stage = 15
  cov_full/    20 chunks/stage = 60  (= fidelity/main)
```
(legacy relevant_5 / relevant / relevant_L1 / relevant_L2 are DEPRECATED — stage gaps, too small.)

## Verified properties
- chunk len 241–371 chars (no inject_chars truncation); recon-pool/top_k ≈ 6:1 (≥5:1 discriminable).
- stage-gate precise: recon query → recon chunks; theft query → theft chunks.
- hard_neg cosine to a deceiver query (top 0.796) ≥ main (0.773) → can crowd top-k = realizes
  spec §1 `fid_weak` (answer ranked BELOW cutoff) and `fid_poison` (answer absent).
- ground truth taught = STAGE_OPTIMAL_5: recon→{statustext,ghost_port}; intrusion/persist→
  {flight_sim,reboot_sim,statustext}; theft→{credential_leak,statustext}.

## Phase 2 wiring TODO (make_knowledge, not yet done)
- fid_strong → fidelity/main ; fid_weak/fid_poison → main + distractor_dir=fidelity/hard_neg
  (fid_weak = rank-push: include relevant pool but let hard_neg out-rank into top-k; fid_poison = main excluded)
- cov_min/mid/full → coverage/<level> with fidelity fixed at strong
- top_k=4 (exact 50% split, C2 fix) when mixing relevant+distractor
