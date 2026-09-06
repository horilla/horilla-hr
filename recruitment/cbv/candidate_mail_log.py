"""
This page is handling the cbv methods of mail log tab in employee individual page.
"""

from typing import Any

from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.cbv.mail_log_tab import MailLogTabList
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import HorillaListView
from recruitment.cbv_decorators import all_manager_can_enter
from recruitment.models import Candidate


@method_decorator(login_required, name="dispatch")
@method_decorator(
    all_manager_can_enter(perm="recruitment.view_candidate"), name="dispatch"
)
class CandidateMailLogTabList(MailLogTabList):
    """
    list view for mail log tab in candidate
    """

    def get_context_data(self, **kwargs: Any):
        """
        Adds a search URL to the context based on the candidate's primary key.
        """
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        context["search_url"] = (
            f"{reverse('candidate-mail-log-list',kwargs={'pk': pk})}"
        )
        return context

    def get_queryset(self):
        """
        Returns a filtered and ordered queryset of email logs for the specified candidate.
        """

        # queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        candidate_obj = Candidate.objects.filter(id=pk).first()
        if not candidate_obj:
            return HorillaListView.get_queryset(self).none()
        return (
            HorillaListView.get_queryset(self)
            .filter(to__icontains=candidate_obj.email)
            .order_by("-created_at")
        )

    def dispatch(self, request, *args, **kwargs):
        """
        To avoide parent permissions
        """
        if not Candidate.objects.filter(id=kwargs.get("pk")).exists():
            return HttpResponse()
        return super(MailLogTabList, self).dispatch(request, *args, **kwargs)
