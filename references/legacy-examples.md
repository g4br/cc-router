# Archived v1 examples — non-normative

Preserved for compatibility with earlier references. These historical family,
version, price and effort claims are not current capability or billing evidence.
Do not use them to infer host support or route v2 tasks. Use router-v2.md and the
configured catalogue instead. This archive has not been revalidated against hosts.

# Usage examples by model and effort level

Models: Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.1.
Effort levels: `low`, `medium`, `high`, `xhigh`, `max`.

Every model has the five effort levels, so each one appears with 5 × 20 examples. Total: 400 examples. The examples are generic software and knowledge work in three kinds: text (writing, review, summary, classification, translation), code (generation, refactor, debugging, review, design) and data (extraction, validation, analysis, pipelines, evaluation of results).

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
| Haiku 5.5 | High-volume, latency-sensitive work: classification, extraction, routing, mechanical edits, subagent chores | `medium` |
| Sonnet 5.5 | Everyday coding and agentic tool use | `high` on the API; `medium` is the documented start for agentic coding |
| Opus 5.5 | Multistep work in a real codebase, code review, knowledge work, design judgment | `medium` |
| Fable 5.1 | What Opus can't solve: long autonomy, ambiguity, original research, whole systems | `high` |

Rule of thumb: raise the effort first when the task is the right kind for the model but the result came out shallow; raise the model when what's missing is judgment, not reasoning time.

Price per million tokens, input / output: Haiku $0.10 / $0.50 up to 100k tokens of prompt and $0.50 / $2.50 above that; Sonnet $2 / $10; Opus $4 / $20; Fable $10 / $50. Keep Haiku steps small in context.

## How the router uses this file

The router does not pick a configuration from this list. `route.py` decides from the step's `operation` and flags. To fill those fields, use the [cases checked against the router](#classifying-operation-and-flags-for-routepy) at the end of this file. The list above describes what each model and effort level is suited for; use it to judge whether a routed decision makes sense and to escalate after a failure.

Haiku `xhigh` and `max`, Sonnet `low`, `xhigh` and `max`, Opus `low` and Fable `max` are not rungs of the Claude ladder, so `route.py` never returns them. Opus `max` is a rung reached only by escalation. The Fable rungs are inactive by default (see `config/ladder.json`).

---

## Haiku 5.5

First Haiku with effort levels. Documented role: high-volume, latency-sensitive work such as classification, routing, extraction and subagent tasks. On terminal-based agentic coding it scores well below Sonnet 5.5, so implementation stays on Sonnet; on knowledge work the gap is small.

### low

Chat, short tool tasks and simple high-volume requests with a checkable output. The documentation warns that under a long agent prompt it may skip a search, stop early or skip a check at this level: give it one-shot work.

1. Classify each support ticket in a batch by topic from a fixed list.
2. Rate a batch of product reviews as positive, neutral or negative.
3. Extract names, dates and amounts from an invoice text and return them as JSON.
4. Translate a list of user interface strings, keeping placeholders intact.
5. Summarize a meeting transcript in three bullet points.
6. Detect the language of each message in a batch.
7. Write a one-line commit message from a small diff.
8. Flag which emails in an inbox export contain a deadline.
9. Check whether a JSON or YAML file is valid and point to the line with the error.
10. Rename the variables of a short function to descriptive names.
11. Convert a code snippet from one quoting or formatting style to another within one file.
12. Explain in one sentence what a one-line shell command does.
13. Add type hints to a short function whose types are obvious from use.
14. Convert a CSV between delimiters or encodings.
15. Convert units in a table (for example Fahrenheit to Celsius, miles to kilometers).
16. Normalize dates and identifiers in a column to one format.
17. Pull the error line and exit code out of a long log.
18. Check a list of records against a schema and list the ones that fail.
19. Count rows per category in a small table and return the totals.
20. Route an incoming request to the right queue from its text, with a fixed set of queues.

### medium

The documented starting point for most work, including short agentic coding. Short tool tasks with no decisions and a check it can run itself.

