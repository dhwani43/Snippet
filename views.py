from rest_framework.response import Response
from .serializers import VDocSerializer, ElementSerializer, VKeySerializer
from rest_framework import status
from .models import VDoc, Element, VKey
from api.models import File
from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.conf import settings
from django.utils import timezone
from backend.utils import upload_file_chunked
import json

class VKeyView(ModelViewSet):
    queryset = VKey.objects.all()
    serializer_class = VKeySerializer

    def create(self, request, *args, **kwargs):
        # Update the timestamp of the associated VDoc
        vDoc = VDoc.objects.get(id=request.data.get("vdoc"))
        vDoc.updated_at = timezone.now()
        vDoc.save()
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ElementView(ModelViewSet):
    serializer_class = ElementSerializer
    queryset = Element.objects.all()

    def create(self, request, *args, **kwargs):
        # Update the timestamp of the associated VDoc
        vDoc = VDoc.objects.get(id=request.data.get("vdoc"))
        vDoc.updated_at = timezone.now()
        vDoc.save()
        if request.data.get("field_type") == "checkbox":
            request.data["width"] = request.data["height"] = 25
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # Update the timestamp of the associated VDoc
        vDoc = VDoc.objects.get(id=request.data.get("vdoc"))
        vDoc.updated_at = timezone.now()
        vDoc.save()
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request, *args, **kwargs):
        # Update the timestamp of the associated VDoc
        vDoc = VDoc.objects.get(id=request.data.get("vdoc"))
        vDoc.updated_at = timezone.now()
        vDoc.save()
        return super().delete(request, *args, **kwargs)


class UndoRedo(APIView):
    def post(self, request, *args, **kwargs):
        vDoc = request.query_params.get("vDoc")
        # Delete all elements associated with the specified VDoc
        Element.objects.filter(vdoc=vDoc).all().delete()
        # Update the timestamp of the associated VDoc
        vDoc = VDoc.objects.get(id=vDoc)
        vDoc.updated_at = timezone.now()
        vDoc.save()
        if len(request.data):
            # Serialize and save new elements
            serializer = ElementSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response([], status=status.HTTP_200_OK)

class VDocsView(ModelViewSet):
    serializer_class = VDocSerializer
    http_method_names = ['get', 'post', 'put', 'delete']

    def get_queryset(self):
        # Filter VDocs based on search query
        search_query = self.request.query_params.get("search")
        if search_query:
            result = VDoc.objects.filter(
                Q(name__contains=search_query),
                company=self.request.user.company
            ).order_by("-updated_at")
            return result
        vDocs = VDoc.objects.filter(company=self.request.user.company).order_by("-updated_at")
        return vDocs

    def create(self, request, *args, **kwargs):
        user = request.user
        data = {
            "name": request.data['name'],
            "company": user.company.id,
            "created_by": user.id,
            "updated_by": user.id
        }
        serializer = VDocSerializer(data=data)

        if serializer.is_valid():
            vdoc = serializer.save()
            # Create default keys when creating a new VDoc
            VKey.objects.bulk_create([
                VKey(vdoc=vdoc, name="Name", type="customer", required=True),
                VKey(vdoc=vdoc, name="Phone", type="customer", required=True),
                VKey(vdoc=vdoc, name="Email", type="customer", required=True)
            ])
            return Response(data=serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(data=serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk):
        try:
            vDocs = VDoc.objects.filter(pk=pk).first()
            request.data['company'] = request.user.company.pk
            if len(request.FILES) > 0:
                file = request.FILES.get('file')
                s3_bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                s3_object_key = file.name
                # Upload file to AWS S3
                response = StreamingHttpResponse(
                    upload_file_chunked(s3_bucket_name, file, s3_object_key),
                    content_type='text/event-stream'
                )
                file_object = File()
                file_object.file.name = file.name
                file_object.save()

                vDocData = VDoc.objects.get(pk=pk)
                vDocData.document = file_object
                vDocData.save()

                serializer = VDocSerializer(vDocData)
                response['custom-data'] = json.dumps(serializer.data)
                return response
            elif request.data['type'] == "deleteDocument":
                # Delete associated document
                vDocs.document.delete()
            elif request.data['type'] == "editName":
                # Update VDoc name
                vDocs.name = request.data.get('name')
                vDocs.save()
            serializer = VDocSerializer(vDocs)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
