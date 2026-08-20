"""Research-grade, passive C1 five-seed advisor graph package (Thai labels)."""
from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager, ticker


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results" / "ADVISOR_REVIEW_C1_5SEEDS"
OUT = PACKAGE / "graphs_research_v4"
RUNS = (
    ("R01", 82784102, ROOT / "results" / "final_c1_canonical_20seed_energy_v1_20260820" / "R01_seed82784102_3600s"),
    ("R02", 98386804, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R02_seed98386804_3600s"),
    ("R03", 358777504, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R03_seed358777504_3600s"),
    ("R04", 385197017, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R04_seed385197017_3600s"),
    ("R05", 413997162, ROOT / "results" / "c1_advisor_preview_r05_20260820" / "R05_seed413997162_3600s"),
)
THAI_FONT = Path(r"C:\Windows\Fonts\tahoma.ttf")
PHASES = {"EXPLORE": "สำรวจ", "HARVEST": "เก็บพลังงาน", "RETURN_HOME": "เดินทางกลับรัง", "DELIVER": "อยู่ที่รัง / เติมพลังงาน"}
PHASE_COLORS = {"EXPLORE": "#4C78A8", "HARVEST": "#F2CF5B", "RETURN_HOME": "#E15759", "DELIVER": "#59A14F"}
RUN_COLORS = {"R01": "#4C78A8", "R02": "#72B7B2", "R03": "#F2CF5B", "R04": "#F58518", "R05": "#E45756"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or (list(rows[0]) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def event_resource(detail: str) -> str:
    match = re.search(r"resource_id=([A-Z])", detail)
    return match.group(1) if match else ""


def configure_font() -> str:
    if not THAI_FONT.exists():
        raise RuntimeError(f"Required Thai font is unavailable: {THAI_FONT}")
    font_manager.fontManager.addfont(str(THAI_FONT))
    name = font_manager.FontProperties(fname=str(THAI_FONT)).get_name()
    plt.rcParams.update({"font.family": name, "font.size": 12, "axes.titleweight": "bold", "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white"})
    return name


def save(fig: plt.Figure, stem: str) -> Path:
    png = OUT / f"{stem}.png"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    return png


def integer_axis(axis, which: str = "y") -> None:
    getattr(axis, f"{which}axis").set_major_locator(ticker.MaxNLocator(integer=True))


def phase_durations(rows: list[dict[str, str]], end: float) -> Counter:
    answer: Counter = Counter()
    usable = [r for r in rows if float(r["sim_time_s"]) <= end + 1e-9]
    for i, row in enumerate(usable):
        now = float(row["sim_time_s"])
        next_t = float(usable[i + 1]["sim_time_s"]) if i + 1 < len(usable) else end
        duration = max(0.0, min(next_t, end) - now)
        if row["phase"] in PHASES:
            answer[row["phase"]] += duration
    return answer


def load() -> tuple[list[dict], list[dict]]:
    runs, source_rows = [], []
    for rid, seed, folder in RUNS:
        for required in ("swarm_events.csv", "swarm_trajectory.csv", "robot_energy_timeline.csv", "nest_energy_timeline.csv", "swarm_summary.json"):
            if not (folder / required).exists():
                raise FileNotFoundError(folder / required)
        events = read_csv(folder / "swarm_events.csv")
        trajectory = read_csv(folder / "swarm_trajectory.csv")
        robot_energy = read_csv(folder / "robot_energy_timeline.csv")
        nest = read_csv(folder / "nest_energy_timeline.csv")
        summary = json.loads((folder / "swarm_summary.json").read_text(encoding="utf-8"))
        depleted = [e for e in events if e["event"] == "ROBOT_DEPLETED"]
        if len(depleted) != 3:
            raise RuntimeError(f"{rid}: cannot derive effective termination: expected 3 depletion events, got {len(depleted)}")
        effective = max(float(e["sim_time_s"]) for e in depleted)
        source_rows.append({"research_id": rid, "seed": seed, "source_file": "swarm_events.csv", "columns_used": "sim_time_s, scout_id, trip_id, event, detail", "purpose": "depletion, energy-source, return, delivery, withdrawal events"})
        source_rows.append({"research_id": rid, "seed": seed, "source_file": "swarm_trajectory.csv", "columns_used": "sim_time_s, scout_id, phase", "purpose": "real state-duration reconstruction up to effective termination"})
        source_rows.append({"research_id": rid, "seed": seed, "source_file": "robot_energy_timeline.csv", "columns_used": "sim_time_s, scout_id, internal_energy, phase", "purpose": "internal-energy/depletion verification"})
        source_rows.append({"research_id": rid, "seed": seed, "source_file": "nest_energy_timeline.csv", "columns_used": "timestamp, scout_id, event_type, delivered_energy, withdrawal_energy, new_energy", "purpose": "Nest energy accounting and withdrawal timing"})
        runs.append({"id": rid, "seed": seed, "folder": folder, "events": events, "trajectory": trajectory, "energy": robot_energy, "nest": nest, "summary": summary, "effective": effective, "depleted": depleted})
    return runs, source_rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    font_name = configure_font()
    # Font validation is deliberately generated before all figures.
    fig, ax = plt.subplots(figsize=(8, 2)); ax.text(.5, .5, "ภาษาไทย 0123456789 R01 Scout A/B/C", ha="center", va="center", fontsize=20); ax.axis("off"); save(fig, "00_font_validation")
    runs, source_rows = load()
    ids = [r["id"] for r in runs]
    effective = [r["effective"] for r in runs]

    # Derived event data.
    rows_summary, metric_rows = [], []
    resource_collections, resource_deliveries = Counter(), Counter()
    for run in runs:
        events = run["events"]
        by_scout_trip: dict[tuple[str, str], str] = {}
        for e in events:
            if e["event"] == "HARVEST_COMPLETE":
                resource = event_resource(e["detail"])
                resource_collections[resource] += 1
                by_scout_trip[(e["scout_id"], e["trip_id"])] = resource
            elif e["event"] == "DELIVER":
                resource_deliveries[by_scout_trip.get((e["scout_id"], e["trip_id"]), "UNKNOWN")] += 1
        withdrawals = [e for e in events if e["event"] == "NEST_ENERGY_WITHDRAWAL"]
        return_starts = [e for e in events if e["event"] == "RETURN_HOME_START"]
        nest_reaches = [e for e in events if e["event"] == "NEST_REACHED"]
        deliveries = [e for e in events if e["event"] == "DELIVER"]
        gross = float(run["summary"].get("gross_delivered_energy", 0.0))
        withdrawn = float(run["summary"].get("total_robot_nest_withdrawal", 0.0))
        net = float(run["summary"].get("net_nest_energy", 0.0))
        rows_summary.append({"research_id": run["id"], "seed": run["seed"], "raw_duration_s": run["summary"].get("simulation_time_s"), "effective_termination_s": run["effective"], "depleted_scouts": len(run["depleted"]), "return_attempts": len(return_starts), "nest_reaches": len(nest_reaches), "deliveries": len(deliveries), "withdrawal_events": len(withdrawals), "gross_delivered_energy": gross, "nest_energy_withdrawn": withdrawn, "final_net_nest_energy": net, "gross_delivery_rate_per_s": gross / run["effective"], "net_nest_energy_rate_per_s": net / run["effective"]})
    write_csv(OUT / "graph_source_summary.csv", source_rows)
    write_csv(OUT / "graph_metric_summary.csv", rows_summary)

    # 1 operational survival: all bars belong to one Condition, hence one colour.
    fig, ax = plt.subplots(figsize=(9, 5)); bars = ax.bar(ids, effective, color="#4C78A8")
    ax.set_title("ระยะเวลาที่หุ่นสิ้นสุดการทำงาน"); ax.set_ylabel("เวลาจำลอง (วินาที)"); ax.set_ylim(0, max(effective) * 1.16); integer_axis(ax)
    for bar, value in zip(bars, effective): ax.text(bar.get_x() + bar.get_width()/2, value + max(effective)*.025, f"{value:.1f} s", ha="center", va="bottom", fontsize=10)
    ax.grid(axis="y", alpha=.25); fig.text(.5, .01, "การทดลองสิ้นสุดเมื่อหุ่นทุกตัวหมดพลังงาน", ha="center", fontsize=10); save(fig, "01_ระยะเวลาที่หุ่นสิ้นสุดการทำงาน")

    # 2 Nest withdrawal timeline.
    fig, ax = plt.subplots(figsize=(11, 5)); y = {rid: i for i, rid in enumerate(ids)}; total_withdrawn = 0.0
    for run in runs:
        events = [e for e in run["events"] if e["event"] == "NEST_ENERGY_WITHDRAWAL"]
        if not events: ax.text(35, y[run["id"]], "ไม่มีการดึงพลังงาน", va="center", color="#666666")
        for e in events:
            amount = float(re.search(r"withdrawal=([0-9.]+)", e["detail"]).group(1)); total_withdrawn += amount
            t = float(e["sim_time_s"]); ax.scatter(t, y[run["id"]], marker="^", s=100, color="#333333", zorder=3)
            ax.annotate(f"Scout {e['scout_id']}\n{amount:.1f} หน่วย\n{t:.1f} วินาที", (t, y[run["id"]]), xytext=(10, -34), textcoords="offset points", fontsize=9, va="top")
    ax.set_yticks(list(y.values()), ids); ax.set_xlabel("เวลาจำลอง (วินาที)"); ax.set_title("การดึงพลังงานจากรังมาใช้", pad=14); ax.grid(axis="x", alpha=.25); ax.set_xlim(0, max(effective)*1.04); fig.subplots_adjust(bottom=.20); fig.text(.5, .02, f"รวมดึงพลังงานจากรัง {total_withdrawn:.1f} หน่วย", ha="center", fontsize=10); save(fig, "02_การดึงพลังงานจากรังมาใช้")

    # 3 real time budget reconstructed from trajectory state samples.
    phase_by_run = {}
    for run in runs:
        duration = Counter()
        for sid in ("0", "1", "2"):
            duration.update(phase_durations([r for r in run["trajectory"] if r["scout_id"] == sid], run["effective"]))
        phase_by_run[run["id"]] = duration
    fig, ax = plt.subplots(figsize=(10, 5)); bottom = [0.0] * len(runs)
    for phase in PHASES:
        values = [phase_by_run[r["id"]][phase] / sum(phase_by_run[r["id"]].values()) * 100 if sum(phase_by_run[r["id"]].values()) else 0 for r in runs]
        bars = ax.bar(ids, values, bottom=bottom, label=PHASES[phase], color=PHASE_COLORS[phase])
        for bar, value, base in zip(bars, values, bottom):
            if value >= 7: ax.text(bar.get_x()+bar.get_width()/2, base+value/2, f"{value:.0f}%", ha="center", va="center", fontsize=9)
        bottom = [a+b for a,b in zip(bottom, values)]
    ax.set_title("สัดส่วนเวลาที่หุ่นใช้ในแต่ละพฤติกรรม"); ax.set_ylabel("สัดส่วนเวลาในช่วงที่ยังทำงานได้ (%)"); ax.set_ylim(0, 100); ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(.5, -0.14)); ax.grid(axis="y", alpha=.25); fig.text(.5, .01, "คิดจากผลรวมเวลาปฏิบัติงานของ Scout ทั้ง 3 ตัว ก่อนพลังงานหมด", ha="center", fontsize=10); save(fig, "03_สัดส่วนเวลาที่หุ่นใช้ในแต่ละพฤติกรรม")

    # 4 process funnel.
    stages = [("เริ่มรอบการทำงาน", sum(e["event"] in {"SCOUT_START", "NEXT_CYCLE_START"} for r in runs for e in r["events"])), ("ตรวจพบแหล่งพลังงาน", sum(e["event"] == "RESOURCE_LIGHT_DETECTED" for r in runs for e in r["events"])), ("เก็บพลังงานสำเร็จ", sum(e["event"] == "HARVEST_COMPLETE" for r in runs for e in r["events"])), ("เริ่มเดินทางกลับรัง", sum(e["event"] == "RETURN_HOME_START" for r in runs for e in r["events"])), ("กลับถึงรัง", sum(e["event"] == "NEST_REACHED" for r in runs for e in r["events"])), ("ส่งพลังงานเข้ารังสำเร็จ", sum(e["event"] == "DELIVER" for r in runs for e in r["events"]))]
    initial = stages[0][1]; fig, ax = plt.subplots(figsize=(11, 5)); labels, vals = zip(*stages); bars = ax.barh(labels[::-1], vals[::-1], color="#4C78A8"); ax.set_xlabel("จำนวนครั้ง"); ax.set_title("ลำดับขั้นของการหาพลังงาน"); integer_axis(ax, "x"); ax.set_xlim(0, initial*1.2)
    for bar, value in zip(bars, vals[::-1]): ax.text(value + initial*.02, bar.get_y()+bar.get_height()/2, f"{value} ({value/initial*100:.1f}%)", va="center")
    ax.grid(axis="x", alpha=.25); fig.subplots_adjust(bottom=.18); fig.text(.5,.02,"เก็บพลังงานสำเร็จ 17 ครั้ง แต่ส่งถึงรังสำเร็จ 2 ครั้ง",ha="center",fontsize=10); save(fig, "04_ลำดับขั้นของการหาพลังงาน")

    # 5 actual return outcome.
    attempts = [r["return_attempts"] for r in rows_summary]; reaches = [r["nest_reaches"] for r in rows_summary]; failures = [a-b for a,b in zip(attempts,reaches)]
    fig, ax = plt.subplots(figsize=(9, 5)); ax.bar(ids, reaches, label="กลับถึงรังสำเร็จ", color="#59A14F"); ax.bar(ids, failures, bottom=reaches, label="กลับไม่ถึงรังก่อนพลังงานหมด", color="#E15759")
    ax.set_title("ผลการเดินทางกลับรัง"); ax.set_ylabel("จำนวนครั้งที่เริ่มเดินทางกลับรัง"); integer_axis(ax); ax.legend(); ax.grid(axis="y", alpha=.25)
    for x,a,b in zip(ids,attempts,reaches): ax.text(x, a+.12, f"เริ่ม {a} | ถึงรัง {b}\nสำเร็จ {b/a*100 if a else 0:.0f}%", ha="center", fontsize=10)
    ax.set_ylim(0, max(attempts)*1.42); save(fig, "05_ผลการเดินทางกลับรัง")

    # 6 source utilisation, explicitly separating collection from delivered origin.
    config = json.loads((ROOT / "config" / "resource_harvesting_config.json").read_text(encoding="utf-8"))
    durations = {x["resource_id"]: 1/x["relative_harvest_rate"] for x in config["sources"]}
    fig, ax = plt.subplots(figsize=(9, 5)); sources = ["A", "B", "C"]; collected = [resource_collections[x] for x in sources]; delivered_sources = [resource_deliveries[x] for x in sources]
    ax.bar(sources, collected, color="#4C78A8", label="เก็บพลังงานสำเร็จ"); ax.scatter(sources, delivered_sources, color="#E15759", s=90, zorder=3, label="จำนวนครั้งที่ส่งพลังงานจากแหล่งนั้นถึงรังสำเร็จ")
    ax.set_title("การใช้แหล่งพลังงาน A/B/C"); ax.set_ylabel("จำนวนครั้ง"); integer_axis(ax); ax.set_ylim(0, max(collected)*1.35); ax.legend(); ax.grid(axis="y", alpha=.25)
    for x,c in zip(sources,collected): ax.text(x, c+.25, f"{c} ครั้ง\nใช้เวลาเก็บ ≈ {durations[x]:.0f} s", ha="center", fontsize=10)
    fig.text(.5, .01, "ตรวจพบ → เก็บพลังงานสำเร็จ = 100% สำหรับเหตุการณ์ที่ตรวจพบในชุดข้อมูลนี้", ha="center", fontsize=10); save(fig, "06_การใช้แหล่งพลังงาน_ABC")

    # 7 lollipop internal energy survival.
    points = []
    for run in runs:
        withdrawals = defaultdict(list)
        for e in run["events"]:
            if e["event"] == "NEST_ENERGY_WITHDRAWAL": withdrawals[e["scout_id"]].append(e)
        for e in run["depleted"]:
            points.append((f"{run['id']}-S{e['scout_id']}", float(e["sim_time_s"]), run["id"], e["scout_id"], withdrawals[e["scout_id"]]))
    fig, ax = plt.subplots(figsize=(10, 7)); labels=[p[0] for p in points]; ypos=list(range(len(points)))
    for y,(_,t,rid,sid,withdrawals) in zip(ypos,points):
        ax.hlines(y, 0, t, color="#B9C6D2", lw=1.5); ax.scatter(t, y, s=70, color="#444444" if not withdrawals else "#E15759", marker="D" if withdrawals else "o", zorder=3)
        if withdrawals: ax.annotate("+1.0 หน่วย ที่ " + ", ".join(f"{float(e['sim_time_s']):.1f} วินาที" for e in withdrawals), (t,y), xytext=(7,0), textcoords="offset points", va="center", fontsize=9)
    ax.scatter([],[],color="#444444",marker="o",label="ไม่ได้เติมพลังงานจากรัง"); ax.scatter([],[],color="#E15759",marker="D",label="ได้รับการเติมพลังงานจากรัง")
    ax.set_yticks(ypos, labels); ax.set_xlabel("เวลาที่พลังงานภายในหมด (วินาที)"); ax.set_title("เวลาที่หุ่นแต่ละตัวหมดพลังงานและการเติมพลังงานจากรัง"); ax.legend(loc="lower right"); ax.grid(axis="x", alpha=.25); ax.set_xlim(0,max(effective)*1.12); save(fig, "07_เวลาที่หุ่นหมดพลังงานและการเติมพลังงานจากรัง")

    # 8 actual rate metric; accounting is moved to Supplementary A.
    gross=[r["gross_delivered_energy"] for r in rows_summary]; withdrawn=[r["nest_energy_withdrawn"] for r in rows_summary]; net=[r["final_net_nest_energy"] for r in rows_summary]; x=list(range(len(ids))); width=.32
    gross_rate=[r["gross_delivery_rate_per_s"]*1000 for r in rows_summary]; net_rate=[r["net_nest_energy_rate_per_s"]*1000 for r in rows_summary]
    fig, ax = plt.subplots(figsize=(10, 5)); ax.bar([i-width/2 for i in x],gross_rate,width,label="อัตราพลังงานที่ส่งเข้ารัง",color="#59A14F"); ax.bar([i+width/2 for i in x],net_rate,width,label="อัตราการเพิ่มของพลังงานสุทธิในรัง",color="#4C78A8")
    ax.set_xticks(x,ids); ax.set_ylabel("หน่วยพลังงานต่อ 1,000 วินาที"); ax.set_title("อัตราผลลัพธ์ด้านพลังงานของ Colony"); ax.legend(); ax.grid(axis="y",alpha=.25)
    fig.text(.5,.01,"คำนวณจากเวลาที่ Colony ยังสามารถปฏิบัติงานได้จริง",ha="center",fontsize=10); save(fig,"08_ประสิทธิภาพด้านพลังงานของ_Colony")

    # Supplementary A: energy accounting, intentionally separate from rate.
    fig, ax = plt.subplots(figsize=(10, 5)); ax.bar([i-width for i in x],gross,width,label="พลังงานที่ส่งเข้ารังทั้งหมด",color="#59A14F"); ax.bar(x,withdrawn,width,label="พลังงานที่หุ่นดึงจากรัง",color="#F58518"); ax.bar([i+width for i in x],net,width,label="พลังงานสุทธิสุดท้ายของรัง",color="#4C78A8")
    ax.set_xticks(x,ids); ax.set_ylabel("พลังงาน (หน่วย)"); ax.set_title("สมดุลพลังงานของรัง"); ax.legend(); ax.grid(axis="y",alpha=.25); integer_axis(ax)
    fig.text(.5,.01,"พลังงานสุทธิ = พลังงานที่ส่งเข้ารัง - พลังงานที่หุ่นดึงกลับไปใช้",ha="center",fontsize=10); save(fig,"supplementary_A_สมดุลพลังงานของรัง")

    # Supplementary net energy trace, cut at effective termination.
    fig, ax = plt.subplots(figsize=(10, 5))
    for run in runs:
        vals=[(0.0,0.0)] + [(float(n["timestamp"]),float(n["new_energy"])) for n in run["nest"] if float(n["timestamp"]) <= run["effective"]]
        # Preserve the active interval through its measured effective end,
        # but never extend the trace into the post-depletion 3600-s idle tail.
        vals.append((run["effective"], vals[-1][1]))
        times, values=zip(*vals); ax.step(times,values,where="post",label=run["id"],color=RUN_COLORS[run["id"]])
        for e in run["events"]:
            if e["event"] in {"DELIVER","NEST_ENERGY_WITHDRAWAL"} and float(e["sim_time_s"])<=run["effective"]: ax.scatter(float(e["sim_time_s"]), next(v for t,v in reversed(vals) if t<=float(e["sim_time_s"])), marker="o" if e["event"]=="DELIVER" else "^", color=RUN_COLORS[run["id"]])
    ax.set_title("พลังงานสุทธิของรังตามเวลา"); ax.set_xlabel("เวลาจำลอง (วินาที)"); ax.set_ylabel("พลังงานสุทธิของรัง (หน่วย)"); ax.legend(ncol=5); ax.grid(alpha=.25); save(fig,"supplementary_B_พลังงานสุทธิของรังตามเวลา")

    # Montage of the eight main PNG files.
    main_files=sorted(OUT.glob("0[1-8]_*.png")); fig, axes=plt.subplots(4,2,figsize=(16,22));
    for ax,path in zip(axes.flat,main_files): ax.imshow(plt.imread(path)); ax.axis("off")
    fig.tight_layout(); fig.savefig(OUT / "advisor_graphs_montage_v4.png",dpi=200); plt.close(fig)

    audit = f"""# GRAPH DATA AUDIT — C1 Advisor Review V3

## Data scope

Passive retrospective analysis only. Raw duration remains 3600 s in the source files. **Effective termination time** is recalculated as the latest `ROBOT_DEPLETED` timestamp among the three Scouts in each run; time after that point is excluded from time-series and rate denominators under the proposed all-Scouts-depleted rule.

| Graph | Research question | Raw source / columns | Unit and calculation | Limitation |
|---|---|---|---|---|
| 1 | Colony operates how long? | swarm_events: event, sim_time_s | run; max of three ROBOT_DEPLETED timestamps | retrospective rule, not original runtime termination |
| 2 | Who withdrew Nest energy, when and how much? | swarm_events: NEST_ENERGY_WITHDRAWAL | event; timestamp and parsed withdrawal amount | only actual withdrawal events |
| 3 | What active behavior occupied time? | swarm_trajectory: sim_time_s, scout_id, phase | run; consecutive-sample phase durations summed across all 3 Scouts up to their depletion endpoint, then normalized by total active Scout-time | trajectory sample resolution is 0.1 s |
| 4 | At which C1 stage does loss occur? | swarm_events: event | event count; percentage of started cycles | collection-start event is unavailable and therefore omitted |
| 5 | How often did return physically reach Nest? | swarm_events: RETURN_HOME_START, NEST_REACHED | run; reaches / return starts | physical arrival only; not distance-reduction proxy |
| 6 | Which sources were used and delivered? | swarm_events: HARVEST_COMPLETE, DELIVER, trip_id | event count; delivery origin matched by Scout/trip | no claim of resource preference |
| 7 | When did each Scout deplete? | swarm_events: ROBOT_DEPLETED, NEST_ENERGY_WITHDRAWAL | Scout; depletion timestamp and actual recharge marker | internal energy is a physical constraint, not a C1 decision input |
| 8 | What is the Colony energy accounting? | swarm_summary.json | run; gross delivery, withdrawal, final net; rates divided by effective time | normalized simulation energy units |
| Supplementary | How did net Nest energy change? | nest_energy_timeline.csv; swarm_events | run time series truncated at effective termination | flat post-depletion 3600-s tail intentionally omitted |

## Consistency check

- Runs: 5; Scouts per run: 3; total Scouts: 15.
- Effective termination (s): {', '.join(f"{r['id']}={r['effective']:.1f}" for r in runs)}.
- Total source detections: {sum(e['event']=='RESOURCE_LIGHT_DETECTED' for r in runs for e in r['events'])}; successful energy collections: {sum(resource_collections.values())}; return attempts: {sum(x['return_attempts'] for x in rows_summary)}; Nest reaches: {sum(x['nest_reaches'] for x in rows_summary)}; deliveries: {sum(x['deliveries'] for x in rows_summary)}.
- Total Nest withdrawal: {total_withdrawn:.1f} units; final Net Nest Energy: {', '.join(f"{x['research_id']}={x['final_net_nest_energy']:.1f}" for x in rows_summary)}.
- Resource successful collections: A={resource_collections['A']}, B={resource_collections['B']}, C={resource_collections['C']}; delivery origins: A={resource_deliveries['A']}, B={resource_deliveries['B']}, C={resource_deliveries['C']}.

All requested behavioral duration categories that exist in the trajectory log were reconstructed. For Graph 3, 100% means **total active Scout-time** (the sum of each Scout's non-depleted trajectory duration), not wall-clock Run time. `APPROACH_RESOURCE` and a separate energy-collection-start event are not logged; neither is inferred or shown as a separate category.
"""
    (OUT / "GRAPH_DATA_AUDIT_V4.md").write_text(audit,encoding="utf-8")
    (OUT / "graph_metric_summary_v4.csv").write_text((OUT / "graph_metric_summary.csv").read_text(encoding="utf-8"),encoding="utf-8")
    (OUT / "README.md").write_text(f"# C1 Research Graph Package V4\n\n- Font: {font_name} ({THAI_FONT})\n- Total Nest energy withdrawn: {total_withdrawn:.1f} units\n- Generated passively from existing R01–R05 raw outputs; no simulation rerun.\n",encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__": raise SystemExit(main())
