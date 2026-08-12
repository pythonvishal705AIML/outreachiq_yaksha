-- Check campaigns table structure and created_by field
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'campaigns'
ORDER BY ORDINAL_POSITION;

-- Check for campaigns with NULL created_by
SELECT 
    COUNT(*) as total_campaigns,
    COUNT(created_by) as campaigns_with_user,
    COUNT(*) - COUNT(created_by) as campaigns_without_user
FROM campaigns;

-- Show sample campaigns with and without created_by
SELECT 
    id,
    name,
    created_by,
    org_id,
    status,
    created_at
FROM campaigns
ORDER BY created_at DESC
LIMIT 10;
