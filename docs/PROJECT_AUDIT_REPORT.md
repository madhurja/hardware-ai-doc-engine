# Project Audit Report

This report records the most recent software-quality audit pass.

## Flaws Found And Fixed

| Area | Flaw | Fix |
| --- | --- | --- |
| Privacy | Local-only generation could still use `OPENAI_API_KEY` from the environment. | Explicit empty API keys now disable external AI calls. |
| Upload safety | Uploaded files were read fully into memory. | Uploads are now streamed in chunks with a 75 MB per-file limit. |
| Upload integrity | Duplicate filenames could overwrite earlier intake files. | Duplicate uploads now receive unique suffixes such as `_2`. |
| Upload hygiene | Unsupported files could be placed in intake folders. | Target-specific file extension validation now rejects unsupported types. |
| Private cache | The service worker could cache API responses and generated PDFs. | API and output routes now bypass the offline cache. |
| Document layout | Wide tables and extracted schematic text could overflow PDF pages. | PDF CSS now uses fixed table layout, repeated headers, and aggressive word wrapping. |
| HTML safety | Raw HTML in generated Markdown could pass through to HTML output. | Markdown is escaped before HTML conversion. |
| Evidence honesty | The app showed readiness but not enough release-blocking flaws. | A flaw radar now reports blockers, major flaws, minor flaws, release status, and next actions. |
| Scanner robustness | Very large or excessive manually dropped files could overload scanning. | Scanner now caps file size and file count. |

## Current Verification

- Python tests pass.
- JavaScript syntax checks pass.
- Generated SPC58NH manual includes the flaw audit section.
- The app status endpoint reports quality audit data.

## Remaining Product-Level Limits

- The audit is evidence-based, not a replacement for certified lab testing.
- PCB layout, BOM, firmware, and measured bench data are still required before release-grade claims.
- Native CAD parsing can be expanded later for deeper net connectivity and layout scoring.