1. Fill a document template from a JSON record, field by field, and check that no placeholder is left.
2. Rewrite a paragraph to a given reading level, keeping every fact.
3. Draft the release notes for a version from the list of merged pull request titles.
4. Write a one-line docstring for every function in a module.
5. Proofread a page for spelling and grammar without changing its meaning.
6. Produce a table of contents for a long Markdown document from its headings.
7. Find where a function is defined and list its call sites across the repository.
8. Fix a syntax error or missing import pointed out by the traceback, and rerun the script.
9. Sort imports and fix formatting in a module, then run the formatter check.
10. Generate a dependency file from a script's imports and confirm the script still imports.
11. Write the cron entry, shell alias or one-line script for a documented routine task.
12. Create a `.gitignore` or `.editorconfig` for a project of a given stack.
13. Add a progress log line to each step of a script.
14. Write a regular expression that matches the supplied positive and negative test cases.
15. Write a SQL query filtered by date and category, and run it against the test database.
16. Convert a data frame between wide and long format and check the row count.
17. Extract a table from a PDF manual into CSV.
18. Compare two configuration files and list the keys that differ with their values.
19. Run the test suite and summarize the failures by module.
20. Open a documented public page with the browser tool and return its table as JSON.

### high

Documented for knowledge work, longer agent tasks and strict instruction following. The rung for a `tweak`: a change that follows an existing pattern exactly, with a test to run.

1. Summarize a long technical report faithfully, keeping every number and caveat.
2. Translate a technical document keeping the exact terminology list supplied.
3. Write a short installation README for a script from its `--help` output.
4. Answer a specific library API question from the documentation pages supplied.
5. Grade a batch of short answers against a rubric with explicit criteria.
6. Fill a long form or spreadsheet template where every field has a stated rule.
7. Support chatbot that must hold its system prompt when users argue or keep asking.
8. Rename a function across the whole package, updating imports, and run the tests.
9. Add a command-line argument to an existing script, following its existing argument pattern.
10. Add one more entry to a configuration dictionary and regenerate the sample output.
11. Write a test for a pure function in the style of the existing test file.
12. Add a new route or environment variable to a Dockerfile or reverse-proxy config and rebuild.
13. Convert a module from one standard library API to its modern equivalent and run its tests.
14. Create a health check endpoint following the existing router pattern, with its test.
15. Apply the project's style guide to a dozen scripts, one at a time, running each after the change.
16. Extract a structured dataset from hundreds of similar documents, with a validation script after each batch.
17. Standardize file names in a folder according to a template, verifying the count before and after.
18. Validate a data export against its schema and produce a report of violations by column.
19. Compute summary statistics for a dataset and check them against known totals.
20. Deduplicate a contact list with a stated matching rule and report what was merged.

### xhigh

Not a rung. The documentation says to use it only where an eval showed a gain over `high`, and to run the same eval on Sonnet 5.5 and compare cost and speed. In multi-turn chats at this level the model sometimes writes its whole answer in thinking and returns no visible text.

1. Apply a mechanical migration across dozens of files, validating each with the tests.
2. Reprocess and validate an archive of files with a fixed check per file.
3. Extraction campaign over thousands of documents with a validator after each batch.
4. Long browser-use flow over many pages where every step is checkable.
5. Fill a large spreadsheet from documents with strict rules per column.
6. Apply a style standard to a whole repository, one file at a time.
7. Bulk classification with a hard rubric where an eval showed `high` falls short.
8. Generate per-customer reports from a template for hundreds of customers, checking each output.
9. Translate a large documentation set section by section with a glossary and a consistency check.
10. Label a large dataset for training with a detailed annotation guide.
11. Transcribe and clean a batch of scanned forms with a per-field validator.
12. Run a long multi-step tool task where `high` stopped early in your eval.
13. Review hundreds of pull request titles and descriptions for compliance with a template.
14. Convert a legacy data dump into a normalized schema, table by table, with row-count checks.
15. Generate unit tests for every pure function in a package from their docstrings, running each.
16. Build an index of a large document set: one summary and keyword list per document.
17. Second attempt at a Haiku task that failed at `high` when Sonnet is unavailable or quota is tight.
18. Audit a large configuration repository against a checklist, file by file.
19. Produce a changelog for a year of commits, grouped by component.
20. Cross-check a long list of citations against the reference list, one by one.

### max

