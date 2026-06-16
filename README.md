# DAI Resumes

A repository for storing résumés organized **by role**, with an AI pipeline that
scores each résumé against role-specific criteria and ranks the top candidates.

It uses the [Claude API](https://platform.claude.com) (model `claude-opus-4-8`)
to evaluate each résumé against a structured rubric and produce an explainable,
per-criterion score.

---

## How it works

```
roles/<role>/resumes/*.pdf|*.docx        ← drop résumés here
        │
        ▼
  parse text (pdfplumber / python-docx)
        │
        ▼
  score against criteria/<role>.yaml      ← Claude API, structured output
        │
        ▼
  rank candidates  ───►  results/<role>/*.json + ranking.md
```

Each role has:

- **A criteria file** — `criteria/<role>.yaml` defines the rubric: weighted
  criteria, must-haves, and the scoring scale.
- **A résumé folder** — `roles/<role>/resumes/` holds the candidate files
  (PDF and DOCX supported).

The scorer reads the rubric, evaluates every résumé in the role folder, and
writes a ranked shortlist to `results/<role>/`.

---

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

You can get a key from the [Claude Console](https://platform.claude.com).

### 3. Add résumés

Drop candidate files into the role folder you care about, e.g.:

```
roles/software_engineer/resumes/jane_doe.pdf
roles/software_engineer/resumes/john_smith.docx
```

A sample role (`software_engineer`) and rubric ship with the repo so you can try
the pipeline immediately.

### 4. Score and rank

```bash
# Score every résumé for a role and print the ranking
python -m src.cli rank software_engineer

# List the roles available
python -m src.cli list-roles

# Score a single file without committing it to a role folder
python -m src.cli score-file software_engineer path/to/resume.pdf
```

Results land in `results/software_engineer/`:

- `ranking.md` — human-readable shortlist, best candidate first.
- `<candidate>.json` — full per-criterion breakdown for each résumé.

---

## Adding a new role

1. Create the résumé folder:

   ```bash
   mkdir -p roles/data_analyst/resumes
   ```

2. Create the rubric `criteria/data_analyst.yaml` (copy
   `criteria/software_engineer.yaml` as a starting point).

3. Drop résumés in and run `python -m src.cli rank data_analyst`.

The role name is just the filename stem of the criteria file and the folder name
under `roles/` — keep them identical.

---

## Continuous integration

Two GitHub Actions workflows are included:

- **`CI`** (`.github/workflows/ci.yml`) — runs on every push and pull request.
  Installs dependencies, compiles the sources, and validates that every
  `criteria/<role>.yaml` is a well-formed rubric. Needs no API key.
- **`Score résumés`** (`.github/workflows/score.yml`) — manually triggered
  (`workflow_dispatch`). Pick a role; it scores that role's résumés and uploads
  the ranking as a build artifact. Requires an `ANTHROPIC_API_KEY` repository
  secret (Settings → Secrets and variables → Actions).

## Repository layout

```
DAI_Resumes/
├── criteria/                 # one <role>.yaml rubric per role
│   └── software_engineer.yaml
├── roles/                    # résumés stored by role
│   └── software_engineer/
│       └── resumes/          # drop .pdf / .docx here
├── results/                  # generated scores + rankings (git-ignored)
├── src/                      # the scoring pipeline
│   ├── config.py             # paths + settings
│   ├── criteria.py           # load/validate rubric YAML
│   ├── parsing.py            # PDF/DOCX → text
│   ├── scorer.py             # Claude API scoring
│   ├── ranking.py            # aggregate + rank + render
│   └── cli.py                # command-line entry point
├── requirements.txt
└── .env.example
```

---

## Privacy note

Résumés contain personal data. Scoring sends résumé text to the Claude API.
Review your data-handling obligations (GDPR/CCPA, candidate consent) before
uploading real candidate data, and avoid committing real résumés to a public
repository.
