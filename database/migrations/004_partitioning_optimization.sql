-- Description: Setup database partitioning optimization and performance tuning
-- Migration ID: 004
-- Prerequisites: Base schema, security roles, audit system

-- =============================================================================
-- PARTITIONING OPTIMIZATION
-- =============================================================================

-- Create partition maintenance function
CREATE OR REPLACE FUNCTION create_bot_partition(p_bot_id TEXT)
RETURNS VOID AS $$
BEGIN
    -- Create partitions for all partitioned tables
    EXECUTE format('CREATE TABLE IF NOT EXISTS girls_profiles_%s PARTITION OF girls_profiles FOR VALUES WITH (MODULUS 10, REMAINDER %s)',
        p_bot_id, (hashtext(p_bot_id) % 10));
        
    EXECUTE format('CREATE TABLE IF NOT EXISTS conversations_%s PARTITION OF conversations FOR VALUES WITH (MODULUS 10, REMAINDER %s)',
        p_bot_id, (hashtext(p_bot_id) % 10));
        
    EXECUTE format('CREATE TABLE IF NOT EXISTS messages_%s PARTITION OF messages FOR VALUES WITH (MODULUS 10, REMAINDER %s)',
        p_bot_id, (hashtext(p_bot_id) % 10));
        
    EXECUTE format('CREATE TABLE IF NOT EXISTS bot_metrics_%s PARTITION OF bot_metrics FOR VALUES WITH (MODULUS 10, REMAINDER %s)',
        p_bot_id, (hashtext(p_bot_id) % 10));
        
    RAISE NOTICE 'Created partitions for bot_id: %', p_bot_id;
END;
$$ LANGUAGE plpgsql;

