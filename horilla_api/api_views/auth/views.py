from axes.handlers.proxy import AxesProxyHandler
from django.contrib.auth import authenticate
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from drf_yasg import openapi
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from horilla_api.docs import document_api

from ...api_serializers.auth.serializers import (
    GetEmployeeSerializer,
    LoginRequestSerializer,
    PasswordResetSerializer,
)


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    # The only unauthenticated write path in the API. django-axes locks an
    # account after repeated *failed* passwords, but counts nothing when the
    # credentials are valid -- so a leaked password can be replayed to mint
    # tokens as fast as the server answers. ScopedRateThrottle bounds that
    # by IP, on top of the axes lockout.
    throttle_scope = "login"

    @document_api(
        operation_description="Authenticate user and return JWT access token with employee info",
        request_body=LoginRequestSerializer,
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "employee": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "full_name": openapi.Schema(type=openapi.TYPE_STRING),
                            "employee_profile": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Profile image URL",
                            ),
                        },
                    ),
                    "access": openapi.Schema(
                        type=openapi.TYPE_STRING, description="JWT access token"
                    ),
                    "face_detection": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "face_detection_image": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Face detection image URL",
                        nullable=True,
                    ),
                    "geo_fencing": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "company_id": openapi.Schema(
                        type=openapi.TYPE_INTEGER, nullable=True
                    ),
                },
            ),
        },
        tags=["auth"],
    )
    def post(self, request):
        if "username" in request.data and "password" in request.data:
            username = request.data.get("username")
            password = request.data.get("password")
            # Pass `request`: django-axes needs it to attribute the attempt to
            # a client and enforce the lockout. Without it the API login is
            # exempt from the brute-force protection the HTML login has --
            # and axes raises rather than silently allowing it.
            user = authenticate(request, username=username, password=password)
            if user:
                refresh = RefreshToken.for_user(user)
                employee = user.employee_get
                face_detection = False
                face_detection_image = None
                geo_fencing = False
                company_id = None
                # Each of these is optional configuration: get_company() can
                # return None, the face_detection and geo_fencing reverse
                # one-to-ones need not exist, and an ImageField with no file
                # raises on .url. Narrowed from bare excepts so a genuine
                # failure in this block is logged instead of silently
                # degrading the login response.
                company = employee.get_company()
                if company is not None:
                    company_id = company.id
                    try:
                        face_detection = company.face_detection.start
                    except (ObjectDoesNotExist, AttributeError):
                        pass
                    try:
                        geo_fencing = company.geo_fencing.start
                    except (ObjectDoesNotExist, AttributeError):
                        pass
                try:
                    face_detection_image = employee.face_detection.image.url
                except (ObjectDoesNotExist, AttributeError, ValueError):
                    pass
                result = {
                    "employee": GetEmployeeSerializer(employee).data,
                    "access": str(refresh.access_token),
                    "face_detection": face_detection,
                    "face_detection_image": face_detection_image,
                    "geo_fencing": geo_fencing,
                    "company_id": company_id,
                }
                return Response(result, status=200)
            else:
                # A locked-out caller must be told so, not handed another 401.
                # AxesStandaloneBackend returns None rather than raising, so
                # without this check axes counts the failures but never blocks
                # -- the API would keep accepting guesses past the limit while
                # the HTML login stops at five.
                if AxesProxyHandler.is_locked(
                    request, credentials={"username": username}
                ):
                    return Response(
                        {
                            "error": _(
                                "Too many failed login attempts. Try again later."
                            )
                        },
                        status=429,
                    )
                return Response({"error": _("Invalid credentials")}, status=401)
        else:
            return Response(
                {"error": _("Please provide Username and Password")}, status=400
            )


class PasswordResetAPIView(APIView):
    """
    Allows an authenticated employee to change their own password.

    GET  — returns the fields required for the reset form.
    POST — verifies the old password and saves the new one.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    def get(self, _request):
        return Response(
            {"fields": ["old_password", "new_password", "confirm_password"]},
            status=200,
        )

    def post(self, request):
        serializer = PasswordResetSerializer(
            data=request.data, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"message": _("Password updated successfully.")}, status=200)
