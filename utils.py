import os
import boto3
from botocore.exceptions import ClientError
from werkzeug.utils import secure_filename

class S3Handler:
    def __init__(self, bucket_name):
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name

    def upload_file(self, file, folder):
        """
        S3'e dosya yükler
        """
        try:
            filename = secure_filename(file.filename)
            file_key = f"{folder}/{filename}"
            self.s3_client.upload_fileobj(file, self.bucket_name, file_key)
            return file_key
        except ClientError as e:
            print(f"S3 upload error: {e}")
            return None

    def download_file(self, file_key):
        """
        S3'den dosya indirir
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=file_key)
            return response['Body'].read()
        except ClientError as e:
            print(f"S3 download error: {e}")
            return None

    def delete_file(self, file_key):
        """
        S3'den dosya siler
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_key)
            return True
        except ClientError as e:
            print(f"S3 delete error: {e}")
            return False
