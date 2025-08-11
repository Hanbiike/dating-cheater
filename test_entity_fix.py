#!/usr/bin/env python3
"""
Simple test to verify admin message sending works after entity resolution fix.
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, '/Users/han/gpt-5-dater')

from src.config.config import Config
from src.core.bot import main
from telethon import TelegramClient
from src.core.connection_manager import ConnectionManager


async def test_admin_message():
    """Test sending a message to admin after entity pre-loading."""
    print("🧪 Testing admin message sending after entity resolution fix...")
    
    # Load config
    config = Config.from_env()
    ADMIN_CHAT_ID = config.admin_chat_id
    SESSION_NAME = config.telegram.session_name
    TELEGRAM_API_ID = config.telegram.api_id
    TELEGRAM_API_HASH = config.telegram.api_hash
    TELEGRAM_PHONE = config.telegram.phone
    
    print(f"Admin Chat ID: {ADMIN_CHAT_ID}")
    
    # Create client
    client = TelegramClient(SESSION_NAME, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    connection_manager = ConnectionManager(client, TELEGRAM_PHONE)
    
    try:
        # Connect
        print("🔗 Connecting to Telegram...")
        connected = await connection_manager.connect_with_retry(lambda: "")
        if not connected:
            print("❌ Failed to connect to Telegram")
            return False
        
        print("✅ Connected to Telegram")
        
        # Entity cache
        entity_cache = {}
        
        # Enhanced resolve_peer function (copy from implementation)
        async def resolve_peer(chat_id: int):
            """Enhanced entity resolution with multiple fallback strategies."""
            if chat_id in entity_cache:
                return entity_cache[chat_id]
            
            try:
                from telethon.tl.types import InputPeerUser, PeerUser
                entity = await client.get_input_entity(chat_id)
                entity_cache[chat_id] = entity
                print(f"✅ Entity resolved via get_input_entity for {chat_id}")
                return entity
            except ValueError as e:
                print(f"⚠️ get_input_entity failed for {chat_id}: {e}")
                
                try:
                    entity = await client.get_entity(chat_id)
                    if hasattr(entity, 'access_hash') and entity.access_hash:
                        from telethon.tl.types import InputPeerUser
                        input_entity = InputPeerUser(entity.id, entity.access_hash)
                        entity_cache[chat_id] = input_entity
                        print(f"✅ Entity resolved via get_entity + InputPeerUser for {chat_id}")
                        return input_entity
                except Exception as e2:
                    print(f"⚠️ get_entity strategy failed for {chat_id}: {e2}")
                
                try:
                    async for dialog in client.iter_dialogs():
                        if hasattr(dialog.entity, 'id') and dialog.entity.id == chat_id:
                            entity_cache[chat_id] = dialog.input_entity
                            print(f"✅ Entity resolved via dialog iteration for {chat_id}")
                            return dialog.input_entity
                except Exception as e3:
                    print(f"⚠️ Dialog iteration failed for {chat_id}: {e3}")
            
            from telethon.tl.types import PeerUser
            print(f"⚠️ Using PeerUser fallback for {chat_id}")
            return PeerUser(chat_id)
        
        # Test entity resolution
        print(f"🔍 Testing entity resolution for admin {ADMIN_CHAT_ID}...")
        peer = await resolve_peer(ADMIN_CHAT_ID)
        print(f"✅ Peer resolved: {type(peer).__name__}")
        
        # Test message sending
        test_message = "🧪 Entity Resolution Fix Test - Message sending working!"
        print(f"📤 Sending test message: {test_message}")
        
        await client.send_message(peer, test_message)
        print("✅ Message sent successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    finally:
        await client.disconnect()
        print("🔌 Disconnected from Telegram")


if __name__ == "__main__":
    result = asyncio.run(test_admin_message())
    if result:
        print("🎉 Entity Resolution Fix Test PASSED!")
    else:
        print("❌ Entity Resolution Fix Test FAILED!")
