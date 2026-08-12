-- ============================================================================
-- DATABASE OPTIMIZATION FOR INBOX USER FILTERING
-- ============================================================================
-- 
-- This file contains SQL commands to optimize the inbox filtering performance
-- by adding an index on the sent_from field.
--
-- IMPORTANT: Run these commands after deploying the code changes.
-- ============================================================================

-- Check current table structure
-- ============================================================================
-- PostgreSQL:
\d sent_emails;

-- MySQL:
DESCRIBE sent_emails;

-- Check existing indexes
-- ============================================================================
-- PostgreSQL:
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'sent_emails';

-- MySQL:
SHOW INDEXES FROM sent_emails;


-- Add index on sent_from field (RECOMMENDED)
-- ============================================================================
-- This index will significantly improve inbox query performance by allowing
-- fast lookups of emails sent by a specific user.

-- PostgreSQL:
CREATE INDEX IF NOT EXISTS idx_sent_emails_sent_from 
ON sent_emails(sent_from);

-- MySQL:
CREATE INDEX idx_sent_emails_sent_from 
ON sent_emails(sent_from);


-- Add composite index for even better performance (OPTIONAL)
-- ============================================================================
-- If you frequently filter by both sent_from and status, this composite
-- index will provide better performance.

-- PostgreSQL:
CREATE INDEX IF NOT EXISTS idx_sent_emails_sent_from_status 
ON sent_emails(sent_from, status);

-- MySQL:
CREATE INDEX idx_sent_emails_sent_from_status 
ON sent_emails(sent_from, status);


-- Add composite index for sent_from and sent_at (OPTIONAL)
-- ============================================================================
-- This index optimizes the common query pattern: filter by sent_from and
-- order by sent_at DESC.

-- PostgreSQL:
CREATE INDEX IF NOT EXISTS idx_sent_emails_sent_from_sent_at 
ON sent_emails(sent_from, sent_at DESC);

-- MySQL:
CREATE INDEX idx_sent_emails_sent_from_sent_at 
ON sent_emails(sent_from, sent_at DESC);


-- Analyze query performance BEFORE adding indexes
-- ============================================================================
-- Run this query to see the current execution plan:

-- PostgreSQL:
EXPLAIN ANALYZE
SELECT * FROM sent_emails 
WHERE sent_from = 'user@example.com' 
ORDER BY sent_at DESC 
LIMIT 10;

-- MySQL:
EXPLAIN
SELECT * FROM sent_emails 
WHERE sent_from = 'user@example.com' 
ORDER BY sent_at DESC 
LIMIT 10;


-- Analyze query performance AFTER adding indexes
-- ============================================================================
-- Run the same query again to compare performance:

-- PostgreSQL:
EXPLAIN ANALYZE
SELECT * FROM sent_emails 
WHERE sent_from = 'user@example.com' 
ORDER BY sent_at DESC 
LIMIT 10;

-- MySQL:
EXPLAIN
SELECT * FROM sent_emails 
WHERE sent_from = 'user@example.com' 
ORDER BY sent_at DESC 
LIMIT 10;


-- Check index usage statistics (PostgreSQL only)
-- ============================================================================
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched
FROM pg_stat_user_indexes
WHERE tablename = 'sent_emails'
ORDER BY idx_scan DESC;


-- Estimate index size
-- ============================================================================
-- PostgreSQL:
SELECT 
    pg_size_pretty(pg_relation_size('idx_sent_emails_sent_from')) as index_size;

-- MySQL:
SELECT 
    index_name,
    ROUND(stat_value * @@innodb_page_size / 1024 / 1024, 2) as size_mb
FROM mysql.innodb_index_stats
WHERE table_name = 'sent_emails' 
AND index_name = 'idx_sent_emails_sent_from';


-- Maintenance: Rebuild indexes if needed
-- ============================================================================
-- PostgreSQL:
REINDEX INDEX idx_sent_emails_sent_from;

-- MySQL:
OPTIMIZE TABLE sent_emails;


-- Remove indexes if needed (for rollback)
-- ============================================================================
-- PostgreSQL:
DROP INDEX IF EXISTS idx_sent_emails_sent_from;
DROP INDEX IF EXISTS idx_sent_emails_sent_from_status;
DROP INDEX IF EXISTS idx_sent_emails_sent_from_sent_at;

-- MySQL:
DROP INDEX idx_sent_emails_sent_from ON sent_emails;
DROP INDEX idx_sent_emails_sent_from_status ON sent_emails;
DROP INDEX idx_sent_emails_sent_from_sent_at ON sent_emails;


-- ============================================================================
-- PERFORMANCE EXPECTATIONS
-- ============================================================================
--
-- Without Index:
-- - Query scans entire table (Sequential Scan)
-- - Time: 50-500ms for 10,000 rows
-- - Cost: High CPU usage
--
-- With Index:
-- - Query uses index (Index Scan)
-- - Time: 1-10ms for 10,000 rows
-- - Cost: Low CPU usage
--
-- Recommended: Add at least the basic sent_from index
-- ============================================================================


-- ============================================================================
-- DEPLOYMENT CHECKLIST
-- ============================================================================
--
-- [ ] 1. Backup database before making changes
-- [ ] 2. Run EXPLAIN ANALYZE to check current performance
-- [ ] 3. Create the idx_sent_emails_sent_from index
-- [ ] 4. Run EXPLAIN ANALYZE again to verify improvement
-- [ ] 5. Monitor query performance in production
-- [ ] 6. Consider adding composite indexes if needed
--
-- ============================================================================
