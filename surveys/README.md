# Surveys

Employee surveys for Horilla HR: HR builds a survey (from scratch or from the library of
questionnaires), chooses who gets it, and each person answers on a personal link that
needs no login. Results, a CSV export and a dashboard show the outcome.

Originally contributed by @yuri-val (#1361).

## How it works

1. **Build.** A survey is a title, a few settings and an ordered list of questions of
   these types: short text, long text, single choice, multiple choice, yes/no, Likert,
   1-5 rating, 0-10 score (NPS), number and date. A questionnaire from the library
   (*Surveys > Library*) is copied into the survey; the copy can be changed freely.
2. **Choose the audience.** All employees, chosen departments, chosen job positions or
   chosen people. Only active employees of the survey's own company are invited.
3. **Open it.** Opening creates one invitation per person and sends the link by e-mail
   and as a Horilla notification. A survey that is already open can send the link to
   people who joined the audience since (*Send to New People*).
4. **People answer.** `/surveys/s/<token>/` shows the questions. Answers are saved as
   they are typed and the person can come back to the same link until the survey closes.
5. **Close it** (or let the closing date pass). Results and export are available while
   the survey is open and after it closes.

## Who may do what

| Who | May |
|---|---|
| HR with `surveys.change_survey` | Everything: create and edit surveys, edit questions, open, close, send, copy a link, resend |
| A survey's **managers** (named on the survey) | See that survey, its audience and results, export the results, send reminders |
| Anyone with `surveys.view_surveyresponse` | See results (not the audience actions) |
| Everyone else | Only answer on their own link |

The *Surveys* menu is shown to people with module permissions. A manager who has no
module rights is notified when they are named and reaches the survey from that
notification.

Opening and closing, question changes and per-person links always need
`surveys.change_survey`; managers cannot do them.

## Anonymous surveys: what is and is not promised

Choose *Anonymous* when creating the survey. It cannot be changed once the survey is open.

What an anonymous survey does:

- The response is stored **without a user** and with **only the date** (no time of day),
  so it cannot be matched to a person by the login that wrote it or by when it arrived.
- The link between a response and its invitation is removed when the response is
  submitted. HR sees **who has answered** (and on which day), never **what** they answered.
- Results and export stay hidden until at least **5 people** have answered. Set
  `SURVEYS_MIN_RESPONSES` in the Django settings to change the number.
- The export has no time column, and its rows are shuffled, so they do not line up with
  the audience list. Free-text answers are listed alphabetically, not in the order they
  arrived. Results cannot be cut by department.
- Unfinished drafts of an anonymous survey are deleted when it closes.
- A person whose link stops working (left, deactivated) cannot answer.

What it does **not** promise:

- Free text can give a person away by what it says. Tell people not to write anything
  they would not want recognised.
- With few people in the audience, even 5 answers can point at someone.
- Someone who watches the results page before and after one particular person answers
  can work out that person's answer. The minimum number does not prevent this.
- People with direct database access can read the tables. Anonymity here is about what
  the application shows to HR.
- An unfinished draft (before the person submits) is still tied to their invitation until
  it is submitted or the survey closes.

## Links and tokens

Every invitation has a random 43-character token in its link. Tokens are stored in plain
text on purpose: HR needs *Copy link* and *Send again*, which cannot work from a hash. The
trade-off is that anyone with read access to the database can open a person's link, so
treat database access accordingly. To limit exposure:

- A link only works while the survey is open and the person is active.
- Public pages are served with `Cache-Control: no-store` and `Referrer-Policy: same-origin`,
  and are not indexed.
- A guess that misses is counted per client address (behind a proxy, set
  `HORILLA_TRUSTED_PROXIES` so the real address is used); after 30 misses in 10 minutes
  further misses are refused for the rest of the window. A valid link is never throttled.
- *Copy link* asks the server for the link when pressed, so it is not written into the
  page for people who only look at the audience list.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `SURVEYS_MIN_RESPONSES` | `5` | Answers needed before an anonymous survey shows results or export |

It is read with `getattr`, so it does not have to be defined in `settings`.

## Management command

```
python manage.py seed_survey_library
```

adds the standard questionnaires (eNPS, engagement pulse, new hire check-in) to the
library if they are missing. The same is available as *Load Standard Questionnaires* in
the library. Running it again adds nothing.

## Accessibility

The answer page is built to be used with a keyboard and a screen reader: every question is
a labelled field or a `fieldset` with a `legend`, required and invalid answers are
announced and the first error is focused, focus is visible, the save status is a polite
live region, and inputs are 16 px so phones do not zoom. Charts have a text version
(hidden table) next to them, and questions can be reordered with Move up / Move down
buttons as well as by dragging. Colours reach a 4.5:1 contrast in light and dark mode.

## Tests

```
python manage.py test surveys
```

The tests need PostgreSQL for the two that use parallel requests; the rest also run on
SQLite. `surveys` is part of the CI smoke labels (see the Makefile).

## Not in this version

Sending in a background queue (large audiences send inside the request), scheduled
reminders, a preview or test send, XLSX export, duplicating a survey, trends between
surveys.
