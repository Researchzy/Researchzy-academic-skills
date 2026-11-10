<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/researchzy-logo-dark.svg">
    <img src="assets/researchzy-logo.svg" alt="Researchzy" width="330">
  </picture>
</p>

<h1 align="center">Researchzy Academic Skills</h1>

<p align="center">
  <b>Give your AI agent the skills of a careful researcher — working from real papers.</b><br>
  Find papers among 250 million records, review the literature, get full text lawfully,<br>
  read closely, check your references, and prepare your manuscript and your responses to reviewers.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="CHANGELOG.md"><img alt="Version" src="https://img.shields.io/badge/Version-2.0.0-4C6BD6.svg"></a>
  <a href="#-whats-included"><img alt="Skills" src="https://img.shields.io/badge/Skills-9-brightgreen.svg"></a>
  <a href="plugins/researchzy/docs/tools.md"><img alt="MCP tools" src="https://img.shields.io/badge/MCP_tools-9-orange.svg"></a>
  <a href="#-whats-included"><img alt="Papers" src="https://img.shields.io/badge/Papers-250M-8FA8E8.svg"></a>
  <a href="https://agentskills.io/"><img alt="Agent Skills" src="https://img.shields.io/badge/Standard-Agent_Skills-blueviolet.svg"></a>
  <a href="https://github.com/Researchzy/Researchzy-academic-skills/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/Researchzy/Researchzy-academic-skills/actions/workflows/tests.yml/badge.svg"></a>
  <a href="#-getting-started"><img alt="Works with" src="https://img.shields.io/badge/Works_with-Claude_Code_|_Codex_|_Cursor_|_Gemini_CLI-blue.svg"></a>
</p>

---

