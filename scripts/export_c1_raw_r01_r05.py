"""Lossless file-copy export for the five preliminary C1 advisor runs."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "RAW_EXPORT_C1_R01_R05"
ZIP = ROOT / "results" / "RAW_EXPORT_C1_R01_R05.zip"
RUNS = (
    ("R01", 82784102, ROOT / "results" / "final_c1_canonical_20seed_energy_v1_20260820" / "R01_seed82784102_3600s"),
    ("R02", 98386804, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R02_seed98386804_3600s"),
    ("R03", 358777504, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R03_seed358777504_3600s"),
    ("R04", 385197017, ROOT / "results" / "c1_advisor_preview_parallel_r02_r04_20260820" / "R04_seed385197017_3600s"),
    ("R05", 413997162, ROOT / "results" / "c1_advisor_preview_r05_20260820" / "R05_seed413997162_3600s"),
)
DERIVED = {"summary.json", "swarm_summary.json", "swarm_trip_summary.csv"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def table_shape(path: Path) -> tuple[int | None, int | None]:
    if path.suffix.lower() != ".csv": return None, None
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream); header = next(reader, [])
        return sum(1 for _ in reader), len(header)


def purpose(relative: Path) -> str:
    name = relative.name
    known = {
        "swarm_events.csv": "raw event log: resource, return, Nest, delivery, depletion, recovery",
        "events.csv": "raw simulator event log", "swarm_trajectory.csv": "raw per-step Scout trajectory/state/action observations",
        "trajectory.csv": "raw simulator trajectory", "movement.csv": "raw movement log", "wheel.csv": "raw wheel log",
        "encoder.csv": "raw encoder log", "odometry.csv": "raw odometry log", "imperfection.csv": "raw simulator imperfection log",
        "robot_energy_timeline.csv": "raw per-Scout internal-energy timeline", "nest_energy_timeline.csv": "raw Nest-energy event timeline",
        "metadata.json": "run metadata/configuration", "console_stdout.txt": "raw run standard output", "console_stderr.txt": "raw run standard error",
        "summary.json": "derived run summary", "swarm_summary.json": "derived swarm summary", "swarm_trip_summary.csv": "derived trip summary",
    }
    return known.get(name, "source/config snapshot" if relative.parts[0] == "source_snapshot" else "run output (purpose not classified)")


def main() -> int:
    repair = "--repair" in sys.argv
    if (OUT.exists() or ZIP.exists()) and not repair:
        raise RuntimeError(f"Refusing to overwrite existing export target: {OUT} or {ZIP}")
    OUT.mkdir(parents=True, exist_ok=repair)
    manifest: list[dict] = []; checksums: list[tuple[str, str]] = []; run_counts = {}; seed_notes = []
    for rid, expected_seed, source in RUNS:
        if not source.is_dir(): raise FileNotFoundError(source)
        metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
        actual_seed = metadata.get("configuration", {}).get("decision_random_seed")
        if actual_seed != expected_seed: seed_notes.append(f"{rid}: expected {expected_seed}, metadata has {actual_seed}")
        files = sorted(item for item in source.rglob("*") if item.is_file())
        run_counts[rid] = len(files)
        for original in files:
            rel = original.relative_to(source); exported = OUT / rid / rel
            exported.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(original, exported)
            source_hash, export_hash = sha256(original), sha256(exported)
            if source_hash != export_hash: raise RuntimeError(f"checksum mismatch after copy: {original}")
            rows, columns = table_shape(original)
            manifest.append({"Run": rid, "Seed": actual_seed, "Original_Path": str(original), "Exported_Path": str(exported), "Filename": original.name, "Extension": original.suffix, "File_Size_Bytes": original.stat().st_size, "Row_Count_if_Tabular": rows, "Column_Count_if_Tabular": columns, "Purpose_if_Known": purpose(rel), "Raw_or_Derived": "DERIVED" if original.name in DERIVED else "RAW", "SHA256": source_hash})
            checksums.append((source_hash, str(Path(rid) / rel)))
    fields = list(manifest[0])
    with (OUT / "FILE_MANIFEST.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(manifest)
    with (OUT / "CHECKSUMS_SHA256.txt").open("w", encoding="utf-8", newline="") as stream:
        for digest, rel in checksums: stream.write(f"{digest}  {rel}\n")
    source_text = "\n".join(f"- {rid}: `{source}` (seed `{seed}`)" for rid, seed, source in RUNS)
    (OUT / "README_RAW_EXPORT.md").write_text(f"""# C1 R01–R05 Raw Data Export

This package is a lossless copy of every file inside the five specified original run folders. No simulation was rerun; no rows, timestamps, columns, state/action names, or numeric values were transformed. Derived summaries are retained but marked `DERIVED` in `FILE_MANIFEST.csv`.

## Source folders and expected seeds

{source_text}

## Major data available

