"""
Management command to sync Stock records from StockMovement
⚠️ DEPRECATED: This command is for legacy data migration only.
All new stock movements should use MovementService directly.
"""
from django.core.management.base import BaseCommand
from product.models import Stock, StockMovement
from decimal import Decimal


class Command(BaseCommand):
    help = '⚠️ DEPRECATED: Sync Stock records from existing StockMovement records (legacy migration only)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING(
            '⚠️ WARNING: This command is deprecated and should only be used for legacy data migration.'
        ))
        self.stdout.write(self.style.WARNING(
            'All new stock movements should use MovementService directly.'
        ))
        self.stdout.write('')
        
        movements = StockMovement.objects.all().order_by('timestamp')
        self.stdout.write(f'Processing {movements.count()} movements...')
        
        processed = 0
        for movement in movements:
            stock, created = Stock.objects.get_or_create(
                product=movement.product,
                warehouse=movement.warehouse,
                defaults={'quantity': 0}
            )
            
            if movement.movement_type in ['in', 'return_in']:
                stock.quantity += movement.quantity
                stock.save()
                processed += 1
                self.stdout.write(f'  + {movement.product.name}: +{movement.quantity}')
            elif movement.movement_type in ['out', 'return_out']:
                stock.quantity = max(0, stock.quantity - movement.quantity)
                stock.save()
                processed += 1
                self.stdout.write(f'  - {movement.product.name}: -{movement.quantity}')
        
        self.stdout.write(self.style.SUCCESS(f'\nProcessed {processed} movements'))
        
        stocks = Stock.objects.all()
        self.stdout.write(f'\nTotal Stock records: {stocks.count()}')
        for stock in stocks:
            self.stdout.write(f'  - {stock.product.name} in {stock.warehouse.name}: {stock.quantity}')

