RAT-INSPIRED COLLECTIVE FORAGING REFACTOR

Core memories
-------------
1. Working Memory: current Trip only
2. Experience Memory: successful route experience across Trips

Explicitly removed from runtime
-------------------------------
- TopologicalMap
- persistent nodes and edges
- PendingTraversal
- loop closure
- frontier routing
- graph cycle reasoning

Decision points are trip-local landmarks only. They are not connected into a
world map. Experience is a successful sequence of decisions and route commands,
with distance, energy cost, resource score, success count, and confidence.

Files to overwrite
------------------
- autonomous_foraging_controller.py
- working_memory.py
- experience_memory.py
- main.py

Files to delete
---------------
- topological_map.py
- junction_controller.py
- __pycache__/ (entire folder)

All other hardware, sensor, motion, HUD, logging, world, and experiment-mode
files remain in place.
