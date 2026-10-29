"""
Pay periods, and payroll runs as records rather than a shared string.

Two things were missing, and they are the reason batch payroll could not be
managed:

**When a pay month begins and ends was never written down.** Every caller
decided for itself — the bulk form defaults to the 1st of the month, the
scheduler hardcodes "a month back from today", the demo data uses the 1st to
the 28th. Nothing could say "our pay month is the 26th to the 25th", and
nothing could list the periods of a year.

**A batch was a free-text name.** `Payslip.group_name` is a CharField with no
identity: two unrelated runs that happen to share a name are the same batch as
far as the system is concerned, renaming one renames both, and there is nowhere
to record who ran it, when, what it totalled, or whether it has been approved.
Regenerating a payslip through any path that does not pass the name silently
erases it.

So: a period is configured once per company, and a run is a row. Payslips
belong to it, it carries its own totals and counts, and its status moves
through a defined set of transitions rather than being assigned freely.

Modelled on the v2 engine's own PayrollBatch, which solved the same
problem for the v2 engine — the state machine and the denormalised counters
are its ideas. It is not reused directly because it is bound to v2's own
Payslip table.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from horilla.models import HorillaModel


def _ordinal(day):
    """1st, 2nd, 3rd, 4th ... 11th, 12th, 13th, 21st ..."""
    suffix = (
        "th"
        if 10 <= day % 100 <= 20
        else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    )
    return f"{day}{suffix}"


class PayPeriodSettings(HorillaModel):
    """
    When a pay month begins and ends, for one company.

    Only calendar months are offered. A cut-off cycle — the 26th to the 25th —
    is a real requirement and is deliberately NOT a choice here yet, because
    it is not a settings question: ``months_between_range`` splits any range
    into calendar months and counts working days per calendar month, and the
    proration bases and the loss-of-pay divisor read those counts. Offering
    the option before that is audited would mean prorating against the wrong
    boundaries, quietly.
    """

    CALENDAR_MONTH = "calendar_month"
    CYCLE_DAY = "cycle_day"
    BOUNDARY_CHOICES = [
        (CALENDAR_MONTH, _("Calendar month (1st to last day)")),
        (CYCLE_DAY, _("Cycle starting on a chosen day")),
    ]

    boundary = models.CharField(
        max_length=20,
        choices=BOUNDARY_CHOICES,
        default=CALENDAR_MONTH,
        verbose_name=_("Period Runs"),
        help_text=_(
            "How a pay period is bounded. A cycle starts on a chosen day and runs "
            "for as many days as the month it starts in has, so it can cross into "
            "the next month (from the 15th of September to the 14th of October). "
            "Each month's share is worked out against that month's own working days."
        ),
    )
    LAST_DAY = 31
    START_DAY_CHOICES = [
        (1, _("1st (calendar month)")),
        *[(day, _ordinal(day)) for day in range(2, 31)],
        (LAST_DAY, _("Last day")),
    ]
    cycle_start_day = models.PositiveSmallIntegerField(
        default=1,
        choices=START_DAY_CHOICES,
        verbose_name=_("Period Runs"),
        help_text=_(
            "The day a pay period begins. It runs until the day before the same day "
            "next month, so it can cross into the next month (from the 15th of "
            "September to the 14th of October). Each month's share is worked out "
            "against that month's own working days. The 29th and 30th fall back to "
            'the month\'s last day when it is shorter, and "Last day of the month" '
            "begins on whichever day ends each month, 28th to 31st."
        ),
    )
    pay_day_of_month = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Pay On Day"),
        help_text=_(
            "0 pays a number of days after the period ends (Pay Day). 1 to 30, or 31 for "
            "the last day of the month, pays on the first such day after the period ends; "
            "the 29th and 30th fall back to the month's last day when it is shorter."
        ),
    )
    pay_day_offset = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Pay Day"),
        help_text=_(
            "Days after the period ends that people are actually paid. Zero "
            "means the last day of the period. This is a date on the run, not "
            "something the engine calculates with."
        ),
    )
    input_cutoff_days = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Input Cut-off"),
        help_text=_(
            "Days before the period ends after which attendance and leave "
            "changes are not expected to affect the run. Advisory: it is "
            "shown on the run, and nothing is blocked by it."
        ),
    )

    auto_generate = models.BooleanField(
        default=False,
        verbose_name=_("Generate Payslips Automatically"),
        help_text=_(
            "Draft payslips are created for the company's employees on the day after "
            "each pay period ends."
        ),
    )

    last_generated_end = models.DateField(
        null=True,
        blank=True,
        editable=False,
        help_text=_(
            "End date of the latest period payslips were generated for. Claimed before "
            "generating, so two runs never generate the same period."
        ),
    )

    company_id = models.OneToOneField(
        Company,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name=_("Company"),
    )
    objects = HorillaCompanyManager("company_id")

    class Meta:
        verbose_name = _("Pay Period Settings")
        verbose_name_plural = _("Pay Period Settings")

    def __str__(self):
        return (
            f"{self.company_id or _('All companies')} — {self.get_boundary_display()}"
        )

    # --- the settings list in Payroll Settings ------------------------------------------------
    def get_company(self):
        return self.company_id or _("All companies")

    @staticmethod
    def _span(start, end):
        return f"{start.day} {start:%b %Y} \u2013 {end.day} {end:%b %Y}"

    def next_auto_run(self, today=None):
        """``(start, end, run_date)``: the period automatic generation does next, and when."""
        from datetime import date, timedelta

        today = today or date.today()
        last_start, last_end = self.last_completed_period(today)
        if (
            today == last_end + timedelta(days=1)
            and (self.last_generated_end or date.min) < last_end
        ):
            return last_start, last_end, today
        start, end = self.period_for(today)
        return start, end, end + timedelta(days=1)

    def manual_period(self, today=None):
        """The period Generate Payslips does: the last one that has finished."""
        from datetime import date

        return self.last_completed_period(today or date.today())

    def generate_title(self):
        start, end = self.manual_period()
        return _("Generate payslips now for %(period)s") % {
            "period": self._span(start, end)
        }

    def auto_generate_display(self):
        from django.utils.html import format_html

        if not self.auto_generate:
            return _("Off")
        start, end, run = self.next_auto_run()
        text = _("Generates payslips for %(period)s on %(run)s.") % {
            "period": self._span(start, end),
            "run": f"{run.day} {run:%b %Y}",
        }
        return format_html(
            '<span class="pp-tip">{}<span class="pp-tip__body">{}</span></span>',
            _("On"),
            text,
        )

    def get_generate_url(self):
        from django.urls import reverse

        return reverse("pay-period-generate", kwargs={"pk": self.pk})

    def get_instance_id(self):
        return self.pk

    def pay_day_display(self):
        """The pay day as the list shows it: a day of the month, or days after the period."""
        if self.pay_day_of_month:
            return (
                _("Last day")
                if self.pay_day_of_month == self.LAST_DAY
                else _ordinal(self.pay_day_of_month)
            )
        days = self.pay_day_offset or 0
        if days == 0:
            return _("On the last day of the period")
        return _("%(days)s days after the period ends") % {"days": days}

    def get_update_url(self):
        from django.urls import reverse

        return reverse("pay-period-update", kwargs={"pk": self.pk})

    def get_delete_url(self):
        from django.urls import reverse

        return reverse("pay-period-delete", kwargs={"pk": self.pk})

    def clean(self):
        # One setting per company, and one for "all companies". The database's own uniqueness
        # only covers real companies: it lets any number of rows through with no company.
        from django.core.exceptions import ValidationError

        if self.company_id_id is None:
            others = PayPeriodSettings.objects.entire().filter(company_id__isnull=True)
            if self.pk:
                others = others.exclude(pk=self.pk)
            if others.exists():
                raise ValidationError(
                    {"company_id": _("A pay period for all companies already exists.")}
                )

    @property
    def start_day(self):
        """The day a period begins, 1 to 30, or LAST_DAY for the last day of each month."""
        day = self.cycle_start_day or 1
        return day if 1 <= day <= self.LAST_DAY else 1

    def start_in(self, year, month):
        """The date the period of that month begins: the chosen day, or the month's last day."""
        import calendar
        from datetime import date

        last = calendar.monthrange(year, month)[1]
        return date(year, month, min(self.start_day, last))

    def _next_month(self, year, month):
        return (year, month + 1) if month < 12 else (year + 1, 1)

    def period_for(self, on_date):
        """
        The pay period containing ``on_date``, as ``(start, end)``.

        One place that answers this, so the wizard, the scheduler and any
        report agree on what "this month" means instead of each deciding. A
        period ends the day before the next one begins, so consecutive periods
        leave no gap and no overlap whatever day they start on.
        """
        from datetime import timedelta

        this = self.start_in(on_date.year, on_date.month)
        if on_date >= this:
            start = this
        else:
            year, month = (
                (on_date.year, on_date.month - 1)
                if on_date.month > 1
                else (on_date.year - 1, 12)
            )
            start = self.start_in(year, month)
        following = self.start_in(*self._next_month(start.year, start.month))
        return start, following - timedelta(days=1)

    def end_for(self, start):
        """
        The last day of a period that begins on ``start``.

        A start that falls on one of this setting's own boundaries ends where the next
        one begins. Any other start (the wizard allows one) runs for as many days as its
        own month has.
        """
        from datetime import timedelta

        if start == self.start_in(start.year, start.month):
            return self.start_in(
                *self._next_month(start.year, start.month)
            ) - timedelta(days=1)
        return self.period_end_for(start)

    def last_completed_period(self, today):
        """The most recent period that has finished: the one before the period containing ``today``."""
        from datetime import timedelta

        start, _end = self.period_for(today)
        return self.period_for(start - timedelta(days=1))

    def save(self, *args, **kwargs):
        # Kept in step for anything that still reads it: 1st is the calendar month.
        self.boundary = self.CALENDAR_MONTH if self.start_day == 1 else self.CYCLE_DAY
        super().save(*args, **kwargs)

    def summary(self):
        """The rule in a sentence, for the places that say where a period comes from."""
        day = self.start_day
        if day == 1:
            return str(_("Calendar month (1st to last day)"))
        if day == self.LAST_DAY:
            return str(_("Cycle starting on the last day of each month"))
        shorter = str(_(" (or the last day if shorter)")) if day > 28 else ""
        return (
            str(
                _("Cycle starting on the %(day)s of each month")
                % {"day": _ordinal(day)}
            )
            + shorter
        )

    @staticmethod
    def period_end_for(start):
        """
        The last day of a pay period that begins on ``start``.

        As many days as the start's own month has, so a period may begin on any
        day and cross into the next month: from the 1st it is the calendar month,
        from the 15th of September it runs to the 14th of October.
        """
        import calendar
        from datetime import timedelta

        return start + timedelta(
            days=calendar.monthrange(start.year, start.month)[1] - 1
        )

    def pay_date_for(self, period_end):
        """
        When people are paid for a period ending on ``period_end``.

        Either a number of days after it, or the first occurrence of a day of the month after
        it: the 5th, the 30th (the last day when the month is shorter), or the last day.
        """
        import calendar
        from datetime import date, timedelta

        day = self.pay_day_of_month
        if not day:
            return period_end + timedelta(days=self.pay_day_offset)
        year, month = period_end.year, period_end.month
        for _step in range(2):
            candidate = date(year, month, min(day, calendar.monthrange(year, month)[1]))
            if candidate > period_end:
                return candidate
            year, month = (year, month + 1) if month < 12 else (year + 1, 1)
        return candidate

    @classmethod
    def for_company(cls, company):
        """
        The settings in force, falling back to an unsaved default.

        Returned rather than created, so merely opening the wizard on a
        company that has never configured payroll does not write a row.
        """
        found = cls.objects.entire().filter(company_id=company).first()
        if found is None:
            found = cls.objects.entire().filter(company_id__isnull=True).first()
        return found or cls()


