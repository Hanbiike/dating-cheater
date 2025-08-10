-- Description: Data migration from JSON files to PostgreSQL tables  
-- Migration ID: 005
-- Prerequisites: All schema migrations completed

-- =============================================================================
-- JSON DATA MIGRATION UTILITIES
-- =============================================================================

-- Function to validate JSON data structure
CREATE OR REPLACE FUNCTION validate_json_structure(json_data JSONB, expected_fields TEXT[])
RETURNS BOOLEAN AS $$
DECLARE
    field TEXT;
BEGIN
    -- Check if all expected fields exist
    FOREACH field IN ARRAY expected_fields
    LOOP
        IF NOT json_data ? field THEN
            RAISE WARNING 'Missing required field: %', field;
            RETURN FALSE;
        END IF;
    END LOOP;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to safely extract JSON field with default
CREATE OR REPLACE FUNCTION safe_json_extract(json_data JSONB, field_path TEXT, default_value TEXT DEFAULT NULL)
RETURNS TEXT AS $$
BEGIN
    IF json_data IS NULL THEN
        RETURN default_value;
    END IF;
    
    RETURN COALESCE((json_data #>> string_to_array(field_path, '.')), default_value);
END;
$$ LANGUAGE plpgsql;

-- Function to convert timestamp string to proper timestamp
CREATE OR REPLACE FUNCTION parse_timestamp(ts_string TEXT)
RETURNS TIMESTAMP AS $$
BEGIN
    IF ts_string IS NULL OR ts_string = '' THEN
        RETURN NULL;
    END IF;
    
    -- Try different timestamp formats
    BEGIN
        -- ISO 8601 format
        RETURN ts_string::TIMESTAMP;
    EXCEPTION WHEN OTHERS THEN
        BEGIN
            -- Unix timestamp
            RETURN TO_TIMESTAMP(ts_string::NUMERIC);
        EXCEPTION WHEN OTHERS THEN
            -- Return NULL if can't parse
            RETURN NULL;
        END;
    END;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- DATA MIGRATION FUNCTIONS
-- =============================================================================

-- Function to migrate a single girl profile from JSON
CREATE OR REPLACE FUNCTION migrate_girl_profile(
    p_bot_id TEXT,
    p_json_data JSONB,
    p_source_file TEXT
)
RETURNS UUID AS $$
DECLARE
    v_profile_id UUID;
    v_chat_id BIGINT;
    v_telegram_id BIGINT;
    v_name TEXT;
    v_last_activity TIMESTAMP;
    v_message_count INTEGER;
    v_summary JSONB;
    v_profile JSONB;
    v_previous_response_id TEXT;
    v_additional_data JSONB;
BEGIN
    -- Extract and validate data
    v_chat_id := (safe_json_extract(p_json_data, 'chat_id'))::BIGINT;
    v_telegram_id := COALESCE((safe_json_extract(p_json_data, 'telegram_id'))::BIGINT, v_chat_id);
    v_name := safe_json_extract(p_json_data, 'name', 'Unknown');
    v_last_activity := parse_timestamp(safe_json_extract(p_json_data, 'last_activity'));
    v_message_count := COALESCE((safe_json_extract(p_json_data, 'message_count', '0'))::INTEGER, 0);
    v_summary := COALESCE(p_json_data -> 'summary', '{}'::JSONB);
    v_profile := COALESCE(p_json_data -> 'profile', '{}'::JSONB);
    v_previous_response_id := safe_json_extract(p_json_data, 'previous_response_id');
    
    -- Create additional metadata
    v_additional_data := jsonb_build_object(
        'source_file', p_source_file,
        'migrated_at', NOW(),
        'original_data', p_json_data,
        'migration_version', '1.0'
    );
    
    -- Validate required fields
    IF v_chat_id IS NULL THEN
        RAISE EXCEPTION 'Missing required field: chat_id in file %', p_source_file;
    END IF;
    
    -- Insert or update profile
    INSERT INTO girls_profiles (
        bot_id, telegram_id, chat_id, name, last_activity, 
        message_count, summary, profile, previous_response_id, additional_data
    )
    VALUES (
        p_bot_id, v_telegram_id, v_chat_id, v_name, v_last_activity,
        v_message_count, v_summary, v_profile, v_previous_response_id, v_additional_data
    )
    ON CONFLICT (bot_id, telegram_id) DO UPDATE SET
        chat_id = EXCLUDED.chat_id,
        name = EXCLUDED.name,
        last_activity = EXCLUDED.last_activity,
        message_count = EXCLUDED.message_count,
        summary = EXCLUDED.summary,
        profile = EXCLUDED.profile,
        previous_response_id = EXCLUDED.previous_response_id,
        additional_data = EXCLUDED.additional_data,
        updated_at = NOW()
    RETURNING id INTO v_profile_id;
    
    RAISE NOTICE 'Migrated girl profile: % (ID: %)', v_name, v_profile_id;
    RETURN v_profile_id;
END;
$$ LANGUAGE plpgsql;

-- Function to migrate conversation messages from JSON
CREATE OR REPLACE FUNCTION migrate_conversation_messages(
    p_bot_id TEXT,
    p_chat_id BIGINT,
    p_messages_json JSONB,
    p_source_file TEXT
)
RETURNS UUID AS $$
DECLARE
    v_conversation_id UUID;
    v_girl_profile_id UUID;
    v_message_record JSONB;
    v_message_count INTEGER := 0;
    v_sender_type TEXT;
    v_content TEXT;
    v_direction TEXT;
    v_timestamp TIMESTAMP;
    v_metadata JSONB;
BEGIN
    -- Get or create conversation
    SELECT id INTO v_conversation_id
    FROM conversations 
    WHERE bot_id = p_bot_id AND chat_id = p_chat_id;
    
    -- Get girl profile ID if exists
    SELECT id INTO v_girl_profile_id
    FROM girls_profiles
    WHERE bot_id = p_bot_id AND chat_id = p_chat_id;
    
    -- Create conversation if doesn't exist
    IF v_conversation_id IS NULL THEN
        INSERT INTO conversations (bot_id, chat_id, girl_profile_id, title, message_count)
        VALUES (
            p_bot_id, 
            p_chat_id, 
            v_girl_profile_id,
            'Conversation ' || p_chat_id,
            jsonb_array_length(p_messages_json)
        )
        RETURNING id INTO v_conversation_id;
    END IF;
    
    -- Process each message
    FOR v_message_record IN SELECT * FROM jsonb_array_elements(p_messages_json)
    LOOP
        -- Extract message data
        v_content := safe_json_extract(v_message_record, 'text', '');
        v_direction := safe_json_extract(v_message_record, 'direction', 'in');
        v_timestamp := parse_timestamp(safe_json_extract(v_message_record, 'ts'));
        
        -- Determine sender type
        v_sender_type := CASE 
            WHEN v_direction = 'out' THEN 'bot'
            ELSE 'user'
        END;
        
        -- Create metadata
        v_metadata := jsonb_build_object(
            'source_file', p_source_file,
            'original_index', v_message_count,
            'migrated_at', NOW(),
            'original_data', v_message_record
        );
        
        -- Insert message
        INSERT INTO messages (
            conversation_id, bot_id, sender_type, content, 
            direction, timestamp, metadata
        )
        VALUES (
            v_conversation_id, p_bot_id, v_sender_type, v_content,
            v_direction, v_timestamp, v_metadata
        );
        
        v_message_count := v_message_count + 1;
    END LOOP;
    
    -- Update conversation message count
    UPDATE conversations 
    SET message_count = v_message_count, updated_at = NOW()
    WHERE id = v_conversation_id;
    
    RAISE NOTICE 'Migrated % messages for conversation %', v_message_count, p_chat_id;
    RETURN v_conversation_id;
END;
$$ LANGUAGE plpgsql;

-- Function to create default bot for migration
CREATE OR REPLACE FUNCTION create_migration_bot(
    p_bot_name TEXT DEFAULT 'Migrated Bot',
    p_telegram_token TEXT DEFAULT NULL,
    p_owner_id BIGINT DEFAULT NULL
)
RETURNS TEXT AS $$
DECLARE
    v_bot_id TEXT;
    v_config JSONB;
BEGIN
    -- Create bot configuration
    v_config := jsonb_build_object(
        'migration_source', 'json_files',
        'migration_date', NOW(),
        'version', '1.0',
        'automated_migration', true
    );
    
    -- Insert bot
    INSERT INTO bots (name, telegram_token, owner_telegram_id, status, config)
    VALUES (
        p_bot_name,
        p_telegram_token,
        p_owner_id,
        'active',
        v_config
    )
    RETURNING bot_id INTO v_bot_id;
    
    RAISE NOTICE 'Created migration bot: % (ID: %)', p_bot_name, v_bot_id;
    RETURN v_bot_id;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- MIGRATION VERIFICATION FUNCTIONS
-- =============================================================================

-- Function to verify migration completeness
CREATE OR REPLACE FUNCTION verify_migration_completeness(p_bot_id TEXT)
RETURNS TABLE(
    category TEXT,
    expected_count INTEGER,
    actual_count BIGINT,
    status TEXT,
    details TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'Bot Configuration' as category,
        1 as expected_count,
        COUNT(*)::BIGINT as actual_count,
        CASE WHEN COUNT(*) = 1 THEN 'OK' ELSE 'ERROR' END as status,
        'Bot ID: ' || p_bot_id as details
    FROM bots b WHERE b.bot_id = p_bot_id
    
    UNION ALL
    
    SELECT 
        'Girl Profiles' as category,
        0 as expected_count,  -- We don't know expected count
        COUNT(*)::BIGINT as actual_count,
        CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END as status,
        'Profiles found: ' || COUNT(*)::text as details
    FROM girls_profiles gp WHERE gp.bot_id = p_bot_id
    
    UNION ALL
    
    SELECT 
        'Conversations' as category,
        0 as expected_count,
        COUNT(*)::BIGINT as actual_count,
        CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END as status,
        'Conversations found: ' || COUNT(*)::text as details
    FROM conversations c WHERE c.bot_id = p_bot_id
    
    UNION ALL
    
    SELECT 
        'Messages' as category,
        0 as expected_count,
        COUNT(*)::BIGINT as actual_count,
        CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END as status,
        'Messages found: ' || COUNT(*)::text as details
    FROM messages m WHERE m.bot_id = p_bot_id;
END;
$$ LANGUAGE plpgsql;

-- Function to check data integrity after migration
CREATE OR REPLACE FUNCTION check_migration_integrity(p_bot_id TEXT)
RETURNS TABLE(
    check_name TEXT,
    status TEXT,
    issue_count BIGINT,
    details TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'Orphaned Conversations' as check_name,
        CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'WARNING' END as status,
        COUNT(*) as issue_count,
        'Conversations without matching girl profiles: ' || COUNT(*)::text as details
    FROM conversations c
    LEFT JOIN girls_profiles gp ON c.bot_id = gp.bot_id AND c.chat_id = gp.chat_id
    WHERE c.bot_id = p_bot_id AND gp.id IS NULL
    
    UNION ALL
    
    SELECT 
        'Messages Without Conversations' as check_name,
        CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ERROR' END as status,
        COUNT(*) as issue_count,
        'Messages without valid conversations: ' || COUNT(*)::text as details
    FROM messages m
    LEFT JOIN conversations c ON m.conversation_id = c.id
    WHERE m.bot_id = p_bot_id AND c.id IS NULL
    
    UNION ALL
    
    SELECT 
        'Null Timestamps' as check_name,
        CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'WARNING' END as status,
        COUNT(*) as issue_count,
        'Messages with null timestamps: ' || COUNT(*)::text as details
    FROM messages m
    WHERE m.bot_id = p_bot_id AND m.timestamp IS NULL
    
    UNION ALL
    
    SELECT 
        'Empty Message Content' as check_name,
        CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'WARNING' END as status,
        COUNT(*) as issue_count,
        'Messages with empty content: ' || COUNT(*)::text as details
    FROM messages m
    WHERE m.bot_id = p_bot_id AND (m.content IS NULL OR TRIM(m.content) = '');
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- MIGRATION REPORTING
-- =============================================================================

-- Function to generate migration summary report
CREATE OR REPLACE FUNCTION generate_migration_report(p_bot_id TEXT)
RETURNS TABLE(
    section TEXT,
    metric TEXT,
    value TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'MIGRATION SUMMARY' as section,
        'Bot ID' as metric,
        p_bot_id as value
    
    UNION ALL
    
    SELECT 
        'MIGRATION SUMMARY' as section,
        'Migration Date' as metric,
        TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS') as value
        
    UNION ALL
    
    SELECT 
        'DATA COUNTS' as section,
        'Girl Profiles' as metric,
        COUNT(*)::text as value
    FROM girls_profiles WHERE bot_id = p_bot_id
    
    UNION ALL
    
    SELECT 
        'DATA COUNTS' as section,
        'Conversations' as metric,
        COUNT(*)::text as value
    FROM conversations WHERE bot_id = p_bot_id
    
    UNION ALL
    
    SELECT 
        'DATA COUNTS' as section,
        'Total Messages' as metric,
        COUNT(*)::text as value
    FROM messages WHERE bot_id = p_bot_id
    
    UNION ALL
    
    SELECT 
        'DATA QUALITY' as section,
        'Profiles with Names' as metric,
        COUNT(*)::text || '/' || (SELECT COUNT(*) FROM girls_profiles WHERE bot_id = p_bot_id)::text as value
    FROM girls_profiles WHERE bot_id = p_bot_id AND name IS NOT NULL AND TRIM(name) != ''
    
    UNION ALL
    
    SELECT 
        'DATA QUALITY' as section,
        'Messages with Timestamps' as metric,
        COUNT(*)::text || '/' || (SELECT COUNT(*) FROM messages WHERE bot_id = p_bot_id)::text as value
    FROM messages WHERE bot_id = p_bot_id AND timestamp IS NOT NULL
    
    ORDER BY section, metric;
END;
$$ LANGUAGE plpgsql;

-- Grant necessary permissions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_base_role;

COMMENT ON FUNCTION migrate_girl_profile IS 'Migrates a single girl profile from JSON data to PostgreSQL';
COMMENT ON FUNCTION migrate_conversation_messages IS 'Migrates conversation messages from JSON array to PostgreSQL';
COMMENT ON FUNCTION verify_migration_completeness IS 'Verifies that migration was completed successfully';
COMMENT ON FUNCTION check_migration_integrity IS 'Checks data integrity after migration';

-- Migration completion notification
DO $$
BEGIN
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'JSON DATA MIGRATION UTILITIES COMPLETE';
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'Created: JSON validation functions';
    RAISE NOTICE 'Created: Data migration functions';
    RAISE NOTICE 'Created: Migration verification functions';
    RAISE NOTICE 'Created: Integrity check functions';
    RAISE NOTICE 'Created: Migration reporting functions';
    RAISE NOTICE 'Ready: For Python migration script execution';
    RAISE NOTICE '==========================================';
END $$;
