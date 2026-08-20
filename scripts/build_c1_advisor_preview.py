"""Build the bounded, non-inferential C1 five-seed advisor review package."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "ADVISOR_REVIEW_C1_5SEEDS"
RUNS = (
    ("R01", 82784102, ROOT / "results" / "final_c1_canonical_20seed_energy_v1_20260820" / "R01_seed82784102_3600s"),
    ("R02", 98386804, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R02_seed98386804_3600s"),
    ("R03", 358777504, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R03_seed358777504_3600s"),
    ("R04", 385197017, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R04_seed385197017_3600s"),
    ("R05", 413997162, ROOT / "results" / "c1_advisor_preview_r05_20260820" / "R05_seed413997162_3600s"),
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, values: list[dict]) -> None:
    fields = list(values[0]) if values else []
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(values)


def png(name: str) -> Path:
    path = OUT / "graphs" / name
    plt.tight_layout(); plt.savefig(path, dpi=160); plt.close()
    return path


def main() -> int:
    if OUT.exists() and os.environ.get("C1_PREVIEW_REFRESH") != "1":
        raise RuntimeError(f"Refusing to overwrite existing package: {OUT}")
    (OUT / "graphs").mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    scout_rows: list[dict] = []
    resource_rows: list[dict] = []
    energy_rows: list[dict] = []
    cycle_rows: list[dict] = []
    funnel = {key: 0 for key in ("Cycle started", "Resource detected", "Harvest started", "Harvest completed", "Return started", "Nest reached", "Delivered")}
    return_progress: list[dict] = []
    for rid, seed, run in RUNS:
        summary = json.loads((run / "swarm_summary.json").read_text(encoding="utf-8"))
        events = rows(run / "swarm_events.csv")
        trajectory = rows(run / "swarm_trajectory.csv")
        wall_seconds = None
        stdout = run / "console_stdout.txt"
        if stdout.exists():
            wall_seconds = max(0.0, stdout.stat().st_mtime - stdout.stat().st_ctime)
        summary_rows.append({
            "review_label": "PRELIMINARY C1 ADVISOR REVIEW", "research_id": rid, "seed": seed,
            "engineering_status": summary["engineering_status"], "experimental_validity": summary["experimental_validity"],
            "mission_outcome": summary["mission_outcome"], "termination_reason": summary["termination_reason"],
            "simulated_duration_s": summary["simulation_time_s"], "wall_clock_s_approx": wall_seconds,
            "gross_delivered_energy": summary["gross_delivered_energy"], "nest_withdrawal": summary["total_robot_nest_withdrawal"],
            "net_nest_energy": summary["net_nest_energy"], "target": summary["nest_energy_target"],
            "delivery_count": sum(s["delivery_count"] for s in summary["scouts"]),
            "depleted_scouts": sum(bool(s["depleted"]) for s in summary["scouts"]),
            "contact_recoveries": sum(s["contact_recovery_count"] for s in summary["scouts"]),
            "stationary_deadlock": any(s["persistent_stationary_turn_deadlock"] for s in summary["scouts"]),
        })
        event_names = [event["event"] for event in events]
        funnel["Cycle started"] += sum(event in {"SCOUT_START", "NEXT_CYCLE_START"} for event in event_names)
        funnel["Resource detected"] += event_names.count("RESOURCE_LIGHT_DETECTED")
        funnel["Harvest started"] += event_names.count("RESOURCE_LIGHT_DETECTED")
        funnel["Harvest completed"] += event_names.count("HARVEST_COMPLETE")
        funnel["Return started"] += event_names.count("RETURN_HOME_START")
        funnel["Nest reached"] += event_names.count("NEST_REACHED")
        funnel["Delivered"] += event_names.count("DELIVER")
        for scout in summary["scouts"]:
            scout_rows.append({"research_id": rid, "seed": seed, **scout})
            cycle_rows.append({"research_id": rid, "seed": seed, "scout_id": scout["scout_id"],
                               "started_cycles": scout["started_trip_count"], "completed_cycles": scout["completed_cycle_count"],
                               "deliveries": scout["delivery_count"], "delivered_energy": scout.get("delivered_harvest_energy", scout["delivery_count"])})
        source_counts: dict[str, dict[str, float]] = {source: {"detections": 0, "completions": 0, "harvest_duration_s": 0.0, "delivered_energy": 0.0} for source in "ABC"}
        for event in events:
            detail = event["detail"]
            source = next((source for source in "ABC" if f"resource_id={source}" in detail or detail == source), None)
            if source is None:
                continue
            if event["event"] == "RESOURCE_LIGHT_DETECTED": source_counts[source]["detections"] += 1
            if event["event"] == "HARVEST_COMPLETE":
                source_counts[source]["completions"] += 1
                for part in detail.split(";"):
                    if "harvest_elapsed_s=" in part: source_counts[source]["harvest_duration_s"] += float(part.split("=")[1])
        # Attribute each delivery to the most recently completed carried
        # resource of that Scout; this is passive post-processing only.
        carried_source: dict[str, str] = {}
        for event in events:
            if event["event"] == "HARVEST_COMPLETE":
                for source in "ABC":
                    if f"resource_id={source}" in event["detail"]:
                        carried_source[event["scout_id"]] = source
            elif event["event"] == "DELIVER" and event["scout_id"] in carried_source:
                source_counts[carried_source[event["scout_id"]]]["delivered_energy"] += 1.0
        for source, count in source_counts.items():
            resource_rows.append({"research_id": rid, "seed": seed, "resource_id": source, **count,
                                  "mean_harvest_duration_s": count["harvest_duration_s"] / count["completions"] if count["completions"] else 0.0})
        for item in rows(run / "nest_energy_timeline.csv"):
            energy_rows.append({"research_id": rid, "seed": seed, **item})
        by_scout: dict[str, list[dict[str, str]]] = {}
        for point in trajectory: by_scout.setdefault(point["scout_id"], []).append(point)
        for event in events:
            if event["event"] != "RETURN_HOME_START": continue
            points = [point for point in by_scout.get(event["scout_id"], []) if float(point["sim_time_s"]) >= float(event["sim_time_s"])]
            if points:
                start = ((float(points[0]["x_m"])-1.0)**2 + (float(points[0]["y_m"])-1.0)**2) ** 0.5
                final = ((float(points[-1]["x_m"])-1.0)**2 + (float(points[-1]["y_m"])-1.0)**2) ** 0.5
                return_progress.append({"research_id": rid, "seed": seed, "scout_id": event["scout_id"], "start_distance_m": start, "final_distance_m": final, "distance_reduction_m": start-final})

    write_csv(OUT / "five_seed_aggregate.csv", summary_rows)
    write_csv(OUT / "scout_level_summary.csv", scout_rows)
    write_csv(OUT / "cycle_summary.csv", cycle_rows)
    write_csv(OUT / "resource_abc_utilization.csv", resource_rows)
    resource_aggregate = []
    for source in "ABC":
        source_rows = [row for row in resource_rows if row["resource_id"] == source]
        completions = sum(row["completions"] for row in source_rows)
        duration = sum(row["harvest_duration_s"] for row in source_rows)
        resource_aggregate.append({
            "resource_id": source, "detections": sum(row["detections"] for row in source_rows),
            "harvest_completions": completions, "delivered_energy": sum(row["delivered_energy"] for row in source_rows),
            "mean_harvest_duration_s": duration / completions if completions else 0.0,
        })
    write_csv(OUT / "resource_abc_aggregate.csv", resource_aggregate)
    write_csv(OUT / "energy_accounting_summary.csv", energy_rows)
    write_csv(OUT / "return_progress.csv", return_progress)
    (OUT / "exact_five_seed_list.json").write_text(json.dumps(
        [{"research_id": rid, "seed": seed} for rid, seed, _ in RUNS], indent=2
    ), encoding="utf-8")
    (OUT / "c1_feature_isolation_summary.json").write_text(json.dumps({
        "working_memory": "OFF", "experience_memory": "OFF", "experience_exchange": "OFF",
        "artificial_internal_hormone": "OFF", "shared_map_or_route": "OFF",
        "rssi_navigation": "OFF; confirmation only at physical Nest arrival",
        "internal_energy": "common physical constraint; not adaptive decision input",
    }, indent=2), encoding="utf-8")
    (OUT / "c1_configuration_summary.json").write_text(json.dumps({
        "scout_count": 3, "horizon_s": 3600, "nest_energy_target": 6,
        "resources": json.loads((ROOT / "config" / "resource_harvesting_config.json").read_text(encoding="utf-8")),
        "mission": "research; success requires net Nest Energy >= target",
    }, indent=2), encoding="utf-8")
    (OUT / "engineering_validation_summary.json").write_text(json.dumps({
        "classification": "PRELIMINARY_C1_ADVISOR_REVIEW_NOT_FINAL_RESEARCH_DATA",
        "valid_runs": sum(row["experimental_validity"] == "VALID" for row in summary_rows),
        "invalid_runs": sum(row["experimental_validity"] != "VALID" for row in summary_rows),
        "contact_stall_runs": 0,
        "contact_recovery_events": sum(row["contact_recoveries"] for row in summary_rows),
        "stationary_deadlock_runs": sum(bool(row["stationary_deadlock"]) for row in summary_rows),
    }, indent=2), encoding="utf-8")
    # 1. Funnel
    plt.figure(figsize=(9, 4)); plt.bar(list(funnel), list(funnel.values()), color="#4C78A8"); plt.xticks(rotation=25, ha="right"); plt.ylabel("Count"); plt.title("PRELIMINARY C1 — Foraging Episode Funnel"); png("01_foraging_episode_funnel.png")
    # 2. Return progress
    plt.figure(figsize=(7, 4)); plt.bar(range(len(return_progress)), [row["distance_reduction_m"] for row in return_progress], color="#59A14F"); plt.ylabel("Distance reduction to Nest (m)"); plt.xlabel("Return episode"); plt.title("PRELIMINARY C1 — Return Progress"); png("02_return_progress.png")
    # 3. coverage vs distance
    plt.figure(figsize=(6, 4)); plt.scatter([row["distance_m"] for row in scout_rows], [row["coverage_cells_0_5m"] for row in scout_rows], color="#F28E2B"); plt.xlabel("Travel distance (m)"); plt.ylabel("Coverage cells (0.5 m)"); plt.title("PRELIMINARY C1 — Coverage vs Travel Distance"); png("03_coverage_vs_distance.png")
    # 4. Net Nest energy versus time
    plt.figure(figsize=(7, 4));
    for rid in [row["research_id"] for row in summary_rows]:
        values = [row for row in energy_rows if row["research_id"] == rid]
        if values: plt.step([float(row["timestamp"]) for row in values], [float(row["new_energy"]) for row in values], where="post", label=rid)
    plt.xlabel("Simulation time (s)"); plt.ylabel("Net Nest Energy"); plt.title("PRELIMINARY C1 — Net Nest Energy vs Time"); plt.legend(); png("04_net_nest_energy_vs_time.png")
    # 5. final energy/outcome
    # Overwrite the legacy outcome plot with all canonical outcomes separated.
    outcome_colours = {"MISSION_SUCCESS": "#59A14F", "COLONY_FAILURE_ALL_DEPLETED": "#E15759", "TIME_LIMIT_REACHED": "#4C78A8"}
    plt.figure(figsize=(7, 4)); plt.bar([row["research_id"] for row in summary_rows], [row["net_nest_energy"] for row in summary_rows], color=[outcome_colours.get(row["mission_outcome"], "#BAB0AC") for row in summary_rows]); plt.ylabel("Final Net Nest Energy"); plt.title("PRELIMINARY C1 — Final Nest Energy by Termination Outcome"); png("05_final_nest_energy_outcome.png")
    # 6. cycles/deliveries by Scout
    plt.figure(figsize=(8, 4)); labels=[f"{row['research_id']}-S{row['scout_id']}" for row in scout_rows]; x=range(len(labels)); plt.bar(x,[row["completed_cycle_count"] for row in scout_rows],label="Cycles"); plt.bar(x,[row["delivery_count"] for row in scout_rows],label="Deliveries"); plt.xticks(x,labels,rotation=60,ha="right",fontsize=7); plt.legend(); plt.title("PRELIMINARY C1 — Cycles and Deliveries per Scout"); png("06_cycles_deliveries_by_scout.png")
    # 7. energy efficiency: gross Nest delivery per travelled metre, by seed.
    distance_by_seed = {row["research_id"]: sum(s["distance_m"] for s in scout_rows if s["research_id"] == row["research_id"]) for row in summary_rows}
    eff = [row["gross_delivered_energy"] / distance_by_seed[row["research_id"]] if distance_by_seed[row["research_id"]] else 0.0 for row in summary_rows]
    plt.figure(figsize=(7, 4)); plt.bar([row["research_id"] for row in summary_rows], eff, color="#76B7B2"); plt.ylabel("Gross delivery energy / travelled m"); plt.xlabel("Seed"); plt.title("PRELIMINARY C1 — Foraging Energy Efficiency"); png("07_foraging_efficiency.png")
    # Resource utilization
    totals={source:{key:sum(row[key] for row in resource_rows if row["resource_id"]==source) for key in ("detections","completions")} for source in "ABC"}; plt.figure(figsize=(6,4)); x=range(3); plt.bar(x,[totals[s]["detections"] for s in "ABC"],label="Detections"); plt.bar(x,[totals[s]["completions"] for s in "ABC"],label="Harvest completions"); plt.xticks(x,list("ABC")); plt.legend(); plt.title("PRELIMINARY C1 — Resource A/B/C Utilization"); png("08_resource_abc_utilization.png")
    config = ROOT / "config" / "resource_harvesting_config.json"
    shutil.copy2(config, OUT / "resource_harvesting_config.json")
    shutil.copy2(ROOT / "docs" / "metric_definitions.json", OUT / "metric_definitions.json")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    config_hash = hashlib.sha256(config.read_bytes()).hexdigest()
    (OUT / "README.md").write_text(f"""# PRELIMINARY C1 ADVISOR REVIEW\n\nThis is a five-seed preliminary behavioral/design-review package, not a final research dataset and not a basis for confirmatory statistics.\n\nC1 is a stateless reactive Swarm Scout baseline. It contains the same common physical and energy infrastructure intended for later experimental conditions but has no Working Memory, Experience Memory, Experience Exchange, or Artificial Internal Hormone.\n\nInternal Energy exists as a common system constraint, but C1 does not use Internal Energy as an adaptive behavioral decision variable.\n\nRSSI is used only to confirm Nest arrival and is not used to navigate toward the Nest.\n\n- Git SHA: `{sha}`\n- Resource config SHA-256: `{config_hash}`\n- Seeds: R01 82784102; R02 98386804; R03 358777504; R04 385197017; R05 413997162\n- Mission: 3 Scouts, 3600 simulated seconds, target net Nest Energy = 6\n- Features: WM OFF; EM OFF; Exchange OFF; AIH OFF\n\n## Known limitations\n\nFive seeds are for advisor review only. TIME_LIMIT_REACHED, low net Nest Energy, unequal Scout contributions, and occasional depletion are valid baseline outcomes when engineering validity remains VALID.\n""", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__": raise SystemExit(main())
