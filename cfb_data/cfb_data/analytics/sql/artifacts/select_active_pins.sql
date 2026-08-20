SELECT pin.pin_name
FROM artifact_pin_transitions AS pin
WHERE pin.content_digest = ?
  AND pin.transition_id = (
    SELECT MAX(latest.transition_id)
    FROM artifact_pin_transitions AS latest
    WHERE latest.content_digest = pin.content_digest
      AND latest.pin_name = pin.pin_name
  )
  AND pin.state = 'pinned'
ORDER BY pin.pin_name
