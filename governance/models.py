from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
import threading
import json
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class IdempotencyRecord(models.Model):
    """
    Ensures operations are not duplicated by tracking unique operation keys.
    Thread-safe implementation with proper database constraints.
    """
    operation_type = models.CharField(
        max_length=100,
        help_text="Type of operation (e.g., 'journal_entry', 'stock_movement')"
    )
    idempotency_key = models.CharField(
        max_length=255,
        help_text="Unique key for this operation"
    )
    result_data = models.JSONField(
        help_text="Serialized result of the operation"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this idempotency record expires"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_idempotency_records',
        help_text="User who initiated the operation"
    )
    
    class Meta:
        unique_together = ['operation_type', 'idempotency_key']
        indexes = [
            models.Index(fields=['operation_type', 'idempotency_key']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['created_at']),
        ]
        verbose_name = "Idempotency Record"
        verbose_name_plural = "Idempotency Records"
    
    def __str__(self):
        return f"{self.operation_type}:{self.idempotency_key}"
    
    def clean(self):
        """Validate the idempotency record"""
        if self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError("Expiration time must be in the future")
    
    def is_expired(self):
        """Check if this idempotency record has expired"""
        return self.expires_at <= timezone.now()
    
    @classmethod
    def check_and_record(cls, operation_type, idempotency_key, result_data, user, expires_in_hours=24):
        """
        Thread-safe method to check for existing operation or record new one.
        Returns (is_duplicate, record)
        """
        with transaction.atomic():
            try:
                # Try to get existing record
                existing = cls.objects.select_for_update().get(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key
                )
                
                if existing.is_expired():
                    # Record expired, delete it and create new one
                    existing.delete()
                    record = cls.objects.create(
                        operation_type=operation_type,
                        idempotency_key=idempotency_key,
                        result_data=result_data,
                        expires_at=timezone.now() + timezone.timedelta(hours=expires_in_hours),
                        created_by=user
                    )
                    return False, record
                else:
                    # Return existing result
                    return True, existing
                    
            except cls.DoesNotExist:
                # No existing record, create new one
                record = cls.objects.create(
                    operation_type=operation_type,
                    idempotency_key=idempotency_key,
                    result_data=result_data,
                    expires_at=timezone.now() + timezone.timedelta(hours=expires_in_hours),
                    created_by=user
                )
                return False, record


class AuditTrail(models.Model):
    """
    Comprehensive audit trail for all sensitive operations.
    Thread-safe implementation with proper data capture.
    """
    model_name = models.CharField(
        max_length=100,
        help_text="Name of the model being audited"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the object being audited"
    )
    operation = models.CharField(
        max_length=50,
        choices=[
            ('CREATE', 'Create'),
            ('UPDATE', 'Update'),
            ('DELETE', 'Delete'),
            ('VIEW', 'View'),
            ('ADMIN_ACCESS', 'Admin Access'),
            ('AUTHORITY_VIOLATION', 'Authority Violation'),
        ],
        help_text="Type of operation performed"
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='governance_audit_trails',
        help_text="User who performed the operation (null for system operations)"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    before_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Data before the operation"
    )
    after_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Data after the operation"
    )
    source_service = models.CharField(
        max_length=100,
        help_text="Service that initiated the operation"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.TextField(
        null=True,
        blank=True,
        help_text="User agent string"
    )
    additional_context = models.JSONField(
        null=True,
        blank=True,
        help_text="Additional context information"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['operation', 'timestamp']),
            models.Index(fields=['source_service', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]
        verbose_name = "Audit Trail"
        verbose_name_plural = "Audit Trails"
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.operation} on {self.model_name}#{self.object_id} by {self.user.username}"
    
    @classmethod
    def log_operation(cls, model_name, object_id, operation, user, source_service, 
                     before_data=None, after_data=None, request=None, **kwargs):
        """
        Thread-safe method to log an operation.
        """
        try:
            # Extract request information if available
            ip_address = None
            user_agent = None
            if request:
                ip_address = cls._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Create audit record atomically
            with transaction.atomic():
                audit_record = cls.objects.create(
                    model_name=model_name,
                    object_id=object_id,
                    operation=operation,
                    user=user,
                    source_service=source_service,
                    before_data=before_data,
                    after_data=after_data,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    additional_context=kwargs
                )
                
            logger.info(f"Audit trail created: {audit_record}")
            return audit_record
            
        except Exception as e:
            logger.error(f"Failed to create audit trail: {e}")
            # Don't raise exception to avoid breaking the main operation
            return None
    
    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class QuarantineRecord(models.Model):
    """
    Isolates suspicious or corrupted data for investigation.
    """
    model_name = models.CharField(
        max_length=100,
        help_text="Name of the model containing corrupted data"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the corrupted object"
    )
    corruption_type = models.CharField(
        max_length=100,
        choices=[
            ('ORPHANED_ENTRY', 'Orphaned Journal Entry'),
            ('NEGATIVE_STOCK', 'Negative Stock'),
            ('UNBALANCED_ENTRY', 'Unbalanced Journal Entry'),
            ('MULTIPLE_ACTIVE_YEAR', 'Multiple Active Academic Years'),
            ('INVALID_SOURCE_LINK', 'Invalid Source Linkage'),
            ('AUTHORITY_VIOLATION', 'Authority Boundary Violation'),
            ('SUSPICIOUS_PATTERN', 'Suspicious Data Pattern'),
        ],
        help_text="Type of corruption detected"
    )
    original_data = models.JSONField(
        help_text="Original data before quarantine"
    )
    quarantine_reason = models.TextField(
        help_text="Detailed reason for quarantine"
    )
    quarantined_at = models.DateTimeField(auto_now_add=True)
    quarantined_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='quarantined_records',
        help_text="User or system that quarantined the data"
    )
    status = models.CharField(
        max_length=50,
        choices=[
            ('QUARANTINED', 'Quarantined'),
            ('UNDER_REVIEW', 'Under Review'),
            ('RESOLVED', 'Resolved'),
            ('PERMANENT', 'Permanent Quarantine'),
        ],
        default='QUARANTINED'
    )
    resolution_notes = models.TextField(
        null=True,
        blank=True,
        help_text="Notes about resolution"
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='resolved_quarantine_records'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['corruption_type', 'status']),
            models.Index(fields=['quarantined_at']),
            models.Index(fields=['status']),
        ]
        verbose_name = "Quarantine Record"
        verbose_name_plural = "Quarantine Records"
        ordering = ['-quarantined_at']
    
    def __str__(self):
        return f"{self.corruption_type} - {self.model_name}#{self.object_id}"
    
    def resolve(self, user, notes=""):
        """Mark quarantine record as resolved"""
        with transaction.atomic():
            self.status = 'RESOLVED'
            self.resolved_at = timezone.now()
            self.resolved_by = user
            self.resolution_notes = notes
            self.save()
            
            # Log the resolution
            AuditTrail.log_operation(
                model_name='QuarantineRecord',
                object_id=self.id,
                operation='UPDATE',
                user=user,
                source_service='QuarantineSystem',
                before_data={'status': 'QUARANTINED'},
                after_data={'status': 'RESOLVED'},
                resolution_notes=notes
            )


