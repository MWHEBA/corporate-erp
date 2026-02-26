from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class GovernanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "governance"
    
    def ready(self):
        """
        Initialize governance system when Django starts.
        Validates authority matrix, sets up monitoring, and ensures auto-activation.
        """
        # Only run during normal Django startup, not during migrations
        import sys
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return
            
        try:
            # Import here to avoid circular imports
            from .services.authority_service import AuthorityService
            
            # Validate authority matrix configuration
            logger.info("Validating governance authority matrix...")
            errors = AuthorityService.validate_startup_authority_matrix()
            
            if errors:
                logger.error(f"Authority matrix validation failed: {errors}")
                # Don't raise exception to avoid breaking startup
                # Just log the errors for investigation
            else:
                logger.info("✅ Authority matrix validation passed")
                
            # Log authority matrix for debugging
            logger.info(f"Authority matrix loaded: {len(AuthorityService.AUTHORITY_MATRIX)} models governed")
            logger.info(f"Critical models protected: {len(AuthorityService.CRITICAL_MODELS)} models")
            
            # Clean up any expired delegations on startup
            try:
                cleaned_count = AuthorityService.cleanup_expired_delegations()
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} expired authority delegations")
            except Exception as e:
                logger.warning(f"Failed to cleanup expired delegations: {e}")
            
            # Initialize payroll signal adapters
            try:
                from .signals import payroll_signals
                logger.info("✅ Payroll signal adapters initialized")
            except ImportError as e:
                logger.warning(f"Could not initialize payroll signal adapters: {e}")
            except Exception as e:
                logger.error(f"Payroll signal adapter initialization failed: {e}", exc_info=True)
            
            # Initialize auto-activation signals
            try:
                from .signals import auto_activation
                logger.info("✅ Governance auto-activation signals initialized")
            except ImportError as e:
                logger.warning(f"Could not initialize auto-activation signals: {e}")
            except Exception as e:
                logger.error(f"Auto-activation signal initialization failed: {e}", exc_info=True)
            
            # Ensure Governance is active on startup
            try:
                from .signals.auto_activation import GovernanceAutoActivation
                
                # فحص صحة Governance
                health = GovernanceAutoActivation.is_governance_healthy()
                
                if not health.get('healthy', False):
                    logger.warning("🔴 Governance غير صحي عند بدء التشغيل")
                    logger.warning(f"المكونات المفقودة: {health.get('missing_components', [])}")
                    logger.warning(f"سير العمل المفقود: {health.get('missing_workflows', [])}")
                    
                    # محاولة التفعيل التلقائي
                    if GovernanceAutoActivation.ensure_governance_active():
                        logger.info("✅ تم تفعيل Governance تلقائياً عند بدء التشغيل")
                    else:
                        logger.warning("⚠️ فشل التفعيل التلقائي لـ Governance عند بدء التشغيل")
                else:
                    logger.info("✅ Governance صحي ومفعل عند بدء التشغيل")
                    
            except Exception as e:
                logger.warning(f"فشل فحص/تفعيل Governance عند بدء التشغيل: {e}")
                
        except ImportError as e:
            logger.warning(f"Could not initialize governance system: {e}")
        except Exception as e:
            logger.error(f"Governance system initialization failed: {e}", exc_info=True)
