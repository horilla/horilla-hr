"""A translated string placed inside a JavaScript string must go through ``|escapejs``.

``{% trans "Carry Forward" %}`` renders whatever the active language says. In French that
is ``Transporter vers l'avant``, so

    { name: '{% trans "Carry Forward" %}', data: carryData }

reaches the browser as

    { name: 'Transporter vers l'avant', data: carryData }

The apostrophe ends the JavaScript string early, the script stops with a syntax error, and
everything after it on the page - the summary cards at the top of a list tab, in the report in
issue #1207 - never loads. Nothing fails in English, so it only shows once a language with
apostrophes (French, Italian, Catalan, ...) is switched on.

``|escapejs`` turns ``'``, ``"`` and ``\\`` into ``\\uXXXX`` escapes, which are safe inside a
JavaScript string whichever quote delimits it, and inside an HTML attribute too.

How this test reads a template
------------------------------
It looks at the places where the browser runs JavaScript: inline ``<script>`` blocks (only those
that really are JavaScript - ``type="text/template"``, ``application/json`` and the like hold
HTML or data, and ``|escapejs`` would be wrong there) and ``onclick=``-style attributes.

Inside that code it walks the text the way a JavaScript parser would - strings, ``//`` and
``/* */`` comments - and treats a Django tag (``{% ... %}``, ``{{ ... }}``, ``{# ... #}``) as one
opaque piece. A ``{% trans %}`` or ``{% translate %}`` that falls anywhere inside a string, not only
directly between the quotes, must carry ``|escapejs``. A ``{% blocktrans %}`` cannot take a
filter of its own: wrap it in ``{% filter escapejs %}...{% endfilter %}``, or capture it with
``{% blocktrans ... as text %}`` outside the string and print ``{{ text|escapejs }}`` inside it.

Translations in plain HTML text, in ordinary attributes, or in a ``text/template`` block are not
JavaScript and are left alone.

One more case is not about quotes. If the JavaScript string is later handed to something that
parses it as HTML (a template literal given to jQuery's ``.html()``, say) and the text can come
from a request, ``|escapejs`` alone is not enough: it writes ``<`` as ``\\u003C``, which JavaScript
turns back into a real ``<`` before the HTML parser sees it. Use ``|force_escape|escapejs`` there
(see ``templates/filter_tags.html``). This test cannot know where a string ends up, so it only
checks for ``|escapejs``.

Known limits: it does not look at ``hx-on:*``, ``@click`` or ``href="javascript:..."``, and a
regular-expression literal that contains a quote can confuse the string tracking. None of these
occurs in the templates today.
"""

import re
import unittest
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    "staticfiles",
    "venv",
    ".venv",
    "env",
}

# Script types the browser runs as JavaScript; anything else (text/template, application/json,
# text/x-template, ...) is data or HTML.
JAVASCRIPT_TYPES = {"", "text/javascript", "application/javascript", "module"}