class AuthorityDelegation(models.Model):
    """
    Manages temporary authority delegation between services.
    """
    from_service = models.CharField(
        max_length=100,
        help_text="Service delegating authority"
    )
    to_service = models.CharField(
        max_length=100,
        help_text="Service receiving authority"
    )
    model_name = models.CharField(
        max_length=100,
        help_text="Model for which authority is delegated"
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this delegation expires"
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='granted_authority_delegations',
        help_text="User who granted the delegation"
    )
    reason = models.TextField(
        help_text="Reason for delegation"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this delegation is currently active"
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='revoked_authority_delegations'
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['from_service', 'to_service', 'model_name']),
            models.Index(fields=['expires_at', 'is_active']),
            models.Index(fields=['granted_at']),
        ]
        verbose_name = "Authority Delegation"
        verbose_name_plural = "Authority Delegations"
        ordering = ['-granted_at']
    
    def __str__(self):
        return f"{self.from_service} → {self.to_service} for {self.model_name}"
    
    def clean(self):
        """Validate the delegation"""
        if self.expires_at <= self.granted_at:
            raise ValidationError("Expiration time must be after grant time")
        
        # Check for maximum delegation duration (24 hours)
        max_duration = timezone.timedelta(hours=24)
        if self.expires_at - self.granted_at > max_duration:
            raise ValidationError(f"Delegation duration cannot exceed {max_duration}")
    
    def is_expired(self):
        """Check if this delegation has expired"""
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if this delegation is currently valid"""
        return self.is_active and not self.is_expired() and not self.revoked_at
    
    def revoke(self, user, reason=""):
        """Revoke this delegation"""
        with transaction.atomic():
            self.is_active = False
            self.revoked_at = timezone.now()
            self.revoked_by = user
            self.save()
            
            # Log the revocation
            AuditTrail.log_operation(
                model_name='AuthorityDelegation',
                object_id=self.id,
                operation='UPDATE',
                user=user,
                source_service='AuthorityService',
                before_data={'is_active': True},
                after_data={'is_active': False},
                revocation_reason=reason
            )
    
    @classmethod
    def check_delegation(cls, from_service, to_service, model_name):
        """
        Check if there's a valid delegation for the given parameters.
        Thread-safe implementation.
        """
        with transaction.atomic():
            try:
                delegation = cls.objects.select_for_update().get(
                    from_service=from_service,
                    to_service=to_service,
                    model_name=model_name,
                    is_active=True,
                    expires_at__gt=timezone.now(),
                    revoked_at__isnull=True
                )
                return delegation.is_valid()
            except cls.DoesNotExist:
                return False
            except cls.MultipleObjectsReturned:
                # Multiple active delegations - this shouldn't happen
                logger.error(f"Multiple active delegations found: {from_service} → {to_service} for {model_name}")
                return False


# Thread-local storage for governance context
_governance_context = threading.local()


class GovernanceContext:
    """
    Thread-safe context manager for governance operations.
    Provides current user, service, and operation context.
    """
    
    @classmethod
    def set_context(cls, user=None, service=None, operation=None, request=None):
        """Set governance context for current thread"""
        _governance_context.user = user
        _governance_context.service = service
        _governance_context.operation = operation
        _governance_context.request = request
    
    @classmethod
    def get_context(cls):
        """Get governance context for current thread"""
        return {
            'user': getattr(_governance_context, 'user', None),
            'service': getattr(_governance_context, 'service', None),
            'operation': getattr(_governance_context, 'operation', None),
            'request': getattr(_governance_context, 'request', None),
        }
    
    @classmethod
    def clear_context(cls):
        """Clear governance context for current thread"""
        for attr in ['user', 'service', 'operation', 'request']:
            if hasattr(_governance_context, attr):
                delattr(_governance_context, attr)
    
    @classmethod
    def get_current_user(cls):
        """Get current user from context"""
        return getattr(_governance_context, 'user', None)
    
    @classmethod
    def get_current_service(cls):
        """Get current service from context"""
        return getattr(_governance_context, 'service', None)
