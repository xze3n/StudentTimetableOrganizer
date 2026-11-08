# Milestone 2: Proposed Architecture and Project Plan

Status: draft. Design decisions will be filled in after the team interview.

## Submission

Upload the proposed architecture (diagrams and explanation) and project plan to GitHub in the `docs/` folder. This document will contain both.

Explain how the project idea becomes a system the team can build and evaluate, including the reasons behind design choices.

## 1. Problem and data

The existing [RFC](RFC.md) proposes a conversational student timetable assistant. Students describe preferences, and the system uses official timetable information and a dedicated scheduling solver to propose a timetable and check for conflicts.

Confirmed scope:

- UBB Cluj, Faculty of Mathematics and Computer Science.
- Support all undergraduate study years: three or four, depending on specialization.
- Answer only questions about timetables and timetable organization. Course content, course documents, and prerequisite reasoning are outside scope.
- Use official published timetables. The historical timetables are available from 2014; which versions to ingest remains undecided.
- Delegate conflict checking to a dedicated solver.
- Each request uses one selected academic year and semester; historical versions remain separate.
- The student provides specialization, teaching language, study year, group, and subgroup. The assistant asks for missing details and uses the published group timetable as the starting set of activities.
- Switching seminar and lab groups is a core feature. Alternatives must stay within the same specialization, teaching language, and study year. Lectures remain fixed initially.
- A timetable alternative does not guarantee permission to attend another group. A reported refusal excludes the specific seminar/lab alternative for the selected semester. Ask for clarification if the restriction is ambiguous, then rerun scheduling.
- Flexible preferences may be traded off; explicit availability restrictions are mandatory. Never silently drop a required activity or relax a mandatory restriction. Explain infeasibility and ask what can change.
- Rank valid schedules by the student's stated preferences; ask for priority when preferences conflict. Minimize group changes when schedules are otherwise equivalent.
- Expose a tool that fetches official timetables from a UBB timetable URL. The published URL structure identifies the academic year and semester; fetching the same URL again must support updated timetable content.
- Fetch only the semester explicitly requested by the student; do not automatically fetch older semesters. Cache the fetched data locally, support explicit refresh, and clearly report fetching failures and any use of cached data.
- RAG retrieves timetable information using semester and student-context filters. Exact times, alternatives, and conflicts come from structured records and the solver, which receives the complete matching activity records rather than only retrieved chunks.

This narrows the RFC references to course catalogs and prerequisite rules and defers its calendar-export proposal.

To confirm:

- Concrete parsing and retrieval components. Python, SQLite, OR-Tools, and a local MCP server are approved.

Official source examples:

