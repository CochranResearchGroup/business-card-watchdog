# System Architecture

## Control Plane

`BatchOrchestrator` is the deterministic host controller. It owns discovery, run directory creation, job state, ledger writes, worker concurrency, sink decision recording, and stop/failure state.

Model or agent intelligence must feed structured artifacts into this controller. It must not directly mutate contact stores or global workflow state.

## Data Plane

Images are discovered from files, directories, or `$fsr` aliases in user config. Each card gets a job ID and artifact directory under:

```text
~/.local/share/business-card-watchdog/runs/<run-id>/artifacts/<job-id>/
```

The existing `business-card-to-contact` skill is called as a subprocess adapter. Its OCR, crop, review, Google, Apollo, and Odoo stub behavior remains independently reviewable.

## Sink Plane

Routing is config-driven and dry-run by default. The first scaffold records sink decisions but does not implement live Odoo writes. Google writes remain delegated to the underlying skill only when dry-run is disabled and `google_contacts` is enabled.

Future sink adapters should share a common idempotency contract:

- match by provider stable ID when known
- else fingerprint
- else email, phone, exact name
- store write/readback evidence in runtime state

