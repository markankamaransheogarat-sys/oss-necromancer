# oss-necromancer

A small pipeline for **reviving abandoned open-source projects**: find popular-but-dead repositories with a permissive license and a clean algorithmic core, then rebuild them in modern, memory-safe Rust (+ WebAssembly), with tests, CI, benchmarks and a live demo — crediting the original author.

First rebirth: **[rebirth-ik](https://github.com/markankamaransheogarat-sys/rebirth-ik)** — inverse kinematics, reborn from [TheComet/ik](https://github.com/TheComet/ik) ([live demo](https://markankamaransheogarat-sys.github.io/rebirth-ik/)).

## Stage 1 — finder

`finder/finder.py` searches GitHub (read-only, through the `gh` CLI) and ranks candidates.

```bash
gh auth login                       # once
python finder/finder.py --years 5 --deep 40
# → out/candidates.md and out/candidates.json
```

**Hard filters**

* stars 500 – 15 000
* no push for ≥ `--years` years (archived repos welcome)
* languages C, C++, Python
* **strictly permissive license** (MIT, Apache-2.0, BSD-2/3-Clause, Unlicense). GPL/AGPL/LGPL/MPL/unknown are excluded by the search *and* re-checked in code.

**Scoring heuristics**

* a clean algorithmic core, found by word-boundary matching of ~110 domain terms (compression, crypto, DSP, physics, geometry, pathfinding, parsers, math) — machine-learning repos, clients, wrappers and apps are filtered out;
* popularity, forks, open issues;
* **unmet demand**: open issues asking for Rust / WASM / bindings / 64-bit;
* self-containedness: penalties for GUI/OS-specific dependencies (Qt, GTK, X11, OpenGL, Win32, CUDA…) and for huge code bases; bonus for having tests (a ready oracle for the rewrite);
* a name-collision check against crates.io.

The latest run is in [`out/candidates.md`](out/candidates.md).

## Stage 2 — the rebirth blueprint

1. **Read, don't trust.** Study the original; port its *ideas*, keep its tests as acceptance scenarios. Check whether it actually works (the original `ik` did not: stub tests, empty solvers).
2. **Rust core** — `#![forbid(unsafe_code)]`, zero-allocation API where it matters, `no_std` + `libm`, optional `rayon`.
3. **WebAssembly demo** — a single HTML file, deployed to GitHub Pages by CI.
4. **Honest benchmarks** — Criterion, fixed work per iteration, published with the hardware and with what was *not* compared.
5. **Credit** — the original license text and author are preserved; the README says plainly what was missing upstream.

## Rules of the road

* Never copy GPL-family code. Permissive originals only; keep their copyright notice.
* Don't claim speed-ups you didn't measure.
* Clean up build artifacts (`target/`) after verification; keep an eye on disk space.

MIT licensed.
