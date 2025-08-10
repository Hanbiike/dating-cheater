#!/usr/bin/env python3
"""
Main entry point wrapper for Han Dating Bot.
Phase 2C Integration: ProcessSupervisor integration with backward compatibility.
"""

import sys
import os
import asyncio

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Phase 2C Integration: Use MainIntegrator for mode detection and routing
try:
    from src.processsupervisor.manager.main_integrator import MainIntegrator, legacy_main_compatibility
    
    # Use MainIntegrator for enhanced multi-bot capability
    def main():
        """Enhanced main entry point with ProcessSupervisor integration"""
        integrator = MainIntegrator()
        args = integrator.parse_arguments()
        return asyncio.run(integrator.run(args))
        
except ImportError:
    # Fallback to legacy single-bot mode if ProcessSupervisor not available
    from src.core.bot import main
    
    print("Warning: ProcessSupervisor not available, falling back to single-bot mode")

if __name__ == "__main__":
    # Check if running with enhanced integration
    if 'MainIntegrator' in locals():
        sys.exit(main())
    else:
        # Legacy fallback
        asyncio.run(main())