class PayrollBatch(HorillaModel):
    """
    One payroll run: a period, the people in it, and what it came to.

    The status is a state machine rather than a free assignment. Payroll is
    approved by someone and then paid, and a system that lets a paid run be
    moved back to draft cannot be relied on to say what was paid.
    """

    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (DRAFT, _("Draft")),
        (REVIEW, _("In review")),
        (APPROVED, _("Approved")),
        (PAID, _("Paid")),
        (CANCELLED, _("Cancelled")),
    ]

    # Paid is terminal. A run that has been paid is a record of money that
    # left the business; correcting it means another run, not an edit.
    ALLOWED_TRANSITIONS = {
        DRAFT: {REVIEW, APPROVED, CANCELLED},
        REVIEW: {DRAFT, APPROVED, CANCELLED},
        APPROVED: {REVIEW, PAID, CANCELLED},
        PAID: set(),
        CANCELLED: set(),
    }

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    PROGRESS_CHOICES = [
        (PENDING, _("Not started")),
        (RUNNING, _("Generating")),
        (DONE, _("Finished")),
        (FAILED, _("Failed")),
    ]

    batch_name = models.CharField(max_length=150, verbose_name=_("Batch name"))
    period_start = models.DateField(verbose_name=_("Period start"))
    period_end = models.DateField(verbose_name=_("Period end"))
    pay_date = models.DateField(null=True, blank=True, verbose_name=_("Pay date"))

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=DRAFT, db_index=True
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payroll_batches",
        editable=False,
    )

    # Denormalised, as the v2 engine did it: a run list showing twenty runs
    # would otherwise aggregate every payslip of every one of them to draw a
    # single column.
    employee_count = models.PositiveIntegerField(default=0, editable=False)
    processed_count = models.PositiveIntegerField(default=0, editable=False)
    generated_count = models.PositiveIntegerField(default=0, editable=False)
    failed_count = models.PositiveIntegerField(default=0, editable=False)
    flagged_count = models.PositiveIntegerField(
        default=0, editable=False, verbose_name=_("Flagged (net zero or capped)")
    )

    total_gross = models.FloatField(default=0, editable=False)
    total_deductions = models.FloatField(default=0, editable=False)
    total_net = models.FloatField(default=0, editable=False)
    total_employer = models.FloatField(default=0, editable=False)

    progress_state = models.CharField(
        max_length=20, choices=PROGRESS_CHOICES, default=PENDING, editable=False
    )
    last_error = models.TextField(blank=True, default="", editable=False)

    company_id = models.ForeignKey(
        Company,
        null=True,
        editable=False,
        on_delete=models.PROTECT,
        related_name="payroll_batches",
    )
    objects = HorillaCompanyManager("company_id")

    class Meta:
        ordering = ["-period_end", "-created_at"]
        verbose_name = _("Payroll Batch")
        verbose_name_plural = _("Payroll Batches")
        indexes = [
            models.Index(
                fields=["status", "-period_end"], name="payroll_batch_status_idx"
            ),
        ]

    def __str__(self):
        return f"{self.batch_name} ({self.period_start} — {self.period_end})"

    def save(self, *args, **kwargs):
        from base.auth_backends import stamp_company_on_create

        if not self.pk:
            stamp_company_on_create(self)
        super().save(*args, **kwargs)

    def can_transition_to(self, new_status):
        """
        ``(allowed, reason)`` rather than a raise, so a view can say why.
        """
        if new_status == self.status:
            return False, _("It is already %(status)s.") % {
                "status": self.get_status_display()
            }
        if new_status not in dict(self.STATUS_CHOICES):
            return False, _("%(status)s is not a status.") % {"status": new_status}
        if new_status not in self.ALLOWED_TRANSITIONS[self.status]:
            if self.status == self.PAID:
                return False, _(
                    "A paid run cannot be changed. Correct it with another run."
                )
            return False, _("A run that is %(current)s cannot become %(wanted)s.") % {
                "current": self.get_status_display(),
                "wanted": dict(self.STATUS_CHOICES)[new_status],
            }
        if (
            new_status in (self.APPROVED, self.PAID)
            and self.progress_state != self.DONE
        ):
            return False, _("The run has not finished generating.")
        return True, ""

    @property
    def percent_complete(self):
        if not self.employee_count:
            return 0
        return min(100, round(self.processed_count / self.employee_count * 100))

    @property
    def is_finished(self):
        return self.progress_state in (self.DONE, self.FAILED)

    def breadcrumb_name(self):
        return self.batch_name

    @property
    def active_payslip_count(self):
        """Payslips of employees who are still active -- the count a run shows."""
        return self.payslips.filter(employee_id__is_active=True).count()

    # -- columns of the runs list (payroll.cbv.payroll_batch) --------------
    def period_display(self):
        start, end = self.period_start, self.period_end
        return f"{start.day} {start:%b} – {end.day} {end:%b %Y}"

    def get_detail_url(self):
        from django.urls import reverse

        return reverse("payroll-batch-detail", args=[self.pk])

    def run_actions(self):
        from horilla_views.cbv_methods import render_template

        return render_template(
            path="payroll/batch/_run_actions.html", context={"instance": self}
        )

    def people_display(self):
        return self.active_payslip_count

    def pay_date_display(self):
        return f"{self.pay_date:%d %b %Y}" if self.pay_date else "—"

    def _money(self, amount):
        from horilla_views.cbv_methods import render_template

        return render_template(
            path="cbv/payslip/pay_display.html", context={"amount": amount}
        )

    def gross_display(self):
        return self._money(self.total_gross)

    def deductions_display(self):
        return self._money(self.total_deductions)

    def net_display(self):
        return self._money(self.total_net)

    def status_pill(self):
        from django.utils.html import format_html

        return format_html(
            '<span class="pb__pill pb__pill--{}">{}</span>',
            self.status,
            self.get_status_display(),
        )

    def refresh_totals(self):
        """
        Recompute the counters from the payslips actually attached.

        Called at the end of a run rather than incremented as it goes: a
        resumed or retried run would otherwise double-count.
        """
        from django.db.models import Count, Sum

        figures = self.payslips.aggregate(
            count=Count("id"),
            gross=Sum("gross_pay"),
            deduction=Sum("deduction"),
            net=Sum("net_pay"),
        )
        self.generated_count = figures["count"] or 0
        self.total_gross = figures["gross"] or 0
        self.total_deductions = figures["deduction"] or 0
        self.total_net = figures["net"] or 0
        self.flagged_count = self.payslips.filter(net_pay__lte=0).count()
        self.failed_count = self.lines.filter(status=PayrollBatchLine.FAILED).count()
        self.save(
            update_fields=[
                "generated_count",
                "total_gross",
                "total_deductions",
                "total_net",
                "flagged_count",
                "failed_count",
            ]
        )


