"""Deterministic answers built from the same context JSON. Used when no language model is available, and as
the safe replacement when a model answer quotes a number that is not in the context."""


def n(v) -> str:
    """Whole number with a thousands separator."""
    return f"{int(round(v)):,}"


def _signed(v: float) -> str:
    return f"{'plus' if v >= 0 else 'minus'} {n(abs(v))}"


def _fmt(short: str, drivers: list[str], caution: str) -> str:
    return f"Short answer: {short}\nKey drivers:\n" + "\n".join(f"- {d}" for d in drivers[:3]) + f"\nOne caution: {caution}"


def _flags(facts: dict) -> list[str]:
    out = []
    if facts.get("exam_week"):
        out.append("It is an exam week, when more students eat in the mess.")
    if facts.get("holiday") or facts.get("festival"):
        out.append("It is a holiday or festival day.")
    if facts.get("students_mostly_away"):
        out.append("Most students are away.")
    return out


def _attendance(facts: dict) -> str | None:
    if not facts or not facts.get("expected_attendance"):
        return None
    last = facts.get("attendance_last_week")
    return (f"Expected attendance is {n(facts['expected_attendance'])}, against {n(last)} last week." if last
            else f"Expected attendance is {n(facts['expected_attendance'])}.")


def _caution(ctx: dict, default: str) -> str:
    notes = list(ctx.get("missing", [])) + list(ctx.get("caveats", []))
    return (notes[0] if notes else default)


def _dish(ctx: dict) -> str:
    d, f, t = ctx.get("dish"), ctx["day_facts"], ctx["slot_totals"]
    where = f"{ctx['weekday']} {ctx['meal_slot']}"
    if d is None:
        lead = f"{ctx['missing'][0]} " if ctx.get("missing") else ""
        short = (f"{lead}For {where} we suggest cooking {n(t['recommended'])} portions, against a usual plan of {n(t['usual_plan'])}. "
                 f"The most likely demand is {n(t['p50'])}.")
        drivers = [x for x in [_attendance(f), f"The usual plan is the {ctx['usual_plan_rule']}."] if x] + _flags(f)
        return _fmt(short, drivers, _caution(ctx, f"The likely range for the day is {n(t['p10'])} to {n(t['p90'])}."))
    gap = d["usual_plan_minus_most_likely"]
    if d["usual_plan"]:
        side = f"{n(abs(gap))} {'above' if gap > 0 else 'below'} the most likely demand of {n(d['most_likely'])}"
        short = f"The usual plan for {d['name']} is {n(d['usual_plan'])}, which is {side}. We suggest cooking {n(d['recommended'])}."
    else:
        short = f"There is no usual plan for {d['name']} yet. The most likely demand is {n(d['most_likely'])} and we suggest cooking {n(d['recommended'])}."
    drivers = []
    if d["demand_last_week"] is not None:
        two = f" and {n(d['demand_two_weeks_ago'])} two weeks ago" if d["demand_two_weeks_ago"] is not None else ""
        drivers.append(f"{n(d['demand_last_week'])} were wanted last week{two}; the usual plan averages the recent weeks and adds a buffer.")
    drivers += [x for x in [_attendance(f)] if x] + _flags(f)
    if d["limited_stock_dish"]:
        drivers.append("This dish has limited stock and often runs out, so past eating understates demand.")
    if d["range_is_wide"]:
        caution = (f"The likely range is {n(d['low_end'])} to {n(d['high_end'])}, which is wide, so treat this number with extra care.")
    else:
        caution = f"The likely range is {n(d['low_end'])} to {n(d['high_end'])}; real demand can land anywhere inside it."
    return _fmt(short, drivers, _caution(ctx, caution) if ctx.get("missing") or ctx.get("caveats") else caution)


def _range(ctx: dict) -> str:
    t, cal = ctx["slot_totals"], ctx.get("calibration")
    short = (f"For {ctx['weekday']} {ctx['meal_slot']}, the most likely demand for the dishes shown is {n(t['p50'])}, and the likely "
             f"range is {n(t['p10'])} to {n(t['p90'])}.")
    drivers = [f"Low end {n(t['p10'])}: about 1 day in 10 demand is expected to be below this.",
               f"High end {n(t['p90'])}: about 1 day in 10 demand is expected to be above this."]
    if cal:
        drivers.append(f"In past checks about {cal['percent_of_days_inside_range_test']} percent of real days landed inside the range.")
    else:
        drivers.append("The range is a spread of plausible outcomes, not a promise.")
    caution = f"We suggest cooking {n(t['recommended'])}, which covers about 3 days in 4; on the other days the line may run short."
    return _fmt(short, drivers, _caution(ctx, caution) if ctx.get("caveats") else caution)


