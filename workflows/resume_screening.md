# Workflow: Resume Screening

## Objective
Screen a batch of resumes against a job description and produce a ranked shortlist PDF report.

## Inputs Required
| Input | Location | Notes |
|---|---|---|
| Job description | `config/job_description.json` | Edit before each new role |
| Screening criteria | `config/screening_criteria.json` | Scoring rubric; adjust weights as needed |
| Resumes | `resumes/` | PDF or DOCX files |
| API key | `.env` → `ANTHROPIC_API_KEY` | Never commit `.env` to git |

## Outputs
| Output | Location |
|---|---|
| Parsed resume text | `.tmp/resumes/<name>.json` |
| Candidate scores | `.tmp/scores.json` |
| Shortlist PDF | `output/shortlist_YYYY-MM-DD.pdf` |

---

## Full Pipeline

### Step 0 — Prepare for a fresh run
```bash
rm -rf .tmp/
```

### Step 1 — Parse resumes
```bash
python tools/parse_resumes.py --input resumes/
```
Reads every `.pdf` / `.docx` in `resumes/` and writes `.tmp/resumes/<name>.json`.

**Edge cases:**
- Scanned PDFs (image-only) will fail with "No text could be extracted". Use an OCR tool first.
- Password-protected PDFs will raise an exception; decrypt before parsing.
- Very short extractions (< 200 chars) usually indicate extraction failure.

### Step 2 — Score candidates ⚠️ API call — confirm first
```bash
python tools/score_candidates.py --job config/job_description.json
```
Calls `claude-sonnet-4-6` once per resume. Prompt caching reduces cost for batches — the
system prompt and job description are cached and only the per-resume text is charged at full rate.

**Single resume:**
```bash
python tools/score_candidates.py \
  --resume .tmp/resumes/candidate.json \
  --job config/job_description.json
```

**Edge cases:**
- If Claude returns malformed JSON, the candidate is skipped with a warning.
- Rate-limit errors (HTTP 429): wait ~60 s and re-run; already-scored candidates will need
  re-scoring (delete `.tmp/scores.json` and rerun, or pass `--resume` for individuals).
- If `ANTHROPIC_API_KEY` is missing, the script exits with an auth error immediately.

### Step 3 — Generate report
```bash
python tools/generate_report.py
```
Reads `.tmp/scores.json` and writes `output/shortlist_YYYY-MM-DD.pdf`.

---

## Single-Resume Quick Path
```bash
# Parse one resume
python tools/parse_resumes.py --input resumes/alice.pdf

# Score it
python tools/score_candidates.py \
  --resume .tmp/resumes/alice.json \
  --job config/job_description.json

# Generate report
python tools/generate_report.py
```

---

## Customising the Job Description
Edit `config/job_description.json`:
- `role_title` — appears in the report header
- `required_skills` / `preferred_skills` — Claude uses these for `skills_match` scoring
- `experience_years_min` — sets the floor for experience scoring
- `scoring_weights` — must sum to 1.0; weight keys must match criteria dimension names

## Customising Scoring Criteria
Edit `config/screening_criteria.json`:
- Add/remove dimensions (keep `scoring_weights` in sync)
- Adjust `scoring_guide` bands to change the scoring bar for each dimension
- Update `recommendation_thresholds` to change STRONG_YES / YES / MAYBE / NO cutoffs

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "No text could be extracted" | Scanned/image PDF | Run through OCR (e.g. Adobe, Tesseract) first |
| JSON parse error in scoring | Claude returned extra text | Usually transient; re-run the individual resume |
| Report is empty | `scores.json` not found | Run Step 2 first |
| Low scores across all candidates | Overly strict criteria | Adjust `scoring_guide` or weights in config |
| Very slow scoring | Large batch | Use `tqdm` progress bar; consider running overnight |

---

## Known Limitations
- Text extraction quality depends on how the PDF was created. Complex layouts (tables, columns) may lose structure.
- Claude scoring is probabilistic — minor phrasing changes can shift scores by a few points.
- The system does not currently handle multiple pages where content wraps unexpectedly.

## Self-Improvement Loop
If a tool fails or produces poor results:
1. Identify the root cause (wrong config? extraction failure? bad prompt?)
2. Fix the tool or config
3. Re-run the affected step
4. Document the fix in the relevant section above before closing the session