Researchzy Academic Skills is **nine agent skills for the whole life of a paper**, from reviewing the literature to answering the reviewers, in three plugins: one that searches real papers and needs a Researchzy account, and two that work on your own files with no account. They follow the open [Agent Skills](https://agentskills.io/) standard, install as plugins in **Claude Code** and **Codex**, and work in any host that supports Agent Skills. These are the same skills that run inside the [Researchzy Agent](https://researchzy.com).

> ⭐ **If these skills save you an afternoon, please [star the repository](https://github.com/Researchzy/Researchzy-academic-skills).** Stars help other researchers find it and tell us which skills to build next.

## ✨ Why Researchzy

- 📚 **Real papers, not invented citations.** Search returns real bibliographic records from about 250 million scholarly papers across arXiv, PubMed and open-access literature. The reading skills never turn metadata into full-text claims or page numbers.
- 🧭 **Reviews you can audit.** A literature review logs every search with its counts, records why each paper was kept or left out, reads the core papers in full, and cites only papers the index returned.
- ✅ **References you can trust.** The reference check tells you which references in a draft are real, which carry another paper's DOI or a wrong author, and which were retracted. It can also check that a cited paper says what your sentence says, with a quote and a page.
- 🔓 **Full text, the lawful way.** The PDFs Researchzy holds come first, then open-access copies (PMC, Unpaywall, openly licensed publisher PDFs, arXiv), then full text through *your own* Elsevier, Springer Nature or IEEE API keys. Every attempt is recorded in `manifest.json`.
- 🔍 **Reads like a careful colleague.** A close reading works through the key formulas with concrete numbers and marks where the evidence stops. A Paper Card ties every claim to its experiment and ends with testable research ideas.
- ✍️ **From draft to acceptance.** Audit your statistics, draft the Data and Code Availability statement journals ask for, and turn reviewer comments into a point-by-point response, a cover letter and a LaTeX revision package.
- 🧩 **Works where you work.** Plugins for Claude Code and Codex; `npx skills` or `gh skill` for Cursor, Gemini CLI, GitHub Copilot, Antigravity and 40+ other hosts.
- 🔒 **You stay in control.** The skills run in your agent. Researchzy only answers the literature tools, after you sign in and approve their scopes, and you can disconnect at any time.

## 📦 What's Included

### `researchzy` — find and review the literature (needs a Researchzy account)

| Skill | What it does |
|---|---|
| 🔎 [`researchzy`](plugins/researchzy/skills/researchzy/SKILL.md) | **Start here.** Search 250M papers by keywords, title, DOI or arXiv ID; filter by year, field and venue; sort by citations; browse and organize your library; fetch PDFs; hand every other task to the skill that fits<br>**You get:** Real metadata and verified local PDFs |
| 🧭 [`researchzy-literature-review`](plugins/researchzy/skills/researchzy-literature-review/SKILL.md) | A literature review on a topic: confirmed questions, logged searches in five passes, screening with reasons, full-text reading of the core papers, synthesis by theme<br>**You get:** `review.md` with a comparison table and gaps, `papers.csv`, `references.bib` and a search log |

The plugin connects nine [MCP tools](plugins/researchzy/docs/tools.md): `search_papers`, `get_paper`, `list_collections`, `create_collection`, `list_library_papers`, `add_paper_to_library`, `get_pdf_download`, `create_pdf_upload` and `get_profile`.

### `researchzy-reading` — read papers (no account)

| Skill | What it does |
|---|---|
| 📥 [`researchzy-download`](plugins/researchzy-reading/skills/researchzy-download/SKILL.md) | Get full text for a list of DOIs or titles from open access or your own publisher API keys<br>**You get:** Verified PDFs or full text, and a `manifest.json` of every attempt |
| 📖 [`researchzy-deep-read`](plugins/researchzy-reading/skills/researchzy-deep-read/SKILL.md) | Close reading of one paper: how the authors got there, which design choices carry the result, the key formulas with real numbers, how far the evidence reaches<br>**You get:** A Markdown long-read |
| 🗂️ [`researchzy-paper-card`](plugins/researchzy-reading/skills/researchzy-paper-card/SKILL.md) | A structured 16-section analysis of one paper: question, method logic, experiment-to-claim evidence, limitations, critique, research ideas<br>**You get:** A source-anchored `paper-card.md` and an audit report |

### `researchzy-manuscript` — prepare, check and revise a manuscript (no account)

| Skill | What it does |
|---|---|
| 📊 [`researchzy-stats-review`](plugins/researchzy-manuscript/skills/researchzy-stats-review/SKILL.md) | Audit a manuscript's statistical reporting: experimental units, replication, uncertainty, tests, figure statistics<br>**You get:** Issues by severity, a ready-to-paste Statistical analysis section, and questions for the authors |
| 🗄️ [`researchzy-data-availability`](plugins/researchzy-manuscript/skills/researchzy-data-availability/SKILL.md) | Draft or audit Data and Code Availability statements, repository plans and dataset citations<br>**You get:** A ready-to-paste statement, repository and citation actions, and missing-information flags |
| ✅ [`researchzy-reference-check`](plugins/researchzy-manuscript/skills/researchzy-reference-check/SKILL.md) | Check every reference of a manuscript or `.bib` against Crossref, DataCite, arXiv, PubMed and Researchzy: it exists, its DOI is its own, authors and year match, it is not retracted. Optionally check that each cited paper supports the sentence citing it<br>**You get:** A report with a verdict and evidence per reference, a corrected `.bib`, and quotes with pages for checked claims |
| 💬 [`researchzy-rebuttal`](plugins/researchzy-manuscript/skills/researchzy-rebuttal/SKILL.md) | Turn an editor's letter and reviewer comments into a revision package<br>**You get:** A master tracker, one response per reviewer, a cover letter, and optional LaTeX files |

The two plugins without an account work on the PDFs, text and files you give them. With `researchzy` installed and connected they do more: the reading skills find a paper by DOI or title and use the PDF Researchzy holds, and the reference check looks up references that have no DOI and can check that a cited paper supports the sentence that cites it.

## 🔄 One Workflow, from Search to Revision

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 260}}}%%
flowchart LR
    A["🔎 Find and review<br/>researchzy<br/>researchzy-literature-review"] --> B["📥 Get the full text<br/>researchzy-download"]
    B --> C["📖 Read<br/>researchzy-deep-read<br/>researchzy-paper-card"]
    C --> D["✍️ Write<br/>researchzy-stats-review<br/>researchzy-data-availability<br/>researchzy-reference-check"]
    D --> E["💬 Revise<br/>researchzy-rebuttal"]
    classDef step fill:#E7ECF7,stroke:#4C6BD6,color:#111113
    class A,B,C,D,E step
```

Use the whole chain or any single step. With `researchzy` installed, start there and it picks the next skill for you.

## 🚀 Getting Started

### Claude Code

```text
/plugin marketplace add Researchzy/Researchzy-academic-skills
/plugin install researchzy-reading@researchzy      # read papers, no account
/plugin install researchzy-manuscript@researchzy   # check and revise a manuscript, no account
/plugin install researchzy@researchzy              # search and literature reviews, needs an account
```

Install the ones you want. After installing `researchzy`, run `/mcp`, choose **researchzy** and sign in to your Researchzy account. Ask in plain words, or start a skill by name, for example `/researchzy-manuscript:researchzy-reference-check`.

### Codex

```sh
codex plugin marketplace add Researchzy/Researchzy-academic-skills
codex plugin add researchzy-reading@researchzy      # read papers, no account
codex plugin add researchzy-manuscript@researchzy   # check and revise a manuscript, no account
codex plugin add researchzy@researchzy              # search and literature reviews, needs an account
```

Only `researchzy` asks you to sign in (or run `codex mcp login researchzy`). Start a new task so Codex loads the skills. Ask in plain words, or start a skill by name, for example `$researchzy-reference-check`.

### Cursor, Gemini CLI, GitHub Copilot, Antigravity and other Agent Skills hosts

```sh
npx skills add Researchzy/Researchzy-academic-skills
```

or, with the [GitHub CLI](https://cli.github.com/) 2.90+:

```sh
gh skill install Researchzy/Researchzy-academic-skills --all
gh skill install Researchzy/Researchzy-academic-skills researchzy-rebuttal   # just one skill
```

To use the `researchzy` skill's search and library, also add the MCP server `https://app.researchzy.com/mcp` to your host. [Connection setup](docs/connection.md) has the steps for Claude, Claude Code, VS Code and Codex.

