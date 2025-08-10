-- Migration 002: Create Security Roles and RLS Policies
-- Description: Database security model with Row Level Security
-- Date: 2025-01-10
-- Dependencies: 001_create_base_schema.sql

-- Create migration log table if not exists
CREATE TABLE IF NOT EXISTS migration_log (
    id SERIAL PRIMARY KEY,
    migration_id VARCHAR(10) UNIQUE NOT NULL,
    description TEXT,
    applied_at TIMESTAMP DEFAULT NOW()
);

-- Create base roles hierarchy
DO $$
BEGIN
    -- Base application role
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_base_role') THEN
        CREATE ROLE app_base_role;
    END IF;

    -- Bot role (inherits from base)
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bot_role') THEN
        CREATE ROLE bot_role INHERIT;
        GRANT app_base_role TO bot_role;
    END IF;

    -- Admin role (inherits from bot)
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'admin_role') THEN
        CREATE ROLE admin_role INHERIT;
        GRANT bot_role TO admin_role;
    END IF;

    -- Super admin role (inherits from admin)
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'super_admin_role') THEN
        CREATE ROLE super_admin_role INHERIT;
        GRANT admin_role TO super_admin_role;
    END IF;
END $$;

-- Grant basic permissions to app_base_role
GRANT USAGE ON SCHEMA public TO app_base_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_base_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_base_role;

-- Create admin users table
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    role_level VARCHAR(50) DEFAULT 'bot_admin',
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- Create bot permissions table
CREATE TABLE IF NOT EXISTS admin_bot_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID REFERENCES admin_users(id) ON DELETE CASCADE,
    bot_id UUID REFERENCES bots(bot_id) ON DELETE CASCADE,
    permissions JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(admin_id, bot_id),
    CONSTRAINT valid_permissions CHECK (jsonb_typeof(permissions) = 'object')
);

-- Enable Row Level Security on all partitioned tables
ALTER TABLE girls_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_metrics ENABLE ROW LEVEL SECURITY;

-- Bot isolation policy (primary security boundary)
CREATE POLICY bot_data_isolation_girls ON girls_profiles
    FOR ALL
    TO bot_role
    USING (
        bot_id = coalesce(
            current_setting('app.current_bot_id', true)::UUID,
            (SELECT bot_id FROM admin_bot_permissions abp 
             JOIN admin_users au ON abp.admin_id = au.id 
             WHERE au.username = current_user LIMIT 1)
        )
    );

CREATE POLICY bot_data_isolation_conversations ON conversations
    FOR ALL
    TO bot_role
    USING (
        bot_id = coalesce(
            current_setting('app.current_bot_id', true)::UUID,
            (SELECT bot_id FROM admin_bot_permissions abp 
             JOIN admin_users au ON abp.admin_id = au.id 
             WHERE au.username = current_user LIMIT 1)
        )
    );

CREATE POLICY bot_data_isolation_messages ON messages
    FOR ALL
    TO bot_role
    USING (
        bot_id = coalesce(
            current_setting('app.current_bot_id', true)::UUID,
            (SELECT bot_id FROM admin_bot_permissions abp 
             JOIN admin_users au ON abp.admin_id = au.id 
             WHERE au.username = current_user LIMIT 1)
        )
    );

CREATE POLICY bot_data_isolation_metrics ON bot_metrics
    FOR ALL
    TO bot_role
    USING (
        bot_id = coalesce(
            current_setting('app.current_bot_id', true)::UUID,
            (SELECT bot_id FROM admin_bot_permissions abp 
             JOIN admin_users au ON abp.admin_id = au.id 
             WHERE au.username = current_user LIMIT 1)
        )
    );

-- Admin access policy (override for admin operations)
CREATE POLICY admin_cross_bot_access_girls ON girls_profiles
    FOR ALL
    TO admin_role
    USING (
        bot_id IN (
            SELECT abp.bot_id FROM admin_bot_permissions abp
            JOIN admin_users au ON abp.admin_id = au.id
            WHERE au.username = current_user AND au.is_active = true
        )
    );

