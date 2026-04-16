#!/usr/bin/env python3
"""
Step 2: Score parsed resumes against the job description using Claude.

Reads .tmp/resumes/*.json (or a single file) and writes .tmp/scores.json.

Prompt caching is used so the system prompt + job context is only charged once
per batch; only the per-resume text varies.

Usage:
    python tools/score_candidates.py --job config/job_description.json
    python tools/score_candidates.py --resume .tmp/resumes/alice.json \\
                                     --job config/job_description.json

NOTE: This script calls the Anthropic API and costs money.
      Confirm before running on large batches.
"""
import argparse
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

PARSED_DIR = Path(".tmp/resumes")
SCORES_FILE = Path(".tmp/scores.json")
CRITERIA_FILE = Path("config/screening_criteria.json")

# ── system prompt (will be prompt-cached) ────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert technical recruiter and hiring manager. Your task is to \
evaluate a candidate's resume against a specific job description and return \
a structured JSON assessment.

Be objective, evidence-based, and consistent. Score each dimension on a \
0–100 scale using the provided scoring guides. Do not invent information \
not present in the resume.

You MUST respond with a single valid JSON object — no markdown fences, no \
extra text — matching this schema exactly:

{
  "candidate_name": "<string or null>",
  "overall_score": <integer 0-100>,
  "dimension_scores": {
    "skills_match":   <integer 0-100>,
    "experience":     <integer 0-100>,
    "education":      <integer 0-100>,
    "communication":  <integer 0-100>,
    "overall_fit":    <integer 0-100>
  },
  "strengths": ["<string>", ...],
  "concerns":  ["<string>", ...],
  "recommendation": "<STRONG_YES | YES | MAYBE | NO>",
  "summary": "<2-3 sentence narrative summary>"
}
"""

# ── helpers ──────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_job_context(job: dict, criteria: dict) -> str:
    """Serialize job description + scoring criteria into a prompt block."""
    lines = [
        f"# Job: {job['role_title']}",
        "",
        job.get("summary", ""),
        "",
        "## Required Skills",
        *[f"- {s}" for s in job.get("required_skills", [])],
        "",
        "## Preferred Skills",
        *[f"- {s}" for s in job.get("preferred_skills", [])],
        "",
        f"## Experience: {job.get('experience_years_min', 'N/A')}+ years "
        f"(preferred: {job.get('experience_years_preferred', 'N/A')}+)",
        f"## Education: {job.get('education', 'N/A')}",
        "",
        "## Scoring Weights",
    ]
    for dim, weight in job.get("scoring_weights", {}).items():
        lines.append(f"- {dim}: {int(weight * 100)}%")

    lines += ["", "## Dimension Scoring Guides"]
    for dim in criteria.get("dimensions", []):
        lines.append(f"\n### {dim['label']} ({dim['name']})")
        lines.append(dim["description"])
        for band, desc in dim.get("scoring_guide", {}).items():
            lines.append(f"  {band}: {desc}")

    thresholds = criteria.get("recommendation_thresholds", {})
    lines += [
        "",
        "## Recommendation Thresholds",
        f"- STRONG_YES: overall_score >= {thresholds.get('STRONG_YES', 80)}",
        f"- YES:         overall_score >= {thresholds.get('YES', 65)}",
        f"- MAYBE:       overall_score >= {thresholds.get('MAYBE', 50)}",
        f"- NO:          overall_score <  {thresholds.get('MAYBE', 50)}",
    ]
    return "\n".join(lines)


def weighted_score(dimension_scores: dict, weights: dict) -> int:
    total = sum(
        dimension_scores.get(dim, 0) * weight
        for dim, weight in weights.items()
    )
    return round(total)


# ── scoring ──────────────────────────────────────────────────────────────────

def score_resume(
    client: anthropic.Anthropic,
    resume: dict,
    job_context_block: list,   # pre-built cached content block list
    job: dict,
    criteria: dict,
) -> dict:
    """Call Claude to evaluate a single resume. Returns the parsed score dict."""
    resume_text = (
        f"Candidate file: {resume['filename']}\n\n"
        f"{resume['raw_text']}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": job_context_block
                + [
                    {
                        "type": "text",
                        "text": f"\n---\nResume to evaluate:\n\n{resume_text}",
                    }
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)

    # Recompute overall_score from dimension_scores + weights so it's consistent
    result["overall_score"] = weighted_score(
        result.get("dimension_scores", {}),
        job.get("scoring_weights", {}),
    )

    # Derive recommendation from thresholds if not already valid
    thresholds = criteria.get("recommendation_thresholds", {})
    score = result["overall_score"]
    if score >= thresholds.get("STRONG_YES", 80):
        result["recommendation"] = "STRONG_YES"
    elif score >= thresholds.get("YES", 65):
        result["recommendation"] = "YES"
    elif score >= thresholds.get("MAYBE", 50):
        result["recommendation"] = "MAYBE"
    else:
        result["recommendation"] = "NO"

    # Attach source metadata
    result["source_file"] = resume["filename"]
    result["email"] = resume.get("email")
    result["phone"] = resume.get("phone")

    # Cache usage info (for transparency / cost awareness)
    usage = response.usage
    result["_cache_read_tokens"] = getattr(usage, "cache_read_input_tokens", 0)
    result["_cache_created_tokens"] = getattr(usage, "cache_creation_input_tokens", 0)
    result["_output_tokens"] = usage.output_tokens

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score parsed resumes against a job description via Claude API."
    )
    parser.add_argument(
        "--job", default="config/job_description.json",
        help="Path to job_description.json"
    )
    parser.add_argument(
        "--criteria", default=str(CRITERIA_FILE),
        help="Path to screening_criteria.json"
    )
    parser.add_argument(
        "--resume",
        help="Score a single parsed resume JSON. Omit to score all in .tmp/resumes/"
    )
    parser.add_argument(
        "--output", default=str(SCORES_FILE),
        help=f"Output path for scores JSON (default: {SCORES_FILE})"
    )
    args = parser.parse_args()

    job_path = Path(args.job)
    criteria_path = Path(args.criteria)

    if not job_path.exists():
        print(f"ERROR: {job_path} not found.", file=sys.stderr)
        sys.exit(1)
    if not criteria_path.exists():
        print(f"ERROR: {criteria_path} not found.", file=sys.stderr)
        sys.exit(1)

    job = load_json(job_path)
    criteria = load_json(criteria_path)

    # Collect resume files
    if args.resume:
        resume_files = [Path(args.resume)]
    else:
        resume_files = sorted(PARSED_DIR.glob("*.json"))

    if not resume_files:
        print(
            f"No parsed resume JSONs found in {PARSED_DIR}/\n"
            "Run parse_resumes.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Scoring {len(resume_files)} resume(s) for: {job['role_title']}")
    print(f"Model: {MODEL}\n")

    # Build the cached job-context block once (shared across all resume calls)
    job_context_text = build_job_context(job, criteria)
    job_context_block = [
        {
            "type": "text",
            "text": job_context_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    client = anthropic.Anthropic()

    scores = []
    total_cache_read = 0
    total_cache_created = 0

    for resume_path in tqdm(resume_files, desc="Scoring"):
        try:
            resume = load_json(resume_path)
            result = score_resume(client, resume, job_context_block, job, criteria)
            scores.append(result)
            total_cache_read += result.pop("_cache_read_tokens", 0)
            total_cache_created += result.pop("_cache_created_tokens", 0)
        except json.JSONDecodeError as exc:
            print(f"\nWARN: Could not parse Claude response for {resume_path.name}: {exc}")
        except Exception as exc:
            print(f"\nERROR scoring {resume_path.name}: {exc}")

    # Sort by score descending
    scores.sort(key=lambda x: x.get("overall_score", 0), reverse=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nResults saved to {output_path}")
    print(f"Cache tokens — read: {total_cache_read:,}  created: {total_cache_created:,}")
    print("\nTop candidates:")
    for i, s in enumerate(scores[:5], 1):
        name = s.get("candidate_name") or s.get("source_file", "Unknown")
        print(f"  {i}. {name:30s}  score={s['overall_score']:3d}  {s['recommendation']}")


if __name__ == "__main__":
    main()