### Requirements

- **Python 3.10+** for the bundled scripts; `pip install -r plugins/researchzy-reading/requirements.txt` adds PyMuPDF for reading PDFs.
- **Node.js 22+** for `researchzy-download`, plus `pdfplumber` or `pypdf` to verify PDFs.
- A **Researchzy account** for the `researchzy` plugin only.

## 💡 Example Prompts

**Find**
> Find the most-cited papers on CRISPR off-target effects since 2020 and save the top five to my "Gene editing" collection.

> Look up DOI 10.1051/0004-6361/202556799 and arXiv 2508.10985, and tell me which have a PDF.

> Review the literature on sleep deprivation and memory encoding since 2010: what is established, what is disputed, and where are the gaps?

**Get the full text**
> Download the full text of 10.1371/journal.pone.0000308 and 10.1016/j.cell.2020.02.052.

**Read**
> Read arXiv 1706.03762 closely: why did the authors design it this way, and how far does the evidence reach?

> Create a Paper Card for this PDF and separate the authors' claims from your analysis.

**Write and revise**
> Audit the statistical reporting of my manuscript and draft the Statistical analysis section.

> Draft a Data and Code Availability statement for our RNA-seq data and analysis code.

> Check the references in `main.tex`: are they all real, do the DOIs belong to them, and is anything retracted?

> Here are the editor's letter and the reviewers' comments; draft the point-by-point responses and the cover letter.

## 🤖 Prefer No Setup? Try the Researchzy Agent

The [Researchzy Agent](https://researchzy.com) runs these skills for you on its own cloud machine, with Python, the full Researchzy index and your library, all from the browser. Describe the task and come back to the tables, figures and drafts.

## ❓ FAQ

<details>
<summary><b>Do I need a Researchzy account?</b></summary>

Only for the `researchzy` plugin: search, your library and literature reviews. `researchzy-reading` and `researchzy-manuscript` need none and work on the PDFs, text and files you provide. With `researchzy` connected they do more: the reading skills find papers by DOI or title and use the PDFs Researchzy holds, and the reference check looks up references that have no DOI and can run the claim check.
</details>

<details>
<summary><b>Does it download paywalled papers?</b></summary>

Only through publisher APIs you hold keys for (Elsevier, Springer Nature, IEEE). Otherwise it uses open-access copies only, and it records every attempt and its outcome in `manifest.json`.
</details>

<details>
<summary><b>Will my agent make up references?</b></summary>

The literature skills report and cite only the records the search returned, and the reading skills never invent full-text claims or page numbers from metadata. When the full text is missing, they say so. To check a draft you already have, run `researchzy-reference-check` on it.
</details>

<details>
<summary><b>Can I install only some of the skills?</b></summary>

Yes. In Claude Code and Codex, install only the plugins you want. Elsewhere, pick skills in `npx skills add`, or name one with `gh skill install Researchzy/Researchzy-academic-skills <skill>`. Add `researchzy` if you want the reading skills to find and fetch papers for you.
</details>

<details>
<summary><b>Which languages do the skills support?</b></summary>

The skills are written in English, and you can write to them in any language. Paper Cards and close readings follow the language you use; submission texts such as Data Availability statements are drafted in English unless you ask otherwise.
</details>

## 🤝 Contributing

Issues and pull requests are welcome. Run the tests before you open a pull request:

```sh
python3 -m unittest discover -s tests
python3 -m unittest discover -s plugins/researchzy-reading/skills/researchzy-paper-card/tests
python3 -m unittest discover -s plugins/researchzy-manuscript/skills/researchzy-stats-review/shared/tests
python3 -m unittest discover -s plugins/researchzy-manuscript/skills/researchzy-rebuttal/shared/tests
python3 -m pytest plugins/researchzy-manuscript/skills/researchzy-rebuttal/tests
python3 -m unittest discover -s plugins/researchzy-reading/skills/researchzy-download/tests/python
python3 -m unittest discover -s plugins/researchzy/skills/researchzy-literature-review/tests
python3 -m unittest discover -s plugins/researchzy-manuscript/skills/researchzy-reference-check/tests
node --test plugins/researchzy-reading/skills/researchzy-download/tests/unit/*.test.mjs
```

## 📄 License

[Apache License 2.0](LICENSE), except `researchzy-download`, which is under the MIT License ([`LICENSE`](plugins/researchzy-reading/skills/researchzy-download/LICENSE)), and parts of the `researchzy-reference-check` scripts, which derive from MIT-licensed code ([license](plugins/researchzy-manuscript/skills/researchzy-reference-check/scripts/LICENSE-MIT.txt)). Third-party components and their licenses are listed in each plugin's notices: [researchzy-reading](plugins/researchzy-reading/THIRD_PARTY_NOTICES.md) and [researchzy-manuscript](plugins/researchzy-manuscript/THIRD_PARTY_NOTICES.md).
