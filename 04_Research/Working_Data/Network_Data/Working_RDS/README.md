# Working radial-distribution workbooks

These 22 workbooks passed the `src_accelerated` compatibility audit on
2026-10-22. For this audit, **working** means that the workbook:

1. is recognized by `network_loader.py`;
2. passes the connected, single-slack, radial-topology checks; and
3. produces a converged static FBS base-case solution.

It does not mean that every case satisfies the study voltage constraint or that
the published benchmark result has been independently reproduced. Several
converged cases have a minimum voltage below 0.95 pu. See
`07_Implementation/rds_workbook_audit.csv` for the bus count, iteration count,
minimum voltage and calculated loss of every case.

The rejected or non-network workbooks remain in the parent `Network_Data`
folder. Their known limitations are documented in
`07_Implementation/src_accelerated/docs/README_network_loader.md`.
