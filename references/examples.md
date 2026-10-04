# Usage examples by model and effort level

Models: Haiku 4.5, Sonnet 5.5, Opus 5.5, Fable 5.1.
Effort levels: `low`, `medium`, `high`, `xhigh`, `max`.

**Haiku has no effort level.** The `effort` parameter only exists on Sonnet, Opus and Fable. Haiku therefore appears as a single rung with 20 examples, and the other three with 5 × 20. Total: 320 examples.

## How to read this

| Level | What characterizes the task |
|---|---|
| `low` | Closed scope, one step, near-mechanical answer. Speed matters more than depth. |
| `medium` | Well specified, a few steps, few decisions. |
| `high` | Needs real reasoning: several files, debugging, design decisions. |
| `xhigh` | Long horizon (over 30 min), many tool calls, autonomous execution. |
| `max` | Frontier problem. Only when `xhigh` has already failed or a mistake is very expensive. |

| Model | Role | Default effort |
|---|---|---|
| Haiku 4.5 | Volume, triage, extraction, search | not applicable |
| Sonnet 5.5 | Code execution and everyday tasks | `high` |
| Opus 5.5 | Architecture, hard debugging, scientific reasoning | `medium` |
| Fable 5.1 | What Opus can't solve: original research, whole systems, long autonomy | `high` |

Rule of thumb: raise the effort first when the task is the right kind for the model but the result came out shallow; raise the model when what's missing is judgment, not reasoning time.

## How the router uses this file

The router does not pick a configuration from this list. `route.py` decides from the step's `operation` and flags. To fill those fields, use the [cases checked against the router](#classifying-operation-and-flags-for-routepy) at the end of this file. The list above describes what each model and effort level is suited for; use it to judge whether a routed decision makes sense and to escalate after a failure.

Sonnet `xhigh` and `max`, Opus `low` and Fable `max` are not rungs of the Claude ladder, so `route.py` never returns them. The Fable rungs are inactive by default (see `config/ladder.json`).

---

## Haiku 4.5 (single rung)

1. Classify each agricultural news item in a batch as relevant or irrelevant for the bulletin.
2. Extract date, municipality and crop from an alert text and return them as JSON.
3. Rename the variables of a short script to descriptive names.
4. Convert a station list from comma-separated CSV to `sep=';'`.
5. Generate a commit message from a small diff.
6. Summarize a cron log output in three lines.
7. Find which file in the repository defines a given function (search subagent).
8. Translate interface strings from Portuguese to English.
9. Check whether a JSON file is valid and point to the line with the error.
10. Write a one-line docstring for each function in a module.
11. Turn a CDO command into a comment explaining what it does.
12. Standardize map file names according to a template.
13. Give the unit of a GRIB variable from its `shortName`.
14. Generate a title and tags for an already written bulletin.
15. Flag, in a list of PRs, which ones touch dependencies.
16. Convert units in a table (K to °C, m/s to km/h).
17. Extract action items and deadlines from an email.
18. Detect the language and tone of chat user messages.
19. Build a simple regular expression to validate a station code.
20. Do the initial triage of a prompt: is the task simple or does it need a bigger model?

---

## Sonnet 5.5

### low

1. Fix a syntax error or missing import pointed out by the traceback.
2. Add a progress `print()` to each step of a script.
3. Replace `netCDF4` with `xarray.open_dataset` in a simple reading script.
4. Write a function that converts accumulated precipitation into an hourly rate.
5. Adjust the `dpi`, title and colorbar of a matplotlib figure.
6. Create a `.gitignore` for a Python project with data in `data/`.
7. Write the crontab line that runs a script every 6 h.
8. Convert a snippet from `os.path` to `pathlib.Path`.
9. Explain what a one-line `gdal_translate` command does.
10. Generate a basic Dockerfile for a FastAPI app.
11. Add `len(sys.argv)` validation at the start of a script.
12. Reformat a configuration dictionary as YAML.
13. Write a SQL select query filtered by date and station.
14. Rename a function and update its calls within a single file.
15. Create a FastAPI health check endpoint.
16. Write the `rsync` command that mirrors a map folder to the server.
17. Convert a DataFrame time series to columnar JSON.
18. Answer a specific library API question (e.g. `resample` arguments in xarray).
19. Write the Caddy block for reverse-proxying an app.
20. Write a short installation README for a script.