Rarely worth it. For anything that needs reasoning, Sonnet 5.5 at `medium` is the documented comparison and usually wins on cost per solved task.

1. High-volume classification with asymmetric error cost where evals showed a gain over `xhigh`.
2. Independent cross-check of a cheap pipeline's outputs on a sample.
3. Hard extraction from degraded documents (scans, poor OCR) with crop and zoom tools available.
4. Reconciling two large tables that should agree, field by field.
5. Long-horizon mechanical task where early stopping at lower levels was measured.
6. Verifying a batch of generated documents against their source records, number by number.
7. Deduplicating a large catalog with fuzzy matches and a stated rule.
8. Grading an eval set against a rubric at scale, as the judge model.
9. Multi-step browser task with many checks where `xhigh` left steps undone.
10. Any high-volume task where the eval shows `max` beats Sonnet 5.5 `medium` on cost per correct output.
11. Final consistency pass over a large translated document set with a glossary.
12. Checking thousands of generated test cases for duplicates and contradictions.
13. Extracting a complete data model from a large, poorly documented schema dump.
14. Matching records across two systems with inconsistent identifiers, with a confidence score each.
15. Line-by-line comparison of two long policy texts for every difference.
16. Quality screening of a large content library against a detailed policy.
17. Validating a large migrated dataset against the source with per-field tolerances.
18. Recovering structure from a large unstructured log archive.
19. A long tool-driven checklist where every skipped item would be costly.
20. Reprocessing a large archive after a rule change, verifying each item's new value.

---

## Sonnet 5.5

### low

Not a rung. The documentation puts this level at chat, classification, extraction and search, which the Claude ladder sends to Haiku. At `low` on coding tasks the model may report a change without running a check.

1. Rewrite an email to a more formal tone, keeping its content.
2. Answer a factual question from a short document pasted in the prompt.
3. Summarize a pull request description in two sentences.
4. Draft a short announcement from a list of bullet points.
5. Review a short paragraph for clarity and suggest one rewrite.
6. Produce a glossary of the terms used in a short specification.
7. Fix a syntax error or missing import pointed out by the traceback.
8. Add input validation at the start of a script for a required argument.
9. Write a function that converts between two documented formats, with the signature given.
10. Replace a deprecated library call with its documented replacement in one file.
11. Generate a basic Dockerfile for a small web service.
12. Write a short script that renames files in a folder according to a pattern.
13. Explain what a given regular expression matches and give three examples.
14. Create a minimal configuration file for a linter or formatter.
15. Write a SQL query joining two tables with a date filter.
16. Convert a nested JSON document into a flat table.
17. Compute descriptive statistics for one column and flag outliers by a simple rule.
18. Plot one series from a CSV with labeled axes and a title.
19. Load a spreadsheet, drop empty rows and columns, and save it as CSV.
20. Check a dataset for missing values and report the share per column.

### medium

1. Write the README for a module from its code and docstrings.
2. Turn a set of meeting notes into a structured decision log.
3. Review a short document against a checklist and list the gaps.
4. Write user-facing error messages for every failure path of a form.
5. Draft API documentation for three endpoints from their handlers.
6. Rewrite a tutorial so each step can be followed without prior context.
7. Write a complete script that downloads a file, validates it and stores it in a given format.
8. Implement an endpoint with pagination and a filter on an existing data model.
9. Refactor a 300-line script, replacing three repeated blocks with one generic function.
10. Create unit tests for a module with pure functions and clear contracts.
11. Add disk caching to a function that queries an external API.
12. Replace sequential downloads with parallel downloads using a thread pool.
13. Write a Docker Compose file with an API, a database and a proxy.
14. Fix a reproducible bug with a clear traceback in a module of two or three files.
15. Create a CI workflow that runs the tests on every push.
16. Write the parser for a fixed-width or delimited file format from its specification.
17. Aggregate a time series by week, compare two groups and plot the result.
18. Implement a validation step that checks business ranges and outputs a CSV of flags.
19. Build a small ETL step: read from an API, transform to a schema, write to a table.
20. Convert an exploratory notebook into an organized linear script with the same outputs.

### high

