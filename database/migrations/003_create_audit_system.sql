-- Migration 003: Create Audit System
-- Description: Comprehensive audit system with triggers
-- Date: 2025-01-10
-- Dependencies: 001_create_base_schema.sql, 002_create_security_roles.sql

-- Create audit log table
CREATE TABLE IF NOT EXISTS security_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMP DEFAULT NOW(),
    session_id TEXT,
    user_role TEXT NOT NULL,
    bot_id UUID,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL,  -- INSERT, UPDATE, DELETE, SELECT
    resource_id UUID,
    old_values JSONB,
    new_values JSONB,
    query_text TEXT,
    client_ip INET,
    application_name TEXT,
    correlation_id UUID
);

-- Create indexes for audit log
CREATE INDEX idx_audit_timestamp ON security_audit_log(timestamp);
CREATE INDEX idx_audit_user_bot ON security_audit_log(user_role, bot_id);
CREATE INDEX idx_audit_table_op ON security_audit_log(table_name, operation);
CREATE INDEX idx_audit_correlation ON security_audit_log(correlation_id);

-- Enhanced audit trigger function
CREATE OR REPLACE FUNCTION enhanced_audit_trigger()
RETURNS TRIGGER AS $$
DECLARE
    session_info RECORD;
    bot_id_value UUID;
BEGIN
    -- Capture enhanced session information
    SELECT 
        inet_client_addr() as client_ip,
        current_setting('application_name', true) as app_name,
        current_setting('app.session_id', true) as session_id,
        current_setting('app.correlation_id', true) as correlation_id
    INTO session_info;
    
    -- Get bot_id from context or record
    BEGIN
        bot_id_value := current_setting('app.current_bot_id', true)::UUID;
    EXCEPTION WHEN OTHERS THEN
        -- Try to get bot_id from the record
        IF TG_OP IN ('INSERT', 'UPDATE') THEN
            bot_id_value := NEW.bot_id;
        ELSIF TG_OP = 'DELETE' THEN
            bot_id_value := OLD.bot_id;
        END IF;
    END;
    
    -- Insert audit record
    INSERT INTO security_audit_log (
        session_id,
        user_role,
        bot_id,
        table_name,
        operation,
        resource_id,
        old_values,
        new_values,
        query_text,
        client_ip,
        application_name,
        correlation_id
    ) VALUES (
        session_info.session_id,
        current_user,
        bot_id_value,
        TG_TABLE_NAME,
        TG_OP,
        COALESCE(NEW.id, OLD.id),
        CASE WHEN TG_OP IN ('DELETE', 'UPDATE') THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END,
        current_query(),
        session_info.client_ip,
        session_info.app_name,
        session_info.correlation_id::UUID
    );
    
    RETURN COALESCE(NEW, OLD);
EXCEPTION
    WHEN OTHERS THEN
        -- Log audit failures but don't fail the original operation
        RAISE WARNING 'Audit trigger failed: %', SQLERRM;
        RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create audit triggers for all main tables
CREATE TRIGGER audit_bots
    AFTER INSERT OR UPDATE OR DELETE ON bots
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

CREATE TRIGGER audit_girls_profiles
    AFTER INSERT OR UPDATE OR DELETE ON girls_profiles
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

CREATE TRIGGER audit_conversations
    AFTER INSERT OR UPDATE OR DELETE ON conversations
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

CREATE TRIGGER audit_messages
    AFTER INSERT OR UPDATE OR DELETE ON messages
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

CREATE TRIGGER audit_bot_metrics
    AFTER INSERT OR UPDATE OR DELETE ON bot_metrics
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

CREATE TRIGGER audit_admin_users
    AFTER INSERT OR UPDATE OR DELETE ON admin_users
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

CREATE TRIGGER audit_admin_bot_permissions
    AFTER INSERT OR UPDATE OR DELETE ON admin_bot_permissions
    FOR EACH ROW EXECUTE FUNCTION enhanced_audit_trigger();

-- Create function for audit log cleanup
CREATE OR REPLACE FUNCTION cleanup_audit_log(retention_days INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM security_audit_log 
    WHERE timestamp < NOW() - INTERVAL '1 day' * retention_days;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to get audit trail for a resource
CREATE OR REPLACE FUNCTION get_audit_trail(
    table_name_param TEXT,
    resource_id_param UUID,
    limit_param INTEGER DEFAULT 100
)
RETURNS TABLE (
    timestamp TIMESTAMP,
    operation TEXT,
    user_role TEXT,
    old_values JSONB,
    new_values JSONB,
    session_id TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sal.timestamp,
        sal.operation,
        sal.user_role,
        sal.old_values,
        sal.new_values,
        sal.session_id
    FROM security_audit_log sal
    WHERE sal.table_name = table_name_param
      AND sal.resource_id = resource_id_param
    ORDER BY sal.timestamp DESC
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to get bot activity summary
CREATE OR REPLACE FUNCTION get_bot_activity_summary(
    bot_id_param UUID,
    hours_back INTEGER DEFAULT 24
)
RETURNS TABLE (
    table_name TEXT,
    operation TEXT,
    count BIGINT,
    last_activity TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        sal.table_name,
        sal.operation,
        COUNT(*) as count,
        MAX(sal.timestamp) as last_activity
    FROM security_audit_log sal
    WHERE sal.bot_id = bot_id_param
      AND sal.timestamp > NOW() - INTERVAL '1 hour' * hours_back
    GROUP BY sal.table_name, sal.operation
    ORDER BY last_activity DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create automated audit cleanup job function
CREATE OR REPLACE FUNCTION schedule_audit_cleanup()
RETURNS void AS $$
BEGIN
    -- This would integrate with pg_cron if available
    -- For now, just document the cleanup procedure
    RAISE NOTICE 'Audit cleanup should be scheduled to run daily';
    RAISE NOTICE 'Example: SELECT cleanup_audit_log(90);';
END;
$$ LANGUAGE plpgsql;

-- Create security event logging function
CREATE OR REPLACE FUNCTION log_security_event(
    event_type TEXT,
    event_description TEXT,
    severity TEXT DEFAULT 'INFO',
    additional_data JSONB DEFAULT '{}'
)
RETURNS void AS $$
BEGIN
    INSERT INTO security_audit_log (
        user_role,
        table_name,
        operation,
        new_values,
        application_name
    ) VALUES (
        current_user,
        'security_events',
        event_type,
        jsonb_build_object(
            'description', event_description,
            'severity', severity,
            'additional_data', additional_data,
            'timestamp', NOW()
        ),
        'security_monitor'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Comments
COMMENT ON TABLE security_audit_log IS 'Comprehensive audit trail for all database operations';
COMMENT ON FUNCTION enhanced_audit_trigger IS 'Main audit trigger capturing all table changes';
COMMENT ON FUNCTION cleanup_audit_log IS 'Removes old audit records based on retention policy';
COMMENT ON FUNCTION get_audit_trail IS 'Retrieves audit history for a specific resource';
COMMENT ON FUNCTION get_bot_activity_summary IS 'Provides activity summary for a bot';
COMMENT ON FUNCTION log_security_event IS 'Logs custom security events';

-- Migration complete
INSERT INTO migration_log (migration_id, description, applied_at)
VALUES ('003', 'Create audit system', NOW())
ON CONFLICT (migration_id) DO NOTHING;
