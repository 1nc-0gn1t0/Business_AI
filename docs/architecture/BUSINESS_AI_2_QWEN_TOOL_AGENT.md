# BA2/U-03 — Qwen Tool Agent

29.10.2026. Base: merged PR33/main `aadf57e4c8a8a15e02950196063a98fd5151b923`.
Branch `codex/U-03-qwen-tool-agent`; final commit/PR/CI are in the delivery report.
This implements bounded data investigation, not the U-04 industry planner.

## Runtime audit and selected protocol

Actual local Ollama: **0.40.8**, model `qwen3:4b-instruct-2507-q4_K_M`,
digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`,
artifact2497293803bytes. Hardware: RTX3050Ti4GB/16GB host, Docker Desktop/Windows.
Compose's existing pinned Ollama image is0.40.11; this task does not upgrade it or
the working runtime. Native tools are accepted by the installed server, but the
first real native probe returned a coverage call with an **empty categories list**
(40.703s). It would be rejected, not executed. API support is not model reliability.

Selected protocol: separate JSON-schema `PlanProposal` via existing `/api/chat`.
Each schema branch is generated from an actual Tool Registry DTO, with matching
tool/capability/result IDs. A generic arguments object proved insufficient in live
trials. Explicit AOI/UUID values and backend evidence IDs are constrained in the
generation schema; independent runtime validation remains mandatory. No text is
interpreted as Python, SQL, URL, file path or an operator credential.

The existing extractor prompt,384-token budget and profile grounding stay separate.
Only its cancellable HTTP transport is shared: `OllamaLLM.achat`; old extraction
keeps its existing two-attempt behavior, agent steps use **one** network attempt.
There is no automatic stub/provider fallback. Test model dependencies are explicit.
References: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[tool calling](https://docs.ollama.com/capabilities/tool-calling). These are documentation,
not a substitute for the installed-version probes above.

```mermaid
sequenceDiagram
  participant U as Owner / operator
  participant A as v2 Agent endpoint
  participant Q as H-03 → local Qwen
  participant G as Tool Gateway
  participant D as Existing U-01 / U-02
  U->>A: token, expected version, request UUID, question
  A->>A: consent/CAS/admission; persist running snapshot
  A->>Q: bounded structured proposal
  Q-->>A: tool + arguments
  A->>G: recheck owner/consent/CAS/permissions/budget
  G->>D: validated service call, short transaction
  D-->>A: coverage or durable job ID
  A->>Q: untrusted result data + allowed next decisions
  Q-->>A: validated evidence IDs + finish/continue decision
  A->>A: grounded rendering + final consent/CAS publication
  A-->>U: persisted answer, traces, real stages/job reference
