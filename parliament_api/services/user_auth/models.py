from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import secrets
import string


class UserProfile(models.Model):
    """Extended user profile with additional information"""
    
    USER_TYPES = [
        ('researcher', 'Researcher'),
        ('journalist', 'Journalist'),
        ('government', 'Government Official'),
        ('student', 'Student'),
        ('citizen', 'Citizen'),
        ('ngo', 'NGO/Civil Society'),
        ('academic', 'Academic Institution'),
        ('other', 'Other'),
    ]
    
    SUBSCRIPTION_TIERS = [
        ('free', 'Free Tier'),
        ('basic', 'Basic Plan'),
        ('pro', 'Professional Plan'),
        ('enterprise', 'Enterprise Plan'),
    ]

    # One-to-one relationship with Django User
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Profile Information
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='citizen')
    organization = models.CharField(max_length=200, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    
    # Location
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='India')
    
    # Subscription and Usage
    subscription_tier = models.CharField(max_length=20, choices=SUBSCRIPTION_TIERS, default='free')
    subscription_start = models.DateTimeField(null=True, blank=True)
    subscription_end = models.DateTimeField(null=True, blank=True)
    
    # API Usage Limits
    daily_api_limit = models.IntegerField(default=100)  # API calls per day
    monthly_download_limit = models.IntegerField(default=50)  # PDF downloads per month
    
    # Current Usage Counters
    api_calls_today = models.IntegerField(default=0)
    downloads_this_month = models.IntegerField(default=0)
    last_api_call = models.DateTimeField(null=True, blank=True)
    last_download = models.DateTimeField(null=True, blank=True)
    
    # Preferences
    email_notifications = models.BooleanField(default=True)
    newsletter_subscription = models.BooleanField(default=False)
    data_export_format = models.CharField(max_length=10, default='json')  # json, csv, excel
    
    # Account Status
    is_verified = models.BooleanField(default=False)
    verification_date = models.DateTimeField(null=True, blank=True)
    is_premium = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user_type']),
            models.Index(fields=['subscription_tier']),
            models.Index(fields=['is_verified']),
        ]

    def __str__(self):
        return f"Profile: {self.user.username} ({self.user_type})"

    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username

    @property
    def is_subscription_active(self):
        if not self.subscription_end:
            return self.subscription_tier == 'free'
        return timezone.now() <= self.subscription_end

    def can_make_api_call(self):
        """Check if user can make an API call"""
        return self.api_calls_today < self.daily_api_limit

    def can_download_file(self):
        """Check if user can download a file"""
        return self.downloads_this_month < self.monthly_download_limit

    def record_api_call(self):
        """Record an API call"""
        now = timezone.now()
        
        # Reset daily counter if it's a new day
        if self.last_api_call and self.last_api_call.date() < now.date():
            self.api_calls_today = 0
        
        self.api_calls_today += 1
        self.last_api_call = now
        self.save(update_fields=['api_calls_today', 'last_api_call'])

    def record_download(self):
        """Record a file download"""
        now = timezone.now()
        
        # Reset monthly counter if it's a new month
        if (self.last_download and 
            (self.last_download.month != now.month or self.last_download.year != now.year)):
            self.downloads_this_month = 0
        
        self.downloads_this_month += 1
        self.last_download = now
        self.save(update_fields=['downloads_this_month', 'last_download'])

    def upgrade_subscription(self, tier, duration_days=30):
        """Upgrade user subscription"""
        self.subscription_tier = tier
        self.subscription_start = timezone.now()
        self.subscription_end = self.subscription_start + timezone.timedelta(days=duration_days)
        self.is_premium = tier != 'free'
        
        # Update limits based on tier
        tier_limits = {
            'free': {'api': 100, 'downloads': 50},
            'basic': {'api': 1000, 'downloads': 200},
            'pro': {'api': 5000, 'downloads': 1000},
            'enterprise': {'api': 50000, 'downloads': 10000},
        }
        
        if tier in tier_limits:
            self.daily_api_limit = tier_limits[tier]['api']
            self.monthly_download_limit = tier_limits[tier]['downloads']
        
        self.save()