-- Create automatic partition creation trigger
CREATE OR REPLACE FUNCTION auto_create_bot_partition()
RETURNS TRIGGER AS $$
BEGIN
    -- Automatically create partitions when new bot is inserted
    PERFORM create_bot_partition(NEW.bot_id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger to bots table
CREATE TRIGGER auto_partition_trigger
    AFTER INSERT ON bots
    FOR EACH ROW
    EXECUTE FUNCTION auto_create_bot_partition();

-- =============================================================================
-- PERFORMANCE INDEXES
-- =============================================================================

-- Girls profiles indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_girls_profiles_telegram_id 
    ON girls_profiles (telegram_id);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_girls_profiles_last_activity 
    ON girls_profiles (last_activity DESC);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_girls_profiles_message_count 
    ON girls_profiles (message_count DESC);

-- Conversations indexes  
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_chat_id 
    ON conversations (chat_id);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_created_at 
    ON conversations (created_at DESC);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_girl_profile 
    ON conversations (girl_profile_id);

-- Messages indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_timestamp 
    ON messages (conversation_id, timestamp DESC);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_sender_type 
    ON messages (sender_type);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_timestamp 
    ON messages (timestamp DESC);

-- Bot metrics indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bot_metrics_date 
    ON bot_metrics (date DESC);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bot_metrics_metric_type 
    ON bot_metrics (metric_type);

-- Security audit indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_security_audit_event_time 
    ON security_audit_log (event_time DESC);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_security_audit_bot_id 
    ON security_audit_log (bot_id);
    
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_security_audit_event_type 
    ON security_audit_log (event_type);

-- =============================================================================
-- PERFORMANCE VIEWS
-- =============================================================================

-- Bot activity summary view
CREATE OR REPLACE VIEW bot_activity_summary AS
SELECT 
    b.bot_id,
    b.name as bot_name,
    b.status,
    COUNT(DISTINCT gp.id) as total_girls,
    COUNT(DISTINCT c.id) as total_conversations,
    COUNT(DISTINCT m.id) as total_messages,
    MAX(gp.last_activity) as last_girl_activity,
    MAX(m.timestamp) as last_message_time,
    AVG(gp.message_count) as avg_messages_per_girl
FROM bots b
LEFT JOIN girls_profiles gp ON b.bot_id = gp.bot_id
LEFT JOIN conversations c ON b.bot_id = c.bot_id
LEFT JOIN messages m ON b.bot_id = m.bot_id
GROUP BY b.bot_id, b.name, b.status;

-- Daily metrics summary view
CREATE OR REPLACE VIEW daily_metrics_summary AS
SELECT 
    bot_id,
    date,
    SUM(CASE WHEN metric_type = 'messages_sent' THEN value ELSE 0 END) as messages_sent,
    SUM(CASE WHEN metric_type = 'messages_received' THEN value ELSE 0 END) as messages_received,
    SUM(CASE WHEN metric_type = 'new_conversations' THEN value ELSE 0 END) as new_conversations,
    SUM(CASE WHEN metric_type = 'active_users' THEN value ELSE 0 END) as active_users,
    MAX(created_at) as last_updated
FROM bot_metrics
GROUP BY bot_id, date
ORDER BY date DESC;

-- Recent activity view
CREATE OR REPLACE VIEW recent_activity AS
SELECT 
    'message' as activity_type,
    m.bot_id,
    m.conversation_id::text as reference_id,
    m.sender_type,
    LEFT(m.content, 100) as preview,
    m.timestamp as activity_time
FROM messages m
WHERE m.timestamp > NOW() - INTERVAL '24 hours'

UNION ALL

SELECT 
    'profile_update' as activity_type,
    gp.bot_id,
    gp.id::text as reference_id,
    'system' as sender_type,
    'Profile updated: ' || COALESCE(gp.name, 'Unknown') as preview,
    gp.updated_at as activity_time
FROM girls_profiles gp
WHERE gp.updated_at > NOW() - INTERVAL '24 hours'

ORDER BY activity_time DESC;

-- =============================================================================
-- MAINTENANCE FUNCTIONS
-- =============================================================================

-- Function to cleanup old audit logs
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM security_audit_log 
    WHERE event_time < NOW() - INTERVAL '1 day' * retention_days;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RAISE NOTICE 'Cleaned up % old audit log entries', deleted_count;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to update table statistics
CREATE OR REPLACE FUNCTION update_table_statistics()
RETURNS VOID AS $$
BEGIN
    ANALYZE bots;
    ANALYZE girls_profiles;
    ANALYZE conversations;
    ANALYZE messages;
    ANALYZE bot_metrics;
    ANALYZE security_audit_log;
    
    RAISE NOTICE 'Updated statistics for all tables';
END;
$$ LANGUAGE plpgsql;

-- Function to check partition health
CREATE OR REPLACE FUNCTION check_partition_health()
RETURNS TABLE(
    table_name TEXT,
    partition_count BIGINT,
    total_rows BIGINT,
    avg_rows_per_partition NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        schemaname||'.'||tablename as table_name,
        COUNT(*) as partition_count,
        SUM(n_tup_ins + n_tup_upd) as total_rows,
        AVG(n_tup_ins + n_tup_upd) as avg_rows_per_partition
    FROM pg_stat_user_tables 
    WHERE schemaname = 'public' 
    AND tablename LIKE '%_profiles_%' OR tablename LIKE '%_conversations_%' 
    OR tablename LIKE '%_messages_%' OR tablename LIKE '%_metrics_%'
    GROUP BY schemaname||'.'||tablename;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SCHEDULED MAINTENANCE
-- =============================================================================

-- Create maintenance schedule (requires pg_cron extension)
-- SELECT cron.schedule('cleanup-audit-logs', '0 2 * * *', 'SELECT cleanup_old_audit_logs(90);');
-- SELECT cron.schedule('update-statistics', '0 3 * * 0', 'SELECT update_table_statistics();');

-- Alternative: Create maintenance reminder function
CREATE OR REPLACE FUNCTION maintenance_reminder()
RETURNS TABLE(
    task TEXT,
    last_run TIMESTAMP,
    recommendation TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'Audit Log Cleanup' as task,
        (SELECT MAX(event_time) FROM security_audit_log WHERE event_type = 'maintenance') as last_run,
        CASE 
            WHEN (SELECT COUNT(*) FROM security_audit_log WHERE event_time < NOW() - INTERVAL '90 days') > 0
            THEN 'Run cleanup_old_audit_logs(90)'
            ELSE 'No cleanup needed'
        END as recommendation
    
    UNION ALL
    
    SELECT 
        'Statistics Update' as task,
        (SELECT schemaname||'.'||tablename||' last analyzed: '||last_analyze 
         FROM pg_stat_user_tables 
         WHERE schemaname = 'public' 
         ORDER BY last_analyze DESC NULLS LAST 
         LIMIT 1)::timestamp as last_run,
        CASE 
            WHEN (SELECT MIN(last_analyze) FROM pg_stat_user_tables WHERE schemaname = 'public') < NOW() - INTERVAL '7 days'
            THEN 'Run update_table_statistics()'
            ELSE 'Statistics are current'
        END as recommendation;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SECURITY ENHANCEMENTS
-- =============================================================================

-- Create function to rotate security keys (placeholder for future enhancement)
CREATE OR REPLACE FUNCTION rotate_security_keys()
RETURNS VOID AS $$
BEGIN
    -- Log security key rotation event
    INSERT INTO security_audit_log (event_type, details, correlation_id)
    VALUES ('security_key_rotation', 
            '{"action": "key_rotation_initiated", "timestamp": "' || NOW() || '"}',
            'system-' || extract(epoch from now())::text);
            
    RAISE NOTICE 'Security key rotation logged. Implement actual key rotation logic as needed.';
END;
$$ LANGUAGE plpgsql;

-- Create security health check function
CREATE OR REPLACE FUNCTION security_health_check()
RETURNS TABLE(
    check_name TEXT,
    status TEXT,
    details TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        'Row Level Security' as check_name,
        CASE WHEN COUNT(*) > 0 THEN 'ENABLED' ELSE 'DISABLED' END as status,
        'RLS policies: ' || COUNT(*)::text as details
    FROM pg_policies
    WHERE schemaname = 'public'
    
    UNION ALL
    
    SELECT 
        'Database Roles' as check_name,
        'ACTIVE' as status,
        'Active roles: ' || COUNT(*)::text as details
    FROM pg_roles 
    WHERE rolname LIKE 'app_%' OR rolname LIKE 'bot_%'
    
    UNION ALL
    
    SELECT 
        'Recent Security Events' as check_name,
        CASE WHEN COUNT(*) = 0 THEN 'CLEAN' ELSE 'EVENTS_FOUND' END as status,
        'Security events in last 24h: ' || COUNT(*)::text as details
    FROM security_audit_log 
    WHERE event_time > NOW() - INTERVAL '24 hours'
    AND event_type IN ('security_violation', 'unauthorized_access', 'permission_denied');
END;
$$ LANGUAGE plpgsql;

-- Grant necessary permissions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_base_role;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_base_role;

COMMENT ON FUNCTION create_bot_partition IS 'Creates hash partitions for a new bot across all partitioned tables';
COMMENT ON FUNCTION maintenance_reminder IS 'Provides maintenance task recommendations based on current database state';
COMMENT ON FUNCTION security_health_check IS 'Performs security configuration and event health check';

-- Migration completion notification
DO $$
BEGIN
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'PARTITIONING OPTIMIZATION COMPLETE';
    RAISE NOTICE '==========================================';
    RAISE NOTICE 'Created: Partition management functions';
    RAISE NOTICE 'Created: Performance indexes';
    RAISE NOTICE 'Created: Monitoring views';
    RAISE NOTICE 'Created: Maintenance functions';
    RAISE NOTICE 'Created: Security health checks';
    RAISE NOTICE 'Next: Run data migration script';
    RAISE NOTICE '==========================================';
END $$;
