"""run.py — experiment runner for the LLM-vs-LLM honeydrone deception testbed.

Loads config/default.yaml, runs (seed × episode) episodes through episode.run_episode, computes
the standard + continuous metrics, and writes ONE tidy row per episode to results/<tag>/.
Knobs (attacker capacity, single/multi structure per side, retrieval fidelity/coverage) are set
on the command line; see README.md.
"""
from __future__ import annotations
import argparse, asyncio, copy, csv, json
from pathlib import Path

import yaml
from fanet.network import Fanet
from fanet.nodes import NodeType
from core.llm_client import LLMClient, set_llm_context, set_deterministic, reset_calls, get_calls
from core.knowledge import PromptOnly, make_knowledge, open_retrieval_log, close_retrieval_log
from core.agents.attacker import LLMAttacker
from core.agents.attacker_team import make_attacker_team
from core.agents.defender import make_defender
from core.agents.observer import BeliefObserver
from eval.metrics import compute_episode_metrics
from core.deception.skills import stage_optimal_map
from eval.continuous import continuous_metrics
from episode import run_episode

ROOT = Path(__file__).resolve().parent


def build_agents(cfg, net, eff_seed):
    """Build symmetric agents from config (structure axis: single|multi; rag_fidelity=none->PromptOnly).
    cli (LLM client) is shared per episode across attacker, deceivers, and observer."""
    m = cfg["models"]; roles = m["roles"]; gen = m["gen"]; bi = cfg["belief_init"]; sc = cfg["scenario"]
    cli = LLMClient(m["ollama_url"])
    corpus_root = str(ROOT / "corpus")
    emb_url = m.get("embed_url", m["ollama_url"]); emb_model = m.get("embed_model", "nomic-embed-text")

    # ★engine profile flags (deceiver): 5-skill+hint (main) vs 10-skill no-hint (RAG-ladder).
    _truthy = (True, "true", "True", "on", 1)
    extended = sc["deceiver"].get("extended_skills", False) in _truthy
    stage_hint = sc["deceiver"].get("prompt_stage_hint", True) in _truthy

    def know(role_name, fidelity, ext):
        return make_knowledge(fidelity, role=role_name, corpus_root=corpus_root,
                              embed_url=emb_url, model=emb_model, extended=ext)
    # attacker always uses corpus/attacker/relevant (ext=True path); deceiver corpus matches its engine.
    know_atk = know("attacker", sc["attacker"]["rag_fidelity"], True)
    know_dec = know("deceiver", sc["deceiver"]["rag_fidelity"], extended)
    # attacker: single | multi (Recon/Exploit/Reporter) — shared inner belief
    policy = LLMAttacker(cli, know_atk, roles["attacker"], b_init=bi["attacker"],
                         temperature=gen["attacker_temp"], timeout=gen["timeout_sec"], seed=eff_seed)
    attacker = make_attacker_team(sc["attacker"]["structure"], policy=policy)
    # deceiver per honey: single (TacticalDefender) | multi (Orchestrator+Checker+Logger+Persona)
    dstruct = sc["deceiver"]["structure"]
    deceivers = {n.node_id: make_defender(dstruct, n.node_id, cli, know_dec, roles["deceiver"],
                                          timeout=gen["timeout_sec"], seed=eff_seed,
                                          checker_model=roles["deceiver"],
                                          extended=extended, stage_hint=stage_hint)
                 for n in net.nodes if n.ntype == NodeType.HONEY}

    def make_observer():
        return BeliefObserver(cli, roles["observer"], mu_init=bi["observer"],
                              temperature=gen["observer_temp"], timeout=gen["timeout_sec"], seed=eff_seed)
    return cli, attacker, deceivers, make_observer


