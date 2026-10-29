from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from geopy.distance import geodesic
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.models import Company
from geofencing.forms import GeoFencingSetupForm
from horilla.decorators import login_required

from .models import GeoFencing
from .serializers import EmployeeLocationSerializer, GeoFencingSetupSerializer


class GeoFencingSetupGetPostAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("geofencing.view_geofencing", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        company = request.user.employee_get.get_company()
        location = get_object_or_404(GeoFencing, pk=company.id)
        serializer = GeoFencingSetupSerializer(location)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @method_decorator(
        permission_required("geofencing.add_geofencing", raise_exception=True),
        name="dispatch",
    )
    def post(self, request):
        data = request.data
        if not request.user.is_superuser:
            if isinstance(data, QueryDict):
                data = data.dict()
            company = request.user.employee_get.get_company()
            if company:
                data["company_id"] = company.id
        serializer = GeoFencingSetupSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GeoFencingSetupPutDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_location(self, pk):
        try:
            return GeoFencing.objects.get(pk=pk)
        except Exception as e:
            raise serializers.ValidationError(e)

    @method_decorator(
        permission_required("geofencing.change_geofencing", raise_exception=True),
        name="dispatch",
    )
    def put(self, request, pk):
        location = self.get_location(pk)
        company = request.user.employee_get.get_company()
        if request.user.is_superuser or company == location.company_id:
            serializer = GeoFencingSetupSerializer(
                location, data=request.data, partial=True
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        raise serializers.ValidationError(_("Access Denied.."))

    @method_decorator(
        permission_required("geofencing.delete_geofencing", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request, pk):
        location = self.get_location(pk)
        company = request.user.employee_get.get_company()
        if request.user.is_superuser or company == location.company_id:
            location.delete()
            return Response(
                {"message": "GeoFencing location deleted successfully"},
                status=status.HTTP_200_OK,
            )
        raise serializers.ValidationError(_("Access Denied.."))


class GeoFencingEmployeeLocationCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_company(self, request):
        try:
            company = request.user.employee_get.get_company()
            return company
        except Exception as e:
            raise serializers.ValidationError(e)

    def get_company_location(self, request):
        company = self.get_company(request)
        location = GeoFencing.for_company(company)
        if location is None:
            raise serializers.ValidationError(_("No geofencing is configured."))
        return location

    def post(self, request):
        serializer = EmployeeLocationSerializer(data=request.data)
        company_location = self.get_company_location(request)
        if company_location.start:
            if serializer.is_valid():
                geofence_center = (
                    company_location.latitude,
                    company_location.longitude,
                )
                employee_location = (
                    request.data.get("latitude"),
                    request.data.get("longitude"),
                )
                distance = geodesic(geofence_center, employee_location).meters
                if distance <= company_location.radius_in_meters:
                    return Response(
                        {"message": "Inside the geofence"}, status=status.HTTP_200_OK
                    )
                return Response(
                    {"message": "Outside the geofence"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        raise serializers.ValidationError(_("Geofencing is not yet started.."))


class GeoFencingSetUpPermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(
        permission_required("geofencing.view_geofencing", raise_exception=True),
        name="dispatch",
    )
    def get(self, request):
        return Response(status=200)


def get_company(request):
    try:
        selected_company = request.session.get("selected_company")
        if selected_company == "all":
            return None
        company = Company.objects.get(id=selected_company)
        return company
    except Exception as e:
        raise serializers.ValidationError(e)


@login_required
@permission_required("geofencing.add_localbackup")
def geo_location_config(request):
    """
    Edit the geofence of the selected company, or the global one when "all companies" is
    selected. The instance is given its company *before* the form is validated: the model's
    clean() allows only one fence without a company, so validating a company's new fence while
    its company was still empty was rejected ("Not valid") as soon as a global fence existed.
    """
    try:
        company = get_company(request)
    except serializers.ValidationError:
        messages.error(request, _("Select a company first."))
        return render(request, "geo_config.html", {"form": GeoFencingSetupForm()})
    own_fence = GeoFencing.objects.filter(company_id=company).first()
    instance = own_fence or GeoFencing(company_id=company)
    form = GeoFencingSetupForm(instance=instance)
    if request.method == "POST":
        form = GeoFencingSetupForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, _("Geofencing config created successfully."))
        else:
            messages.info(request, _("Not valid"))
    return render(request, "geo_config.html", {"form": form})
