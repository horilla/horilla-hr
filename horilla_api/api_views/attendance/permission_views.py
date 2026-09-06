from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ...api_decorators.base.decorators import manager_permission_required


class AttendancePermissionCheck(APIView):
    permission_classes = [IsAuthenticated]

    @manager_permission_required("attendance.view_attendance")
    def get(self, request):

        return Response(status=200)