1. Review a medium pull request in depth, including edge cases and concurrency.
2. Write a technical design note for a feature from a set of requirements and constraints.
3. Audit a documentation set for contradictions with the current code.
4. Evaluate two competing specifications and recommend one with reasons.
5. Write a postmortem from logs, timeline and chat excerpts.
6. Implement a feature that spans several files (API, data model and frontend).
7. Debug a job that fails intermittently under a scheduler but works in the terminal.
8. Optimize a pipeline that runs out of memory when processing a large input.
9. Refactor a legacy module while preserving behavior, with characterization tests first.
10. Implement token authentication and rate limiting on a public API.
11. Integrate an external API with an OAuth flow, error handling and retries.
12. Solve a CORS problem combined with a gateway timeout between two services.
13. Migrate a set of scripts to an orchestrator with task dependencies.
14. Write an agent skill or plugin with instructions, examples and trigger criteria.
15. Implement a rule engine with thresholds, persistence and hysteresis.
16. Design and implement the chunking or partitioning of an archive for fast point reads.
17. Diagnose why two data sources produce shifted results (units, time zones, ordering).
18. Build a model training pipeline with leak-free temporal validation.
19. Implement calibration of one series against a reference, with verification.
20. Implement quality control that compares each record with its neighbors.

### xhigh

Not a rung. The documentation reserves it for work with a measured quality gain.

1. Implement a small app end to end (backend, frontend and deploy) from a specification.
2. Migrate an entire repository of scripts to a package structure, keeping everything running.
3. Upgrade a project to a major dependency version with breaking changes and fix all the tests.
4. Write the test suite of an untested project, file by file.
5. Port a pipeline to several input sources with different conventions.
6. Implement a complete reporting pipeline: ingestion, analysis, text, figures and distribution.
7. Convert a set of shell scripts to a typed language, with verified output parity.
8. Apply the style standard to dozens of modules in the repository, validating each one.
9. Build a multi-screen dashboard from a prototype.
10. Implement a device configurator from already decoded captures.
11. Reprocess and validate a historical archive, fixing the failures found along the way.
12. Containerize an old environment and resolve the library incompatibilities one by one.
13. Build a mobile app from the command line all the way to the installable package.
14. Fix a series of bugs from a backlog, with one logical change per bug.
15. Build a retrieval pipeline over a document base, with evaluation.
16. Write the complete documentation of an API (reference and examples) by reading the code.
17. Write the firmware of a small device with several screens, sensors and navigation.
18. Check an application against a security checklist and apply the fixes.
19. Build a scoring pipeline with training, validation and output generation.
20. Execute an already approved multi-step refactoring plan, running the tests at each stage.

### max

Not a rung. In most cases, moving up to Opus pays off more than Sonnet at `max`. It fits a hard but well-bounded problem when you want to spare the Opus quota.

1. Find the cause of a subtle numerical difference (order of 1e-3) between two already isolated implementations.
2. Show that two implementations of an algorithm are equivalent, or find the counterexample.
3. Resolve a race condition in asynchronous code within a single module.
4. Derive and implement a formula from a paper, checking units and signs.
5. Second attempt at a bug that Sonnet `high` did not solve, before escalating to Opus.
6. Final line-by-line review of a critical script that runs unattended in production.
7. Optimize a critical numerical loop (vectorization, compiled kernel) with proof of equivalence.
8. Work out a poorly documented binary format from samples.
9. Design the optimal matching algorithm between two sets, with complexity analysis.
10. Verify the consistency between a database schema and its migrations when real data is at stake.
11. Resolve an extensive merge conflict between two branches that diverged heavily.
12. Follow a deep traceback in a third-party library down to the root cause.
13. Write a parser grammar with many edge cases and demonstrate its coverage.
14. Check the math of a hand-implemented evaluation metric.
15. Rewrite a slow SQL query based on its execution plan.
16. Find a systematic error in a coordinate or unit conversion pipeline.
17. Design the state machine of a device with all transitions and failure modes.
18. Assess, case by case, whether an API change breaks existing clients.
19. Hard problem at a time of tight quota, with Opus unavailable.
20. Independent cross-check of a solution produced by another model.

---

## Opus 5.5

### low

Not a rung: the orchestrator does these judgment calls itself. Listed to show what the family is for even at its cheapest level.

