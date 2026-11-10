"""
Parsing of record ids posted by the list pages.

Bulk actions post their ids in more than one shape: repeated ``ids`` params
(jQuery ``traditional`` and htmx ``hx-vals`` arrays), or one JSON string such as
"[1, 2]", sometimes JSON-encoded a second time when a form round-trips it
through a hidden input. Passing any of these straight to ``id__in`` raises a
ValueError (a 500) for the shapes the view did not expect, so views read their
ids through these helpers instead.
"""

import ast
import json


def parse_posted_id_list(raw):
    """
    Ids from one posted value, as a list of ints.

    The value is decoded until it stops being text, so JSON, JSON inside JSON
    and a Python list literal all work. A missing, empty or malformed value
    yields an empty list; entries that are not integers are dropped and
    duplicates collapse.
    """
    value = raw
    for _attempt in range(2):
        if not isinstance(value, str):
            break
        value = value.strip()
        if not value:
            return []
        try:
            value = json.loads(value)
        except ValueError:
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return []
    if isinstance(value, (int, str)):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    ids = []
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError, OverflowError):
            continue
        if number not in ids:
            ids.append(number)
    return ids


def posted_ids(querydict, name="ids"):
    """
    Ids posted under ``name`` in a QueryDict (request.POST or request.GET),
    whether repeated (?ids=1&ids=2) or as a single JSON string (ids="[1, 2]").
    """
    ids = []
    for value in querydict.getlist(name):
        for number in parse_posted_id_list(value):
            if number not in ids:
                ids.append(number)
    return ids
