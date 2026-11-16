# Writing the talk

A talk is not the paper read aloud. The paper is organised for a reader who can go back; a talk is heard once, in order, at the speaker's pace. Plan it from the message, not from the paper's sections.

## Start from one sentence

Before the first slide, write the sentence you want the audience to repeat afterwards. Every slide either makes that sentence believable or is cut. For the author's own paper it is usually the main result with its condition ("A fixed window halves memory on long inputs without losing accuracy"). For a journal club it is the presenter's verdict on the paper ("The memory saving is solid; the accuracy claim rests on tasks that favour local evidence").

## Titles are claims

- Each title is a full sentence with a verb that states what the slide shows: "Peak memory falls by 48% at 16,384 tokens", not "Results" or "Memory".
- Read the titles alone, in order. They should make the argument without the slides: problem, idea, evidence, limits, conclusion. If two titles in a row could swap places, the order is not doing any work.
- Keep a title to two lines on the slide (about 12 to 15 words). A longer claim usually holds two messages: split the slide.
- A number in a title is the number the audience should remember; it must be in the paper (the check finds it).
- The title frame, section dividers and the closing slide are exempt from the rule, but the closing slide still works best as the take-home claim, not "Thank you" or "Questions?".

## One message per slide

| On the slide | In the notes |
|---|---|
| The claim, as the title | The transition from the previous slide, in the first sentence |
| Two to four short fragments that support it, or one figure with one or two fragments | Why it matters and how to read the figure: axes, what each colour is, where to look |
| The one or two numbers that carry the claim, exactly as the paper prints them | The same numbers said the way they are spoken: "about half", "from 31 to 16 gigabytes" |
| The source of a figure or table | Caveats, definitions, the method detail someone might ask about |

- Fragments, not sentences: "31.2 GB dense against 16.1 GB sparse", not "We observed that the dense model required 31.2 GB…".
- Do not read statistics aloud. A p-value, an interval or a test statistic belongs on the slide or in a backup slide; the notes say what it means ("clearly larger than the run-to-run spread").
- Two to five spoken sentences per slide, with a transition at the start ("Halving memory only matters if accuracy holds, so…"). Notes that take much less time to say than the slide's seconds mean either silence or improvisation; the check flags a deck whose notes cover less than half the planned time.
- Spend time where the evidence is: in a research talk about 40 to 50% of the time goes to results. Backup slides hold what you cut but expect to be asked.

## Arcs

Choose the arc from the occasion, not from the paper's section order.

| Talk | Arc | Notes |
|---|---|---|
| Own paper, conference or seminar | Problem and why it matters (1–2 slides); the gap; the idea in one slide; 2–4 result slides, one claim each; limits; take-home | No outline slide in a talk under 20 minutes. Related work only as far as it explains the gap |
| Own paper, lightning | The problem in one slide; the one result; the take-home | Three to five slides; one figure at most |
| Journal club | The paper and the question it asks; why this paper; the design in one slide; the key results with the paper's own figures; the presenter's appraisal: strengths, limits, whether the conclusions follow from the evidence; what it means for the group; questions for discussion | The appraisal is the point of the session, not a summary of the abstract |
| Defence or job talk | The question of the whole work; one strand per chapter or project, each with its result; what ties them together; limits and next steps | Slower pace: fewer slides per minute |
| Lecture | Concepts in the order they build; one worked example per concept | Slides stay up longer and may carry more text |

### Journal club appraisal

A journal club presents somebody else's work, so the slides must keep two voices apart.

- The paper's results are shown with the paper's figures, unchanged, with a source label. The title states what the figure shows, in the presenter's words.
- The presenter's judgement is marked as such: "Our view: the control group is too small to rule out…". Strengths and limits each get their own slide or half-slide.
- Judgements need reasons from the paper: the design, the sample, the analysis, missing comparisons. Not "seems weak".
- For the appraisal itself, use `researchzy-paper-review` (plugin `researchzy-manuscript`, when installed) for a structured critique and `researchzy-stats-review` (same plugin) for the statistics; use `researchzy-deep-read` (plugin `researchzy-reading`, when installed) to work through the paper section by section first. Bring their conclusions into the plan; this skill does not repeat that work.
- Context from other papers (a later replication, a competing method) is a number or claim that is not in the paper: it needs an `Allow:` line naming the source the user gave or a Researchzy record read in this session. Never from memory.

## Avoid

- Slides that are the paper's sections in order (Introduction, Methods, Results, Discussion).
- An outline slide, a "Thank you" slide and a "Questions?" slide in a short talk: they take slots from evidence.
- Bullets the speaker reads word for word.
- Prepared answers to questions that contain numbers not in the paper.
- More than one figure per slide unless the two are compared and the title says so.
