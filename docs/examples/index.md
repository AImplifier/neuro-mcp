# Examples

Five realistic, end-to-end agent workflows spanning all five tool areas. Every
call sequence and output shape below is grounded in an actual exercised path
in `testing/full_verify.py` and/or the `testing/persona_*.py` scripts — not
invented — so you can run the same calls yourself and expect the same shapes
back.

1. [Clinical Review, Annotation & EHR Audit](clinical-review-ehr-audit.md) —
   a clinician's journey from a new patient through review, annotation, and a
   versioned diagnosis, ending with an audit-trail lookup.
2. [Research Preprocessing & Spectral Pipeline](research-preprocessing-spectral.md) —
   the full sensor-level MNE pipeline from raw file to spectral/ERP/
   time-frequency features.
3. [Source Imaging (ESI) Pipeline](source-imaging-esi.md) — localizing
   cortical sources from scalp EEG using the fsaverage template head.
4. [Interactive Visualization Generation](interactive-visualization.md) —
   producing the three self-contained NEUROII-style HTML viewers.
5. [neuroii Integration](neuroii-integration.md) — the neuroii round-trip
   (contract vs. live), pushing a recording and pulling clinician annotations
   back into the store.

Each example uses a synthetic 20-channel EEG recording (the same kind
`testing/make_synthetic.py` generates: standard 10-20 layout, a stim channel,
and an injected 10 Hz alpha-band rhythm) so the numbers you see are
reproducible if you run the calls yourself against
`testing/make_synthetic.py`'s output.
