STRICT RAT WIN-SHIFT FIX

OVERWRITE
---------
autonomous_foraging_controller.py

CONFIRMED FROM run_20260806_211440_042881
-----------------------------------------
Seed 920265301 remained in Trip 1 for more than 2,000 simulation
seconds, travelled about 196.48 m, and made 122 decisions without
finding Energy.

The repeated region involved D017, D019 and D022. Visit counts were
increasing correctly, but the old probability rule still allowed a
repeatedly used branch to be selected. Once all branches had similar
counts, the same local cycle could restart indefinitely.

NEW RULE
--------
1. Find the minimum current-Trip visit count among open actions.
2. Only actions with that minimum count remain eligible.
3. On a tie, avoid the action chosen on the previous visit when another
   equally fresh action exists.
4. Random selection and Experience bonus operate only inside the
   eligible action set.

This is Working-Memory win-shift. It is not a map, planner or SLAM.

EXPECTED DECISION LOG
---------------------
Each action now shows:
    trip=
    eligible=
    avoid_last=
    exp=
    p=

Non-eligible repeated actions have:
    eligible=0
    p=0.0%