```

## Executable catalog

All tool argument/result contracts have revisionv1 inside the additive agent-v2 API.
Every call requires an owned conversation and current assistant consent.

| Tool ID | Capability / result | Additional permission | Implementation / limit |
| --- | --- | --- | --- |
| `list_data_capabilities` | data.describe / capabilities | None | U-01 registry + bounded metadata coverage; categories/local state/adapter/permissions separately |
| `check_data_coverage` | data.coverage / coverage | None | Existing U-01 coverage,<=4categories, canonical territory/AOI; no POI scan |
| `check_data_sufficiency` | data.sufficiency / sufficiency | None | Existing deterministic sufficiency using reviewed templates below |
| `request_data_acquisition` | data.acquire / acquisition_job | Current U-02 operator credential + explicit matching AOI | Existing U-02 create/cache/dedup/source policy; only osm/geo.mapped_poi,<=1creation/run |
| `get_acquisition_status` | data.job_status / acquisition_job | Current operator credential + owner-bound job grant | Existing U-02 job/latest event; UUID must belong to a run of this conversation; no polling loop |

Dataset summary is not duplicated: coverage already includes versions, extent,
freshness/provenance/license/limitations. Model context has no raw POI arrays or full
geometry. Evidence is limited to two dataset references per category with explicit
`dataset_count`/`evidence_truncated`; an oversized result is rejected, not silently
turned into a complete city claim.

Three sufficiency templates: `mapped_poi_v1` (POI), `vehicle_context_v1` (POI+vehicle
network), `nonspatial_inputs_v1` (budget+costs, no map). They specify data requirements;
`executor_supported=false` explicitly prevents treating them as implemented industry
algorithms. Public user inputs remain unknown; this tool does not read other profiles.
Unknown industries are never coerced to coffee. Assumptions/U-04/U-05 are not implemented.

The four sources remain osm/synthetic/ghsl/licensed,18categories. Only OSM POI has a
remote adapter. GHSL/licensed have no downloader. OSM network remains review_required
by default; the agent cannot approve it. Public Overpass remains an expiring operator
smoke path, not a continuously operating application backend. See [U-02](BUSINESS_AI_2_DYNAMIC_ACQUISITION.md).

## Authority and isolation

The v2 request uses the existing `X-Conversation-Token`. Optional
`X-Acquisition-Token` is validated by the existing U-02 operator check; it stays
request-local, never enters model context, traces, response, hashes or logs.
It must still match at each significant operation and publication. Providing a role,
owner, permission or token in model JSON has no effect and extra argument keys fail.

This is the existing shared deployment-operator credential, **not** a new multi-user
operator identity system. U-02's standalone API remains operator-wide. Through the
agent, job IDs are additionally granted only to the authorized conversation that
created/attached them. Global public datasets can be shared; private job traces cannot.
Another conversation, even with the shared operator credential, cannot use its agent
status tool to inspect an ungranted job. Ordinary users cannot initiate imports or
read operator runs. Granting assistant consent does not grant operator powers.

For mutations, the request must contain `acquisition_scope={territory,aoi}`. The
model-proposed scope must match exactly, then U-02 checks source/category/actual AOI
area/current cache/source policy/resources. A UUID mentioned in text is only a syntax
hint for generation; Gateway still checks its owner grant. Neither generated text nor
the output schema is authorization.

## API and persistence

Feature flag: `BA_AGENT_ENABLED=1`; default0, including Compose/.env.example. No UI
flow changes or automatic replacement of `/api/v1/.../messages`.

```http
POST /api/v2/conversations/{conversation_id}/agent
X-Conversation-Token: <owner token>
Content-Type: application/json

