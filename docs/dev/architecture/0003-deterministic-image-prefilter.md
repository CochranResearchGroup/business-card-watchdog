# Deterministic Image Prefilter

Status: Implemented first pass  
Authority: `PRODUCT_SPEC.md`

## Purpose

The prefilter reduces false-positive workload before business-card OCR/App Intelligence verification. It is deterministic and records evidence for every candidate image before the business-card pipeline runs.

## Current Analyzers

Core analyzer:

- Reads PNG, JPEG, and GIF dimensions from file headers without loading pixels.
- Scores business-card-like aspect ratios using long-side/short-side ratio.
- Treats ratios around common business card crops as weak evidence only. Aspect ratio can make a file `uncertain`, but does not make it `likely_business_card` by itself.

Optional analyzer:

- If OpenCV (`cv2`) is installed, it runs a Canny/contour pass looking for quadrilaterals with business-card-like rectangle ratios.
- It records up to 10 candidate boxes and raises confidence when multiple card-like rectangles are visible in one larger phone photo.
- If OpenCV is not installed, the analyzer reports that fact and does not fail the run.
- Install it with `uv pip install --python .venv/bin/python -e ".[vision]"`; the project uses `opencv-python-headless` to avoid GUI dependencies.

## Decisions

The classifier returns:

- `likely_business_card`
- `not_business_card`
- `uncertain`

Default config:

```toml
[prefilter]
enabled = true
min_score = 0.55
process_uncertain = false
```

By default, `not_business_card` and `uncertain` images are rejected before the OCR/App Intelligence pipeline. The rejection is recorded in `events.jsonl`, the job state, and `preclassification.json`.

`likely_business_card` requires deterministic rectangle evidence at or above the configured minimum score. This avoids sending ordinary 16:9 phone photos to App Intelligence just because their whole-image aspect ratio happens to be close to a business-card crop.

## Limits

This first pass is strongest for cropped or mostly-card images. Full phone-camera photos where a card occupies a small part of the image need OpenCV contour detection or a later OCR/vision hint to avoid false negatives.

Future deterministic hints can include:

- text density from local OCR
- email/phone/URL token detection
- connected-component layout
- EXIF orientation normalization
- configurable allowlist folders or filename patterns
