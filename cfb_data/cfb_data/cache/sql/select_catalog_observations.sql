SELECT namespace, grain, payload
FROM catalog_observations
WHERE
{% for pair in range(pair_count) %}
    (namespace = ? AND grain = ?){% if not loop.last %} OR{% endif %}
{% endfor %}