- Per-step Scout trajectory/state/action data: `swarm_trajectory.csv`
- Simulator trajectory/movement/wheel/encoder/odometry logs: `trajectory.csv`, `movement.csv`, `wheel.csv`, `encoder.csv`, `odometry.csv`
- Event-level resource, return, Nest, delivery, depletion and recovery data: `swarm_events.csv`
- Robot internal-energy timeline: `robot_energy_timeline.csv`
- Nest energy timeline: `nest_energy_timeline.csv`
- Configuration and source snapshots: `metadata.json`, `source_snapshot/`
- Console diagnostics: `console_stdout.txt`, `console_stderr.txt`

Exact behavioral time budgets can be independently reconstructed from `swarm_trajectory.csv` phase samples, with the caveat that no separate `APPROACH_RESOURCE` phase is logged. Sensor observations are present only to the extent embedded in the per-step trajectory fields; no separate raw ToF/Solar/RSSI sensor timeline file was generated.

Seed verification: {"MISMATCH — " + "; ".join(seed_notes) if seed_notes else "all metadata seeds match the requested mapping."}
""", encoding="utf-8")
    (OUT / "MISSING_DATA_REPORT.md").write_text("""# Missing Data Report

| Metric | Status | Exact source file(s) | Note |
|---|---|---|---|
| A. Effective termination time | AVAILABLE | swarm_events.csv / ROBOT_DEPLETED | Latest depletion event per Run. |
| B. Per-Scout depletion time | AVAILABLE | swarm_events.csv / ROBOT_DEPLETED | Event timestamp per Scout. |
| C. Robot Internal Energy vs time | AVAILABLE | robot_energy_timeline.csv | Per-Scout timeline. |
| D. Nest Energy vs time | AVAILABLE | nest_energy_timeline.csv | Event-level timeline. |
| E. Nest withdrawal events | AVAILABLE | swarm_events.csv, nest_energy_timeline.csv | Event-level. |
| F. Delivery events | AVAILABLE | swarm_events.csv, nest_energy_timeline.csv | Event-level. |
| G. Resource A/B/C detections | AVAILABLE | swarm_events.csv / RESOURCE_LIGHT_DETECTED | Resource ID in detail field. |
| H. Resource collection start/end | PARTIAL | swarm_events.csv / HARVEST_ACTIVE, HARVEST_COMPLETE | Start is repeated activity rather than one transition event. |
| I. Resource collection duration | AVAILABLE | swarm_events.csv / HARVEST_COMPLETE | Completion detail includes elapsed seconds. |
| J. Return attempt start | AVAILABLE | swarm_events.csv / RETURN_HOME_START | Event-level. |
| K. Nest reached | AVAILABLE | swarm_events.csv / NEST_REACHED | Physical arrival confirmation. |
| L. Return success/failure | PARTIAL | swarm_events.csv, robot_energy_timeline.csv | Success is direct; unsuccessful return inferred from started return followed by depletion/no Nest reached. |
| M. Full trajectory | AVAILABLE | swarm_trajectory.csv, trajectory.csv | Per-step data retained in full, including post-depletion rows. |
| N. Distance travelled | AVAILABLE | swarm_trajectory.csv | Cumulative/trip distance columns. |
| O. Behavior/state duration | PARTIAL | swarm_trajectory.csv / phase | EXPLORE, HARVEST, RETURN_HOME, DELIVER, DEPLETED exist; no separate APPROACH_RESOURCE or RECHARGE phase. |
| P. Collision/recovery events | AVAILABLE | swarm_events.csv | Contact/recovery events. |
| Q. Sensor values | PARTIAL | swarm_trajectory.csv | Local sensor fields are available there; no distinct sensor timeline CSV exists. |
| R. Cycle boundaries | AVAILABLE | swarm_events.csv, swarm_trip_summary.csv | SCOUT_START/NEXT_CYCLE_START and trip summary. |
""", encoding="utf-8")
    # Include checksums for package metadata too, after writing it. These are not Run files and do not enter the per-run manifest.
    for name in ("README_RAW_EXPORT.md", "FILE_MANIFEST.csv", "MISSING_DATA_REPORT.md"):
        checksums.append((sha256(OUT / name), name))
    with (OUT / "CHECKSUMS_SHA256.txt").open("a", encoding="utf-8", newline="") as stream:
        for digest, rel in checksums[-3:]: stream.write(f"{digest}  {rel}\n")
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(path for path in OUT.rglob("*") if path.is_file()): archive.write(file, Path(OUT.name) / file.relative_to(OUT))
    with zipfile.ZipFile(ZIP) as archive:
        if archive.testzip() is not None: raise RuntimeError("ZIP integrity check failed")
        expected = {(Path(OUT.name) / p.relative_to(OUT)).as_posix() for p in OUT.rglob("*") if p.is_file()}
        if set(archive.namelist()) != expected: raise RuntimeError("ZIP content mismatch")
    exported_counts = {rid: sum(1 for p in (OUT / rid).rglob("*") if p.is_file()) for rid, _, _ in RUNS}
    if exported_counts != run_counts: raise RuntimeError(f"run file count mismatch: {run_counts} vs {exported_counts}")
    print(json.dumps({"source_file_counts": run_counts, "exported_file_counts": exported_counts, "seed_mismatches": seed_notes, "zip": str(ZIP)}, indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