def _whatif(ctx: dict) -> str:
    b, a = ctx["before"], ctx["after"]
    chg = ctx["change_in_recommended"]
    pct = f" ({ctx['change_in_recommended_pct']:+g} percent)" if ctx.get("change_in_recommended_pct") is not None else ""
    short = (f"With {ctx['change']} on {ctx['weekday']} {ctx['meal_slot']}, the recommended quantity goes from "
             f"{n(b['recommended'])} to {n(a['recommended'])}, {_signed(chg)}{pct}.")
    drivers = [f"The most likely demand goes from {n(b['p50'])} to {n(a['p50'])}.",
               f"Expected attendance goes from {n(ctx['expected_attendance_before'])} to {n(ctx['expected_attendance_after'])}."]
    top = ctx["biggest_dish_changes"]
    if top and top[0]["change"]:
        drivers.append(f"The biggest change is {top[0]['name']}, from {n(top[0]['recommended_before'])} to {n(top[0]['recommended_after'])}.")
    caution = _caution(ctx, "This is a what if. Nothing is saved until you approve a plan.")
    return _fmt(short, drivers, caution)


def _week(ctx: dict) -> str:
    focus = ctx["focus_days"]
    busiest = f"{ctx['highest_day']} is expected to be the busiest day and {ctx['lowest_day']} the quietest over the next 7 days"
    if focus:
        parts = [f"{d['weekday']} is expected at {n(d['most_likely'])}" + (f", {_signed(d['change_from_previous_day'])} from the day before"
                                                                         if d.get("change_from_previous_day") is not None else "") for d in focus[:2]]
        short = f"For {ctx['meal_slot']}, " + " and ".join(parts) + "."
        drivers = [f"Over the week, {busiest}."]
    else:
        short = f"For {ctx['meal_slot']}, {busiest}."
        drivers = [f"{d['weekday']}: most likely {n(d['most_likely'])}, cook {n(d['recommended'])}."
                   for d in ctx["week_days"] if d["weekday"] in (ctx["highest_day"], ctx["lowest_day"])]
    for d in focus[:2]:
        if d["exam_week"]:
            drivers.append(f"{d['weekday']} falls in an exam week, when more students eat in the mess.")
        elif d.get("attendance_last_week"):
            drivers.append(f"Expected attendance on {d['weekday']} is {n(d['expected_attendance'])}, against {n(d['attendance_last_week'])} a week earlier.")
        if d.get("same_weekday_last_week_actual"):
            drivers.append(f"Last {d['weekday']} {n(d['same_weekday_last_week_actual'])} were wanted.")
    caution = _caution(ctx, "Later days in the week are less certain than the next day, so check back as the week goes on.")
    return _fmt(short, drivers, caution)


def _risk(ctx: dict) -> str:
    c = ctx["risk_counts"]
    short = (f"For {ctx['weekday']} {ctx['meal_slot']}, {c['high']} dishes have high surplus risk, {c['medium']} medium and {c['low']} low.")
    if ctx.get("week_risk"):
        worst = max(ctx["week_risk"], key=lambda d: (d["high"], d["medium"]))
        short += (f" Across the week, {worst['weekday']} has the most dishes at high risk ({worst['high']})." if worst["high"]
                  else " No day this week has dishes at high risk.")
    drivers = [f"{d['name']}: usual plan {n(d['usual_plan'])}, likely range {n(d['low_end'])} to {n(d['high_end'])}."
               for d in ctx["dishes_at_risk"][:3]] or ["No dish has a usual plan well above its likely range."]
    caution = "Risk is a first version: high means the usual plan is above the top of the likely range, medium means it is more than 10 percent above the most likely amount."
    return _fmt(short, drivers, caution)


def template_answer(ctx: dict) -> str:
    """Answer for any context, in the same three part format as the language model answer."""
    if ctx["intent"] == "out_of_scope":
        return ctx["message"]
    return {"explain_dish": _dish, "explain_range": _range, "explain_week": _week,
            "summarise_surplus_risk": _risk}.get(ctx["intent"], _whatif)(ctx)