class PayrollBatchLine(HorillaModel):
    """
    One employee's place in a run: queued, done, failed, or skipped.

    The run is generated in slices rather than in one request, so it needs to
    know who has already been done — otherwise a resumed run would pay people
    twice, and a failed employee would be indistinguishable from one not yet
    reached. It is also what the result table is built from: "22 generated, 3
    failed" is only useful if you can see which three and why.
    """

    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    STATUS_CHOICES = [
        (QUEUED, _("Queued")),
        (DONE, _("Generated")),
        (FAILED, _("Failed")),
        (SKIPPED, _("Skipped")),
    ]

    payroll_batch = models.ForeignKey(
        PayrollBatch, on_delete=models.CASCADE, related_name="lines"
    )
    employee_id = models.ForeignKey(
        "employee.Employee",
        on_delete=models.CASCADE,
        related_name="payroll_batch_lines",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=QUEUED, db_index=True
    )
    message = models.TextField(blank=True, default="")
    payslip = models.ForeignKey(
        "payroll.Payslip",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="run_lines",
    )

    objects = HorillaCompanyManager("employee_id__employee_work_info__company_id")

    class Meta:
        ordering = ["employee_id__employee_first_name", "id"]
        unique_together = [["payroll_batch", "employee_id"]]
        verbose_name = _("Payroll Batch Line")
        verbose_name_plural = _("Payroll Batch Lines")

    def __str__(self):
        return f"{self.employee_id} — {self.get_status_display()}"
