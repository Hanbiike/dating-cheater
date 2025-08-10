-- Migration 001: Create Base Schema
-- Description: Core database schema for multi-bot support
-- Date: 2025-01-10
-- Dependencies: None

-- Create custom types
CREATE TYPE bot_status_enum AS ENUM ('active', 'inactive', 'maintenance', 'error');
CREATE TYPE message_sender_enum AS ENUM ('user', 'bot', 'system');

-- Core Bot Management Table
CREATE TABLE bots (
    bot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    telegram_token VARCHAR(255) NOT NULL UNIQUE,
    telegram_bot_username VARCHAR(100),
    owner_telegram_id BIGINT,
    status bot_status_enum DEFAULT 'inactive',
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP,
    
    CONSTRAINT valid_config CHECK (jsonb_typeof(config) = 'object')
);

-- Girls Profiles (Partitioned by bot_id)
CREATE TABLE girls_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID NOT NULL REFERENCES bots(bot_id) ON DELETE CASCADE,
    telegram_id BIGINT NOT NULL,
    chat_id BIGINT,
    name VARCHAR(100),
    last_activity TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    summary JSONB DEFAULT '{}',
    profile JSONB DEFAULT '{}',
    previous_response_id VARCHAR(255),
    additional_data JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(bot_id, telegram_id),
    CONSTRAINT valid_summary CHECK (jsonb_typeof(summary) = 'object'),
    CONSTRAINT valid_profile CHECK (jsonb_typeof(profile) = 'object'),
    CONSTRAINT valid_additional_data CHECK (jsonb_typeof(additional_data) = 'object')
) PARTITION BY HASH (bot_id);

-- Conversations (Partitioned by bot_id)
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID NOT NULL REFERENCES bots(bot_id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    girl_profile_id UUID REFERENCES girls_profiles(id) ON DELETE SET NULL,
    title VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_message_at TIMESTAMP DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    
    UNIQUE(bot_id, chat_id)
) PARTITION BY HASH (bot_id);

-- Messages (Partitioned by bot_id)  
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    bot_id UUID NOT NULL REFERENCES bots(bot_id) ON DELETE CASCADE,
    telegram_message_id INTEGER,
    sender_type message_sender_enum NOT NULL,
    sender_id BIGINT,
    content TEXT,
    message_type VARCHAR(50) DEFAULT 'text',
    direction VARCHAR(10), -- 'in' or 'out'
    timestamp TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_metadata CHECK (jsonb_typeof(metadata) = 'object')
) PARTITION BY HASH (bot_id);

-- Bot Metrics (Partitioned by bot_id)
CREATE TABLE bot_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id UUID NOT NULL REFERENCES bots(bot_id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL,
    metric_tags JSONB DEFAULT '{}',
    timestamp TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT valid_metric_tags CHECK (jsonb_typeof(metric_tags) = 'object')
) PARTITION BY HASH (bot_id);

-- Create initial partitions (4 partitions for each table)
-- Girls Profiles Partitions
CREATE TABLE girls_profiles_p0 PARTITION OF girls_profiles
    FOR VALUES WITH (modulus 4, remainder 0);
CREATE TABLE girls_profiles_p1 PARTITION OF girls_profiles
    FOR VALUES WITH (modulus 4, remainder 1);
CREATE TABLE girls_profiles_p2 PARTITION OF girls_profiles
    FOR VALUES WITH (modulus 4, remainder 2);
CREATE TABLE girls_profiles_p3 PARTITION OF girls_profiles
    FOR VALUES WITH (modulus 4, remainder 3);

-- Conversations Partitions
CREATE TABLE conversations_p0 PARTITION OF conversations
    FOR VALUES WITH (modulus 4, remainder 0);
CREATE TABLE conversations_p1 PARTITION OF conversations
    FOR VALUES WITH (modulus 4, remainder 1);
CREATE TABLE conversations_p2 PARTITION OF conversations
    FOR VALUES WITH (modulus 4, remainder 2);
CREATE TABLE conversations_p3 PARTITION OF conversations
    FOR VALUES WITH (modulus 4, remainder 3);

-- Messages Partitions
CREATE TABLE messages_p0 PARTITION OF messages
    FOR VALUES WITH (modulus 4, remainder 0);
CREATE TABLE messages_p1 PARTITION OF messages
    FOR VALUES WITH (modulus 4, remainder 1);
CREATE TABLE messages_p2 PARTITION OF messages
    FOR VALUES WITH (modulus 4, remainder 2);
CREATE TABLE messages_p3 PARTITION OF messages
    FOR VALUES WITH (modulus 4, remainder 3);

-- Bot Metrics Partitions
CREATE TABLE bot_metrics_p0 PARTITION OF bot_metrics
    FOR VALUES WITH (modulus 4, remainder 0);
CREATE TABLE bot_metrics_p1 PARTITION OF bot_metrics
    FOR VALUES WITH (modulus 4, remainder 1);
CREATE TABLE bot_metrics_p2 PARTITION OF bot_metrics
    FOR VALUES WITH (modulus 4, remainder 2);
CREATE TABLE bot_metrics_p3 PARTITION OF bot_metrics
    FOR VALUES WITH (modulus 4, remainder 3);

-- Create indexes for performance
CREATE INDEX idx_bots_status ON bots(status);
CREATE INDEX idx_bots_owner ON bots(owner_telegram_id);
CREATE INDEX idx_bots_telegram_username ON bots(telegram_bot_username);

CREATE INDEX idx_girls_profiles_bot_telegram ON girls_profiles(bot_id, telegram_id);
CREATE INDEX idx_girls_profiles_chat_id ON girls_profiles(chat_id);
CREATE INDEX idx_girls_profiles_last_activity ON girls_profiles(last_activity);

CREATE INDEX idx_conversations_bot_chat ON conversations(bot_id, chat_id);
CREATE INDEX idx_conversations_last_message ON conversations(last_message_at);
CREATE INDEX idx_conversations_girl_profile ON conversations(girl_profile_id);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, timestamp);
CREATE INDEX idx_messages_bot_time ON messages(bot_id, timestamp);
CREATE INDEX idx_messages_direction ON messages(direction, timestamp);

CREATE INDEX idx_bot_metrics_name_time ON bot_metrics(bot_id, metric_name, timestamp);
CREATE INDEX idx_bot_metrics_timestamp ON bot_metrics(timestamp);

-- Comments for documentation
COMMENT ON TABLE bots IS 'Core bot configuration and status tracking';
COMMENT ON TABLE girls_profiles IS 'User profiles for each bot with conversation context';
COMMENT ON TABLE conversations IS 'Conversation metadata and organization';
COMMENT ON TABLE messages IS 'Individual messages in conversations';
COMMENT ON TABLE bot_metrics IS 'Performance and usage metrics per bot';

-- Migration complete marker
INSERT INTO migration_log (migration_id, description, applied_at)
VALUES ('001', 'Create base schema', NOW())
ON CONFLICT DO NOTHING;