1. Quick opinion on which of two architecture approaches to choose.
2. Name a project, module or API with good judgment.
3. Review the tone of a delicate email to a client.
4. One-line verdict on whether an implementation plan makes sense.
5. Explain a hard concept briefly and correctly (for example why a confidence interval is not a probability of the parameter).
6. Choose the right library for a problem among three candidates.
7. Identify the main risk in a sensitive piece of code.
8. Rewrite a paragraph of a technical paper while keeping its precision.
9. Decide the order of steps of an already decomposed task (light orchestration).
10. Interpret an obscure error message without access to the code.
11. Suggest the most likely cause of an incident described in text.
12. Assess whether a statistical result is plausible.
13. Translate technical text with precise domain terminology.
14. Answer a conceptual machine learning question (for example when to use blocked validation).
15. Point out the logical flaw in a short argument.
16. Choose the best title and abstract among candidate versions.
17. Classify the complexity of a task for routing when the case is ambiguous.
18. Give quick feedback on a dashboard layout.
19. Summarize a scientific paper while preserving its caveats.
20. Decide whether it is worth raising the effort or the model for a subproblem.

### medium

The documented default, and the level at which Opus 5.5 carries a multi-file change through a large repository until its tests pass.

1. Plan the implementation of a medium feature before delegating execution to Sonnet.
2. Review a pull request with attention to design decisions, not just bugs.
3. Write the technical specification of an endpoint or service.
4. Draft the methods section of a report from the code and notes.
5. Design the data schema of a new product.
6. Debug a bug that crosses two layers of the system.
7. Carry a cohesive multi-file change through a large repository until its tests pass.
8. Design the validation strategy of a predictive model.
9. Refactor a module when there are interface decisions to make.
10. Compare three infrastructure options with a cost-benefit analysis.
11. Write the system prompt of a document-writing agent.
12. Analyze the results of an experiment and suggest the next ones.
13. Draft the response to a reviewer or auditor.
14. Prepare an infrastructure migration plan with stages and rollback.
15. Diagnose the performance drop of a model or service in production.
16. Structure a domain knowledge base for use by an LLM.
17. Assess a commercial proposal or project scope and point out the gaps.
18. Turn a client's vague requirements into a prioritized backlog.
19. Design the hierarchy of subagents and skills of a workflow.
20. Audit an analysis script for methodological errors.

### high

1. Design the architecture of a new system (for example tiles of a large dataset rendered on the client).
2. Find the root cause of a bug that resisted two attempts by Sonnet.
3. Design an objective detection or classification algorithm from structured inputs.
4. Review the methodology of a model in search of data leakage.
5. Write a long technical report with cohesive argumentation.
6. Debug concurrency or data corruption in a multi-stage pipeline.
7. Design a deterministic classifier from a set of signals.
8. Reverse engineer the protocol of your own device from traffic captures.
9. Review the design of a public API for authentication, authorization and data exposure.
10. Plan the refactoring of a large legacy codebase in safe stages.
11. Design the statistical post-processing of an ensemble of models.
12. Critically assess a scientific paper and redo its main calculation.
13. Decompose a large project into tasks routable to smaller models.
14. Optimize a system with a non-obvious bottleneck (I/O, serialization, network).
15. Design the unified data model of several sources with inconsistent metadata.
16. Write the evaluation plan of an AI agent, with metrics and test cases.
17. Resolve the divergence between two data sources that should agree.
18. Design a sampling or downsampling strategy with statistical justification.
19. Do the competitive and strategic analysis of a product, with recommendations.
20. Arbitrate an architecture trade-off with many constraints (cost, latency, maintenance).

### xhigh

Needs the user's approval. Turns run longer than on earlier Opus models at this level.