async def run_unit(cfg, seed, episode, max_turns, routing):
    eff_seed = seed * 1000 + episode
    set_llm_context(unit=f"s{seed}_e{episode}")
    reset_calls()                                    # token/latency accumulator (per episode)
    net = Fanet.from_config(cfg["scenario"], seed=eff_seed)
    cli, attacker, deceivers, make_observer = build_agents(cfg, net, eff_seed)
    try:
        _dec = cfg.get("deception", "visible")
        deception_mode = {"on": "visible", "off": "none", True: "visible", False: "none"}.get(_dec, _dec)
        if deception_mode not in ("none", "visible", "concealed"):
            deception_mode = "visible"
        conseq_on = cfg.get("consequence_aware", "off") in (True, "on", "true", "True", 1)
        result = await run_episode(net, attacker, deceivers, make_observer,
                                   cfg["thresholds"], cfg["obs_confidence"], max_turns,
                                   seed=eff_seed, routing=routing,
                                   defender_structure=cfg["scenario"]["deceiver"]["structure"],
                                   deception_mode=deception_mode,
                                   consequence_aware=conseq_on,
                                   consequence_gain=float(cfg.get("consequence_gain", 0.3)))
    finally:
        await cli.close()
    row = {"seed": seed, "episode": episode, "routing": routing,
           "attacker_structure": cfg["scenario"]["attacker"]["structure"],
           "deceiver_structure": cfg["scenario"]["deceiver"]["structure"],
           "attacker_rag": cfg["scenario"]["attacker"]["rag_fidelity"],
           "deceiver_rag": cfg["scenario"]["deceiver"]["rag_fidelity"],
           "deception": cfg.get("deception", "on"),
           "consequence_aware": cfg.get("consequence_aware", "off"),
           "consequence_gain": cfg.get("consequence_gain", 0.0)}
    _ext = cfg["scenario"]["deceiver"].get("extended_skills", False) in (True, "true", "True", "on", 1)
    row.update(compute_episode_metrics(result, cfg["thresholds"]["ident_thresh"],
                                       stage_optimal=stage_optimal_map(_ext)))
    hint = int(row.get("honey_engagement") or 0)
    row.update(continuous_metrics(result["trace"], max_turns, honey_turns_hint=hint,
                                  breach_thresh=cfg["thresholds"]["breach_thresh"]))
    # token/latency instrumentation (per-episode totals; per-turn list kept on the result)
    calls = get_calls()
    ptok = sum(c["prompt_tokens"] or 0 for c in calls); ctok = sum(c["completion_tokens"] or 0 for c in calls)
    lat = [c["latency_ms"] for c in calls]
    row["llm_calls"] = len(calls)
    row["prompt_tokens"] = ptok; row["completion_tokens"] = ctok; row["total_tokens"] = ptok + ctok
    row["latency_ms_total"] = round(sum(lat), 1)
    row["latency_ms_per_turn"] = round(sum(lat) / max(1, result["summary"]["turns"]), 1)
    row["attacker_model"] = cfg["models"]["roles"]["attacker"]
    result["_calls"] = calls                          # per-turn token/latency (sidecar)
    return row, result


