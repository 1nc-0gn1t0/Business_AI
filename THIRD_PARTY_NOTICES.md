# Third-party components · H-06 · 27 October 2026

This document does not grant a license to Business AI itself. The project owner has
not selected a repository-wide distribution license. No bank endorsement or trademark
permission follows from any dependency license.

Provided runtime notices, generated from the installed **locked** distributions:

- [Python notices](apps/api/THIRD_PARTY_NOTICES.txt), included at
  `/licenses/THIRD_PARTY_NOTICES.txt` in the API image.
- [Browser notices](apps/web/public/THIRD_PARTY_NOTICES.txt), included in the Vite
  output and served at `/THIRD_PARTY_NOTICES.txt`.
- [Inventory and license evidence hashes](docs/qa/H-06-dependencies.json).
- [Bundled DejaVu font license](apps/api/app/reporting/fonts/LICENSE.txt).

Run `uv sync --locked --project apps/api`, `npm --prefix apps/web ci`, then
`uv run --locked --project apps/api python scripts/inventory_dependencies.py`.
The generator records lock versions, package sources/integrity, actual provided
license-file hashes and verification status. Conditional/uninstalled packages are
not represented as verified. Inventory reflects the Windows audit environment;
platform-specific package sets may differ on Linux. Generated notices are a
practical attribution baseline, **not a legal compatibility certificate**.

## Verified package obligations

MIT/BSD/ISC/Apache notices and applicable copyright/license texts must remain with
distributed copies. Apache NOTICE requirements apply where upstream supplies NOTICE;
Apache terms do not grant trademark rights. Provided NOTICE files are included by the
generator. Avoid removing license directories from installed runtime packages.

Psycopg and psycopg-binary3.3.6 declare **LGPL-3.0-only**, not MIT or LGPL2.1. Their
binding/native-wheel license files remain in the image and notices. Before external
distribution, verify corresponding-source/relinking/replacement requirements for the
actual wheel and its bundled native libraries; a link or this inventory alone is not
proof of full LGPL compliance. Windows libpq18.4 and Linux libpq18.6 differ.

Hypothesis6.170.9 is MPL-2.0, development-only; modified covered files would carry
source obligations if distributed. TypeScript/Playwright are Apache-2.0 development
tools. Tool dependencies are not automatically part of the served browser bundle.
The optional `httpx2-jsfetch1.0` entry is Emscripten-only and uninstalled on the target
Windows/Linux systems; its license text has not been verified in this audit.

DejaVu includes Bitstream/Arev conditions and public-domain changes. Preserve its
provided font license; do not assume every glyph has one generic MIT license.

## Infrastructure and model, separately

| Component | Evidence / obligations |
|---|---|
| PostgreSQL17.5 | [PostgreSQL License](https://www.postgresql.org/about/licence/), retain provided notices |
| PostGIS3.5.2 | [GPL-2.0-or-later source license](https://github.com/postgis/postgis/blob/3.5.2/COPYING); distributing a DB image requires a corresponding-source/compliance process |
| GEOS/PROJ/libxml/GDAL and Debian/Alpine packages | Separate native/system licenses; retain image-provided copyright files and source availability. Full per-binary redistribution compliance remains unverified |
| Python3.12 / Node24 / nginx1.30.6 | Upstream PSF / Node MIT and third-party notices / nginx BSD-style terms; base images aggregate additional software, not a single license |
| Ollama0.40.8 | [MIT source license](https://github.com/ollama/ollama/blob/v0.40.8/LICENSE), separately from model/CUDA dependencies |
| Qwen GGUF Q4_K_M | Specific artifact Apache-2.0 evidence below; weights are not shipped in Git or application images |
| age1.3.2 | [BSD-3-Clause](https://github.com/FiloSottile/age/blob/v1.3.2/LICENSE); external operator tool, retain notices on redistribution |
| uv0.13.1 / pip-audit2.10.1 / Gitleaks8.30.1 / Trivy0.76.1 | Build/audit tools; upstream MIT OR Apache-2.0 / Apache-2.0 / MIT / Apache-2.0 respectively; not product runtime dependencies |

The GPU Ollama image contains native components, potentially including NVIDIA CUDA
materials. Ollama's MIT license does **not** establish rights for every image layer.
Review the actual GPU-image redistribution terms before shipping it to third parties.
No proprietary SDKs, commercial geodata licenses or internal VTB integration are
asserted by this report.

### Actual Qwen artifact

Installed `qwen3:4b-instruct-2507-q4_K_M`,4.0B,GGUF,Q4_K_M:

- Manifest SHA256 `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
- [Official registry tag](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M).
- [Registry manifest](https://registry.ollama.ai/v2/library/qwen3/manifests/4b-instruct-2507-q4_K_M).
- License layer SHA256 `d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12`:
  downloaded layer hash verified; text matched the installed `/api/show` license.
  This supports Apache-2.0 for **this quantized artifact**, not merely the base-model
  card. Weight blob was not independently rehashed or redownloaded.
- Demo manifestv2 checks the installed manifest digest; a mutable tag alone is
  insufficient. Preserve licenses/NOTICE and record modifications when redistributing
  model material. No claim about training-data rights or trademark permission.

## Data and release obligations

OSM is [ODbL](https://www.openstreetmap.org/copyright); keep visible attribution and
review database/derived-database share-alike requirements when distributing extracts.
Raster tile service terms are separate from the OSM database license; the application
does not acquire a paid tile-service entitlement through MapLibre's BSD license.
Synthetic fixtures are explicitly marked; they do not establish market-data rights.
Public VTB source links do not license VTB trademarks or arbitrary website content.

Before external release, the owner must select Business AI's license, approve notices,
verify native/bundled binary and GPU-image obligations, and establish durable source
availability where required. This audit supplies evidence and unresolved items; it
does not replace that review.
