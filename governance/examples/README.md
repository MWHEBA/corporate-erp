# Governance Decorators - Usage Examples

This folder contains practical examples of using governance decorators in the system.

## Available Decorators

### 1. `@governed_service`
For service methods - provides idempotency, audit logging, error handling, and performance monitoring.

**Location:** `governance.services.service_governance`

**See:** `service_example.py` for complete examples

### 2. `@governed_signal_handler`
For Django signal handlers - provides audit logging, error handling, and performance monitoring.

**Location:** `governance.services.signal_governance`

**See:** `signal_example.py` for complete examples

## Quick Start

### Service Example
```python
from governance.services import governed_service

class MyService:
    @governed_service(critical=True, description="My operation")
    def my_method(self, data):
        # Your logic here
        return result
```

### Signal Example
```python
from governance.services import governed_signal_handler
from django.db.models.signals import post_save
from django.dispatch import receiver

@governed_signal_handler("my_signal", critical=True)
@receiver(post_save, sender=MyModel)
def my_signal_handler(sender, instance, created, **kwargs):
    # Your logic here
    pass
```

## Features

### Automatic Idempotency (Services Only)
- Prevents duplicate operations
- Returns cached results for duplicate calls
- Configurable via `enable_idempotency` parameter

### Automatic Audit Logging
- Logs all operations to audit trail
- Captures success/failure status
- Records execution time
- Configurable via `enable_audit` parameter

### Error Handling & Quarantine
- Catches and logs all errors
- Quarantines failed critical operations
- Prevents signal failures from breaking main operations

### Performance Monitoring
- Tracks execution time
- Warns about slow operations
- Provides statistics via `SignalPerformanceMonitor`

## Best Practices

1. **Always use decorators** for services and signals
2. **Use `transaction.on_commit()`** in signals for heavy operations
3. **Set `critical=True`** for operations that must not fail silently
4. **Set `critical=False`** for non-essential operations (like notifications)
5. **Monitor performance** regularly using provided tools

## More Information

- See `service_example.py` for detailed service examples
- See `signal_example.py` for detailed signal examples
- Check `.kiro/steering/unified-services-guide.md` for service standards
- Check `.kiro/steering/unified-signals-guide.md` for signal standards