- [2026–2027, semester I](https://www.cs.ubbcluj.ro/files/orar/2026-1/) and [2025–2026, semester I](https://www.cs.ubbcluj.ro/files/orar/2025-1/) illustrate the year/semester URL structure.
- [Student timetable index](https://www.cs.ubbcluj.ro/files/orar/2026-1/tabelar/index.html) lists specialization, language, and available study years.
- [Sample tabular timetable](https://www.cs.ubbcluj.ro/files/orar/2025-1/tabelar/I1.html) contains day, time, frequency, room, formation, activity type, discipline, and teacher. The precise interpretation of frequency labels must be validated during ingestion.

## 2. Golden dataset

Create 40 manually reviewed timetable scenarios: 10 for development and 30 held out for evaluation. Another teammate reviews each case.

Cover timetable lookups, seminar/lab group switching, teacher refusals, unavailable periods, alternating weeks, missing details, nonexistent activities, and impossible requests. Record expected facts, supporting source records, expected tool behavior, and scheduling constraints.

For scheduling tasks, accept any valid timetable satisfying the specified constraints rather than require a single exact timetable. Concrete scoring metrics remain to be finalized.

## 3. RAG design

Use one complete timetable activity as a searchable record, retaining group, type, day, time, room, teacher, frequency, semester, specialization, and source metadata. The solver receives all matching structured records from SQLite; it does not rely on a top-k retrieval result to construct or validate schedules.

Follow the Week 5–6 lab setup with the Nomic embedding model through LM Studio and persistent Chroma for semantic retrieval. The lab's 90-word chunks and 15-word overlap target prose; this project keeps each timetable activity intact instead.

Run two comparisons from the lab: TF-IDF lexical retrieval versus Chroma vector retrieval, then basic retrieve-and-answer RAG versus corrective RAG with one retry maximum. Measure retrieval separately from answer grounding, citations, model calls, and latency. Do not assume one approach is better before evaluating the timetable questions.

Still to decide: evidence citation format and how the agent handles missing or conflicting timetable evidence.

### Lab guidance under consideration

The [Week 5–6 lab README](../../../Labs/Week5-6/lab03_rag/README.md) and [instructor notes](../../../Labs/Week5-6/lab03_rag/INSTRUCTOR.md) use Nomic (`text-embedding-nomic-embed-text-v1.5`) through LM Studio and persistent Chroma. The notebook uses 90-word chunks with 15-word overlap for prose documents; timetable records may need a different chunking unit to keep complete activities intact.

The lab compares a TF-IDF lexical baseline with vector retrieval, and demonstrates basic RAG, HyDE, corrective RAG with one retry, and agentic RAG with two searches maximum. These demonstrations are options to evaluate, not evidence that every variant is needed or that one is universally better. Keep retrieval quality separate from answer grounding, model-call count, and latency when comparing them.

The proposed Nomic model and Chroma follow the lab and have been approved. The earlier multilingual-e5-small suggestion is no longer under consideration.

## 4. Agent, tools, and architecture

Approved local components:

- Python application.
- SQLite for complete structured timetable records.
- OR-Tools for scheduling and constraint checking.
- A local MCP server using stdio to expose tools to the agent.

To decide:

- Agent decisions and when it asks the student for clarification.
- Tools for looking up official timetable records, retrieving timetable information, solving schedules, and validating results. Calendar export is deferred.
- Which tools the MCP server exposes and their inputs and outputs.
- Responsibilities of the language model, retrieval system, and scheduling solver.

Add a Mermaid architecture diagram and explain the request flow once these decisions are agreed.

## 5. Model choice

**Selected model: Qwen 3.5 9B.**

We chose this model because it was the first model we had to download in the first laboratory, and every team member already has it. Using the same available model gives the team a shared starting point and avoids additional downloads before development begins.

This is a practical starting choice; task performance has not yet been measured. Evaluate preference extraction, tool selection, and grounded answers before deciding whether another model is needed.

## 6. Weekly plan through Week 14

Deferred at the user's request: the current interview concerns the narrow timetable RFC/RAG design. The original assignment still requests a weekly plan through Week 14; that submission requirement remains unresolved.

The final plan must give a deliverable and experiment for every remaining week, covering:

- Dataset collection and ingestion.
- Golden dataset creation and review.
- Retrieval baseline and RAG comparisons.
- MCP tools and scheduling solver integration.
- End-to-end evaluation and error analysis.
- Improvements, demo preparation, and the Week 14 final progress presentation.

## Interview status

Settled: timetable-only scope, target faculty and study-year coverage, dedicated conflict-checking solver, model choice, deferred calendar export, semester isolation, student inputs, mandatory seminar/lab group switching, and hard constraints versus flexible preferences.

Also settled: specific refused alternatives, preference-based ranking, a URL-based fetching tool, and separation of RAG retrieval from complete solver input.

Also settled: fetch only the requested semester, explicit refresh and transparent cache use, Python/SQLite/OR-Tools/local MCP, and 40 reviewed evaluation scenarios split into 10 development and 30 held-out cases.

Also settled: complete timetable activity records as the retrieval unit, Nomic through LM Studio, persistent Chroma, and comparisons of TF-IDF versus vector retrieval and basic versus corrective RAG.

Next: settle citations and missing/conflicting evidence behavior, MCP tool interfaces, and evaluation metrics.
