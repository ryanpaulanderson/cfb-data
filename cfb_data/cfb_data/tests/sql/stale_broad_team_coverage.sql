UPDATE coverage
SET fresh_until = ?
WHERE endpoint = '/teams' AND canonical_filters = ''