1. Autonomously implement a multi-part system designed in the previous stage.
2. Migrate a codebase with hundreds of files, with continuous verification.
3. Investigate a production bug for hours, raising and discarding hypotheses with experiments.
4. Build and evaluate a complete machine learning pipeline, iterating on the results.
5. Rewrite a legacy system in a new architecture while keeping output parity.
6. Orchestrate subagents in a multi-hour task, integrating and checking the results.
7. Implement the algorithm of a complex paper and reproduce its figures.
8. Audit an entire repository (correctness, security, performance) and apply the fixes.
9. Develop a real-time processing app with ingestion, clustering, tracking and visualization.
10. Unify several databases into a single one, with quality control and documentation.
11. Deep literature research with a synthesis report and supporting code.
12. Run the ablation experiments of a model, analyze and report.
13. Port a firmware to another platform, resolving peripheral differences.
14. Build a diagnostic tool with several modules and protocols.
15. Write a complete manuscript from the results, with figures and internal review.
16. Implement an end-to-end alerting system with load tests.
17. Restructure a server's infrastructure (containers, proxy, backups) with a rollback plan.
18. Create and validate a complete public repository (code, tests, documentation, CI).
19. Reanalyze a multi-year dataset with a new methodology and compare it with the old one.
20. Execute a research plan in which each result redefines the next stage.

### max

Reached only by escalation, with the user's approval. The documentation warns that `max` tends to overthink and has diminishing returns.

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
17. Interpretation of an atypical case in which the models or sources diverge strongly.
18. Decoding the protocol of your own device with unknown checksums and fields.
19. Design of the evaluation of a product whose error has asymmetric cost.
20. Subproblem in which the orchestrator already tried `xhigh` and verification failed.

---

## Fable 5.1

Reached by escalation from Opus or by an explicit `user_floor`, with the user's approval, and only when the rungs are active. The documentation says Fable at `low` is often competitive with Opus and Sonnet on cost per task while performing better, and that its gains grow with effort.

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
12. Check the interpretation of an unexpected result.
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
4. Diagnose a problem that crosses theory, statistics and software.
5. Design the target architecture of a platform with several products.
6. Review a system design made by Opus and propose changes.
7. Prepare the product strategy and technical roadmap from a market analysis.
8. Write a research or grant project proposal.
9. Interpret a set of experiments with ambiguous results.
10. Formulate the conceptual scheme of a classifier for a new domain.
11. Design the operational validation protocol of a predictive system.
12. Synthesize scattered literature into a coherent framework.
13. Redesign an entire pipeline that grew without planning.
14. Define the model routing criteria and the boundary cases.
15. Assess several modeling approaches and recommend one, with justification.
16. Structure a long scientific argument before writing.
17. Plan the integration of a new data source across the whole product chain.
18. Review a complex technical scope in search of risks.
19. Design a quality control system that combines rules, statistics and learning.
20. Decide what to cut from a project that does not fit the deadline.

### high

1. Original research: propose and develop a new modeling method.
2. Design and implement a complex system for which Opus `high` delivered an insufficient solution.
3. Debug a failure that arises from the interaction between several systems.
4. Write a complete scientific paper with a methodological contribution.
5. Reformulate a hybrid model with a new architecture.
6. Analyze an extreme event or incident in depth with multiple data sources.
7. Design a new tracking or detection algorithm with sound foundations.
8. Audit the entire methodology of a dissertation or technical report.
9. Design the rendering of a large dataset on the GPU under bandwidth and precision constraints.
10. Build an ensemble prediction scheme with calibration and verification.
11. Translate a vague business problem into a mathematical formulation and solution.
12. Reengineer a large codebase with a change of paradigm.
13. Develop an objective detection method and validate it against manual analysis.
14. Analyze the technical and economic feasibility of a new product.
15. Design a sensitivity study with control of confounding factors.
16. Do the critical synthesis of a research field, identifying gaps.
17. Solve an optimization problem with many constraints.
18. Design firmware and electronics together, with real-time constraints.
19. Diagnose the systematic divergence between a model and observations with testable hypotheses.
20. Long, underspecified task in which you have to decide what to do, not just how.

### xhigh

1. Autonomous multi-hour research project: hypothesis, experiment, analysis and report.
2. Complete construction of a new product, from scratch to deploy.
3. Full rewrite of a platform with several services.
4. Reproduction of a complex paper and extension of its method.
5. Experiment campaign with dozens of runs and intermediate decisions.
6. Investigation of an open problem with no known solution.
7. Migration of an entire operational chain to a new architecture without downtime.
8. Development of a model and its paper in parallel.
9. Orchestration of many subagents in a project with complex dependencies.
10. Audit and repair of an entire system with deep technical debt.
11. Construction of a broad knowledge base with source verification.
12. Development of a hybrid system with rule-based and learned components.
13. Reprocessing of a long historical archive with a new methodology and complete validation.
14. Design and implementation of a cross-platform app with a backend.
15. Exhaustive comparative study of methods, implementing all of them.
16. Breaking a monolith into services, with tests and data migration.
17. Preparation of a long report with new analyses.
18. Construction of a complete embedded system, from protocol to interface.
19. Multi-hour work in which Opus `xhigh` lost the thread or accumulated errors.
20. Long-horizon task in which an early mistake costs everything that follows.

