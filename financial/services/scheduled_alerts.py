"""
Financial Alert Service - DISABLED for Corporate ERP

This service was used for student installment alerts in the Corporate ERP.
It has been disabled as the student modules have been removed from the Corporate ERP system.

If you need alert/notification management for corporate operations, create a new service
specific to corporate financial operations.
"""

from django.utils import timezone
from datetime import timedelta

class FinancialAlertService:
    """
    DISABLED: This service was for student installment alerts.
    Not needed in Corporate ERP system.
    """
    
    @staticmethod
    def get_upcoming_installments(days_ahead=7):
        """DISABLED - Returns empty list"""
        return []
    
    @staticmethod
    def get_overdue_installments():
        """DISABLED - Returns empty list"""
        return []
    
    @staticmethod
    def send_installment_reminders():
        """DISABLED - Does nothing"""
        pass
