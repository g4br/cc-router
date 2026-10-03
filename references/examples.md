# Routing examples for software development

Use this list when unsure about a step's `operation` or flags: find the closest example and copy its classification. The rung and agent names below were checked against the Claude ladder. Codex uses the same operation levels and flags, but its own ladder; use the router's returned agent. If a ladder changes, check the examples again.

The rung does not depend on the amount of code, but on ambiguity, how many components interact, whether the error is reversible and what a silent error costs. 500 lines of boilerplate fit Sonnet low; 5 lines fixing a race condition call for Opus high.

In the flags column, `files>3` means the step touches more than three files. `ambiguous` and `critical` are state fields.

## 0. Haiku (no effort) — `exec-haiku`

Mechanical work with no decisions, checkable at a glance.

| Example | operation | flags |
|---|---|---|
| Replace a string or rename a variable within one file | `mechanical_edit` | — |
| Swap `# ====` banners for `#----`, sort imports, fix formatting | `mechanical_edit` | — |
| Convert a config dict to JSON or YAML | `mechanical_edit` | — |
| Generate `requirements.txt` from a script's imports | `mechanical_edit` | — |
| Find where a function is defined and list its call sites | `search` | — |
| Summarize an obvious traceback or pull values from a log | `read` | — |

## 1. Sonnet low — `exec-sonnet-low`

Small change following an existing pattern.

| Example | operation | flags |
|---|---|---|
| Rename a function across the whole package, updating imports | `mechanical_edit` | files>3 |
| Add a `sys.argv` argument to an existing script | `tweak` | — |
| Add one more variable to the map presets dictionary | `tweak` | — |
| Write a test for a pure function | `tweak` | — |
| Trivial Dockerfile or Caddyfile change (new route, new environment variable) | `tweak` | — |

## 2. Sonnet medium — `exec-sonnet-medium`

Day-to-day implementation with a clear scope.

| Example | operation | flags |
|---|---|---|
| New script: extract an ERA5-Land point series with xarray and save it as CSV | `implementation` | — |
| FastAPI endpoint that reads a file and returns columnar JSON | `implementation` | — |
| Consume a documented REST API and write to a database with an existing schema | `implementation` | — |
| Merge three repeated functions into one generic function with a config dictionary | `implementation` | — |
| GFS download with cfgrib and `filter_by_keys`, scheduled with cron | `implementation` | — |
| README for a module | `writing` | — |
| Aggregate, compare and plot station series | `data_analysis` | — |

## 3. Sonnet high — `exec-sonnet-high`

Clear scope, but with edge cases that need verification.

| Example | operation | flags |
|---|---|---|
| Fix a bug with a failing test and a clear stack trace | `debugging` | — |
| Vectorize a slow loop without changing the numerical result | `implementation` | critical |
| Handle lon 0–360, descending lat and 12Z–12Z accumulation in a grid reader | `implementation` | critical |
| Migrate five scripts from `netCDF4` to xarray with identical outputs | `implementation` | files>3 |
| Retry and timeout in a production service's HTTP client, without swallowing errors | `implementation` | critical |

## 4. Opus medium — `exec-opus-medium`

Spans several modules or needs judgment, with a defined goal.

| Example | operation | flags |
|---|---|---|
| API + database when the data model still has to be designed (upsert, dedup, natural key) | `implementation` | ambiguous, critical |
| Refactor across several modules while keeping the external contract | `implementation` | files>3, critical |
| Critical review of a PR or a production script | `review` | — |
| Concurrency: `multiprocessing` or async FastAPI with a shared resource in the lifespan | `implementation` | ambiguous, critical |

## 5. Opus high — `exec-opus-high`

Costly errors or a non-local cause.

| Example | operation | flags |
|---|---|---|
| Intermittent bug: race condition, memory leak, eccodes or dask hang | `debugging` | ambiguous, critical |
| Intermittent 504 on an endpoint, no stack trace | `debugging` | ambiguous, critical |
| Irreversible data migration in production | `implementation` | files>3, ambiguous, critical |
| Design a public API contract (versioning, error format) | `architecture` | — |
| Validate a physical equation or metric against the reference (units, conservation) | `review` | critical |

## 6. Opus xhigh — `exec-opus-xhigh`

Open problem with no known path, but bounded. **Needs the user's approval before delegating.**

| Example | operation | flags |
|---|---|---|
| Architecture of a new system (tiles rendered on the client GPU) | `architecture` | ambiguous |
| Choosing between approaches with hard trade-offs (zarr or COG, chunking strategy) | `architecture` | ambiguous |
| Diagnose an ML model that generalizes poorly (leakage, sampling bias) | `research` | — |
| Algorithm with no ready reference (tracking convective cells) | `research` | — |
| Security review of a public endpoint | `security` | — |

## 7. Opus max — `exec-opus-max`

Thoroughness over cost. The documentation warns that `max` tends to overthink and has diminishing returns: use sparingly. **Needs the user's approval before delegating.**

| Example | operation | flags |
|---|---|---|
| Vulnerability hunt on an exposed API (authentication, authorization, injection) | `security` | critical |
| Security audit of a server with several exposed services (stops at the ceiling) | `security` | files>3, ambiguous, critical |
| Prove that an interpolation method conserves mass in every edge case | `research` | critical |
| Full review of an operational pipeline before it goes to production | `review` | files>3, ambiguous, critical |

## 8. Fable low — `exec-fable-low`

Open, high-risk problem when you want a first draft to review. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Design a new front-detection method that will feed an operational bulletin | `research` | ambiguous, critical |
| Redesign the architecture of a production system with several services | `architecture` | files>3, ambiguous, critical |

## 9. Fable medium — `exec-fable-medium`

Long autonomous work that loses meaning if split into steps. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Investigate the root cause of a failure spanning server, proxy, API and cron | `investigation` | — |
| Cohesive refactor of a whole package that cannot be split | `long_task` | — |

## 10. Fable high — `exec-fable-high`

Long autonomous work where errors are costly. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Production incident with no initial hypothesis, involving several systems | `investigation` | critical |
| Migrate a whole pipeline (download → processing → API) keeping its outputs | `long_task` | critical |

## 11. Fable xhigh — `exec-fable-xhigh`

Long, autonomous, ambiguous work where errors are costly. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Intermittent forecast degradation that may come from the data, the code or the model | `investigation` | ambiguous, critical |
| Rewrite the core of a production system with open architecture decisions | `long_task` | files>3, ambiguous, critical |

## Notes on the top rungs

- **Security never climbs to Fable.** Fable runs with classifiers that reroute flagged cybersecurity requests to an earlier model. That is why the `security` operation has its ceiling at Opus max (`ceiling_by_operation` in `ladder.json`). If the step fails at the ceiling, the router stops and tells you to ask the user.
- **The position of Fable low and Fable medium is an assumption.** The ladder orders by family first and effort second. There is no measurement showing that Fable low beats Opus max. Compare verified outcomes and token use before treating that order as measured.
- **Fable is off by default (`active: false`)** because, depending on the plan, it bills usage credits instead of drawing on the subscription, and in `-p` mode it bills without asking. Turn it on only if `/model` does not show "Requires usage credits" on the Fable row.
- **`investigation` and `long_task` start at Fable medium.** By definition they are steps that do not split well; if you can split one, split it and classify each part.
