"""
Models for Asset Management System

This module defines Django models to manage assets, their categories, assigning, and requests
within an Asset Management System.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from base.horilla_company_manager import HorillaCompanyManager
from base.models import Company
from employee.models import Employee
from horilla.models import HorillaModel, upload_path
from horilla_views.cbv_methods import render_template


class AssetCategory(HorillaModel):
    """
    Represents a category for different types of assets.
    """

    asset_category_name = models.CharField(
        max_length=255, unique=True, verbose_name=_("Name")
    )
    asset_category_description = models.TextField(
        max_length=255, verbose_name=_("Description")
    )
    objects = models.Manager()
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    objects = HorillaCompanyManager("company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        verbose_name = _("Asset Category")
        verbose_name_plural = _("Asset Categories")

    def __str__(self):
        return f"{self.asset_category_name}"


class AssetLot(HorillaModel):
    """
    Represents a lot associated with a collection of assets.
    """

    lot_number = models.CharField(
        max_length=30,
        null=False,
        blank=False,
        unique=True,
        verbose_name=_("Batch Number"),
    )
    lot_description = models.TextField(
        null=True, blank=True, verbose_name=_("Description")
    )
    company_id = models.ManyToManyField(Company, blank=True, verbose_name=_("Company"))
    objects = HorillaCompanyManager()

    class Meta:
        """
        Meta class to add additional options
        """

        ordering = ["-created_at"]
        verbose_name = _("Asset Batch")
        verbose_name_plural = _("Asset Batches")

    def __str__(self):
        return f"{self.lot_number}"

    def actions(self):
        """
        This method for get custom column for action.
        """

        return render_template(
            path="cbv/asset_batch_no/actions.html",
            context={"instance": self},
        )

    def asset_batch_detail(self):
        """
        detail view
        """

        url = reverse("asset-batch-detail-view", kwargs={"pk": self.pk})

        return url

    def assets_column(self):
        """
        This method for get custom column for action.
        """

        return render_template(
            path="cbv/asset_batch_no/assets_col.html",
            context={"instance": self},
        )

    def detail_actions(self):
        return render_template(
            path="cbv/asset_batch_no/detail_actions.html",
            context={"instance": self},
        )

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("asset-batch-update", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("asset-batch-number-delete", kwargs={"batch_id": self.pk})
        return url


class Asset(HorillaModel):
    """
    Represents a asset with various attributes.
    """

    ASSET_STATUS = [
        ("In use", _("In Use")),
        ("Available", _("Available")),
        ("Not-Available", _("Not-Available")),
    ]
    asset_name = models.CharField(max_length=255, verbose_name=_("Asset Name"))
    owner = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Assigned To"),
    )
    asset_description = models.TextField(
        null=True, blank=True, max_length=255, verbose_name=_("Description")
    )
    asset_tracking_id = models.CharField(
        max_length=30, null=False, unique=True, verbose_name=_("Tracking Id")
    )
    asset_purchase_date = models.DateField(verbose_name=_("Purchase Date"))
    asset_purchase_cost = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name=_("Cost")
    )
    asset_category_id = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, verbose_name=_("Category")
    )
    asset_status = models.CharField(
        choices=ASSET_STATUS,
        default="Available",
        max_length=40,
        verbose_name=_("Status"),
    )
    asset_lot_number_id = models.ForeignKey(
        AssetLot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Batch No"),
    )
    quantity = models.IntegerField(default=1, verbose_name=_("Quantity"))
    expiry_date = models.DateField(null=True, blank=True, verbose_name=_("Expiry Date"))
    notify_before = models.IntegerField(
        default=1, null=True, verbose_name=_("Notify Before (days)")
    )
    objects = HorillaCompanyManager("asset_category_id__company_id")

    @classmethod
    def available_assets(cls):
        """Return assets that still have at least one unit available for assignment."""
        today = timezone.now().date()
        return cls.objects.filter(asset_status="Available").filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gte=today)
        )

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.now().date())

    def current_assignees(self):
        """Employees this asset is currently (actively) assigned to."""
        return Employee.objects.filter(
            allocated_employee__asset_id=self,
            allocated_employee__return_date__isnull=True,
        ).distinct()

    @property
    def available_count(self):
        return self.asset_items.filter(status="Available").count()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Asset")
        verbose_name_plural = _("Assets")

    def __str__(self):
        return f"{self.asset_tracking_id}-{self.asset_name}"

    def asset_name_display(self):
        return self.asset_name

    def action_column(self):
        """
        Action column for asset
        """
        return render_template(
            path="asset/action_column.html", context={"instance": self}
        )

    def asset_status_col(self):
        """
        This method for get custom column for status.
        """

        if self.quantity > 1:
            label = self.get_asset_status_display()
            label = f"{label}<span class='inline-block border-2 border-solid rounded font-bold text-[0.8rem] px-2 py-1 text-[hsl(8,77%,56%)] border-[hsl(8,77%,56%)] ms-5' title='{self.available_count} of {self.quantity} Available'>{self.available_count}/{self.quantity}</span>"
            return label
        return self.get_asset_status_display()

    def row_status_class(self):
        """
        This method for get custom column for status.
        """

        status_class_map = {
            "Available": "row-status--yellow",
            "In use": "row-status--blue",
            "Not-Available": "row-status--gray",
        }
        if self.is_expired:
            return "row-status--red"
        return status_class_map.get(self.asset_status, "")

    def detail_view_action(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/asset/detail_action.html",
            context={"instance": self},
        )

    def asset_detail(self):
        """
        detail view url
        """

        url = reverse_lazy("asset-information", kwargs={"pk": self.pk})
        return url

    def get_update_url(self):
        """
        This method to get update url
        """
        url = reverse_lazy("asset-update", kwargs={"pk": self.pk})
        return url

    def get_delete_url(self):
        """
        This method to get delete url
        """
        url = reverse_lazy("asset-delete", kwargs={"asset_id": self.pk})
        return url

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_asset_items()
        self.update_status_from_items()

    def sync_asset_items(self):
        """
        Create placeholder AssetItems so the item count matches quantity.
        Never removes items - decreasing quantity is a manual/guarded operation.
        """
        existing = self.asset_items.count()
        if existing < self.quantity:
            base_id = self.asset_tracking_id or f"AST{self.pk}"
            new_items = [
                AssetItem(
                    asset_id=self,
                    tracking_id=base_id if idx == 1 else f"{base_id}-{idx}",
                )
                for idx in range(existing + 1, self.quantity + 1)
            ]
            AssetItem.objects.bulk_create(new_items)

        if self.quantity == 1:
            # Single-unit assets have no separate item-editing UI, so the
            # sole item's tracking ID just mirrors the parent's - editing
            # the asset's own Tracking Id field is the only edit path.
            sole_item = self.asset_items.first()
            if sole_item and sole_item.tracking_id != self.asset_tracking_id:
                AssetItem.objects.filter(pk=sole_item.pk).update(
                    tracking_id=self.asset_tracking_id
                )

    def update_status_from_items(self):
        """Recompute asset_status from the aggregate status of its AssetItems."""
        if self.quantity < 1:
            new_status = "Not-Available"
        else:
            statuses = set(self.asset_items.values_list("status", flat=True))
            if not statuses:
                return
            if "Available" in statuses:
                new_status = "Available"
            elif "In use" in statuses:
                new_status = "In use"
            else:
                new_status = "Not-Available"
        if new_status != self.asset_status:
            self.asset_status = new_status
            Asset.objects.entire().filter(pk=self.pk).update(asset_status=new_status)

    def asset_items_action(self):
        """
        This method for get custom column for viewing this asset's items.
        """
        if self.quantity <= 1:
            return ""
        return render_template(
            path="cbv/asset/asset_items_action.html",
            context={"instance": self},
        )

    def clean(self):
        existing_asset = Asset.objects.filter(
            asset_tracking_id=self.asset_tracking_id
        ).exclude(
            id=self.pk
        )  # Exclude the current instance if updating
        if existing_asset.exists():
            raise ValidationError(
                {
                    "asset_description": _(
                        "An asset with this tracking ID already exists."
                    )
                }
            )
        return super().clean()


class AssetItem(HorillaModel):
    """
    Represents a single physical unit belonging to an Asset.
    """

    STATUS = [
        ("Available", _("Available")),
        ("In use", _("In Use")),
        ("Damaged", _("Damaged")),
        ("Lost", _("Lost")),
    ]

    asset_id = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="asset_items",
        verbose_name=_("Asset"),
    )
    tracking_id = models.CharField(
        max_length=30, unique=True, verbose_name=_("Tracking Id")
    )
    status = models.CharField(
        choices=STATUS,
        default="Available",
        max_length=20,
        verbose_name=_("Status"),
    )
    objects = HorillaCompanyManager("asset_id__asset_category_id__company_id")

    class Meta:
        """
        Meta class to add additional options
        """

        ordering = ["tracking_id"]
        verbose_name = _("Asset Item")
        verbose_name_plural = _("Asset Items")

    def __str__(self):
        return f"{self.tracking_id}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.asset_id.update_status_from_items()

    def delete(self, *args, **kwargs):
        asset = self.asset_id
        super().delete(*args, **kwargs)
        asset.update_status_from_items()


class AssetReport(HorillaModel):
    """
    Model representing a report for an asset.

    Attributes:
    - title: A CharField for the title of the report (optional).
    - asset_id: A ForeignKey to the Asset model, linking the report to a specific asset.
    """

    title = models.CharField(max_length=255, blank=True, null=True)
    asset_id = models.ForeignKey(
        Asset, related_name="asset_report", on_delete=models.CASCADE
    )

    def __str__(self):
        """
        Returns a string representation of the AssetReport instance.
        If a title is present, it returns "asset_id - title".
        Otherwise, it returns "report for asset_id".
        """
        return (
            f"{self.asset_id} - {self.title}"
            if self.title
            else f"report for {self.asset_id}"
        )


class AssetDocuments(HorillaModel):
    """
    Model representing documents associated with an asset report.

    Attributes:
    - asset_report: A ForeignKey to the AssetReport model, linking the document to
    a specific asset report.
    - file: A FileField for uploading the document file (optional).
    """

    asset_report = models.ForeignKey(
        "AssetReport", related_name="documents", on_delete=models.CASCADE
    )
    file = models.FileField(upload_to=upload_path, blank=True, null=True)
    objects = models.Manager()

    class Meta:
        verbose_name = _("Asset Document")
        verbose_name_plural = _("Asset Documents")

    def __str__(self):
        return f"document for {self.asset_report}"


class ReturnImages(HorillaModel):
    """
    Model representing images associated with a returned asset.

    Attributes:
    - image: A FileField for uploading the image file (optional).
    """

    image = models.FileField(upload_to=upload_path, blank=True, null=True)


class AssetAssignment(HorillaModel):
    """
    Represents the allocation and return of assets to and from employees.
    """

    STATUS = [
        ("Minor damage", _("Minor damage")),
        ("Major damage", _("Major damage")),
        ("Healthy", _("Healthy")),
    ]
    asset_id = models.ForeignKey(
        Asset, on_delete=models.PROTECT, verbose_name=_("Asset")
    )
    asset_item_id = models.ForeignKey(
        AssetItem,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Asset Item"),
    )
    assigned_to_employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="allocated_employee",
        verbose_name=_("Assigned To"),
    )
    assigned_date = models.DateField(auto_now_add=True)
    assigned_by_employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="assigned_by",
        verbose_name=_("Assigned By"),
    )
    return_date = models.DateField(null=True, blank=True, verbose_name=_("Return Date"))
    return_condition = models.TextField(
        null=True, blank=True, verbose_name=_("Return Condition")
    )
    return_status = models.CharField(
        choices=STATUS,
        max_length=30,
        null=True,
        blank=True,
        verbose_name=_("Return Status"),
    )
    return_request = models.BooleanField(default=False)
    objects = HorillaCompanyManager("asset_id__asset_lot_number_id__company_id")
    return_images = models.ManyToManyField(
        ReturnImages, blank=True, related_name="return_images"
    )
    assign_images = models.ManyToManyField(
        ReturnImages,
        blank=True,
        related_name="assign_images",
        verbose_name=_("Assign Condition Images"),
    )
    objects = HorillaCompanyManager(
        "assigned_to_employee_id__employee_work_info__company_id"
    )

    class Meta:
        """Meta class for AssetAssignment model"""

        ordering = ["-id"]
        verbose_name = _("Asset Allocation")
        verbose_name_plural = _("Asset Allocations")

    def __str__(self):
        return f"{self.assigned_to_employee_id} --- {self.asset_id} --- {self.return_status}"

    def asset_detail_view(self):
        """
        for detail view of page
        """
        url = reverse("asset-history-detail-view", kwargs={"pk": self.pk})
        return url

    def assign_condition_img(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/asset_history/assign_condition.html",
            context={"instance": self},
        )

    def return_condition_img(self):
        """
        This method for get custome coloumn .
        """

        return render_template(
            path="cbv/asset_history/return_condition.html",
            context={"instance": self},
        )

    def asset_action(self):
        """
        This method for get custom column for asset tab action.
        """

        return render_template(
            path="cbv/request_and_allocation/asset_actions.html",
            context={"instance": self},
        )

    def return_status_col(self):
        """
        This method for get custom column for return date.
        """

        return render_template(
            path="cbv/request_and_allocation/return_status.html",
            context={"instance": self},
        )

    def allocation_action(self):
        """
        This method for get custom column for asset allocation tab actions.
        """

        return render_template(
            path="cbv/request_and_allocation/asset_allocation_action.html",
            context={"instance": self},
        )

    def allocation_option(self):
        """
        This method for get custom column for asset tab action.
        """

        return render_template(
            path="cbv/request_and_allocation/allocation_option.html",
            context={"instance": self},
        )

    def asset_detail_action(self):
        """
        This method for get custom column for asset detail  actions.
        """

        return render_template(
            path="cbv/request_and_allocation/asset_detail_action.html",
            context={"instance": self},
        )

    def asset_allocation_detail_action(self):
        """
        This method for get custom column for asset detail  actions.
        """

        return render_template(
            path="cbv/request_and_allocation/detail_action_asset_allocation.html",
            context={"instance": self},
        )

    def get_avatar(self):
        """
        Method will retun the api to the avatar or path to the question template
        """
        url = f"https://ui-avatars.com/api/?name={self.asset_id.asset_name}&background=random"
        return url

    def detail_view_asset(self):
        """
        detail view
        """

        url = reverse("asset-detail-view", kwargs={"pk": self.pk})
        return url

    def detail_view_asset_allocation(self):
        """
        detail view
        """

        url = reverse("asset-allocation-detail-view", kwargs={"pk": self.pk})
        return url

    def asset_detail_status(self):
        """
        Asset tab detail status
        """

        return (
            format_lazy(
                '<span class="link-primary">{}</span>', _("Requested to return")
            )
            if self.return_request
            else format_lazy(
                '<span style = "color : yellowgreen;">{}</span>', _("In use")
            )
        )

    def detail_status(self):
        """
        Asset allocation  tab detail status
        """
        if self.return_date:
            status = format_lazy(
                '<span style = "color : red;" >{}</span>', _("Returned")
            )
        elif self.return_request:
            status = format_lazy(
                '<span class="link-primary">{}</span>', _("Requested to return")
            )
        else:
            status = format_lazy(
                '<span style = "color : yellowgreen;" >{}</span>', _("Allocated")
            )
        return status

    def asset_allocation_detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.assigned_to_employee_id.get_department()} / {self.assigned_to_employee_id.get_job_position()}"

    def status_display(self):
        status = self.asset_id.get_asset_status_display()
        color_class = "oh-dot--warning"  # Adjust based on your status
        return format_html(
            '<span class="oh-dot oh-dot--small me-1 oh-dot--color {color_class}"></span>'
            '<span class="link-warning">{status}</span>',
            color_class=color_class,
            status=status,
        )

    def assigned_date_display(self):
        date_col = self.assigned_date
        color_class = "oh-dot--success"  # Adjust based on your status
        return format_html(
            '<span class="oh-dot oh-dot--small me-1 oh-dot--color {color_class}"></span>'
            '<span class="link-success dateformat_changer">{date_col}</span>',
            color_class=color_class,
            date_col=date_col,
        )

    def get_asset_of_offboarding_employee(self):
        url = f"{reverse('asset-request-allocation-view')}?assigned_to_employee_id={self.assigned_to_employee_id.id}"
        return url

    def get_send_mail_employee_link(self):
        if not self.assigned_to_employee_id:
            return ""
        url = reverse(
            "send-mail-employee", kwargs={"emp_id": self.assigned_to_employee_id.id}
        )
        title = _("Send Mail")
        html = format_html(
            """
            <a
                onclick="event.stopPropagation()"
                hx-get="{}"
                data-toggle="oh-modal-toggle"
                data-target="#sendMailModal"
                title="{}"
                hx-target="#mail-content"
            >
                <ion-icon name="mail-outline"></ion-icon>
            </a>
            """,
            url,
            title,
        )
        return html

    def days_left_display(self):
        expiry = self.asset_id.expiry_date
        if not expiry:
            return "—"
        delta = (expiry - timezone.now().date()).days
        if delta < 0:
            return format_html(
                "<span class='text-danger fw-bold'>Expired {} days ago</span>",
                abs(delta),
            )
        if delta == 0:
            return format_html("<span class='text-danger fw-bold'>Expires today</span>")
        if delta <= 7:
            return format_html("<span class='link-warning'>{} days left</span>", delta)
        return format_html("<span class='link-success'>{} days left</span>", delta)

    def reassign_action(self):
        url = reverse("asset-reassign", kwargs={"pk": self.pk})
        return format_html(
            "<a class='oh-btn oh-btn--secondary oh-btn--sm'"
            "   hx-get='{}'"
            "   hx-target='#genericModalBody'"
            "   data-toggle='oh-modal-toggle'"
            "   data-target='#genericModal'"
            "   onclick='event.stopPropagation()'>{}</a>",
            url,
            _("Reassign"),
        )


class AssetRequest(HorillaModel):
    """
    Represents a request for assets made by employees.
    """

    STATUS = [
        ("Requested", _("Requested")),
        ("Approved", _("Approved")),
        ("Rejected", _("Rejected")),
    ]
    requested_employee_id = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="requested_employee",
        null=False,
        blank=False,
        verbose_name=_("Requesting User"),
    )
    asset_category_id = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, verbose_name=_("Asset Category")
    )
    asset_request_date = models.DateField(auto_now_add=True)
    description = models.TextField(
        null=True, blank=True, max_length=255, verbose_name=_("Description")
    )
    asset_request_status = models.CharField(
        max_length=30, choices=STATUS, default="Requested", null=True, blank=True
    )
    objects = HorillaCompanyManager(
        "requested_employee_id__employee_work_info__company_id"
    )

    class Meta:
        """Meta class for AssetRequest model"""

        ordering = ["-id"]
        verbose_name = _("Asset Request")
        verbose_name_plural = _("Asset Requests")

    def status_col(self):
        """
        This method for get custom coloumn for status.
        """

        return render_template(
            path="cbv/request_and_allocation/status.html",
            context={"instance": self},
        )

    def action_col(self):
        """
        This method for get custom coloumn for action.
        """

        return render_template(
            path="cbv/request_and_allocation/asset_request_action.html",
            context={"instance": self},
        )

    def detail_action_col(self):
        """
        This method for get custom coloumn for detail action.
        """

        return render_template(
            path="cbv/request_and_allocation/asset_request_detail_action.html",
            context={"instance": self},
        )

    def option_col(self):
        """
        This method for get custom coloumn for action.
        """

        return render_template(
            path="cbv/request_and_allocation/asset_request_option.html",
            context={"instance": self},
        )

    def asset_request_detail_subtitle(self):
        """
        Return subtitle containing both department and job position information.
        """
        return f"{self.requested_employee_id.get_department()} / {self.requested_employee_id.get_job_position()}"

    def detail_view_asset_request(self):
        """
        detail view
        """
        url = reverse("asset-request-detail-view", kwargs={"pk": self.pk})
        return url

    def status_html_class(self):
        COLOR_CLASS = {
            "Approved": "oh-dot--success",
            "Requested": "oh-dot--info",
            "Rejected": "oh-dot--danger",
        }

        LINK_CLASS = {
            "Approved": "link-success",
            "Requested": "link-info",
            "Rejected": "link-danger",
        }
        status = self.asset_request_status
        return {
            "color": COLOR_CLASS.get(status),
            "link": LINK_CLASS.get(status),
        }
