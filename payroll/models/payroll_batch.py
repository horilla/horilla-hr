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

    BOUNDARY_CHOICES = [
        ("calendar_month", _("Calendar month (1st to last day)")),
    ]

    boundary = models.CharField(
        max_length=20,
        choices=BOUNDARY_CHOICES,
        default="calendar_month",
        verbose_name=_("Period Runs"),
        help_text=_(
            "How a pay period is bounded. Cut-off cycles such as the 26th to "
            "the 25th are not yet supported: the engine counts working days "
            "by calendar month, so a period crossing a month boundary would "
            "prorate against the wrong one."
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

    def period_for(self, on_date):
        """
        The pay period containing ``on_date``, as ``(start, end)``.

        One place that answers this, so the wizard, the scheduler and any
        report agree on what "this month" means instead of each deciding.
        """
        import calendar

        start = on_date.replace(day=1)
        last = calendar.monthrange(on_date.year, on_date.month)[1]
        return start, on_date.replace(day=last)

    def pay_date_for(self, period_end):
        """When people are paid for a period ending on ``period_end``."""
        from datetime import timedelta

        return period_end + timedelta(days=self.pay_day_offset)

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