def load_config(path):
    raw = yaml.safe_load(open(path))
    # the scenario block (nodes/fanet/gcs/attacker/deceiver) is what Fanet.from_config reads
    raw["scenario"] = {k: raw[k] for k in ("nodes", "fanet", "attacker", "deceiver")}
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config/default.yaml"))
    ap.add_argument("--seeds", default=None, help="comma ints (default: config run.seed .. +episodes)")
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--routing", default=None, choices=["sweep", "belief"])
    ap.add_argument("--attacker-structure", default=None, choices=["single", "multi"])
    ap.add_argument("--deceiver-structure", default=None, choices=["single", "multi"])
    ap.add_argument("--deception", default=None,
                    choices=["none", "visible", "concealed", "on", "off"],
                    help="3-way baseline: none(C1 real-dummy) | visible(C2 honey+tells=on) | concealed(C3 honey,tells suppressed). on/off=backcompat(visible/none)")
    ap.add_argument("--consequence-aware", default=None, choices=["on", "off"], help="attacker learns from real-foothold outcome (F2 A/B)")
    ap.add_argument("--consequence-gain", type=float, default=None, help="weight on the consequence signal (dose-response sweep axis; 0=wire-only)")
    ap.add_argument("--model-attacker", default=None, help="override attacker model (e.g. qwen2.5:14b — capacity rung)")
    ap.add_argument("--attacker-rag", default=None, choices=["none","filler","fid_none","fid_poison","fid_weak","fid_mid","fid_strong","fid_filler","cov_min","cov_mid","cov_full"])
    ap.add_argument("--deceiver-rag", default=None, choices=["none","filler","fid_none","fid_poison","fid_weak","fid_mid","fid_strong","fid_filler","cov_min","cov_mid","cov_full"])
    ap.add_argument("--n-honey", type=int, default=None, help="override honey count (0 = no-honey baseline)")
    ap.add_argument("--n-normal", type=int, default=None)
    ap.add_argument("--deceiver-skillset", default=None, choices=["5", "10"],
                    help="deceiver engine: 5=main(5-skill+stage-hint) | 10=extended(10-skill, RAG-ladder)")
    ap.add_argument("--prompt-stage-hint", default=None, choices=["on", "off"],
                    help="include stage->skill hint in deceiver prompt (5-skill main default on)")
    ap.add_argument("--timeout-sec", type=float, default=None,
                    help="override LLM call timeout (raise under parallel serving so queuing != fallback)")
    ap.add_argument("--deterministic", action="store_true",
                    help="AUDIT: force temp=0 on all LLM calls (bit-exact with PYTHONHASHSEED=0). NOT science mode.")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--out", default=str(ROOT / "results"))
    a = ap.parse_args()

    cfg = load_config(a.config)
    if a.attacker_structure:
        cfg["scenario"]["attacker"]["structure"] = a.attacker_structure
    if a.deceiver_structure:
        cfg["scenario"]["deceiver"]["structure"] = a.deceiver_structure
    if a.deception:
        cfg["deception"] = a.deception
    if a.consequence_aware:
        cfg["consequence_aware"] = a.consequence_aware
    if a.consequence_gain is not None:
        cfg["consequence_gain"] = a.consequence_gain
        if a.consequence_gain > 0 and not a.consequence_aware:
            cfg["consequence_aware"] = "on"        # gain>0 implies the channel is active
    if a.model_attacker:
        cfg["models"]["roles"]["attacker"] = a.model_attacker
    if a.attacker_rag:
        cfg["scenario"]["attacker"]["rag_fidelity"] = a.attacker_rag
    if a.deceiver_rag:
        cfg["scenario"]["deceiver"]["rag_fidelity"] = a.deceiver_rag
    if a.deceiver_skillset:
        cfg["scenario"]["deceiver"]["extended_skills"] = (a.deceiver_skillset == "10")
    if a.prompt_stage_hint:
        cfg["scenario"]["deceiver"]["prompt_stage_hint"] = (a.prompt_stage_hint == "on")
    if a.n_honey is not None:
        cfg["scenario"]["nodes"]["n_honey"] = a.n_honey
    if a.n_normal is not None:
        cfg["scenario"]["nodes"]["n_normal"] = a.n_normal
    if a.timeout_sec is not None:
        cfg["models"]["gen"]["timeout_sec"] = a.timeout_sec
    runc = cfg["run"]
    episodes = a.episodes if a.episodes is not None else runc["episodes"]
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else [runc["seed"]]
    max_turns = a.max_turns if a.max_turns is not None else runc["max_turns"]
    routing = a.routing or runc["routing"]
    if a.deterministic:
        set_deterministic(True)
        print("[AUDIT] --deterministic: all LLM calls forced to temp=0 (greedy). NOT a science run.")

    out_dir = Path(a.out) / a.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config_used.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    units = [(s, e) for s in seeds for e in range(episodes)]
    print(f"running {len(units)} episodes (seeds={seeds} × ep={episodes}) "
          f"max_turns={max_turns} routing={routing} -> {out_dir}")

    traces_dir = out_dir / "traces"; traces_dir.mkdir(exist_ok=True)
    open_retrieval_log(out_dir / "retrieval.jsonl")     # per-turn chunk-id + cosine (RAG audit / Stage 2)
    rows = []
    for i, (s, e) in enumerate(units, 1):
        row, result = asyncio.run(run_unit(cfg, s, e, max_turns, routing))
        rows.append(row)
        # belief-trajectory + token/latency sidecar per episode (theta-aware eval kept here)
        (traces_dir / f"s{s}_e{e}.json").write_text(json.dumps(
            {"trace": result["trace"], "eval": result["eval"],
             "summary": result["summary"], "calls": result.get("_calls", [])}, indent=1))
        print(f"  [{i}/{len(units)}] s{s}_e{e}: survival={row['survival_rate']} "
              f"outcome={row['outcome']} r_spatial={row.get('r_spatial')} "
              f"breach_gain={row['real_breach_gain_total']} tok={row['total_tokens']} fb={row['fallback_rate']}")

    close_retrieval_log()
    with open(out_dir / "results.json", "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows))
    with open(out_dir / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"done: {len(rows)} rows -> {out_dir}/results.csv")


if __name__ == "__main__":
    main()