### medium

1. Write a complete script that downloads one GFS cycle, crops it to a region and saves it as zarr.
2. Implement a FastAPI endpoint with pagination and a period filter.
3. Refactor a 300-line script, replacing three repeated blocks with one generic function.
4. Create unit tests for a unit-conversion module.
5. Plot a cartopy map of accumulated precipitation with a municipality shapefile.
6. Write a script that validates physical ranges in station data and outputs a CSV of flags.
7. Add disk caching to a function that queries an external API.
8. Replace sequential `requests` downloads with parallel downloads using `concurrent.futures`.
9. Put together a `docker-compose.yml` with API, database and proxy.
10. Implement a Streamlit page with a station selector and a time series chart.
11. Convert an exploratory notebook into an organized linear script.
12. Write a Claude Code hook that runs the linter after every edit.
13. Implement IDW interpolation from stations to a regular grid.
14. Fix a reproducible bug with a clear traceback in a module of two or three files.
15. Create a GitHub Actions workflow that runs the tests on every push.
16. Compute degree-days and a simple water balance from daily series.
17. Adapt a map script to accept a second model with different variable names.
18. Write the parser for a fixed-width station file format.
19. Generate a Markdown bulletin from a forecast JSON using a defined template.
20. Review a small PR, pointing out bugs and style deviations.

### high

1. Implement a feature that spans several files (API, data model and frontend).
2. Debug a job that fails intermittently under cron but works in the terminal.
3. Design and implement the zarr chunking scheme of a forecast archive for fast point reads.
4. Optimize an xarray/dask pipeline that runs out of memory when processing a year of data.
5. Implement lightning cluster tracking between time steps, with overlap-based association.
6. Write the alert rule engine with thresholds, persistence and hysteresis.
7. Refactor a legacy module while preserving behavior, with characterization tests first.
8. Implement token authentication and rate limiting on a public API.
9. Diagnose why two models produce shifted maps (projection, longitude convention, latitude order).
10. Build a LightGBM training pipeline with leak-free temporal validation.
11. Implement quantile-mapping bias correction for temperature forecasts.
12. Write a tile server that delivers grid values in a compact binary format.
13. Integrate an external API with an OAuth flow, error handling and retries.
14. Review a medium PR in depth, including edge cases and concurrency.
15. Implement OBD-II PID reading over CAN in firmware, with timeout handling.
16. Solve a CORS problem combined with a gateway timeout between frontend and backend on different domains.
17. Write a fragment shader that colors a scalar field with a palette and bilinear interpolation.
18. Migrate a set of cron scripts to an orchestrator with task dependencies.
19. Implement spatial QC of stations (neighbor comparison) taking terrain into account.
20. Write a Claude Code skill with instructions, examples and trigger criteria.

### xhigh

1. Implement a small app end to end (backend, frontend and deploy) from a specification.
2. Migrate an entire repository of scripts to a package structure, keeping everything running.
3. Upgrade a project to a major dependency version with breaking changes and fix all the tests.
4. Write the test suite of an untested project, file by file.
5. Port a map pipeline from one model to five models with different conventions.
6. Implement a complete bulletin pipeline: ingestion, analysis, text, figures and distribution.
7. Convert a set of shell + CDO scripts to Python/xarray, with verified numerical parity.
8. Apply the style standard to dozens of scripts in the repository, validating each one.
9. Build a multi-screen dashboard from an HTML prototype.
10. Implement the configurator of a USB HID device from already decoded captures.
11. Reprocess and validate a historical archive, fixing the failures found along the way.
12. Dockerize an old conda environment and resolve the library incompatibilities one by one.
13. Build a simple Android app from the command line (Gradle) all the way to the APK.
14. Fix a series of bugs from a backlog, with one logical change per bug.
15. Build a RAG pipeline over a crop knowledge base, with evaluation.
16. Write the complete documentation of an API (reference and examples) by reading the code.
17. Write the firmware of an ESP32 panel with several screens, sensors and single-button navigation.
18. Check a FastAPI app against a security checklist and apply the fixes.
19. Build a statistical downscaling pipeline with training, validation and product generation.
20. Execute an already approved multi-step refactoring plan, running the tests at each stage.

