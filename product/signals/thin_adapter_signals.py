"""
⚠️⚠️⚠️ DEPRECATED - DO NOT USE ⚠️⚠️⚠️

This file is DISABLED and kept for reference only.

REASON: Violates Single Entry Point principle
All stock operations MUST go through MovementService directly.

CORRECT PATTERN:
View/Service → MovementService.process_movement() → Stock Update

WRONG PATTERN (this file):
View → Signal → StockOrchestrator → MovementService → Stock Update
                    ↓
              Duplicate updates!

See: STOCK_MOVEMENT_UNIFICATION_PLAN.md
See: governance/services/movement_service.py

DO NOT RE-ENABLE THIS FILE.

Migration Status: Phase 2.2 - File Disabled ✅
Date: 25 February 2026
"""

import logging

logger = logging.getLogger(__name__)

# All signals disabled - use MovementService directly
logger.info("⚠️ thin_adapter_signals.py is disabled - use MovementService for all stock operations")
