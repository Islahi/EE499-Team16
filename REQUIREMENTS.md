# Requirements Summary

> This is a navigation/summary layer, **not a replacement for the original requirements**. For a major technical decision, inspect the original files under `01_Official/`.

## Authority sources

1. `01_Official/Project_Description/Project Description.docx` — official project brief for Project 36
2. `01_Official/Course_Guidance/EE499 SDP Guidelines v5.pdf` — course process/tasks and assessment expectations
3. `01_Official/Course_Guidance/EE499 SDP Schedule Spring 2026 Intake v1.pdf` — official schedule; Term 2 deadlines are TBD in the supplied version
4. `01_Official/Course_Guidance/EE499_Final_Report_Template_v2025_Fall.docx` — report template

If these conflict with advisor/instructor feedback or team decisions, flag and discuss the conflict; do not silently resolve it.

## Official project brief — core technical intent

The project brief calls for a comprehensive optimization framework for Battery Storage System planning in renewable-dominant power systems.

### Optimization structure

The brief explicitly describes a **two-stage stochastic programming approach**:

- **First stage:** strategic planning decisions including battery location, capacity, and type under uncertainty.
- **Second stage:** detailed operational decisions with feasible/efficient hourly operation over a year.

### Uncertainty

Uncertainty in renewable generation and electricity demand should be represented using historical weather/load data and methods such as:

- Monte Carlo simulation,
- probabilistic forecasting,
- and predictive/statistical analysis across hourly, daily, and seasonal variation.

### Battery representation

Model technical and economic characteristics including:

- energy capacity,
- charge/discharge rates,
- efficiency,
- degradation,
- CAPEX,
- operating cost,
- maintenance cost.

### Performance metrics

Define and validate metrics for:

- load-shedding reduction,
- renewable-curtailment minimization,
- system reliability,
- overall cost-effectiveness.

### Operational feasibility

Evaluate solutions against realistic constraints such as:

- supply-demand/grid stability,
- power-flow limits,
- reserve requirements.

### Validation

Choose a case study and validate the framework against baseline scenarios and/or existing benchmarks.

### Environmental/economic assessment

Assess:

- emission reductions,
- renewable-curtailment effects,
- battery investment cost versus long-term resilience/renewable-integration benefits.

### Extensibility

The framework should be adaptable to future storage technologies and possible sector coupling/extensions.

### Documentation

Document assumptions, constraints, methodology, results, and adaptation guidance sufficiently for transparency and reproducibility.

## Official final-product components

The project description lists:

1. Optimization model
2. Case study analysis
3. Quantitative performance metrics
4. Decision-support tool
5. Report and complete documentation

## Term 2 course tasks

The EE499 guidelines require Term 2 to continue the baseline design, implement major final-product components, conduct trial-and-error toward the final technical design, design/conduct validation experiments, and document the work in the final report. The guidelines also require at least six documented team/advisor meetings during Term 2.
