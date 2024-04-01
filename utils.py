import json
import pandas
import boto3
from django.conf import settings
from rest_framework import pagination
from django.http import StreamingHttpResponse
from api.models import File

# Group data by a specific key
def group_data_by_key(arr, key):
    """
    Group data by a specific key.

    Args:
        arr (list): List of dictionaries containing data.
        key (str): Key to group the data by.

    Returns:
        dict: Dictionary where keys are unique values of the specified key, and values are lists of corresponding data.
    """
    grouped_data = {}
    for item in arr:
        temp = grouped_data.setdefault(item[key], [])
        temp.append(item)
    return grouped_data

# Get unique items from a list of dictionaries based on a specific key
def unique_items_by_key(arr, key):
    """
    Get unique items from a list of dictionaries based on a specific key.

    Args:
        arr (list): List of dictionaries containing data.
        key (str): Key to identify uniqueness.

    Returns:
        list: List of unique dictionaries based on the specified key.
    """
    return list({value[key]: value for value in arr}.values())

# Custom pagination settings
class CustomPagination(pagination.PageNumberPagination):
    page_size = 15
    page_size_query_description = 'page_size'
    max_page_size = 100
    page_query_param = 'p'

# Function for bulk upload of files
def bulk_upload(request, fields):
    """
    Perform bulk upload of files.

    Args:
        request: Django request object.
        fields (list): List of field names to validate against.

    Returns:
        StreamingHttpResponse: Streaming HTTP response with file upload status.
    """
    if request.FILES:
        for file in request.FILES.getlist('file'):
            df = pandas.read_csv(file)
            df.columns = df.columns.str.lower()
            if all(column_name in df.columns for column_name in fields):
                file = request.FILES.get('file')
                s3_bucket_name = settings.AWS_STORAGE_BUCKET_NAME
                s3_object_key = file.name

                response = StreamingHttpResponse(
                    upload_file_chunked(s3_bucket_name, file, s3_object_key),
                    content_type='text/event-stream'
                )
                file_object = File()
                file_object.file.name = file.name
                file_object.save()
                response['custom-data'] = json.dumps(file_object.id)
                return response

# Upload file to AWS S3 bucket in chunks
def upload_file_chunked(bucket_name, file_object, file_name, chunk_size=5242880):
    """
    Upload a file to an AWS S3 bucket in chunks.

    Args:
        bucket_name (str): Name of the AWS S3 bucket.
        file_object (File): File object to be uploaded.
        file_name (str): Name of the file.
        chunk_size (int): Size of each chunk (default: 5 MB).

    Yields:
        str: JSON-encoded progress update containing uploaded bytes and total size.
    """
    file_size = file_object.seek(0, 2)
    file_object.seek(0)

    response = s3.create_multipart_upload(Bucket=bucket_name, Key=file_name)
    upload_id = response['UploadId']

    try:
        part_number = 1
        parts = []
        uploaded_bytes = 0

        while True:
            data = file_object.read(chunk_size)

            if not data:
                break

            response = s3.upload_part(
                Bucket=bucket_name,
                Key=file_name,
                PartNumber=part_number,
                UploadId=upload_id,
                Body=data
            )

            parts.append({
                'PartNumber': part_number,
                'ETag': response['ETag']
            })

            part_number += 1
            uploaded_bytes += len(data)

            # Send progress update as SSE event
            yield json.dumps({"uploaded": uploaded_bytes, "total_size": file_size})

        response = s3.complete_multipart_upload(
            Bucket=bucket_name,
            Key=file_name,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )

    except Exception as e:
        s3.abort_multipart_upload(
            Bucket=bucket_name,
            Key=file_name,
            UploadId=upload_id
        )
        raise e  # Re-raise the exception for error handling
