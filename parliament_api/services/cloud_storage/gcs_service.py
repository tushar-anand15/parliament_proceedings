import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from google.cloud import storage
from google.auth import exceptions as auth_exceptions
from google.api_core import exceptions as gcs_exceptions
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class GCSService:
    """
    Google Cloud Storage service for managing PDF files
    """
    
    def __init__(self):
        """Initialize GCS client with service account credentials"""
        try:
            # Initialize client with service account key
            credentials_path = getattr(settings, 'GCS_CREDENTIALS_PATH', None)
            if credentials_path and os.path.exists(credentials_path):
                self.client = storage.Client.from_service_account_json(credentials_path)
            else:
                # Fallback to environment-based authentication
                self.client = storage.Client(project=settings.GCS_PROJECT_ID)
            
            self.project_id = settings.GCS_PROJECT_ID
            self.debates_bucket_name = settings.GCS_DEBATES_BUCKET
            self.questions_bucket_name = settings.GCS_QUESTIONS_BUCKET
            
            logger.info(f"GCS Service initialized for project: {self.project_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize GCS client: {e}")
            raise
    
    def _get_bucket(self, bucket_name: str) -> storage.Bucket:
        """Get bucket instance, create if doesn't exist"""
        try:
            bucket = self.client.bucket(bucket_name)
            
            # Check if bucket exists
            if not bucket.exists():
                logger.info(f"Creating bucket: {bucket_name}")
                # Create bucket in Mumbai region (asia-south1)
                bucket = self.client.create_bucket(
                    bucket_name,
                    location='asia-south1'
                )
                
                # Set up bucket lifecycle management
                lifecycle_rules = [{
                    'action': {'type': 'Delete'},
                    'condition': {
                        'age': 365 * 7  # Delete after 7 years
                    }
                }]
                bucket.lifecycle_rules = lifecycle_rules
                bucket.patch()
                
                logger.info(f"Bucket created successfully: {bucket_name}")
            
            return bucket
            
        except gcs_exceptions.Forbidden as e:
            logger.error(f"Permission denied accessing bucket {bucket_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error accessing bucket {bucket_name}: {e}")
            raise
    
    def upload_file(self, local_file_path: str, bucket_name: str, object_key: str, 
                   metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Upload file to GCS bucket
        
        Args:
            local_file_path: Path to local file
            bucket_name: GCS bucket name
            object_key: Object key/path in bucket
            metadata: Optional metadata dict
            
        Returns:
            Dict with upload result information
        """
        try:
            if not os.path.exists(local_file_path):
                raise FileNotFoundError(f"Local file not found: {local_file_path}")
            
            bucket = self._get_bucket(bucket_name)
            blob = bucket.blob(object_key)
            
            # Set metadata
            if metadata:
                blob.metadata = metadata
            
            # Set content type
            if local_file_path.lower().endswith('.pdf'):
                blob.content_type = 'application/pdf'
            
            # Upload file
            with open(local_file_path, 'rb') as file_obj:
                blob.upload_from_file(file_obj)
            
            # Get file info
            file_size = os.path.getsize(local_file_path)
            
            result = {
                'success': True,
                'bucket_name': bucket_name,
                'object_key': object_key,
                'file_size': file_size,
                'uploaded_at': timezone.now().isoformat(),
                'gcs_url': f"gs://{bucket_name}/{object_key}",
                'etag': blob.etag
            }
            
            logger.info(f"Successfully uploaded file to GCS: {object_key} ({file_size} bytes)")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload file to GCS: {e}")
            return {
                'success': False,
                'error': str(e),
                'bucket_name': bucket_name,
                'object_key': object_key
            }
    
    def generate_presigned_url(self, bucket_name: str, object_key: str, 
                             expiration_minutes: int = 60) -> Optional[str]:
        """
        Generate presigned URL for secure file access
        
        Args:
            bucket_name: GCS bucket name
            object_key: Object key/path in bucket
            expiration_minutes: URL expiration time in minutes
            
        Returns:
            Presigned URL string or None if failed
        """
        try:
            bucket = self._get_bucket(bucket_name)
            blob = bucket.blob(object_key)
            
            # Check if object exists
            if not blob.exists():
                logger.warning(f"Object not found for presigned URL: {object_key}")
                return None
            
            # Generate signed URL
            expiration = datetime.utcnow() + timedelta(minutes=expiration_minutes)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )
            
            logger.info(f"Generated presigned URL for {object_key} (expires in {expiration_minutes}min)")
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {object_key}: {e}")
            return None
    
    def delete_file(self, bucket_name: str, object_key: str) -> bool:
        """
        Delete file from GCS bucket
        
        Args:
            bucket_name: GCS bucket name
            object_key: Object key/path in bucket
            
        Returns:
            True if successful, False otherwise
        """
        try:
            bucket = self._get_bucket(bucket_name)
            blob = bucket.blob(object_key)
            
            if blob.exists():
                blob.delete()
                logger.info(f"Deleted file from GCS: {object_key}")
                return True
            else:
                logger.warning(f"File not found for deletion: {object_key}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete file from GCS: {e}")
            return False
    
    def get_file_metadata(self, bucket_name: str, object_key: str) -> Optional[Dict[str, Any]]:
        """
        Get file metadata from GCS
        
        Args:
            bucket_name: GCS bucket name
            object_key: Object key/path in bucket
            
        Returns:
            Metadata dict or None if not found
        """
        try:
            bucket = self._get_bucket(bucket_name)
            blob = bucket.blob(object_key)
            
            if not blob.exists():
                return None
            
            # Reload to get latest metadata
            blob.reload()
            
            metadata = {
                'name': blob.name,
                'size': blob.size,
                'content_type': blob.content_type,
                'etag': blob.etag,
                'created': blob.time_created.isoformat() if blob.time_created else None,
                'updated': blob.updated.isoformat() if blob.updated else None,
                'metadata': blob.metadata or {},
                'public_url': blob.public_url
            }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get file metadata: {e}")
            return None
    
    def list_files(self, bucket_name: str, prefix: str = "", limit: int = 100) -> list:
        """
        List files in bucket with optional prefix filter
        
        Args:
            bucket_name: GCS bucket name
            prefix: Object key prefix filter
            limit: Maximum number of files to return
            
        Returns:
            List of file information dicts
        """
        try:
            bucket = self._get_bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=prefix, max_results=limit)
            
            files = []
            for blob in blobs:
                files.append({
                    'name': blob.name,
                    'size': blob.size,
                    'content_type': blob.content_type,
                    'created': blob.time_created.isoformat() if blob.time_created else None,
                    'updated': blob.updated.isoformat() if blob.updated else None
                })
            
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []
    
    def get_bucket_for_document_type(self, document_category: str) -> str:
        """
        Get appropriate bucket name for document type
        
        Args:
            document_category: Document category (parl_debate, parl_question, parl_rs_question, etc.)
            
        Returns:
            Bucket name string
        """
        if document_category == 'parl_debate':
            return self.debates_bucket_name
        elif document_category in ['parl_question', 'parl_rs_question']:
            return self.questions_bucket_name
        else:
            # Default to questions bucket for other types
            return self.questions_bucket_name
    
    def generate_object_key(self, document_category: str, file_name: str, 
                          additional_path: str = "") -> str:
        """
        Generate consistent object key for file storage
        
        Args:
            document_category: Document category
            file_name: Original file name
            additional_path: Additional path components
            
        Returns:
            Object key string
        """
        base_path = document_category.replace('parl_', '')  # debates, questions
        
        if additional_path:
            object_key = f"{base_path}/{additional_path}/{file_name}"
        else:
            object_key = f"{base_path}/{file_name}"
        
        return object_key
