-- Supabase PostgreSQL Schema for GitHub Hub
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor > New Query)

-- Projects table (main data)
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    category TEXT NOT NULL,
    stars INTEGER DEFAULT 0,
    forks INTEGER DEFAULT 0,
    description TEXT,
    url TEXT,
    homepage TEXT,
    language TEXT,
    topics JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    readme_content TEXT,
    ai_summary TEXT,
    ai_tech_stack JSONB DEFAULT '[]'::jsonb,
    ai_use_cases JSONB DEFAULT '[]'::jsonb,
    ai_difficulty INTEGER,
    ai_quick_start TEXT,
    ai_tutorial TEXT,
    last_scanned TIMESTAMPTZ,
    last_analyzed TIMESTAMPTZ,
    recent_stars_growth INTEGER DEFAULT 0,
    ai_rag_summary TEXT,
    ai_visual_summary TEXT,
    screenshot TEXT
);

-- Scan history table
CREATE TABLE IF NOT EXISTS scan_history (
    id SERIAL PRIMARY KEY,
    category TEXT,
    scan_time TIMESTAMPTZ DEFAULT NOW(),
    projects_found INTEGER,
    projects_new INTEGER,
    status TEXT
);

-- Settings table (key-value store)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- News sources table
CREATE TABLE IF NOT EXISTS news_sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    last_scanned TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster category queries
CREATE INDEX IF NOT EXISTS idx_projects_category ON projects(category);

-- Enable Row Level Security (optional, but recommended)
-- For now, allow all access via anon key
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_sources ENABLE ROW LEVEL SECURITY;

-- Policies to allow read/write from anon key
CREATE POLICY "Allow all access to projects" ON projects FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all access to scan_history" ON scan_history FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all access to settings" ON settings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all access to news_sources" ON news_sources FOR ALL USING (true) WITH CHECK (true);
