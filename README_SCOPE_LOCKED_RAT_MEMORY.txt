RAT-INSPIRED DECISION MEMORY — SCOPE-LOCKED REFACTOR

RESEARCH SCOPE
--------------
Memory types:
    1. Working Memory
    2. Experience Memory

Current valid mode:
    Memory Only

Not implemented yet:
    Rat Exchange
    Directional Memory Exchange
    Artificial Internal Hormone

EXPERIENCE MEMORY BEHAVIOR
--------------------------
Experience Memory stores:
    successful decision sequence
    local decision context
    outbound distance
    total trip distance
    energy cost
    resource score
    confidence
    success count

Experience Memory does not store or execute:
    motor movement distances
    wheel commands
    world coordinates
    map nodes
    graph edges
    loop closure
    global localization

TRIP BEHAVIOR
-------------
Trip 1:
    sensor-driven exploration
    Rat-inspired win-shift in Working Memory
    save successful decision sequence at HOME

Trip 2 and later:
    continue sensor-driven movement
    when a real Decision Point is detected:
        compare local context with Experience
        if context matches:
            select the remembered successful action
        otherwise:
            use Rat-weighted win-shift exploration

Light guidance:
    current strict-LOS light overrides route memory
    because it is direct current sensory evidence

REMOVED
-------
EXPERIENCE_REPLAY phase
successful_route_commands()
executable motor-command replay
replay fallback-to-HOME subsystem
Experience replay audit counters
topology compatibility configuration
topology/loop-closure logger stubs

OVERWRITE FILES
---------------
autonomous_foraging_controller.py
experience_memory.py
working_memory.py
experiment_modes.py
main.py
decision_trace_logger.py

DELETE
------
__pycache__/ (entire folder)
startup_error.txt
old PATCH/TEST report files

VALIDATION
----------
All top-level Python files compile.
Local dependency graph has no missing modules.
Motor-command replay symbols are absent.
Contextual decision recall runtime tests pass.
Working Memory remains Trip-local.
Experience Memory remains persistent across Trips.