### max

Not a rung.

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
18. Assessment of a bold hypothesis with all the available evidence.
19. Deadlock in which two `xhigh` runs reached opposite conclusions.
20. Any task in which the cost of being wrong far exceeds the cost of spending the quota.

---

## Classifying operation and flags for route.py

Use this list when unsure about a step's `operation` or flags: find the closest example and copy its classification. The rung and agent names below were checked against the Claude ladder. Codex uses the same operations and flags with its own ladder and its own operation table; use the router's returned agent. If a ladder changes, check the examples again.

The rung does not depend on the amount of code, but on ambiguity, how many components interact, whether the error is reversible and what a silent error costs. 500 lines of boilerplate fit Haiku high; 5 lines fixing a race condition call for Opus high.

In the flags column, `files>3` means the step touches more than three files. `ambiguous` and `critical` are state fields.

### 0. Haiku low — `exec-haiku-low`

One-shot reading with a checkable answer.

| Example | operation | flags |
|---|---|---|
| Summarize an obvious traceback or pull values from a log | `read` | — |
| Extract the fields of a document as JSON | `read` | — |
| Classify a batch of items against a short rubric | `read` | — |
| Translate a list of strings, keeping placeholders | `read` | — |

### 1. Haiku medium — `exec-haiku-medium`

Mechanical work with no decisions, checked by running something.

| Example | operation | flags |
|---|---|---|
| Find where a function is defined and list its call sites | `search` | — |
| Replace a string or rename a variable within one file | `mechanical_edit` | — |
| Reorder sections, sort imports, fix formatting in one file | `mechanical_edit` | — |
| Convert a config dict to JSON or YAML | `mechanical_edit` | — |
| Generate a dependency file from a script's imports | `mechanical_edit` | — |

### 2. Haiku high — `exec-haiku-high`

Small change following an existing pattern, with a test, or mechanical work across many files.

| Example | operation | flags |
|---|---|---|
| Rename a function across the whole package, updating imports | `mechanical_edit` | files>3 |
| Add a command-line argument to an existing script | `tweak` | — |
| Add one more entry to a configuration dictionary | `tweak` | — |
| Write a test for a pure function | `tweak` | — |
| Trivial Dockerfile or proxy configuration change (new route, new environment variable) | `tweak` | — |

### 3. Sonnet medium — `exec-sonnet-medium`

Day-to-day implementation with a clear scope. Also a `tweak` that touches more than three files.

| Example | operation | flags |
|---|---|---|
| New script: download a dataset, validate it and save it as CSV | `implementation` | — |
| Endpoint that reads a file and returns columnar JSON | `implementation` | — |
| Consume a documented REST API and write to a database with an existing schema | `implementation` | — |
| Merge three repeated functions into one generic function with a config dictionary | `implementation` | — |
| Apply a list of small, specified fixes across five pages or modules | `tweak` | files>3 |
| README for a module | `writing` | — |
| Aggregate, compare and plot two series | `data_analysis` | — |

### 4. Sonnet high — `exec-sonnet-high`

Clear scope, but with edge cases that need verification.

| Example | operation | flags |
|---|---|---|
| Fix a bug with a failing test and a clear stack trace | `debugging` | — |
| Vectorize a slow loop without changing the numerical result | `implementation` | critical |
| Parser that must handle time zones, ordering and missing values correctly | `implementation` | critical |
| Migrate five scripts to a new library with identical outputs | `implementation` | files>3 |
| Retry and timeout in a production service's HTTP client, without swallowing errors | `implementation` | critical |

### 5. Opus medium — `exec-opus-medium`

Spans several modules or needs judgment, with a defined goal.

