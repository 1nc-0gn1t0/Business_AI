# Real OSM fixtures (ODbL-1.0)

© OpenStreetMap contributors. Data license and attribution:
https://www.openstreetmap.org/copyright

These are actual bounded Kazan Overpass snapshots fetched on 2026-10-22,
not invented coordinates or synthetic commercial metrics. Each `.raw.json` has
a `.raw.manifest.json` with bbox, exact query, source URL, source timestamp,
fetch time, original response SHA256 and normalized file SHA256.

Normalization `poi_minimal_v1` removes contributor usernames/UIDs/changeset IDs
and unused/contact tags. Geometry, OSM identity/version/timestamp and selected
POI/boundary tags are preserved. See app/geo/provider.py for the transformation.

- kazan: small central viewport, including cafes; missing boundaries are expected.
- kazan-boundary: viewport around an actual Vakhitovsky boundary vertex, used
  to verify complete boundary import and spatial district filters.

Fixtures are committed so CI never needs live Overpass or a network download.
Mutated fixture copies in tests are explicitly labelled synthetic test mutations
and exist only in isolated temporary databases, never in the application dataset.
No rent, traffic, demand or financial values are provided by these fixtures.
