-- Migration: Add Chat Tables for AI Dialog Feature
-- Date: 2025-12-20
-- Description: Creates chat_conversations and chat_messages tables for interactive AI chat

-- Connect to salesdb
\c salesdb;

-- Create chat_conversations table
CREATE TABLE IF NOT EXISTS chat_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_minute_id UUID NOT NULL REFERENCES meeting_minutes(id) ON DELETE CASCADE,
    title VARCHAR(255),
    context_snapshot JSONB,
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create indexes for chat_conversations
CREATE INDEX IF NOT EXISTS idx_chat_conversations_minute_id ON chat_conversations(meeting_minute_id);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_created_by ON chat_conversations(created_by);
CREATE INDEX IF NOT EXISTS idx_chat_conversations_updated_at ON chat_conversations(updated_at);

-- Create chat_messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    token_count INTEGER,
    message_metadata JSONB,  -- 'metadata' is reserved in SQLAlchemy
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create indexes for chat_messages
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at);

-- Create trigger for updated_at on chat_conversations
CREATE OR REPLACE FUNCTION update_chat_conversations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_chat_conversations_updated_at ON chat_conversations;
CREATE TRIGGER trigger_chat_conversations_updated_at
    BEFORE UPDATE ON chat_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_conversations_updated_at();

-- Add comment for documentation
COMMENT ON TABLE chat_conversations IS 'AI対話セッション管理テーブル';
COMMENT ON TABLE chat_messages IS 'AI対話メッセージ履歴テーブル';
COMMENT ON COLUMN chat_conversations.context_snapshot IS '会話開始時の解析結果スナップショット';
COMMENT ON COLUMN chat_messages.role IS 'メッセージの役割: user, assistant, system';
COMMENT ON COLUMN chat_messages.token_count IS 'LLMトークン数（コスト管理用）';
COMMENT ON COLUMN chat_messages.message_metadata IS 'メッセージメタデータ';
