# Headless GUI Fix — Equivalence Report

Date: 2026-08-27. Scope: presentation-only fix + behavioral equivalence
proof. Development seed `2118334751` only; no research seed (R01-R20) run.

## Fix applied

**File modified: [main.py](../main.py)** (the `env = irsim.make(...)` call,
immediately inside the multi-Scout `try:` block).

**Exact logic changed:**
```python
# before
env = irsim.make(str(runtime_world_file))

# after
env = irsim.make(
    str(runtime_world_file),
    display=render_enabled,
    disable_all_plot=not render_enabled,
)
```

`render_enabled` is the **existing** flag already computed a few lines
earlier (`main.py:94-95`):
```python
render_enabled = (
    False if fast_headless_research_mode else _env_bool("IRSIM_RENDER", True)
)
```
No new configuration system was introduced — the existing
`IRSIM_RENDER` / `FAST_HEADLESS_RESEARCH_MODE` intent now also reaches
IR-SIM's own `display=` / `disable_all_plot=` constructor parameters
(`irsim/env/env_base.py:144-145`), which previously defaulted to
`display=True, disable_all_plot=False` regardless of those flags.

**Old display behavior:** `display` always `True`, `disable_all_plot`
always `False` — IR-SIM selects an interactive backend (`TkAgg` on
Windows) at import time and `env.end()` unconditionally calls
`plt.pause(3.0)` (the `"...closing in 3.00 seconds."` log line), no matter
what this project's own headless flags said.

**New display behavior:**
- Interactive development mode (`render_enabled=True`, i.e. neither
  `FAST_HEADLESS_RESEARCH_MODE=1` nor `IRSIM_RENDER=0`): `display=True,
  disable_all_plot=False` — **identical to IR-SIM's own prior defaults**,
  so interactive/dev usage is provably unchanged (these are literally the
  same default values IR-SIM used before this fix).
- Headless/research mode (`render_enabled=False`, i.e.
  `FAST_HEADLESS_RESEARCH_MODE=1` or `IRSIM_RENDER=0`): `display=False,
  disable_all_plot=True` — no interactive backend touch, no
  `plt.pause()` anywhere, `env.end()` becomes a no-op plot-wise.

`disable_all_plot` only gates matplotlib artist creation on object-add
(`env_base.py:1023/1046`, `obj._init_plot(...)`, `obj._step_plot()`) and the
plot/animation-saving branch inside `render()`/`end()` — it never touches
`self._objects.append(obj)`, `self.build_tree()`, or any physics/collision
state, so it is presentation-only.

## C1 equivalence result — **PASS, 0 behavioral mismatches**

Compared (seed `2118334751`, 300s, `SWARM_EXPERIMENT_MODE=baseline`):
- **Before:** frozen reference commit `2cc0275`, run unpatched (no fix, no
  launcher hack) — reused from the prior Test K session
  (`scratchpad/test_k/before_2cc0275_frozen`).
- **After:** current working tree **with the real fix applied**
  (`scratchpad/headless_fix/c1_fixed_seed2118334751_300s`).

| File | Rows | Result |
| --- | ---: | --- |
| `swarm_trajectory.csv` | 9000 | identical, all columns |
| `swarm_events.csv` | 408 | identical, all columns |
| `robot_energy_timeline.csv` | 9003 | identical on every shared column |
| `nest_energy_timeline.csv` | 0 | identical (no deliveries this run) |
| `swarm_summary.json` | — | 18 diffs, **all** are the already-known additive `working_memory_*` fields (Test K's finding: these fields simply did not exist in the frozen `2cc0275` schema; the fixed run reports them as `0`, correctly reflecting "no WM activity" since WM is off) — **zero diffs on any pre-existing field** |

**Behavioral mismatch count: 0.**

## C2 equivalence result — **PASS, 0 mismatches (including WM markers)**

Compared (seed `2118334751`, 300s, `SWARM_EXPERIMENT_MODE=working_memory`):
- **Before:** current working tree **without** the fix (unpatched,
  pre-existing GUI issue) — reused from the prior old-vs-new session
  (`scratchpad/old_vs_new/c2_current_seed2118334751_300s`).
- **After:** current working tree **with the fix applied**
  (`scratchpad/headless_fix/c2_fixed_seed2118334751_300s`).

| File | Rows | Result |
| --- | ---: | --- |
| `swarm_trajectory.csv` | 9000 | identical, all columns |
| `swarm_events.csv` | 408 | identical, all columns |
| `robot_energy_timeline.csv` | 9003 | identical, all columns |
| `nest_energy_timeline.csv` | 0 | identical |
| `swarm_summary.json` | — | **0 diffs** on any field, including every `working_memory_*` field |

WM markers in the fixed run (verbatim from `swarm_summary.json` /
`working_memory_events.csv`), identical to the pre-fix run:

| Scout | entries | max_size | reads | pops | prunes | resets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 164 | 164 | 0 | 0 | 0 | 0 |
| 1 | 115 | 115 | 0 | 0 | 0 | 0 |
| 2 | 27 | 39 | 283 | 12 | 0 | 0 |

`working_memory_events.csv` op counts: `WM_ADD=315, WM_POP=12, WM_RESET=3`
(no `WM_PRUNE` at this seed/duration — the same as the pre-fix run; 300s at
this seed does not push any Scout past the 300-entry bound). Resource
detection, collection, return-attempt, Nest-reach, and delivery counts are
all identical to the pre-fix run (verified via the identical
`swarm_events.csv`).

**Behavioral mismatch count: 0.**

## GUI state — directly verified

- `"...closing in 3.00 seconds."` — **NOT observed** in either fixed run's
  console output (present in every prior unpatched run's output).
- No interactive matplotlib window — confirmed by `tasklist` showing zero
  lingering `python.exe` processes immediately after each fixed run exits
  (an interactive `TkAgg` window, if opened, keeps the process/window
  alive or visible until explicitly closed; none appeared here).
- Output files (`swarm_summary.json`, `metadata.json`,
  `swarm_trajectory.csv`, `swarm_events.csv`, `robot_energy_timeline.csv`,
  `state_transitions.csv`, `working_memory_events.csv` for C2) were all
  written normally in both fixed runs.
- Interactive/dev mode (`render_enabled=True`) was not re-run interactively
  in this sandboxed, display-less CLI environment, but is provably
  unchanged: `display=True, disable_all_plot=False` are passed in that
  branch, which are **exactly IR-SIM's own pre-fix default values** — the
  call is byte-identical to the unmodified `irsim.make(str(runtime_world_file))`
  in that branch.

## Conclusion

The fix is confirmed presentation-only: **0 behavioral mismatches** across
trajectory, events, energy timelines, resource/harvest events, and every
WM marker (`WM_ADD`, `WM_POP`, `WM_PRUNE`, `WM_RESET`, aggregate WM reads,
maximum WM size) for both C1-condition and C2. `dt`, physics, controller,
sensors, energy model, WM algorithm, RNG sequencing, and termination logic
were not touched — only the `display=` / `disable_all_plot=` keyword
arguments passed to `irsim.make()`.

**HEADLESS GUI FIX EQUIVALENCE: PASS**