### max

Rare use: in most cases, moving up to Opus pays off more than Sonnet at `max`. It fits a hard but well-bounded problem when you want to spare the Opus quota.

1. Find the cause of a subtle numerical difference (order of 1e-3) between two already isolated implementations.
2. Show that two implementations of an algorithm are equivalent, or find the counterexample.
3. Resolve a race condition in asynchronous code within a single module.
4. Derive and implement a formula from a paper (e.g. thermal front parameter), checking units and signs.
5. Second attempt at a bug that Sonnet `high` did not solve, before escalating to Opus.
6. Final line-by-line review of a critical script that runs unattended in production.
7. Optimize a critical numerical loop (vectorization, numba) with proof of equivalence.
8. Work out a poorly documented binary format from samples.
9. Design the optimal cell association algorithm between frames, with complexity analysis.
10. Verify the consistency between database schema and migrations when real data is at stake.
11. Resolve an extensive merge conflict between two branches that diverged heavily.
12. Follow a deep traceback in a third-party library (dask, eccodes) down to the root cause.
13. Write a parser grammar with many edge cases and demonstrate its coverage.
14. Check the math of a hand-implemented verification metric (CRPS, Brier).
15. Rewrite a slow SQL query based on its execution plan.
16. Find an error of tens of meters in the projection and datum conversion of a GDAL pipeline.
17. Design the state machine of a firmware with all transitions and failure modes.
18. Assess, case by case, whether an API change breaks existing clients.
19. Hard problem at a time of tight quota, with Opus unavailable.
20. Independent cross-check of a solution produced by another model.

---

## Opus 5.5

### low

1. Quick opinion on which of two architecture approaches to choose.
2. Name a project, module or API with good judgment.
3. Review the tone of a delicate email to a client.
4. One-line verdict on whether an implementation plan makes sense.
5. Explain a hard concept briefly and correctly (e.g. why ensemble spread is not error).
6. Choose the right library for a problem among three candidates.
7. Identify the main risk in a sensitive piece of code.
8. Rewrite a paragraph of a scientific paper while keeping its precision.
9. Decide the order of steps of an already decomposed task (light orchestration).
10. Interpret an obscure error message without access to the code.
11. Suggest the most likely diagnosis of a synoptic situation described in text.
12. Assess whether a statistical result is plausible.
13. Translate technical text with precise meteorological terminology.
14. Answer a conceptual ML question (e.g. when to use blocked temporal validation).
15. Point out the logical flaw in a short argument.
16. Choose the best title and abstract among candidate versions.
17. Classify the complexity of a task for routing when the case is ambiguous.
18. Give quick feedback on a dashboard layout.
19. Summarize a scientific paper while preserving its caveats.
20. Decide whether it is worth raising the effort or the model for a subproblem.

### medium

1. Plan the implementation of a medium feature before delegating execution to Sonnet.
2. Review a PR with attention to design decisions, not just bugs.
3. Write the technical specification of an endpoint or service.
4. Draft the methods section of a paper from the code and notes.
5. Design the data schema of a new product.
6. Debug a bug that crosses two layers of the system.
7. Write the meteorological analysis of an event from model fields and observations.
8. Design the validation strategy of a crop yield model.
9. Refactor a module when there are interface decisions to make.
10. Compare three server hardware options with a cost-benefit analysis.
11. Write the system prompt of a bulletin-writing agent.
12. Analyze the results of an experiment and suggest the next ones.
13. Draft the response to a journal reviewer.
14. Prepare an infrastructure migration plan with stages and rollback.
15. Diagnose the performance drop of a model in production.
16. Structure an agroclimatic knowledge base for use by an LLM.
17. Assess a commercial proposal or project scope and point out the gaps.
18. Turn a client's vague requirements into a prioritized backlog.
19. Design the hierarchy of subagents and skills of a workflow.
20. Audit a scientific script for methodological errors.

### high

