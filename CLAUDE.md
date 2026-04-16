# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This project is in **initial setup phase**. The architecture below is the intended design — directories and scripts referenced here need to be created.

## WAT Architecture

This system is built on the WAT (Workflows, Agents, Tools) pattern:

- **Workflows** (`workflows/`) — Markdown SOPs defining objectives, required inputs, tool call sequences, expected outputs, and edge-case handling
- **Agent** (Claude) — Reads workflows, sequences tool calls, handles failures, asks clarifying questions. If a task requires calling an API, read the relevant workflow first, gather inputs, then execute the appropriate tool — don't attempt API calls directly
- **Tools** (`tools/`) — Python scripts that do actual work: parsing resumes, scoring candidates, calling the Claude API, writing reports. Credentials live in `.env`

The separation matters: when AI handles every step directly, compounding error rates (~90%^5 = 59%) make multi-step tasks unreliable. Deterministic scripts handle execution; Claude handles orchestration.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
```

## Pipeline Commands (Target State)

```bash
# Step 1: Parse resumes → .tmp/resumes/*.json
python tools/parse_resumes.py --input resumes/

# Step 2: Score candidates against job description → .tmp/scores.json
python tools/score_candidates.py --job config/job_description.json

# Step 3: Generate ranked shortlist report → output/shortlist_YYYY-MM-DD.pdf
python tools/generate_report.py

# Single resume
python tools/score_candidates.py --resume resumes/candidate.pdf --job config/job_description.json
```

Delete `.tmp/` before a fresh run.

## Configuration

| File | Purpose |
|---|---|
| `config/job_description.json` | Role title, required skills, experience requirements, scoring weights |
| `config/screening_criteria.json` | Evaluation rubric: dimensions and weights |

## Data Flow

```
config/job_description.json ──► score_candidates.py (Claude API)
resumes/*.pdf                        │
      │                              ▼
parse_resumes.py              .tmp/scores.json
      │                              │
.tmp/resumes/*.json ──────► generate_report.py
                                     │
                        output/shortlist_YYYY-MM-DD.pdf
```

## Operating Principles

1. **Reuse before building** — check `tools/` before writing new scripts
2. **Update workflows on failure** — document rate limits, timing quirks, and unexpected behavior in the relevant workflow file; don't overwrite without reason
3. **API calls cost money** — confirm with the user before re-running scripts that hit the Anthropic API
4. **Self-improvement loop**: identify what broke → fix the tool → verify → update the workflow
