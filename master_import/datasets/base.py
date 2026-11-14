"""What a dataset is: its fields, how a file is checked, and how it is written."""

from dataclasses import dataclass, field


@dataclass
class Field:
    key: str  # the name the row carries, and the template's column header
    label: str = ""
    required: bool = False
    aliases: tuple = ()
    sample: str = ""
    group: str = ""
    # How a value is edited on the review page: text, email, tel, date, number,
    # choice (a fixed list), or suggest (free text that offers what already exists).
    kind: str = "text"
    choices: tuple = ()
    suggest: str = ""

    def __post_init__(self):
        self.label = self.label or self.key


@dataclass
class Context:
    """Who is importing, and which company the session is on (None = all)."""

    user: object = None
    company: object = None


@dataclass
class Checked:
    valid: list = field(default_factory=list)
    errors: list = field(
        default_factory=list
    )  # [{"row": n, "data": {...}, "messages": [...]}]
    will_create: dict = field(
        default_factory=dict
    )  # {"companies": ["A"], "departments": [...]}
    unchanged: list = field(
        default_factory=list
    )  # update mode: matched, nothing differs


class Dataset:
    key = ""
    label = ""
    subtitle = ""
    icon = "people-outline"
    permission = ""
    # What changing existing records takes, on top of ``permission`` (which is about adding).
    update_permissions: list = []
    available = True
    # Whether existing records can be updated from a sheet, and the fields that find them.
    supports_update = False
    match_choices: list = []
    # The fields that find a record when the sheet has no say (no choice to offer).
    default_match_keys: list = ["Badge ID"]
    # Match fields that are always used and cannot be unticked.
    locked_match_keys: list = []
    match_help = (
        "Only what the sheet fills in is changed. Blank cells leave the current value alone. "
        "A key itself is never changed: to change Badge ID, find people by Email or Phone."
    )
    hint_create = "Adds people who are not in Horilla yet. Existing Badge IDs and emails are skipped."
    hint_update = "Finds people by Badge ID, Email or Phone and changes only what the sheet fills in."
    hint_both = "Updates people the sheet finds by Badge ID, Email or Phone, and creates everyone else in the same import."
    fields: list = []
    # {will_create key: model}, so the review can name each kind by the model's own plural name.
    created_models: dict = {}
    # A line under the fields on the upload page, in place of the company note.
    upload_note = ""
    # The columns shown for each record in the review tables.
    preview_columns: list = []

    def required_keys(self):
        return [f.key for f in self.fields if f.required]

    def suggestions(self):
        """{suggest key: existing names}, for the fields that offer them."""
        return {}

    def prepare(self, rows, ctx):
        """Hook: fill defaults, derive fields. Returns the rows."""
        return rows

    def check(self, rows, ctx, progress=None, mode="create", match_keys=()) -> Checked:
        """``progress(percent)`` is called as the check goes, 0 to 100."""
        raise NotImplementedError

    def commit(self, rows, ctx, mode="create", progress=None) -> dict:
        raise NotImplementedError
