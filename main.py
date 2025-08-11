#!/usr/bin/env python3
"""
Main entry point for Han Dating Bot.
Direct launch - simplified for immediate bot startup without ProcessSupervisor layers.
"""

import sys
import os
import asyncio
import logging

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def main():
    """Direct bot launch entry point"""
    try:
        # Import and validate configuration first
        from src.config.config import Config
        
        print("🤖 Han Dating Bot - Direct Launch Mode")
        print("📋 Loading configuration from environment...")
        
        # Load configuration from environment
        try:
            config = Config.from_env()
            print("✅ Configuration loaded successfully")
        except Exception as e:
            print(f"❌ Configuration error: {e}")
            print("💡 Please check your .env file and ensure all required variables are set")
            return 1
        
        # Validate critical configuration
        if not config.telegram.api_id or config.telegram.api_id == 0:
            print("❌ TELEGRAM_API_ID not configured")
            return 1
            
        if not config.telegram.api_hash:
            print("❌ TELEGRAM_API_HASH not configured")
            return 1
            
        if not config.telegram.phone:
            print("❌ TELEGRAM_PHONE not configured")
            return 1
        
        print("✅ Critical configuration validated")
        print("🚀 Starting bot in real mode...")
        
        # Import and start the core bot
        from src.core.bot import main as bot_main
        
        # Run the bot
        return asyncio.run(bot_main(config))
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        return 0
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Please ensure all dependencies are installed: pip install -r requirements.txt")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logging.exception("Fatal error in main()")
        return 1

if __name__ == "__main__":
    sys.exit(main())