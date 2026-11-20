# FBS implementation verification — 6 Oct 2026

The attached `FBS_Step_by_Step_Guide.pdf` is preserved unchanged. Its algorithms
are useful verification references; rounded printed numbers are not exact
acceptance targets. The repository design specifies complex-voltage change,
not change of voltage magnitudes alone (the PDF uses both descriptions).

## Results

Tight solve tolerance: 1e-12 pu. These are computed results, not measured data.

| Case | Bus voltage magnitudes (pu), bus order | Total active loss (kW) |
|---|---|---:|
| Guide Example 1 | 1.00000000, 0.98984269, 0.98578031 | 3.714508899 |
| Guide Example 2 | 1.00000000, 0.97476646, 0.96626463, 0.96342032, 0.96908306 | 13.963419940 |

Example 2 slack supply is approximately 733.963419940 kW and
477.907271194 kvar. Net bus demand is 720 kW and 450 kvar; active and reactive
supply minus losses reproduce those demands within 1e-8 in engineering units.
At the default 1e-6 tolerance, Example 1 takes 4 sweeps and Example 2 takes 5,
whereas the guide states 7 for Example 2. At 1e-12 they take 7 and 9 respectively.
Iteration counts depend on the stated convergence criterion and tolerance.

Example 1 first sweep gives V2 = 0.99000 - j0.00750 and
V3 = 0.98600 - j0.01050 exactly to the printed precision. The complex-voltage
change is 0.0175 pu. Final line L2 loss is 0.514528843 kW; total loss is
3.714508899 kW. Guide figures such as 0.003715 pu total active loss are rounded.
The guide's final L1 current magnitude is printed as 0.565684 pu; its computed
value is approximately 0.56568366 pu, consistent with that rounding.

## Independent checks

- `python -m unittest discover -s tests -v`: **12 tests passed**.
- All 12 source modules import, including future-module skeletons.
- `python -m Validation.verify_nodal_reference`: independently assembles Ybus
  and solves nonlinear complex-power nodal equations with SciPy. It does not
  copy the FBS sweep equations or use FBS outputs as its initial guess.

| Case | Maximum complex-voltage difference from nodal reference (pu) |
|---|---:|
| Guide three-bus | 8.995e-15 |
| Guide five-bus | 3.808e-14 |
| Prepared five-bus, synthetic test demand | 4.106e-14 |

The last case uses explicit synthetic loads at buses 2–5: P = 100 × bus_id kW,
Q = 40 × bus_id kvar. These inputs are test fixtures, not published load data.
Acceptance threshold for independent comparisons is 1e-10 pu.

The prepared 11 kV feeder and guide 12.66 kV feeder remain separate. No final
IEEE 33-bus/scenario/BESS optimization validation is claimed here.