{
  "request_id": "<client-generated UUID>",
  "expected_version": 0,
  "content": "Проверь POI и дорожную сеть Москвы"
}
```

Optional operator-only acquisition_scope is an explicit, bounded AOI object; no URL,
SQL, path, shell, model name or resource override is accepted. Read a saved result via
`GET /api/v2/conversations/{conversation_id}/agent/{request_id}` with the same authority.
There is no public generic tool executor or source-policy mutation API.

Response: `schema_version`, request/conversation IDs, profile_version, state, message,
next_step/code, model, traces, model_timings and total_ms. A trace contains tool/capability,
mutation flag, timestamp, validation/execution timings, argument hash, validated arguments,
bounded selection reason, checked result or safe error. No prompts or credentials.
`succeeded` describes checked actions, not reliable economic conclusions or profitable
business. A queued job is not downloaded data; worker availability remains unknown.

Additive migration **0010_agent_runs** adds one owner-FK table, active-owner uniqueness,
response-size constraint and owner/date index. Existing geo/profile/finance/report
tables and snapshots are unchanged. `job_ids` are written with job creation in the
same transaction. Idempotency hashes include the validated agent request; changed
payload or authority under the same request UUID conflicts. Replays do not infer again.
U-02 keys are backend-derived and its global dataset/job dedup remains authoritative.

On publication the existing conversation service appends messages and an unchanged
profile snapshot using the existing revision vocabulary `message`. Version advances;
confirmation/extraction facts do not change. Final consent revision and CAS are checked
again. A profile edit/revocation while waiting prevents stale publication or further tools.
Only36existing v1 paths/126reachable schemas were compared, all unchanged from base.

Runs: running → succeeded/partial/failed/cancelled; expired interrupted runs cannot
resume tools automatically. GET exposes interrupted state after deadline; no fake progress.
Disconnect cancellation waits for DB cleanup. Created U-02 jobs survive independently;
cancel them through the existing operator acquisition API, not by assuming LLM abort
also stopped a worker.

## Budgets, H-03 and safe synthesis

`BA_AGENT_LIMITS_JSON` is trusted operator config, not an argument accepted from Qwen.
Defaults:4LLM calls,3tool calls,<=2calls/tool,<=1acquisition,300s total,12000bytes/result,
22000bytes/context,1000retained runs/20per owner. LLM input/output stays4096/384tokens
(synthesis96). Near-window prompt counts are rejected. These are bounds, not an SLA.

Every attempted LLM step is checkpointed before dispatch, including interrupted calls.
H-03 `QUEUE.slot()` is the **only** inference queue, one slot per model call. Queue wait
and inference/load durations are separate. No connection is held across inference;
no LLM slot spans tool execution or waits for a U-02 job. One API worker/process remains
required; H-03 is not a cross-process GPU scheduler. The acquisition worker is separate.

Flow: proposal → checked tool → structured synthesis decision; only a necessary
`continue` with remaining budget permits another proposal. Duplicate requests stop;
catalog calls cannot repeat. There is no repair by executing guessed arguments and no
dense status polling. Timeout/error can expose a checked partial result; interrupted
calls remain recorded. Errors include unsupported tool/capability/category, invalid
arguments/synthesis, permission/source refusal, scope mismatch, duplicate/budget/context
limit, unavailable Ollama, request conflict and storage limit.

Synthesis is intentionally constrained: Qwen selects an allowed next decision and
references backend evidence. Backend rechecks those references and renders factual
sentences from results; unrestricted model prose is not published as proof of success.
This prevents a fluent hallucination from asserting city coverage or a finished import.
It does not prove the model chose every useful tool or that data are representative.

OSM/registry/tool text is untrusted JSON in a user-role message, never a privileged
instruction. No raw source descriptions/POI names are required. Each subsequent action
passes independent Gateway checks; prompt injection cannot grant a tool or permission.
H-02 byte/header/structure/rate/admission controls now also apply to v2 (the previous
middleware boundary admitted v1 only). Agent requests use the existing model-frequency
budget and H-03 concurrency; stock quotas bound persisted metadata.

Trace visibility expires after7days (410); expired terminal rows are lazily removed on
new admission. Active-owner uniqueness bounds concurrent runs. Global stock exhaustion
fails429, never deletes immutable reports or arbitrary datasets. There is no public
administrative trace/retention endpoint or unbounded audit log.

## Verification and local use

- Unit/gateway/loop/security + new PostGIS tests:43PASS/9.61s (28unit/15DB).
  Final interrupted-replay/clarification persistence rerun2PASS/4.60s.
- Targeted existing DB/agent/inference/conversation/report/registry/populated-migration
  regression:58PASS/116.78s, Windows **Selector** test-process policy.
- Existing extraction/H-03 regression46PASS. Ruff/mypy150files PASS.
- Strict v1 comparison36paths/126schemas unchanged; generated TypeScript/build PASS,
  initial web bundle232KB unchanged. Chromium coffee mock1PASS/12.1s; isolated hardened
  Compose/tmpfs ready/schema0010/web200/catalog4/18, agent default503. Final prek/CI
  in delivery report. Owned smoke containers/network removed without persistent volumes.
- Live Qwen trials, mistakes and measurements are retained under `docs/qa/u-03/`;
  HTTP200 alone is not counted as a successful workflow. Artificial geo fixtures and
  temporary source permission are labelled. No Moscow download is performed by U-03.

### Recorded live outcomes and performance

[Runtime/native audit](../qa/u-03/runtime-audit.json),
[read probes/cold load](../qa/u-03/live-qwen.json),
[final constrained multi-step/permissions/job/status](../qa/u-03/live-qwen-constrained.json),
[measurements](../qa/u-03/measurements.json),
[historical trial summaries](../qa/u-03/live-trials.json).
Historical HTTP200/partial outcomes are not counted as final acceptance passes.

Final constrained probe performed list_data_capabilities→check_data_coverage;
an ordinary owner received operator_permission_required with no job;
the authenticated operator created a real queued U-02 job and read that same granted ID.
Repeated request UUID reused the saved response. Job attempts remained0; no worker,
download or complete Moscow coverage is claimed. Qwen interpreted partial/missing
coverage through constrained evidence/next-step outputs; backend rendered the facts.

| Measurement | Observed scope/value |
| --- | --- |
| Cold first proposal |35.796s, including25.696s model load; explicit unload before probe |
| Cold complete read investigation |69.77s,4LLM calls/2actual tools |
| Warm read operations |10.55…19.16s,2LLM calls; not a guaranteed range |
| H-03 wait |0ms in these serial live probes; separate FIFO/overflow/cancellation tests |
| Python process peak RSS |105988096bytes (~101.1MiB), corrected Win64 measurement |
| GPU used snapshots |3681…3921MiB; includes desktop/other GPU usage, not model-only peak |
| CPU/whole Ollama RAM/total system peak |Not measured; no extrapolation to concurrent city imports |

Per-tool validation/execution timings and token counts are in the evidence, not merged
with GPU time or a durable import duration. Initial Windows memory counter returned0;
that is an invalid reading, not zero memory use. The corrected live follow-up is
[live-memory.json](../qa/u-03/live-memory.json). VRAM headroom is small; context/model
size was not increased and additional parallel models were not introduced.

Legacy real chat: one two-sentence wording was rejected with llm_invalid_response
([retained](../qa/u-03/live-legacy-initial.json)); the standard demo wording passed
HTTP200/ollama, coffee/Kazan/budget2000000.00 in8.266s
([result](../qa/u-03/live-legacy.json)). Original prompt/payload/schema/options compare
identically with merged main. No extraction prompt modification or silent facts fallback
was used to mask that model limitation.

Safe local commands (PG* must identify a disposable QA server, never the working DB):

```powershell
uv run --locked --project apps/api pytest apps/api/tests/test_agent.py -q
# BA_RUN_DB_TESTS=1, disposable PG*:
uv run --locked --project apps/api pytest apps/api/tests/integration/test_agent.py -q
# Run from apps/api so the app/tests packages resolve:
uv run --locked python -m tests.integration.u03_live --output <private-or-QA-output.json>
```

The live probe creates/drops only a randomized isolated database, uses a labelled
artificial Kazan fixture, real local Qwen and real U-01/U-02 services. The operator
dispatch section grants a temporary **QA** source permission, creates a real queued
job and reads its status; no worker or network fetch is started. Tokens are generated
in process and not written to evidence. `--case` limits reruns; `--unload-first` is an
explicit operator option for a controlled cold-load measurement. Do not run a second
inference process alongside normal user traffic. Run schema upgrades through the
existing supported migration process, not against an unbacked working volume.

## Boundaries and U-04

Qwen4B is not perfectly reliable: early trials omitted categories, copied wrong IDs,
repeated tools or returned inconsistent evidence references. The Gateway stopped them;
schema constraints and bounded synthesis improve usability without treating JSON
validation as truth. Preserve failed-trial evidence. No guarantee for arbitrary prompt
wording, all industries or all cities. Raw model-owned prose and general Internet
search remain unavailable. Cold/warm latency is measured per probe, not a guarantee.

U-04 can extend reviewed requirements/industry capabilities behind this Gateway and
introduce ProfileV2 separately. It must not bypass the operator/source boundary,
assume road acquisition exists, change v1 finance formulas, fabricate data or add a
second LLM queue. U-04, U-05 and U-06 have not been started. The pre-existing release
security baseline is still OPEN; this PR does not accept unrelated image risks.