CREATE POLICY admin_cross_bot_access_conversations ON conversations
    FOR ALL
    TO admin_role
    USING (
        bot_id IN (
            SELECT abp.bot_id FROM admin_bot_permissions abp
            JOIN admin_users au ON abp.admin_id = au.id
            WHERE au.username = current_user AND au.is_active = true
        )
    );

CREATE POLICY admin_cross_bot_access_messages ON messages
    FOR ALL
    TO admin_role
    USING (
        bot_id IN (
            SELECT abp.bot_id FROM admin_bot_permissions abp
            JOIN admin_users au ON abp.admin_id = au.id
            WHERE au.username = current_user AND au.is_active = true
        )
    );

CREATE POLICY admin_cross_bot_access_metrics ON bot_metrics
    FOR ALL
    TO admin_role
    USING (
        bot_id IN (
            SELECT abp.bot_id FROM admin_bot_permissions abp
            JOIN admin_users au ON abp.admin_id = au.id
            WHERE au.username = current_user AND au.is_active = true
        )
    );

-- Super admin policy (full access)
CREATE POLICY super_admin_full_access_girls ON girls_profiles
    FOR ALL
    TO super_admin_role
    USING (true);

CREATE POLICY super_admin_full_access_conversations ON conversations
    FOR ALL
    TO super_admin_role
    USING (true);

CREATE POLICY super_admin_full_access_messages ON messages
    FOR ALL
    TO super_admin_role
    USING (true);

CREATE POLICY super_admin_full_access_metrics ON bot_metrics
    FOR ALL
    TO super_admin_role
    USING (true);

-- Create function to create bot-specific user
CREATE OR REPLACE FUNCTION create_bot_user(bot_uuid UUID, bot_name TEXT)
RETURNS TEXT AS $$
DECLARE
    role_name TEXT;
    admin_role_name TEXT;
BEGIN
    -- Generate role names
    role_name := 'bot_' || replace(bot_uuid::text, '-', '_') || '_user';
    admin_role_name := 'bot_' || replace(bot_uuid::text, '-', '_') || '_admin';
    
    -- Create bot user role
    EXECUTE format('CREATE ROLE %I INHERIT', role_name);
    EXECUTE format('GRANT bot_role TO %I', role_name);
    EXECUTE format('ALTER ROLE %I SET app.current_bot_id = %L', role_name, bot_uuid);
    
    -- Create bot admin role
    EXECUTE format('CREATE ROLE %I INHERIT', admin_role_name);
    EXECUTE format('GRANT admin_role TO %I', admin_role_name);
    EXECUTE format('GRANT %I TO %I', role_name, admin_role_name);
    
    RETURN format('Created roles: %s, %s', role_name, admin_role_name);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to drop bot-specific user
CREATE OR REPLACE FUNCTION drop_bot_user(bot_uuid UUID)
RETURNS TEXT AS $$
DECLARE
    role_name TEXT;
    admin_role_name TEXT;
BEGIN
    role_name := 'bot_' || replace(bot_uuid::text, '-', '_') || '_user';
    admin_role_name := 'bot_' || replace(bot_uuid::text, '-', '_') || '_admin';
    
    -- Drop roles if they exist
    EXECUTE format('DROP ROLE IF EXISTS %I', admin_role_name);
    EXECUTE format('DROP ROLE IF EXISTS %I', role_name);
    
    RETURN format('Dropped roles: %s, %s', role_name, admin_role_name);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create indexes for security queries
CREATE INDEX idx_admin_users_username ON admin_users(username) WHERE is_active = true;
CREATE INDEX idx_admin_bot_permissions_admin_bot ON admin_bot_permissions(admin_id, bot_id);

-- Comments
COMMENT ON TABLE admin_users IS 'Administrative users with bot access permissions';
COMMENT ON TABLE admin_bot_permissions IS 'Mapping of admin users to bot access permissions';
COMMENT ON FUNCTION create_bot_user IS 'Creates database roles for a new bot';
COMMENT ON FUNCTION drop_bot_user IS 'Removes database roles for a deleted bot';

-- Migration complete
INSERT INTO migration_log (migration_id, description, applied_at)
VALUES ('002', 'Create security roles and RLS policies', NOW())
ON CONFLICT (migration_id) DO NOTHING;
