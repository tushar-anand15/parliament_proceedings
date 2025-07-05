from django.test import TestCase
from django.contrib.auth.models import User
from .models import ScrapingJob, ScrapingConfig, DataSource


class ScrapingJobTestCase(TestCase):
    """Test cases for ScrapingJob model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
    def test_create_scraping_job(self):
        """Test creating a scraping job"""
        job = ScrapingJob.objects.create(
            name="Test Job",
            description="Test scraping job",
            job_type="incremental",
            started_by=self.user
        )
        
        self.assertEqual(job.name, "Test Job")
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.progress_percent, 0)
        
    def test_job_progress_calculation(self):
        """Test progress percentage calculation"""
        job = ScrapingJob.objects.create(
            name="Progress Test",
            total_questions_expected=100,
            questions_processed=25,
            started_by=self.user
        )
        
        self.assertEqual(job.progress_percent, 25.0)
        
    def test_start_job(self):
        """Test starting a job"""
        job = ScrapingJob.objects.create(
            name="Start Test",
            started_by=self.user
        )
        
        job.start_job(worker_id="worker-1", pid=12345)
        
        self.assertEqual(job.status, "running")
        self.assertEqual(job.worker_id, "worker-1")
        self.assertEqual(job.pid, 12345)
        self.assertIsNotNone(job.started_at)


class ScrapingConfigTestCase(TestCase):
    """Test cases for ScrapingConfig model"""
    
    def test_default_config(self):
        """Test default configuration management"""
        config1 = ScrapingConfig.objects.create(
            name="Config 1",
            is_default=True
        )
        
        config2 = ScrapingConfig.objects.create(
            name="Config 2",
            is_default=True  # This should unset config1's default
        )
        
        config1.refresh_from_db()
        
        self.assertFalse(config1.is_default)
        self.assertTrue(config2.is_default)
        
    def test_get_default_config(self):
        """Test getting default configuration"""
        config = ScrapingConfig.objects.create(
            name="Default Config",
            is_default=True
        )
        
        default_config = ScrapingConfig.get_default()
        self.assertEqual(default_config, config)


class DataSourceTestCase(TestCase):
    """Test cases for DataSource model"""
    
    def test_record_success(self):
        """Test recording successful access"""
        source = DataSource.objects.create(
            name="Test API",
            source_type="api",
            base_url="https://api.example.com"
        )
        
        source.record_success()
        
        self.assertIsNotNone(source.last_accessed)
        self.assertIsNotNone(source.last_success)
        self.assertEqual(source.error_count, 0)
        
    def test_record_error(self):
        """Test recording failed access"""
        source = DataSource.objects.create(
            name="Test API",
            source_type="api"
        )
        
        source.record_error()
        source.record_error()
        
        self.assertIsNotNone(source.last_accessed)
        self.assertEqual(source.error_count, 2) 