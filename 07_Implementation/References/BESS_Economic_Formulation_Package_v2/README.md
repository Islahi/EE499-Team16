# EE499 BESS annual economic objective — reference package

Contents:

1. `BESS_Economic_Objective_Change.md` — full, source-linked mathematical and software change proposal (no GWO/GA equations).
2. `source_excerpt/Sindi_Table3_user_supplied.png` — Table 3 excerpt supplied in the conversation. **Not** the full article.
3. `papers/PAPER_DOWNLOADS.md` — direct public PDF URLs with citations and download instructions.
4. `papers/paper_manifest.json` — machine-readable records and actual download status.
5. `papers/download_papers.py` — Python script to retrieve open-access full-paper PDFs on a network-connected computer.

**Download integrity notice:** Four open-access reference PDFs are included under
`papers/` and recorded in `paper_manifest.json`. The download helper and source
URLs remain available for independent retrieval and verification. The additional
`1-s2.0-S2352467723001984-main.pdf` file is a separately supplied article and is
not one of the four numbered references in the manifest.

The proposal is a documentation artifact only; it does not change the user's original project source code.

## v2 additions

- Section E2 now explicitly lists **all proposed parameters** and marks values as paper-sourced, software defaults, project assumptions, or TBD.
- Section E3 adds **peer-reviewed import/export constraint references**, the PCC transformer apparent-power equation, and four scenario definitions.
- **No numerical import/export limit is asserted as universally valid.** Obtain the PCC rating and interconnection allowance or label test values as assumptions.
- See `papers/GRID_LIMIT_REFERENCES.md` for the additional source links and their evidentiary scope.