class APIKey(models.Model):
    """Model for managing user API keys"""
    
    KEY_SCOPES = [
        ('read', 'Read Access'),
        ('download', 'Download Access'),
        ('full', 'Full Access'),
        ('admin', 'Admin Access'),
    ]

    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_keys')
    
    # Key Information
    name = models.CharField(max_length=100)  # User-friendly name
    key = models.CharField(max_length=100, unique=True)
    key_prefix = models.CharField(max_length=10)  # First few chars for display
    
    # Permissions
    scope = models.CharField(max_length=20, choices=KEY_SCOPES, default='read')
    allowed_ips = models.TextField(blank=True)  # Comma-separated IP addresses
    
    # Usage Tracking
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    
    # Status
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"API Key: {self.name} ({self.user.username})"

    def save(self, *args, **kwargs):
        if not self.key:
            self.generate_key()
        super().save(*args, **kwargs)

    def generate_key(self):
        """Generate a new API key"""
        # Generate a secure random key
        alphabet = string.ascii_letters + string.digits
        key = 'pk_' + ''.join(secrets.choice(alphabet) for _ in range(40))
        
        # Ensure uniqueness
        while APIKey.objects.filter(key=key).exists():
            key = 'pk_' + ''.join(secrets.choice(alphabet) for _ in range(40))
        
        self.key = key
        self.key_prefix = key[:8]  # Store first 8 chars for display

    @property
    def is_valid(self):
        """Check if the API key is valid"""
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def record_usage(self, ip_address=None):
        """Record API key usage"""
        self.last_used = timezone.now()
        self.usage_count += 1
        self.save(update_fields=['last_used', 'usage_count'])

    def revoke(self):
        """Revoke the API key"""
        self.is_active = False
        self.save(update_fields=['is_active'])


class UserSession(models.Model):
    """Model to track user sessions and activity"""
    
    # User Information
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True)
    
    # Session Details
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=50, blank=True)  # mobile, desktop, tablet
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    
    # Location (if available)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    # Activity Tracking
    pages_visited = models.IntegerField(default=0)
    api_calls_made = models.IntegerField(default=0)
    files_downloaded = models.IntegerField(default=0)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['session_key']),
            models.Index(fields=['ip_address']),
        ]

    def __str__(self):
        return f"Session: {self.user.username} - {self.ip_address}"

    def end_session(self):
        """End the user session"""
        self.is_active = False
        self.ended_at = timezone.now()
        self.save(update_fields=['is_active', 'ended_at'])

    @property
    def duration(self):
        """Get session duration"""
        end_time = self.ended_at or timezone.now()
        return end_time - self.created_at


class UserActivity(models.Model):
    """Model to track detailed user activities"""
    
    ACTIVITY_TYPES = [
        ('login', 'User Login'),
        ('logout', 'User Logout'),
        ('api_call', 'API Call'),
        ('download', 'File Download'),
        ('search', 'Search Query'),
        ('profile_update', 'Profile Update'),
        ('subscription_change', 'Subscription Change'),
        ('export', 'Data Export'),
    ]

    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    session = models.ForeignKey(UserSession, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Activity Information
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField(blank=True)
    endpoint = models.CharField(max_length=200, blank=True)  # API endpoint or page
    method = models.CharField(max_length=10, blank=True)  # GET, POST, etc.
    
    # Context Data
    request_data = models.JSONField(default=dict, blank=True)
    response_status = models.IntegerField(null=True, blank=True)
    
    # Performance
    response_time = models.FloatField(null=True, blank=True)  # in seconds
    
    # Metadata
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    
    # Timestamp
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'activity_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['endpoint']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.activity_type} ({self.timestamp})"


class UserNotification(models.Model):
    """Model for user notifications"""
    
    NOTIFICATION_TYPES = [
        ('system', 'System Notification'),
        ('scraping', 'Scraping Update'),
        ('download', 'Download Complete'),
        ('subscription', 'Subscription Alert'),
        ('api_limit', 'API Limit Warning'),
        ('security', 'Security Alert'),
        ('feature', 'New Feature'),
    ]

    # Relationships
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    
    # Notification Content
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Status
    is_read = models.BooleanField(default=False)
    is_sent = models.BooleanField(default=False)
    
    # Actions
    action_url = models.URLField(blank=True)
    action_text = models.CharField(max_length=50, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        return f"Notification: {self.title} - {self.user.username}"

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    def mark_as_sent(self):
        """Mark notification as sent"""
        if not self.is_sent:
            self.is_sent = True
            self.sent_at = timezone.now()
            self.save(update_fields=['is_sent', 'sent_at'])
