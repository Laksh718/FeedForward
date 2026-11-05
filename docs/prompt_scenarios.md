# Prompt scenarios

The copilot answers in four steps. Only the last one uses a language model.

1. **Understand** (rules, `copilot/nlu.py`): intent and entities from the question. No language model.
2. **Compute** (plain Python, `copilot/context_builder.py`): the forecast or what if is run, and every figure the answer may use
   is put into one context JSON. No language model.
3. **Write** (`copilot/explain.py`): one request to the hosted language model with PROMPT_V2, the context JSON and the question.
4. **Check** (`explain.ungrounded_numbers`): every figure of 10 or more in the answer must appear in the context. If one does not,
   or if there is no key or no network, the deterministic template answer (`copilot/templates.py`) is shown instead.

NLU is the front end and NLG is the back end of a small dialogue system. The language model is a transformer based model that is
used only for language generation: it receives text and returns text. It never chooses what runs and never acts.
Self attention lets such a model weigh which words of the question and which figures in the context matter most for each word
it writes, which is why putting the exact figures in the prompt works better than asking from memory.

## The prompts

| | PROMPT_V1 | PROMPT_V2 (used by the app) |
|---|---|---|
| Role and boundary | none | kitchen copilot, explains only, never offers to act; six numbered rules in all |
| Figures | none, the model must guess | context JSON with every figure |
| Missing information | not handled | rule: say what is missing |
| Uncertainty | not handled | rule: say so when the range is wide (`range_is_wide`) |
| Examples | none | two short worked examples |
| Format | free text | Short answer, Key drivers, One caution (under 120 words) |
| Settings | default | temperature 0.2, at most 500 tokens, one request per answer (Google Gemini, `gemini-3.1-flash-lite` by default) |

## The five use case scenarios

| # | Scenario | Question used | Intent | Figures in the context | A good answer must |
|---|---|---|---|---|---|
| 1 | Why a dish is above or below the usual plan | "Why is Chappathi above the usual plan?" | explain_dish | usual plan, most likely, likely range, recommended, demand last week and two weeks ago, expected attendance against last week | compare the usual plan with the most likely demand, name the drivers (recent weeks, attendance), and mention the range |
| 2 | What if attendance rises 15 percent | "What if attendance rises 15%?" | whatif_attendance | totals before and after, expected attendance before and after, biggest dish changes | give the new recommended quantity and the difference, and say nothing is saved |
| 3 | What an exam week does to demand | "What does an exam week do to demand?" | whatif_special_day | the same what if figures with the exam week switched on | report the size of the change honestly, even when it is small |
| 4 | Summarise the week's surplus risk | "Summarise the week's surplus risk." | summarise_surplus_risk | risk counts for the day and for each of the next 7 days, dishes at risk, the risk rule | count the dishes by risk level, name the ones to watch, and say the risk rule is a first version |
| 5 | Explain the likely range to a non technical person | "Explain the P10 to P90 range to someone who is not technical." | explain_range | low end, most likely, high end, definitions, how often real days landed inside the range in held out checks | avoid the words P10 and P90, use "1 day in 10", and say what the recommendation covers |

## What V1 is expected to get wrong, and what V2 changes

| Failure | Why it happens with V1 | What V2 does |
|---|---|---|
| Invents numbers | the model has no figures, so it makes some up | the context JSON holds the figures and the check rejects anything else |
| Sounds sure when it should not | no information about the range | `range_is_wide` and the caution line |
| Offers to change or order food | no boundary | role line: explains only |
| Jargon (P90, quantile) | no audience given | rule 4 and the plain words in the examples |
| Long or unstructured answers | no format | three part format and a word limit |

`reports/prompt_comparison.md` holds the real before and after answers. Generate it with your key:

```powershell
python -m feedforward.copilot.compare_prompts
```

Without a key the script prints "No LLM key found. Set GEMINI_API_KEY in .env and run again." and leaves the report as it is.

## Out of scope questions

Approving, changing quantities, ordering food, ingredient stock questions and anything unrelated get a fixed message and
never reach the language model. A what if the dashboard cannot try (for example "what if more students come") gets a message
listing the changes it can try.
