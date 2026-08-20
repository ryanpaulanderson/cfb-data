SELECT run.*, transition.state
FROM runs AS run
JOIN run_transitions AS transition
  ON transition.transition_id = (
    SELECT MAX(latest.transition_id)
    FROM run_transitions AS latest
    WHERE latest.run_id = run.run_id
  )
WHERE run.run_id = ?
