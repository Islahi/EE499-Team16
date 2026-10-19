# Experimental accelerated implementation

This folder is an isolated copy of the implementation. The stable `src` package
and its launcher are unchanged. Run this copy with:

```powershell
python -m pip install -r .\07_Implementation\requirements-accelerated.txt
python .\07_Implementation\examples\run_accelerated_ui.py
```

The Settings dialog adds two controls:

- **Power-flow backend**: Python reference, NumPy arrays, Numba compiled CPU, or
  experimental CuPy CUDA GPU.
- **GWO CPU workers**: evaluates different candidate batteries in separate
  processes. Start with physical CPU cores rather than all logical threads.

The default remains one worker and the Python backend. Select an accelerated
backend deliberately; the program never silently falls back to Python.

## What each acceleration changes

1. **Parallel candidates**: GWO candidates within one iteration are independent,
   so multiple worker processes can evaluate them concurrently. Results are put
   back into deterministic candidate order before leader selection. This changes
   runtime, not the seeded search equations. Windows worker inputs must be
   serializable. If a worker cannot start, retry with one worker to diagnose it.
2. **Array/Numba FBS**: the radial topology is converted to arrays. NumPy provides
   a testable array reference and Numba compiles its backward/forward sweeps.
   Numba's first call includes compilation; compare warm runs.
3. **GPU FBS**: CuPy runs the same arrays on NVIDIA CUDA. It currently supports
   one GPU with one controlling CPU worker. It is experimental: one 33-bus solve
   is very small, so launch and transfer overhead can make it slower than Numba.
   A GPU advantage is not assumed until the complete workload is benchmarked.

Do not combine several CPU processes with the current single-GPU backend. That
would make every process contend for the same device and duplicate GPU memory.

## NVIDIA/CuPy installation

On the university computer, first run `nvidia-smi` and record the CUDA version.
Create a separate virtual environment, then install exactly one matching wheel:

```powershell
# Example for CUDA 12.x
python -m pip install cupy-cuda12x

# Or, for CUDA 13.x (not both)
python -m pip install cupy-cuda13x
```

The GPU choice remains unavailable when CuPy cannot see a CUDA device. AMD and
integrated graphics are not supported by this backend.

## Verification and benchmarking

```powershell
python -m unittest discover -s .\07_Implementation\tests_accelerated -v
python .\07_Implementation\examples\benchmark_fbs.py `
  .\04_Research\Working_Data\Network_Data\IEEE_33Bus_Network_Data.xlsx `
  --format ieee33 --runs 200
```

The benchmark excludes one warm-up call so Numba compilation and CUDA startup do
not distort steady-state timing. It also checks every available backend against
the Python loss result. This microbenchmark is not enough to predict the full
optimization time; use the UI's elapsed time and identical seed/catalog/profile
inputs for an end-to-end comparison.

## Limits

- The GPU implementation is real but line-by-line FBS is sequential on a radial
  feeder. Future speed work should batch many hours/candidates on the GPU rather
  than adding more per-line kernels.
- Parallel speed is bounded by memory, serialization, duplicate candidates, and
  the sequential portion of GWO. Twice the workers does not imply twice the speed.
- Numba and CuPy are optional dependencies. Only the Python and NumPy backends can
  be verified on a computer where they are absent.
