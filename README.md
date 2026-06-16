# DAI Resumes

A repository for a **Data & AI hiring team** to store résumés **by role**, define
a ranking rubric per role, and run AI-driven assessments to surface top
candidates. Built around three ideas:

1. **Résumés are stored by role** — drop files into `roles/<role>/resumes/`.
2. **Criteria are defined per role** — a rubric in `roles/<role>/role.yaml`, with
   an optional job description. You can also auto-draft a rubric from a JD.
3. **Pools and criteria are decoupled** — you can assess *any* résumé pool against
   *any* role's criteria. That makes the seniority ladder (Associate → Principal
   Data Engineer) and overlap between roles easy to handle: score the Data
   Engineer applicant pool against the Senior Data Engineer rubric in one command.

Scoring uses the [Claude API](https://platform.claude.com) (model
`claude-opus-4-8`) with structured outputs, so every candidate gets an
explainable, per-criterion breakdown.

---

## How it works

```
roles/<role>/role.yaml          ← criteria (may `extends:` a family template)
roles/<role>/job_description.md  ← optional JD, fed to the scorer
roles/<role>/resumes/*.pdf|docx  ← the pool submitted for this role
        │
        ▼
  assess  <role>  --pool <any role or path>     ← criteria ✕ pool, decoupled
        │
        ▼  Claude API, structured per-criterion scoring
  results/<role>/<label>/ranking.md + *.json
```

---

## Seeded roles

The repo ships with rubrics for the team's hiring families. Run
`python -m src.cli list-roles` to see them:

| Family | Roles | Template |
| ------ | ----- | -------- |
| Data Engineer | `associate_data_engineer`, `data_engineer`, `senior_data_engineer`, `principal_data_engineer` | `templates/data_engineer.yaml` |
| Data Architect | `data_architect` | `templates/data_architect.yaml` |
| BI Developer | `bi_developer` | `templates/bi_developer.yaml` |
| AI Engineer | `ai_engineer` | `templates/ai_engineer.yaml` |

The four Data Engineer roles **share one rubric** (the template) and only
override the experience weight and must-haves per level — so the difference
between Associate and Principal is purely the seniority bar, not a rewritten
rubric.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # set ANTHROPIC_API_KEY
```

```bash
# 1. Drop résumés into a role's pool
#    roles/data_engineer/resumes/jane_doe.pdf
#    roles/data_engineer/resumes/john_smith.docx

# 2. Assess them against that role and rank
python -m src.cli rank data_engineer

# 3. Read the shortlist
#    results/data_engineer/applicants/ranking.md
```

---

## Commands

```bash
# Discover what's configured
python -m src.cli list-roles
python -m src.cli list-templates

# Assess a role against its own applicant pool
python -m src.cli rank <role>

# Assess any pool(s) against a role's criteria (the cross-pool feature)
python -m src.cli assess <role> --pool <role-or-path> [--pool ...] [--label NAME]

# Score a single file ad hoc
python -m src.cli score-file <role> path/to/resume.pdf

# Draft a role's rubric from a job description (uses Claude)
python -m src.cli draft-criteria <role> --jd path/to/jd.txt \
    [--family data_engineer] [--seniority senior] [--extends data_engineer]
```

### Cross-pool assessment (the scalability piece)

A résumé submitted for one posting is often relevant to another — the same
person may fit Data Engineer *and* Senior Data Engineer. You don't have to
re-collect résumés. Point a role's criteria at another pool:

```bash
# Score everyone who applied for Data Engineer against the SENIOR rubric
python -m src.cli assess senior_data_engineer --pool data_engineer

# Combine multiple pools into one ranking for a newly posted role
python -m src.cli assess principal_data_engineer \
    --pool senior_data_engineer --pool data_engineer --label talent_pool

# A pool can also be any folder or glob
python -m src.cli assess ai_engineer --pool ./inbox/2026-q3/
```

Results go to `results/<role>/<label>/`. When a run draws from more than one
pool, `ranking.md` adds a **Source** column so you can see which posting each
candidate originally applied to.

---

## Defining and tuning criteria

A role file is small when it extends a family template — it sets the seniority
and overrides only what differs:

```yaml
# roles/senior_data_engineer/role.yaml
role: senior_data_engineer
title: "Senior Data Engineer"
seniority: senior          # associate | mid | senior | principal
extends: data_engineer     # template in templates/

criteria:
  - id: experience_relevance
    weight: 4              # heavier than mid-level; other criteria inherited

must_haves:
  - "5+ years of professional data engineering experience."
  - "Has led the design of production data pipelines or platforms."
```

The template (`templates/data_engineer.yaml`) defines the full criteria list,
the 0–5 scale, and the default must-haves. Weights are relative and normalized
automatically. `seniority` is passed to the model so scores are calibrated to
the level.

### Starting from a job description

Drop in a JD and let Claude propose a starter rubric:

```bash
python -m src.cli draft-criteria staff_data_engineer \
    --jd ./jds/staff_de.txt --family data_engineer --seniority principal
```

This writes `roles/staff_data_engineer/role.yaml` (and a copy of the JD). Review
and tune the weights, then add résumés and `assess`.

If you'd rather hand-write a role, copy an existing `roles/*/role.yaml` or extend
a template.

---

## Continuous integration

Two GitHub Actions workflows are included:

- **`CI`** (`.github/workflows/ci.yml`) — on every push/PR: installs deps,
  compiles the sources, and validates that every role rubric resolves (template
  `extends`, weights normalize, criteria well-formed). No API key needed.
- **`Assess résumés`** (`.github/workflows/score.yml`) — manually triggered
  (`workflow_dispatch`). Choose a role, an optional pool, and a label; it runs
  the assessment and uploads the ranking as an artifact. Requires an
  `ANTHROPIC_API_KEY` repository secret.

---

## Repository layout

```
DAI_Resumes/
├── templates/                # reusable family rubrics (extend these)
│   ├── data_engineer.yaml
│   ├── data_architect.yaml
│   ├── bi_developer.yaml
│   └── ai_engineer.yaml
├── roles/                    # one folder per role
│   └── <role>/
│       ├── role.yaml         # criteria (may `extends:` a template)
│       ├── job_description.md # optional
│       └── resumes/          # the pool submitted for this role
├── results/                  # generated rankings + scores (git-ignored)
├── src/
│   ├── config.py             # paths + settings
│   ├── criteria.py           # rubric loading + template resolution
│   ├── parsing.py            # PDF/DOCX → text; résumé-pool resolution
│   ├── scorer.py             # Claude API scoring (seniority + JD aware)
│   ├── ranking.py            # aggregate + rank + render
│   ├── generate.py           # draft a rubric from a job description
│   └── cli.py                # command-line entry point
├── requirements.txt
└── .env.example
```

---

## Privacy note

Résumés contain personal data. Scoring sends résumé text to the Claude API.
Review your data-handling obligations (GDPR/CCPA, candidate consent) before
uploading real candidate data, and don't commit real résumés to a public repo —
`.gitignore` already excludes `roles/**/resumes/*.pdf|docx`.
