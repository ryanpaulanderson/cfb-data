UPDATE response_records
SET fresh_until = ?
WHERE endpoint = '/teams'