1. Design the architecture of a new system (e.g. grid-value tiles rendered on the client GPU).
2. Find the root cause of a bug that resisted two attempts by Sonnet.
3. Design an objective front detection algorithm with cyclone, warm front and occlusion.
4. Review the methodology of a hybrid model in search of data leakage.
5. Write a long technical report with cohesive argumentation.
6. Debug concurrency or data corruption in a multi-stage pipeline.
7. Design a deterministic classifier of synoptic systems from NWP fields.
8. Reverse engineer the protocol of your own device from traffic captures.
9. Review the design of a public API for authentication, authorization and data exposure.
10. Plan the refactoring of a large legacy codebase in safe stages.
11. Design the statistical post-processing of a multi-model ensemble.
12. Critically assess a scientific paper and redo its main calculation.
13. Decompose a large project into tasks routable to smaller models.
14. Optimize a system with a non-obvious bottleneck (I/O, serialization, network).
15. Design the unified data model of several station networks with inconsistent metadata.
16. Write the evaluation plan of an AI agent, with metrics and test cases.
17. Resolve the divergence between two data sources that should agree.
18. Design a downscaling strategy with physical and statistical justification.
19. Do the competitive and strategic analysis of a product, with recommendations.
20. Arbitrate an architecture trade-off with many constraints (cost, latency, maintenance).

### xhigh

1. Autonomously implement a multi-part system designed in the previous stage.
2. Migrate a codebase with hundreds of files, with continuous verification.
3. Investigate a production bug for hours, raising and discarding hypotheses with experiments.
4. Build and evaluate a complete ML pipeline, iterating on the results.
5. Rewrite a legacy system in a new architecture while keeping output parity.
6. Orchestrate subagents in a multi-hour task, integrating and checking the results.
7. Implement the algorithm of a complex scientific paper and reproduce its figures.
8. Audit an entire repository (correctness, security, performance) and apply the fixes.
9. Develop a nowcasting app with satellite ingestion, clustering, tracking and visualization.
10. Unify several station databases into a single one, with QC and documentation.
11. Deep literature research with a synthesis report and supporting code.
12. Run the ablation experiments of a model, analyze and report.
13. Port a firmware to another platform, resolving peripheral differences.
14. Build a vehicle diagnostic scanner with several modules and protocols.
15. Write a complete manuscript from the results, with figures and internal review.
16. Implement an end-to-end alert system with load tests.
17. Restructure a server's infrastructure (containers, proxy, backups) with a rollback plan.
18. Create and validate a complete public repository (code, tests, documentation, CI).
19. Reanalyze a multi-year dataset with a new methodology and compare it with the old one.
20. Execute a research plan in which each result redefines the next stage.

### max

1. Bug that survived Opus `xhigh` and is blocking production.
2. Architecture decision that is irreversible or very expensive to undo.
3. Final verification of the methodology before submitting a paper.
4. Proof or refutation of a property of a critical algorithm.
5. Root cause of an incident with contradictory evidence.
6. Review of code on which money, safety or unrecoverable data depend.
7. Design of a new method with no ready reference in the literature.
8. Reconciliation of results that diverge between the implementation and the reference paper.
9. Risk assessment of a data migration with no possibility of rollback.
10. Long mathematical derivation in which a sign error invalidates everything.
11. Diagnosis of the slow degradation of a model with no apparent cause.
12. Design of an expensive experiment that can only be run once.
13. Technical opinion that will serve as the basis for a contract or expert report.
14. Optimization of an already well-optimized algorithm, chasing the last gain.
15. Analysis of a concurrent or distributed system in search of invalid states.
16. Adversarial review of your own plan before a long execution.
17. Interpretation of an atypical meteorological case in which the models diverge strongly.
18. Decoding the protocol of your own device with unknown checksums and fields.
19. Design of the evaluation of a product whose error has asymmetric cost.
20. Subproblem in which the orchestrator already tried `xhigh` and verification failed.

---

## Fable 5.1

### low

Even at `low`, Fable is for short answers where what matters is the quality of the judgment.