COMMENT_BLOCK = re.compile(
    r"\{%\s*comment(?:\s[^%]*)?%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL
)
DJANGO_TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", re.DOTALL)
TRANSLATE_TAG = re.compile(r"\{%\s*(trans|translate)\b")
BLOCK_TRANSLATE_TAG = re.compile(r"\{%\s*(blocktrans|blocktranslate)\b")
CAPTURES_INTO_VARIABLE = re.compile(r"\sas\s+\w+\s*%\}$")
FILTER_OPEN = re.compile(r"\{%\s*filter\s+(.*?)\s*%\}", re.DOTALL)
FILTER_CLOSE = re.compile(r"\{%\s*endfilter\s*%\}")
INLINE_SCRIPT = re.compile(
    r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE
)
SCRIPT_TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]*)""", re.IGNORECASE)
SCRIPT_SRC = re.compile(r"\bsrc\s*=", re.IGNORECASE)
EVENT_ATTRIBUTE_START = re.compile(r"""\bon[a-z]+\s*=\s*(["'])""", re.IGNORECASE)
STRING_QUOTES = {"'", '"', "`"}


def templates():
    root = Path(__file__).resolve().parents[2]
    for path in sorted(root.rglob("*.html")):
        if SKIP_DIRS.isdisjoint(path.relative_to(root).parts):
            yield root, path


def unsafe_in_strings(code):
    """
    Offsets (into ``code``) and text of translations that sit inside a JavaScript string and are
    not escaped. ``code`` is JavaScript with Django tags in it.
    """
    found = []
    state = None  # None, a quote character, "//" or "/*"
    filters = []  # the {% filter ... %} blocks around the current position
    i = 0
    while i < len(code):
        if code.startswith(("{%", "{{", "{#"), i):
            match = DJANGO_TAG.match(code, i)
            if match is None:
                i += 2
                continue
            tag = match.group(0)
            filter_open = FILTER_OPEN.match(tag)
            if filter_open:
                filters.append(filter_open.group(1))
            elif FILTER_CLOSE.match(tag):
                if filters:
                    filters.pop()
            elif state in STRING_QUOTES and not any(
                "escapejs" in name for name in filters
            ):
                # a {% filter escapejs %}...{% endfilter %} block escapes everything inside it,
                # including a {% blocktrans %}, which cannot take a filter of its own
                # `{% trans "..." as t %}` only captures the text; where `{{ t|escapejs }}` is
                # printed is a separate, visible expression
                if (
                    TRANSLATE_TAG.match(tag)
                    and "escapejs" not in tag
                    and not CAPTURES_INTO_VARIABLE.search(tag)
                ):
                    found.append((i, tag))
                elif BLOCK_TRANSLATE_TAG.match(tag):
                    found.append((i, tag))
            i = match.end()
            continue
        char = code[i]
        if state is None:
            if char in STRING_QUOTES:
                state = char
            elif code.startswith("//", i):
                state = "//"
                i += 1
            elif code.startswith("/*", i):
                state = "/*"
                i += 1
        elif state in STRING_QUOTES:
            if char == "\\":
                i += 1
            elif char == state:
                state = None
        elif state == "//":
            if char == "\n":
                state = None
        elif state == "/*":
            if code.startswith("*/", i):
                state = None
                i += 1
        i += 1
    return found


def javascript_regions(text):
    """(offset, code) for every inline JavaScript block and event-handler attribute value."""
    regions = []
    for match in INLINE_SCRIPT.finditer(text):
        attributes = match.group(1)
        if SCRIPT_SRC.search(attributes):
            continue
        type_match = SCRIPT_TYPE.search(attributes)
        script_type = type_match.group(1).lower() if type_match else ""
        if script_type in JAVASCRIPT_TYPES:
            regions.append((match.start(2), match.group(2)))
    for match in EVENT_ATTRIBUTE_START.finditer(text):
        quote = match.group(1)
        start = match.end()
        i = start
        while i < len(text):
            if text.startswith(("{%", "{{", "{#"), i):
                tag = DJANGO_TAG.match(text, i)
                i = tag.end() if tag else i + 2
                continue
            if text[i] == quote:
                break
            i += 1
        regions.append((start, text[start:i]))
    return regions


def without_comment_blocks(text):
    """``{% comment %}`` blocks are not rendered; blank them out, keeping every offset."""
    return COMMENT_BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def problems_in(text):
    """Line numbers and tags of translations that would break the JavaScript around them."""
    text = without_comment_blocks(text)
    found = []
    for offset, code in javascript_regions(text):
        for position, tag in unsafe_in_strings(code):
            found.append((text.count("\n", 0, offset + position) + 1, tag))
    return sorted(set(found))


class TranslationsAreEscapedInJavaScript(unittest.TestCase):
    def test_the_check_sees_the_bug(self):
        cases = [
            "<script>var x = { name: '{% trans \"Carry Forward\" %}' };</script>",
            "<script>var x = { name: \"{% translate 'Carry Forward' %}\" };</script>",
            # the tag is not the only thing in the string
            "<script>var x = \"{% trans 'Still to match:' %} \" + count;</script>",
            "<script>var x = `${count} {% trans 'items' %}`;</script>",
            "<a onclick=\"confirm('{% trans 'Sure?' %}')\">x</a>",
            # blocktrans cannot take |escapejs
            "<script>var x = '{% blocktrans %}Don't{% endblocktrans %}';</script>",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(len(problems_in(case)), 1, case)

    def test_the_check_accepts_escaped_and_non_javascript_text(self):
        cases = [
            "<script>var x = { name: '{% trans \"Carry Forward\"|escapejs %}' };</script>",
            "<script>var x = \"{% translate 'Carry Forward'|escapejs as t %}\";</script>",
            # a blocktrans cannot take a filter, but a {% filter escapejs %} block around it works
            "<script>var x = '{% filter escapejs %}{% blocktrans %}Don't{% endblocktrans %}{% endfilter %}';</script>",
            '<button onclick="go(&quot;{% filter escapejs %}{% blocktrans %}Don\'t{% endblocktrans %}{% endfilter %}&quot;)">x</button>',
            # capturing the text into a variable and printing it escaped is the safe pattern too
            "<script>var x = '{% trans \"Submit Feedback?\" as t %}{{ t|escapejs }}';</script>",
            # a translation outside any string is fine
            "<script>var title = {% trans 'Hello' as t %}{{ t|escapejs|default:'' }};</script>",
            # a quote inside a comment does not start a string
            "<script>// don't do this\nvar label = '{% trans \"Ok\"|escapejs %}';</script>",
            "<script>/* it's fine */ var a = 1;</script>",
            # code that is commented out with {% comment %} is never rendered
            "{% comment %}<a onclick=\"confirm('{% trans 'Sure?' %}')\">x</a>{% endcomment %}",
            # HTML and data blocks are not JavaScript
            '<script type="text/template"><p title=\'{% trans "Approve" %}\'></p></script>',
            '<script type="application/json">{"a": "{% trans \'x\' %}"}</script>',
            '<p title=\'{% trans "Approve" %}\'>{% trans "Reject" %}</p>',
            "<a href='{% url \"x\" %}' title=\"{% trans 'Approve' %}\">x</a>",
            "<script src=\"{% static 'a.js' %}\"></script>",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(problems_in(case), [], case)

    def test_no_template_puts_an_unescaped_translation_inside_a_js_string(self):
        problems = []
        for root, path in templates():
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line, tag in problems_in(text):
                problems.append(
                    f"{path.relative_to(root).as_posix()}:{line}  {tag[:90]}"
                )
        self.assertEqual(
            problems,
            [],
            "A translation inside a JavaScript string needs |escapejs "
            "(see this module's docstring):\n  " + "\n  ".join(problems),
        )


if __name__ == "__main__":
    unittest.main()