| Example | operation | flags |
|---|---|---|
| API + database when the data model still has to be designed (upsert, dedup, natural key) | `implementation` | ambiguous, critical |
| Refactor across several modules while keeping the external contract | `implementation` | files>3, critical |
| Critical review of a pull request or a production script | `review` | — |
| Concurrency: workers or async handlers with a shared resource | `implementation` | ambiguous, critical |
| Design a public API contract (versioning, error format) | `architecture` | — |
| Cohesive refactor of a whole package that cannot be split | `long_task` | — |

### 6. Opus high — `exec-opus-high`

Costly errors or a non-local cause.

| Example | operation | flags |
|---|---|---|
| Intermittent bug: race condition, memory leak, hang in a native library | `debugging` | ambiguous, critical |
| Intermittent 504 on an endpoint, no stack trace | `debugging` | ambiguous, critical |
| Irreversible data migration in production | `implementation` | files>3, ambiguous, critical |
| Validate a formula or metric against the reference (units, conservation) | `review` | critical |
| Architecture of a new system, or choosing between approaches with hard trade-offs | `architecture` | ambiguous |
| Diagnose a model that generalizes poorly (leakage, sampling bias) | `research` | — |
| Algorithm with no ready reference | `research` | — |
| Security review of a public endpoint | `security` | — |
| Root cause of a failure spanning server, proxy, API and scheduler | `investigation` | — |
| Migrate a whole pipeline (download → processing → API) keeping its outputs | `long_task` | critical |

### 7. Opus xhigh — `exec-opus-xhigh`

Open problem with no known path, or several flags at once. **Needs the user's approval before delegating.** Any combination that adds up beyond this rung stops here, because Opus max is reached only by escalation.

| Example | operation | flags |
|---|---|---|
| Vulnerability hunt on an exposed API (authentication, authorization, injection) | `security` | critical |
| Security audit of a server with several exposed services | `security` | files>3, ambiguous, critical |
| Prove that a numerical method keeps a property in every edge case | `research` | critical |
| Full review of an operational pipeline before it goes to production | `review` | files>3, ambiguous, critical |
| Design a new detection method that will feed a production system | `research` | ambiguous, critical |
| Redesign the architecture of a production system with several services | `architecture` | files>3, ambiguous, critical |
| Production incident with no initial hypothesis, involving several systems | `investigation` | critical |
| Intermittent degradation that may come from the data, the code or the model | `investigation` | ambiguous, critical |
| Rewrite the core of a production system with open architecture decisions | `long_task` | files>3, ambiguous, critical |

### 8. Opus max — `exec-opus-max`

Only by escalation: a step that failed at Opus high or xhigh, or an explicit `user_floor`. **Needs the user's approval.** The examples under Opus `max` above show what to expect from it.

### 9 to 12. Fable low to xhigh — `exec-fable-*`

Inactive by default; when active, reached by escalation from Opus xhigh (which lands on Fable low) or by `user_floor`. **Need the user's approval.** The Fable examples above show what each level is for: `low` for judgment that Opus got wrong, `medium` for investigations and redesigns, `high` for long work where errors are costly, `xhigh` for long, autonomous, ambiguous work.

### Notes on the top rungs

- **Opus max is escalation-only.** No combination of operation and flags lands on it; only a failure at a lower Opus rung or a `user_floor` does. At `max`, Opus runs several times longer than at `medium` for a marginal gain on most work.
- **Security stops at Opus max.** All current families run cybersecurity classifiers, and finding vulnerabilities in source code is allowed on all of them. What is specific to Fable is that its measured bug-finding gains exclude security analysis, so its usage credits buy nothing there. That is why `security` has its ceiling at Opus max (`ceiling_by_operation` in `ladder.json`). If the step fails at the ceiling, the router stops and tells you to ask the user.
- **The position of Fable low above Opus max follows the documentation**, which says Fable at `low` often exceeds the `xhigh` and `max` performance of earlier models. There is still no local measurement; compare verified outcomes and token use before treating that order as measured.
- **Fable is off by default (`active: false`)** because, depending on the plan, it bills usage credits instead of drawing on the subscription, and in `-p` mode it bills without asking. Turn it on only if `/model` does not show "Requires usage credits" on the Fable row.
