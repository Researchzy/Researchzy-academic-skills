# Mock defence

The drill trains retrieval under pressure: the student hears a question they have not just reread and answers from what they know and where to find it. It only works if the student does not see the bank or the outline while it runs.

## Before the first question

- Run it only after `defense_check.py check` exits 0, so that the outlines you judge against are checked.
- Agree the number of questions for this session. A convention the user may change: eight to ten, then a break.
- Say once that this is a typed rehearsal: it trains content, not voice, pace or nerves. Suggest the student also answer aloud from the revision list.
- If the notice states the length of the presentation or the question time, you may mention it as the notice states it. State no other time limit.
- Examiner roles (a methods specialist, a reader from a neighbouring field) may change the tone of the questions, never their substance. Change them without announcing it if the user wants variety.

## One turn

1. Ask one question from the bank. Put the reviewers' questions early and mix the categories. Rephrase it as an examiner would say it; do not read out the anchors.
2. Wait for the answer. Do not hint, praise or correct while the student is answering.
3. Judge the answer against the outline and the thesis, silently, with one of the verdicts below.
4. If the answer is weak, name the gap in one sentence ("the response rate you gave is not the one on page 45") and ask one follow-up, from the question's follow-ups or from the gap. A second follow-up is allowed; after that, move on.
5. Record the turn (below), then ask the next question.

| Verdict | In a Chinese drill | The answer |
|---|---|---|
| `solid` | 稳 | Answers the question, with support that is in the thesis, and survives the follow-up |
| `shaky` | 不稳 | Right direction, but missing the anchor or the number, or hesitant under the follow-up |
| `stuck` | 卡住 | No usable answer |
| `wrong` | 答错 | States something the thesis contradicts, or a number it does not contain |
| `dodged` | 回避 | Answers a different question, or talks around the point |

The student may say `stop` (end the session and debrief), `skip` (next question, recorded as `stuck` with the gap "skipped"), `hint` (give the page to look at, never the answer) or `pause`.

## Recording

Save the student's answer, as typed, to `defense/turn-answer.txt`, then:

```sh
python3 "$SKILL_DIR/scripts/defense_check.py" session --question Q7 --verdict shaky \
  --answer-file defense/turn-answer.txt --gap "Named no source for the 20% attrition; the thesis gives 18.4% (p. 52)"
```

- `--gap` says what was missing or wrong, concretely, with the page when there is one. Every verdict except `solid` needs it.
- The script lists the numbers in the answer that are not in the thesis (or allowed in that question's outline). It refuses `solid` for such an answer: record it as `shaky` or `wrong`, naming the number in the gap.
- A follow-up is recorded as another turn of the same question.

## Debrief

At `stop`, or when the agreed questions are done:

1. Show `defense/revision-list.md`: the questions still weak, grouped by chapter, each with its verdicts, gap, the numbers that were not in the thesis and the pages to reread; then the numbers to know with their printed pages.
2. For each weak question, now show its outline and go through the anchors with the student.
3. Name concrete preparation: which pages to reread, which numbers to learn, which answers to say aloud.
4. Give no score, no readiness rating and no forecast of the result.

A later session starts from `session.jsonl`: ask the weak questions again first. A question that later gets `solid` leaves the revision list; its earlier verdicts stay in the log.