1. Quick second opinion on a conclusion reached by Opus.
2. Judge in one sentence whether a scientific hypothesis holds up.
3. Choose between two already written implementation plans.
4. Find the error in a short derivation.
5. Answer a hard conceptual question on which the other models contradicted each other.
6. Assess how novel a research idea is.
7. Rewrite the contribution paragraph of a paper with maximum precision.
8. Identify the fragile assumption of an experimental design.
9. Break the tie between the diverging reviews of two subagents.
10. Give the verdict on a technical trade-off with long-lasting consequences.
11. Point out what is missing from a specification.
12. Check the physical interpretation of an unexpected result.
13. Suggest the correct formulation of an ill-posed problem.
14. Assess whether a too-good result is data leakage.
15. Summarize a dense paper in a few lines without losing the essential caveat.
16. Indicate which of the possible causes to investigate first.
17. Review the title and thesis of a project proposal.
18. Estimate the feasibility of an approach to an order of magnitude.
19. Give a short, harsh critique of a plan before execution.
20. Answer a specific question on an advanced statistical method.

### medium

1. Plan a multi-week project and decompose it into tasks for Opus and Sonnet.
2. Do the technical review of a manuscript like a demanding referee.
3. Design the methodology of a new study.
4. Diagnose a problem that crosses physics, statistics and software.
5. Design the target architecture of a platform with several products.
6. Review a system design made by Opus and propose changes.
7. Prepare the product strategy and technical roadmap from a market analysis.
8. Write a research or grant project proposal.
9. Interpret a set of experiments with ambiguous results.
10. Formulate the conceptual scheme of a weather type classifier.
11. Design the operational validation protocol of a forecasting system.
12. Synthesize scattered literature into a coherent framework.
13. Redesign an entire pipeline that grew without planning.
14. Define the model routing criteria and the boundary cases.
15. Assess several modeling approaches and recommend one, with justification.
16. Structure a long scientific argument before writing.
17. Plan the integration of a new data source across the whole product chain.
18. Review a complex technical scope in search of risks.
19. Design a QC system that combines rules, statistics and learning.
20. Decide what to cut from a project that does not fit the deadline.

### high

1. Original research: propose and develop a new modeling method.
2. Design and implement a complex system for which Opus `high` delivered an insufficient solution.
3. Debug a failure that arises from the interaction between several systems.
4. Write a complete scientific paper with a methodological contribution.
5. Reformulate a hybrid physical-statistical model with a new architecture.
6. Analyze an extreme event in depth with multiple data sources.
7. Design a new tracking or nowcasting algorithm with sound foundations.
8. Audit the entire methodology of a dissertation or technical report.
9. Design the rendering of meteorological data on the GPU under bandwidth and precision constraints.
10. Build an ensemble forecasting scheme with calibration and verification.
11. Translate a vague business problem into a mathematical formulation and solution.
12. Reengineer a large codebase with a change of paradigm.
13. Develop an objective detection method and validate it against manual analysis.
14. Analyze the technical and economic feasibility of a new product.
15. Design a sensitivity study with control of confounding factors.
16. Do the critical synthesis of a research field, identifying gaps.
17. Solve an optimization problem with many constraints.
18. Design firmware and electronics together, with real-time constraints.
19. Diagnose the systematic divergence between model and observation with physical hypotheses.
20. Long, underspecified task in which you have to decide what to do, not just how.

### xhigh

1. Autonomous multi-hour research project: hypothesis, experiment, analysis and report.
2. Complete construction of a new product, from scratch to deploy.
3. Full rewrite of a platform with several services.
4. Reproduction of a complex paper and extension of its method.
5. Experiment campaign with dozens of runs and intermediate decisions.
6. Investigation of an open problem with no known solution.
7. Migration of the entire operational chain to a new architecture without downtime.
8. Development of a model and its paper in parallel.
9. Orchestration of many subagents in a project with complex dependencies.
10. Audit and repair of an entire system with deep technical debt.
11. Construction of a broad knowledge base with source verification.
12. Development of a hybrid forecasting system with physical and ML components.
13. Climatological reprocessing with a new methodology and complete validation.
14. Design and implementation of a cross-platform app with a backend.
15. Exhaustive comparative study of methods, implementing all of them.
16. Breaking a monolith into services, with tests and data migration.
17. Preparation of a long report with new analyses.
18. Construction of a complete embedded system, from protocol to interface.
19. Multi-hour work in which Opus `xhigh` lost the thread or accumulated errors.
20. Long-horizon task in which an early mistake costs everything that follows.

