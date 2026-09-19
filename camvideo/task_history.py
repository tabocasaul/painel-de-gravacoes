"""Read task usage consistently for limits and queue ordering."""
import math
from automation import task_key


def task_usage(history, phone, task, day=None):
    total = 0.0
    for date, phones in history.get('dias', {}).items():
        if day is not None and date != day:
            continue
        for key, entry in phones.get(phone, {}).items():
            if task_key(entry.get('nome') or key) != task_key(task):
                continue
            value = float(entry.get('segundos', 0) or 0)
            if math.isfinite(value):
                total += max(0, value)
    return total


def priority(targets, usage, lifetime):
    ordered = sorted(targets, key=lambda n: (usage(n), lifetime(n), n))
    skipped = [n for n in ordered if 7200 - usage(n) < 90]
    return {n: targets[n] for n in ordered if n not in skipped}, skipped


def daily_task_rows(history, phone_names, day):
    """Keep known tasks visible at zero on a new day; limits are per phone."""
    names = {}
    for phones in history.get('dias', {}).values():
        for phone in phone_names:
            for key, entry in phones.get(phone, {}).items():
                name = entry.get('nome') or key
                names.setdefault(task_key(name), name)
    rows = []
    for name in names.values():
        phones = []
        for phone in phone_names:
            seconds = task_usage(history, phone, name, day)
            remaining = max(0, 7200 - seconds)
            phones.append(dict(name=phone, seconds=seconds, limit=7200,
                               remainingSeconds=remaining, available=remaining >= 90))
        rows.append(dict(name=name, seconds=sum(p['seconds'] for p in phones),
                         limit=7200 * len(phones), phones=phones,
                         completedPhones=sum(not p['available'] for p in phones)))
    return sorted(rows, key=lambda row: (-row['seconds'], row['name']))
