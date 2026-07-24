# Testing & Verification

The `testing/` folder is **not pytest-based**. Every script is a standalone
`asyncio` program that drives the server the way a real MCP host would — over
FastMCP's in-memory `Client` — against a temp SQLite DB, a temp BIDS root,
and synthetic EEG generated on the fly (`testing/make_synthetic.py`, no
fixture files needed). Each script prints `PASS`/`FAIL`/`SKIP` per check and
exits non-zero if anything failed.

```bash
python testing/verify.py         # fast smoke test
python testing/verify_viz.py     # visualization HTML self-containment checks
python testing/full_verify.py    # comprehensive: all 54 tools, happy + error paths,
                                  # numerical evaluation, coverage assertion,
                                  # writes testing/REPORT.md
```

## What each script covers

- **`verify.py`** — rename integrity, the processing core, the full clinician
  EHR/annotation lifecycle (add → amend → history → void, with audit), and the
  neuroii stub.
- **`verify_viz.py`** — confirms the three visualization tools produce valid,
  self-contained HTML (embedded Plotly, no external references).
- **`full_verify.py`** — the most thorough: every one of the 54 registered
  tools is called at least once (both a happy path and, where meaningful, an
  error path), a mock HTTP server exercises the *configured* neuroii
  integration, and an `evaluate()` pass checks that outputs are not just
  well-formed but *numerically correct* — e.g. that a synthetically injected
  10 Hz rhythm actually shows up as the dominant alpha band, that an EHR
  amendment leaves exactly one active version, that every clinical mutation
  produced an audit row. It finishes with a coverage assertion (every
  registered tool was exercised) and regenerates `testing/REPORT.md`.

## Persona scripts

`persona_clinician.py` and `persona_bci_researcher.py` are not pass/fail
gates — they're narrative "agent persona" scripts that simulate a realistic
user journey (a clinician reviewing a patient, a researcher building a
decoding pipeline) and print a running transcript plus a **wins / friction**
log: what worked smoothly for an agent acting on the user's behalf, and where
the tool surface creates friction (e.g. needing to track a numeric
`recording_id`, or constructing a raw FHIR body). They're a good read for
understanding the *agentic ergonomics* of the tool surface, not just its
correctness.

```bash
python testing/persona_clinician.py
python testing/persona_bci_researcher.py
```

## Optional: Postgres-backed testing

`testing/docker-compose.yml` spins up a local Postgres for full-stack testing
against the production database backend. `verify.py`/`full_verify.py` use
SQLite by default and don't require it.

## Reading `testing/REPORT.md`

`full_verify.py` writes a fresh Markdown report each run: a summary line
(`N passed, N failed, N skipped` across all checks, plus tool coverage), then
one table per functional area (`session`, `preprocess`, `ica`, `epoch`,
`spectral`, `plots`, `export`, `esi`, `viz`, `data`, `annot`, `audit`,
`neuroii`, `evaluation`, `coverage`). Check its generation
timestamp before relying on it — it reflects whatever environment last ran
`full_verify.py`, not necessarily your current one.