### max

1. Frontier problem on which Fable `xhigh` has already failed.
2. The most expensive technical decision of the project, with no way back.
3. Rigorous proof or refutation of a new mathematical result.
4. Final verification of a paper before submission to a high-impact journal.
5. Root cause of a serious incident that no other level could explain.
6. Conception of a novel method for a problem with no satisfactory solution.
7. Complete adversarial review of a critical system before it goes into production.
8. Reconciliation of contradictory evidence in a scientific study.
9. Design of a unique and expensive experiment.
10. Analysis of a case in which all models and experts disagree.
11. Optimization of a method that is already at the limit of the state of the art.
12. High-responsibility technical opinion (expert report, forensic analysis, large contract).
13. Planning of a multi-month project with serious technical risks.
14. Extensive theoretical derivation with independent verification of each step.
15. Full reassessment of a research line in the face of an unexpected result.
16. Diagnosis of a subtle systematic error that runs through an entire processing chain.
17. Architecture of a system that needs to last for years and scale.
18. Assessment of a bold scientific hypothesis with all the available evidence.
19. Deadlock in which two `xhigh` runs reached opposite conclusions.
20. Any task in which the cost of being wrong far exceeds the cost of spending the quota.

---

## Classifying operation and flags for route.py

Use this list when unsure about a step's `operation` or flags: find the closest example and copy its classification. The rung and agent names below were checked against the Claude ladder. Codex uses the same operation levels and flags, but its own ladder; use the router's returned agent. If a ladder changes, check the examples again.

The rung does not depend on the amount of code, but on ambiguity, how many components interact, whether the error is reversible and what a silent error costs. 500 lines of boilerplate fit Sonnet low; 5 lines fixing a race condition call for Opus high.

In the flags column, `files>3` means the step touches more than three files. `ambiguous` and `critical` are state fields.

### 0. Haiku (no effort) — `exec-haiku`

Mechanical work with no decisions, checkable at a glance.

| Example | operation | flags |
|---|---|---|
| Replace a string or rename a variable within one file | `mechanical_edit` | — |
| Swap `# ====` banners for `#----`, sort imports, fix formatting | `mechanical_edit` | — |
| Convert a config dict to JSON or YAML | `mechanical_edit` | — |
| Generate `requirements.txt` from a script's imports | `mechanical_edit` | — |
| Find where a function is defined and list its call sites | `search` | — |
| Summarize an obvious traceback or pull values from a log | `read` | — |

### 1. Sonnet low — `exec-sonnet-low`

Small change following an existing pattern.

| Example | operation | flags |
|---|---|---|
| Rename a function across the whole package, updating imports | `mechanical_edit` | files>3 |
| Add a `sys.argv` argument to an existing script | `tweak` | — |
| Add one more variable to the map presets dictionary | `tweak` | — |
| Write a test for a pure function | `tweak` | — |
| Trivial Dockerfile or Caddyfile change (new route, new environment variable) | `tweak` | — |

### 2. Sonnet medium — `exec-sonnet-medium`

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

### 3. Sonnet high — `exec-sonnet-high`

Clear scope, but with edge cases that need verification.

| Example | operation | flags |
|---|---|---|
| Fix a bug with a failing test and a clear stack trace | `debugging` | — |
| Vectorize a slow loop without changing the numerical result | `implementation` | critical |
| Handle lon 0–360, descending lat and 12Z–12Z accumulation in a grid reader | `implementation` | critical |
| Migrate five scripts from `netCDF4` to xarray with identical outputs | `implementation` | files>3 |
| Retry and timeout in a production service's HTTP client, without swallowing errors | `implementation` | critical |

### 4. Opus medium — `exec-opus-medium`

Spans several modules or needs judgment, with a defined goal.

| Example | operation | flags |
|---|---|---|
| API + database when the data model still has to be designed (upsert, dedup, natural key) | `implementation` | ambiguous, critical |
| Refactor across several modules while keeping the external contract | `implementation` | files>3, critical |
| Critical review of a PR or a production script | `review` | — |
| Concurrency: `multiprocessing` or async FastAPI with a shared resource in the lifespan | `implementation` | ambiguous, critical |

