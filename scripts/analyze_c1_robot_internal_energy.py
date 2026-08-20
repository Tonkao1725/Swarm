"""Add passive Robot Internal Energy analysis to the C1 five-seed package."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re

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
COLORS = {"0": "#078a16", "1": "#1359e8", "2": "#c000c9"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, values: list[dict]) -> None:
    fields = list(values[0]) if values else [
        "research_id", "seed", "scout_id", "initial_internal_energy", "total_nest_energy_withdrawn",
        "withdrawal_timestamp_s", "energy_after_withdrawal", "depletion_timestamp_s", "cycle_id_at_depletion",
        "phase_at_depletion", "resource_last_harvested", "distance_travelled_at_depletion",
        "returned_to_nest_before_depletion", "final_internal_energy",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(values)


def last_at_or_before(values: list[dict[str, str]], timestamp: float) -> dict[str, str] | None:
    eligible = [row for row in values if float(row["sim_time_s"]) <= timestamp + 1e-9]
    return eligible[-1] if eligible else None


def resource_from_detail(detail: str) -> str:
    match = re.search(r"resource_id=([A-Za-z0-9_-]+)", detail)
    return match.group(1) if match else ""


def main() -> int:
    summaries: list[dict] = []
    details: list[dict] = []
    fig, axes = plt.subplots(5, 1, figsize=(13, 15), sharex=True)
    delivery_points: list[tuple[str, float, float]] = []
    withdrawal_points: list[tuple[str, float, float]] = []
    net_lines: list[tuple[str, list[float], list[float]]] = []
    for axis, (rid, seed, run) in zip(axes, RUNS, strict=True):
        energy = read_csv(run / "robot_energy_timeline.csv")
        events = read_csv(run / "swarm_events.csv")
        trajectory = read_csv(run / "swarm_trajectory.csv")
        nest = read_csv(run / "nest_energy_timeline.csv")
        trajectories = {sid: [row for row in trajectory if row["scout_id"] == sid] for sid in ("0", "1", "2")}
        for sid in ("0", "1", "2"):
            series = [row for row in energy if row["scout_id"] == sid]
            axis.plot([float(row["sim_time_s"]) for row in series], [float(row["internal_energy"]) for row in series], color=COLORS[sid], linewidth=1, label=f"Scout {sid}")
            withdrawals = [row for row in events if row["scout_id"] == sid and row["event"] == "NEST_ENERGY_WITHDRAWAL"]
            depletions = [row for row in events if row["scout_id"] == sid and row["event"] == "ROBOT_DEPLETED"]
            harvests = [row for row in events if row["scout_id"] == sid and row["event"] == "HARVEST_COMPLETE"]
            returns = [row for row in events if row["scout_id"] == sid and row["event"] == "RETURN_HOME_START"]
            reached = [row for row in events if row["scout_id"] == sid and row["event"] == "NEST_REACHED"]
            for row in withdrawals:
                time = float(row["sim_time_s"]); after = float(re.search(r"robot_energy=([0-9.]+)", row["detail"]).group(1)); axis.scatter(time, after, marker="^", color="black", zorder=5)
            for row in harvests: axis.axvline(float(row["sim_time_s"]), color="#F28E2B", alpha=.20, linewidth=1)
            for row in returns: axis.axvline(float(row["sim_time_s"]), color="#8E6C8A", alpha=.20, linewidth=1)
            for row in reached: axis.axvline(float(row["sim_time_s"]), color="#59A14F", alpha=.20, linewidth=1)
            for row in depletions: axis.scatter(float(row["sim_time_s"]), 0, marker="x", color="red", zorder=6)
            depletion = depletions[0] if depletions else None
            depletion_t = float(depletion["sim_time_s"]) if depletion else None
            row_at_depletion = last_at_or_before(trajectories[sid], depletion_t) if depletion_t is not None else None
            completed_harvests = [row for row in harvests if depletion_t is None or float(row["sim_time_s"]) <= depletion_t]
            last_harvest = resource_from_detail(completed_harvests[-1]["detail"]) if completed_harvests else ""
            prior_reach = any(depletion_t is not None and float(row["sim_time_s"]) <= depletion_t for row in reached)
            initial = float(series[0]["internal_energy"])
            final = float(series[-1]["internal_energy"])
            withdrawal_times = [float(row["sim_time_s"]) for row in withdrawals]
            withdrawal_after = [float(re.search(r"robot_energy=([0-9.]+)", row["detail"]).group(1)) for row in withdrawals]
            details.append({"research_id": rid, "seed": seed, "scout_id": sid, "initial_internal_energy": initial,
                            "total_nest_energy_withdrawn": sum(float(re.search(r"withdrawal=([0-9.]+)", row["detail"]).group(1)) for row in withdrawals),
                            "withdrawal_timestamp_s": ";".join(map(str, withdrawal_times)), "energy_after_withdrawal": ";".join(map(str, withdrawal_after)),
                            "depletion_timestamp_s": depletion_t if depletion_t is not None else "", "cycle_id_at_depletion": row_at_depletion["cycle_id"] if row_at_depletion else "",
                            "phase_at_depletion": row_at_depletion["phase"] if row_at_depletion else "", "resource_last_harvested": last_harvest,
                            "distance_travelled_at_depletion": row_at_depletion["cumulative_distance_m"] if row_at_depletion else "",
                            "returned_to_nest_before_depletion": prior_reach, "final_internal_energy": final})
        axis.set_title(f"{rid} — seed {seed}"); axis.set_ylabel("Internal Energy"); axis.set_ylim(-.05, 3.15); axis.grid(alpha=.2); axis.legend(loc="upper right", ncol=3)
        for row in nest:
            if row["event_type"] == "DELIVERY": delivery_points.append((rid, float(row["timestamp"]), float(row["new_energy"])))
            else: withdrawal_points.append((rid, float(row["timestamp"]), float(row["new_energy"])))
        net_lines.append((rid, [float(row["timestamp"]) for row in nest], [float(row["new_energy"]) for row in nest]))
    axes[-1].set_xlabel("Simulated time (s)")
    fig.suptitle("PRELIMINARY C1 — Robot Internal Energy vs Time\n▲ recharge, orange=harvest complete, purple=return start, green=Nest reached, × depletion", y=.995)
    fig.tight_layout(); fig.savefig(OUT / "graphs" / "robot_internal_energy_vs_time.png", dpi=160); plt.close(fig)
    plt.figure(figsize=(11, 5))
    for rid, times, net in net_lines:
        if times: plt.step(times, net, where="post", label=f"{rid} net Nest Energy")
    if delivery_points: plt.scatter([x[1] for x in delivery_points], [x[2] for x in delivery_points], marker="o", color="#E15759", label="Gross delivery event", zorder=5)
    if withdrawal_points: plt.scatter([x[1] for x in withdrawal_points], [x[2] for x in withdrawal_points], marker="^", color="black", label="Robot withdrawal event", zorder=5)
    plt.xlabel("Simulated time (s)"); plt.ylabel("Net Nest Energy"); plt.title("PRELIMINARY C1 — Nest Delivery / Withdrawal Timeline"); plt.legend(); plt.grid(alpha=.2); plt.tight_layout(); plt.savefig(OUT / "graphs" / "nest_delivery_withdrawal_timeline.png", dpi=160); plt.close()
    write_csv(OUT / "robot_energy_depletion_summary.csv", details)
    withdrawn = [row for row in details if float(row["total_nest_energy_withdrawn"]) > 0]
    depletions = [row for row in details if row["depletion_timestamp_s"] != ""]
    lines = ["", "## Robot Internal Energy analysis", "", f"- Total Nest withdrawal across five seeds: `{sum(float(row['total_nest_energy_withdrawn']) for row in details):.6f}` units.", "- Recharge withdrawals (Scout, time s, energy after recharge):"]
    lines += [f"  - {row['research_id']} Scout {row['scout_id']}: t={row['withdrawal_timestamp_s']}; energy={row['energy_after_withdrawal']}" for row in withdrawn] or ["  - None."]
    lines += ["- Depletion events (Scout, time s):"]
    lines += [f"  - {row['research_id']} Scout {row['scout_id']}: t={row['depletion_timestamp_s']} (cycle {row['cycle_id_at_depletion']}, phase {row['phase_at_depletion']})" for row in depletions] or ["  - None."]
    lines += ["- Survival after recharge:"]
    for row in withdrawn:
        withdrawal_t = float(str(row["withdrawal_timestamp_s"]).split(";")[0])
        depletion_t = float(row["depletion_timestamp_s"]) if row["depletion_timestamp_s"] != "" else None
        survived = f"{depletion_t - withdrawal_t:.1f} s" if depletion_t is not None else "not depleted before horizon"
        lines.append(f"  - {row['research_id']} Scout {row['scout_id']}: {survived} after recharge.")
    readme_path = OUT / "README.md"
    existing = readme_path.read_text(encoding="utf-8")
    marker = "\n## Robot Internal Energy analysis\n"
    readme_path.write_text(existing.split(marker, 1)[0].rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
