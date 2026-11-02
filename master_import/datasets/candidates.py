"""Candidates: pipeline applicants attached to a recruitment opening."""

import re

from django.db import transaction

from base.models import JobPosition
from employee.methods.methods import import_valid_date
from recruitment.models import Candidate, Recruitment, Stage

from .base import Checked, Context, Dataset, Field

GENDERS = {
    "m": "male",
    "male": "male",
    "man": "male",
    "f": "female",
    "female": "female",
    "woman": "female",
    "o": "other",
    "other": "other",
    "others": "other",
}

SOURCES = {
    "application": "application",
    "application form": "application",
    "software": "software",
    "inside software": "software",
    "other": "other",
}

NEW_RECRUITMENT_STAGES = {"applied", "initial"}

# Where each column ends up, so a value too long for it is caught as that
# row's problem rather than a database error that stops the whole import.
LIMITS = {
    "Candidate Name": (Candidate, "name"),
    "Email": (Candidate, "email"),
    "Mobile": (Candidate, "mobile"),
    "Address": (Candidate, "address"),
    "Country": (Candidate, "country"),
    "State": (Candidate, "state"),
    "City": (Candidate, "city"),
    "Zip": (Candidate, "zip"),
    "Recruitment": (Recruitment, "title"),
}


def _text(value):
    """Numbers that came out of a spreadsheet as 9876543210.0 are the text 9876543210."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


class CandidatesDataset(Dataset):
    key = "candidates"
    label = "Candidates"
    subtitle = "Applicants for an open recruitment"
    icon = "person-add-outline"
    permission = "recruitment.add_candidate"
    supports_update = False
    created_models = {"recruitments": Recruitment}
    preview_columns = [
        "Candidate Name",
        "Email",
        "Mobile",
        "Recruitment",
        "Job Position",
        "Stage",
    ]
    hint_create = (
        "Adds candidates to a recruitment's pipeline. A recruitment named in the sheet that "
        "doesn't exist yet is created from an existing job position."
    )
    upload_note = (
        "Job Position must already exist (create it under Employee Settings first). A Recruitment "
        "named in the sheet that doesn't exist yet is created for that job position. A Stage must "
        "already exist on the recruitment; leave it blank to use the recruitment's Initial stage."
    )

    fields = [
        Field(
            "Candidate Name",
            required=True,
            group="Candidate",
            sample="Alex Carter",
            aliases=("name", "full name", "candidate", "candidate name"),
        ),
        Field(
            "Email",
            required=True,
            group="Candidate",
            sample="alex.carter@email.com",
            aliases=("email address", "e-mail", "mail"),
            kind="email",
        ),
        Field(
            "Mobile",
            group="Candidate",
            sample="9876543210",
            aliases=(
                "phone",
                "phone number",
                "contact",
                "contact number",
                "mobile number",
                "cell",
            ),
            kind="tel",
        ),
        Field(
            "Gender",
            group="Candidate",
            sample="female",
            aliases=("sex",),
            kind="choice",
            choices=("male", "female", "other"),
        ),
        Field(
            "DOB",
            group="Candidate",
            sample="1995-08-21",
            aliases=("date of birth", "birth date", "dob"),
            kind="date",
        ),
        Field(
            "Recruitment",
            required=True,
            group="Pipeline",
            sample="Software Engineer - 2024",
            aliases=("job opening", "opening", "requisition", "position opening"),
            kind="suggest",
            suggest="recruitments",
        ),
        Field(
            "Job Position",
            required=True,
            group="Pipeline",
            sample="Software Engineer",
            aliases=("position", "designation", "job title", "role"),
            kind="suggest",
            suggest="job_positions",
        ),
        Field(
            "Stage",
            group="Pipeline",
            sample="Initial",
            aliases=("pipeline stage", "status"),
            kind="suggest",
            suggest="stages",
        ),
        Field(
            "Source",
            group="Pipeline",
            sample="Software",
            aliases=("candidate source",),
            kind="choice",
            choices=("application", "software", "other"),
        ),
        Field("Address", group="Address", sample="12 Elm Street"),
        Field("Country", group="Address", sample="USA"),
        Field("State", group="Address", sample="California"),
        Field("City", group="Address", sample="Los Angeles"),
        Field("Zip", group="Address", sample="90001"),
        Field(
            "Portfolio",
            group="Address",
            sample="https://alexcarter.dev",
            aliases=("portfolio url", "website"),
        ),
    ]

    def suggestions(self):
        return {
            "recruitments": sorted(
                set(Recruitment.objects.values_list("title", flat=True)) - {None, ""}
            ),
            "job_positions": sorted(
                set(JobPosition.objects.entire().values_list("job_position", flat=True))
                - {None, ""}
            ),
            "stages": sorted(
                set(Stage.objects.values_list("stage", flat=True)) - {None, ""}
            ),
        }

    # ------------------------------------------------------------ prepare
    def prepare(self, rows, ctx):
        for row in rows:
            row["Mobile"] = _text(row.get("Mobile"))
            gender = row.get("Gender")
            if gender:
                row["Gender"] = GENDERS.get(
                    str(gender).strip().lower(), str(gender).strip().lower()
                )
            source = row.get("Source")
            if source:
                row["Source"] = SOURCES.get(
                    str(source).strip().lower(), str(source).strip().lower()
                )
            value = row.get("DOB")
            if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}[ T]", value):
                row["DOB"] = value[:10]
        return rows

    # -------------------------------------------------------------- check
    def check(
        self, rows, ctx: Context, progress=None, mode="create", match_keys=()
    ) -> Checked:
        rows = self.prepare(rows, ctx)
        result = Checked()
        if not rows:
            return result

        recruitments = {
            r.title.strip().lower(): r for r in Recruitment.objects.all() if r.title
        }
        positions = {
            p.job_position.strip().lower(): p
            for p in JobPosition.objects.entire()
            if p.job_position
        }
        max_lengths = {
            key: model._meta.get_field(name).max_length
            for key, (model, name) in LIMITS.items()
        }

        seen_pairs = set()
        new_recruitment_titles = set()
        total = len(rows) or 1

        for index, row in enumerate(rows, start=1):
            if progress and (index % 25 == 0 or index == total):
                progress(5 + int(index / total * 80))
            errors = {}

            name = (row.get("Candidate Name") or "").strip()
            if not name:
                errors["Candidate Name Error"] = "Candidate Name is required."

            email = (row.get("Email") or "").strip()
            if not email:
                errors["Email Error"] = "Email is required."

            job_position_name = (row.get("Job Position") or "").strip()
            job_position = None
            if not job_position_name:
                errors["Job Position Error"] = "Job Position is required."
            else:
                job_position = positions.get(job_position_name.lower())
                if job_position is None:
                    errors["Job Position Error"] = (
                        "This job position does not exist. Create it under Employee Settings first."
                    )

            recruitment_name = (row.get("Recruitment") or "").strip()
            recruitment = None
            if not recruitment_name:
                errors["Recruitment Error"] = "Recruitment is required."
            else:
                recruitment = recruitments.get(recruitment_name.lower())
                if recruitment is None:
                    new_recruitment_titles.add(recruitment_name)
                elif (
                    job_position is not None
                    and not recruitment.open_positions.filter(
                        pk=job_position.pk
                    ).exists()
                ):
                    errors["Job Position Error"] = (
                        f"{job_position_name} is not an open position on this recruitment."
                    )

            stage_name = (row.get("Stage") or "").strip()
            stage = None
            if stage_name:
                if recruitment is not None:
                    stage = Stage.objects.filter(
                        recruitment_id=recruitment, stage__iexact=stage_name
                    ).first()
                    if stage is None:
                        errors["Stage Error"] = (
                            "This stage does not exist on this recruitment."
                        )
                elif stage_name.lower() not in NEW_RECRUITMENT_STAGES:
                    errors["Stage Error"] = (
                        "A new recruitment only has Applied and Initial stages; add other stages afterwards."
                    )

            gender = row.get("Gender")
            if gender and gender not in {"male", "female", "other"}:
                errors["Gender Error"] = "Gender must be male, female or other."

            source = row.get("Source")
            if source and source not in {"application", "software", "other"}:
                errors["Source Error"] = (
                    "Source must be Application, Software or Other."
                )

            dob = None
            if row.get("DOB"):
                date_errors = {}
                dob = import_valid_date(row["DOB"], "DOB", date_errors, "DOB Error")
                errors.update(date_errors)

            for key, limit in max_lengths.items():
                value = row.get(key)
                if limit and value and len(str(value)) > limit:
                    errors[f"{key} Error"] = (
                        f"{key} is {len(str(value))} characters; the most allowed is {limit}."
                    )

            if email:
                pair_key = (
                    recruitment.pk
                    if recruitment is not None
                    else recruitment_name.lower()
                )
                pair = (pair_key, email.lower())
                if pair in seen_pairs:
                    errors["Email Error"] = (
                        "This email and recruitment appear more than once in the file."
                    )
                elif (
                    recruitment is not None
                    and Candidate.objects.filter(
                        recruitment_id=recruitment, email__iexact=email
                    ).exists()
                ):
                    errors["Email Error"] = (
                        "A candidate with this email already exists on this recruitment."
                    )
                else:
                    seen_pairs.add(pair)

            if errors:
                result.errors.append(self._error_entry(row, errors))
                continue

            row.update(
                {
                    "__recruitment": recruitment.pk if recruitment else None,
                    "__recruitment_new": (
                        recruitment_name.lower() if recruitment is None else None
                    ),
                    "__job_position": job_position.pk,
                    "__stage": stage.pk if stage else None,
                    "__stage_name": stage_name or None,
                    "__dob": dob,
                }
            )
            result.valid.append(row)

        result.errors.sort(key=lambda e: e["row"])
        result.will_create = {"recruitments": sorted(new_recruitment_titles)}
        if progress:
            progress(100)
        return result

    @staticmethod
    def _error_entry(row, errors):
        keys = {f.key for f in CandidatesDataset.fields}
        by_field = {
            k[: -len(" Error")]: v
            for k, v in errors.items()
            if k[: -len(" Error")] in keys
        }
        return {
            "row": int(row.get("__row") or 0),
            "name": row.get("Candidate Name") or "-",
            "badge": row.get("Email") or "-",
            "messages": list(errors.values()),
            "by_field": by_field,
            "data": {k: v for k, v in row.items() if k in keys},
        }

    # ------------------------------------------------------------- commit
    def commit(self, rows, ctx: Context, mode="create", progress=None) -> dict:
        step = progress or (lambda percent: None)
        step(5)

        with transaction.atomic():
            positions = {
                p.pk: p
                for p in JobPosition.objects.entire().filter(
                    pk__in={r["__job_position"] for r in rows}
                )
            }

            # Recruitments that don't exist yet, one per distinct title, each
            # opened for the job position of its first row.
            created_recruitments = {}
            for row in rows:
                key = row.get("__recruitment_new")
                if not key or key in created_recruitments:
                    continue
                position = positions[row["__job_position"]]
                recruitment = Recruitment.objects.create(
                    title=row["Recruitment"].strip(),
                    job_position_id=position,
                    vacancy=1,
                    company_id=ctx.company,
                )
                recruitment.open_positions.add(position)
                created_recruitments[key] = recruitment
            step(35)

            # A later row for the same new recruitment may name a different
            # (already-existing) job position; open that one too.
            for row in rows:
                key = row.get("__recruitment_new")
                if key:
                    created_recruitments[key].open_positions.add(
                        positions[row["__job_position"]]
                    )
            step(50)

            recruitments = {
                r.pk: r
                for r in Recruitment.objects.filter(
                    pk__in={r["__recruitment"] for r in rows if r.get("__recruitment")}
                )
            }
            stages = {
                s.pk: s
                for s in Stage.objects.filter(
                    pk__in={r["__stage"] for r in rows if r.get("__stage")}
                )
            }
            step(65)

            candidates = []
            for row in rows:
                recruitment = (
                    recruitments[row["__recruitment"]]
                    if row.get("__recruitment")
                    else created_recruitments[row["__recruitment_new"]]
                )
                stage = stages.get(row.get("__stage")) if row.get("__stage") else None
                if stage is None and row.get("__stage_name"):
                    stage = Stage.objects.filter(
                        recruitment_id=recruitment, stage__iexact=row["__stage_name"]
                    ).first()
                if stage is None:
                    stage = Stage.objects.filter(
                        recruitment_id=recruitment, stage_type="initial"
                    ).first()
                candidates.append(
                    Candidate(
                        name=row["Candidate Name"].strip(),
                        email=row["Email"].strip(),
                        mobile=row.get("Mobile") or "",
                        gender=row.get("Gender") or "male",
                        dob=row.get("__dob"),
                        recruitment_id=recruitment,
                        job_position_id=positions[row["__job_position"]],
                        stage_id=stage,
                        source=row.get("Source") or "software",
                        address=row.get("Address") or None,
                        country=row.get("Country") or None,
                        state=row.get("State") or None,
                        city=row.get("City") or None,
                        zip=row.get("Zip") or None,
                        portfolio=row.get("Portfolio") or "",
                        start_onboard=False,
                    )
                )
            step(85)
            for candidate in candidates:
                candidate.save()
            step(100)

        return {
            "candidates": len(candidates),
            "recruitments": len(created_recruitments),
        }