### 5. Opus high — `exec-opus-high`

Costly errors or a non-local cause.

| Example | operation | flags |
|---|---|---|
| Intermittent bug: race condition, memory leak, eccodes or dask hang | `debugging` | ambiguous, critical |
| Intermittent 504 on an endpoint, no stack trace | `debugging` | ambiguous, critical |
| Irreversible data migration in production | `implementation` | files>3, ambiguous, critical |
| Design a public API contract (versioning, error format) | `architecture` | — |
| Validate a physical equation or metric against the reference (units, conservation) | `review` | critical |

### 6. Opus xhigh — `exec-opus-xhigh`

Open problem with no known path, but bounded. **Needs the user's approval before delegating.**

| Example | operation | flags |
|---|---|---|
| Architecture of a new system (tiles rendered on the client GPU) | `architecture` | ambiguous |
| Choosing between approaches with hard trade-offs (zarr or COG, chunking strategy) | `architecture` | ambiguous |
| Diagnose an ML model that generalizes poorly (leakage, sampling bias) | `research` | — |
| Algorithm with no ready reference (tracking convective cells) | `research` | — |
| Security review of a public endpoint | `security` | — |

### 7. Opus max — `exec-opus-max`

Thoroughness over cost. The documentation warns that `max` tends to overthink and has diminishing returns: use sparingly. **Needs the user's approval before delegating.**

| Example | operation | flags |
|---|---|---|
| Vulnerability hunt on an exposed API (authentication, authorization, injection) | `security` | critical |
| Security audit of a server with several exposed services (stops at the ceiling) | `security` | files>3, ambiguous, critical |
| Prove that an interpolation method conserves mass in every edge case | `research` | critical |
| Full review of an operational pipeline before it goes to production | `review` | files>3, ambiguous, critical |

### 8. Fable low — `exec-fable-low`

Open, high-risk problem when you want a first draft to review. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Design a new front-detection method that will feed an operational bulletin | `research` | ambiguous, critical |
| Redesign the architecture of a production system with several services | `architecture` | files>3, ambiguous, critical |

### 9. Fable medium — `exec-fable-medium`

Long autonomous work that loses meaning if split into steps. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Investigate the root cause of a failure spanning server, proxy, API and cron | `investigation` | — |
| Cohesive refactor of a whole package that cannot be split | `long_task` | — |

### 10. Fable high — `exec-fable-high`

Long autonomous work where errors are costly. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Production incident with no initial hypothesis, involving several systems | `investigation` | critical |
| Migrate a whole pipeline (download → processing → API) keeping its outputs | `long_task` | critical |

### 11. Fable xhigh — `exec-fable-xhigh`

Long, autonomous, ambiguous work where errors are costly. **Needs the user's approval before delegating.** *Inactive in `ladder.json`: while it stays that way, these steps go to `exec-opus-max`.*

| Example | operation | flags |
|---|---|---|
| Intermittent forecast degradation that may come from the data, the code or the model | `investigation` | ambiguous, critical |
| Rewrite the core of a production system with open architecture decisions | `long_task` | files>3, ambiguous, critical |

### Notes on the top rungs

- **Security never climbs to Fable.** Fable runs with classifiers that reroute flagged cybersecurity requests to an earlier model. That is why the `security` operation has its ceiling at Opus max (`ceiling_by_operation` in `ladder.json`). If the step fails at the ceiling, the router stops and tells you to ask the user.
- **The position of Fable low and Fable medium is an assumption.** The ladder orders by family first and effort second. There is no measurement showing that Fable low beats Opus max. Compare verified outcomes and token use before treating that order as measured.
- **Fable is off by default (`active: false`)** because, depending on the plan, it bills usage credits instead of drawing on the subscription, and in `-p` mode it bills without asking. Turn it on only if `/model` does not show "Requires usage credits" on the Fable row.
- **`investigation` and `long_task` start at Fable medium.** By definition they are steps that do not split well; if you can split one, split it and classify each part.
