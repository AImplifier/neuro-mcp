# Tool Reference

neuro-mcp registers **54 tools** on the `neuro-analysis` FastMCP server,
across five areas:

| Area | Tools | State |
|---|---|---|
| [Processing (MNE)](processing.md) | 24 | In-memory, keyed by `session_id` |
| [Source Imaging (ESI)](source-imaging.md) | 9 | Same session, after epoching |
| [Data & EHR](data-ehr.md) | 15 | Persistent (Postgres/SQLite + BIDS) |
| [neuroii Integration](neuroii.md) | 3 | Persistent + external HTTP |
| [Visualization](visualization.md) | 3 | Reads the in-memory session, writes standalone HTML |

## Recommended pipeline order

This is the order embedded in the server's own `instructions` string, which
any MCP client (including the calling agent) can read directly:

```
load_neuro -> filter_neuro -> set_montage -> set_reference ->
detect_bad_channels -> run_ica / apply_ica -> find_events -> epoch_neuro ->
compute_psd / compute_erp / time_frequency

# source imaging, after epoching:
fetch_template_head -> compute_forward -> compute_noise_covariance ->
make_inverse_operator -> apply_inverse (or apply_lcmv_beamformer) ->
extract_label_timecourses
```

Pick a stable `session_id` (e.g. `"default"`, or one per patient/recording)
and reuse it across calls — state (loaded raw data, fitted ICA, epochs,
forward/inverse operators, source estimates) threads through that key. Data
and EHR tools are independent of this: subjects, recordings, and EHR records
persist in the database across sessions and process restarts.

## Two state models, two return-key conventions

Processing tools mutate transient in-memory session state and tend to key
their status as `"status"` (e.g. `filter_neuro` returns `{"status":
"filtered", ...}`). Data/EHR tools mutate the persistent store and key their
result as `"outcome"` (e.g. `add_ehr_record` returns `{"outcome": "created",
...}`). There's no shared response envelope across the two families — when
calling a tool for the first time, check its actual return shape rather than
assuming one convention holds everywhere.

See [Examples](../examples/index.md) for complete, verified call sequences.
