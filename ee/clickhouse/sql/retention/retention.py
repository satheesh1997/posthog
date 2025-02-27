# Would love a clickhouse CTE right about here

RETENTION_SQL = """
SELECT
    datediff(%(period)s, {trunc_func}(toDateTime(%(start_date)s)), reference_event.event_date) as period_to_event_days,
    datediff(%(period)s, reference_event.event_date, {trunc_func}(toDateTime(event_date))) as period_between_events_days,
    COUNT(DISTINCT event.person_id) count
FROM (
    SELECT 
    timestamp AS event_date,
    pdi.person_id as person_id
    FROM events e join (SELECT person_id, distinct_id FROM person_distinct_id WHERE team_id = %(team_id)s) pdi on e.distinct_id = pdi.distinct_id
    where toDateTime(e.timestamp) >= toDateTime(%(start_date)s) AND toDateTime(e.timestamp) <= toDateTime(%(end_date)s)
    AND e.team_id = %(team_id)s {returning_query} {filters}
    {extra_union}
) event
JOIN (
    {reference_event_sql}
) reference_event
    ON (event.person_id = reference_event.person_id)
WHERE {trunc_func}(event.event_date) >= {trunc_func}(reference_event.event_date)
GROUP BY period_to_event_days, period_between_events_days
ORDER BY period_to_event_days, period_between_events_days
"""

REFERENCE_EVENT_SQL = """
SELECT DISTINCT 
{trunc_func}(e.timestamp) as event_date,
pdi.person_id as person_id
from events e JOIN (SELECT person_id, distinct_id FROM person_distinct_id WHERE team_id = %(team_id)s) pdi on e.distinct_id = pdi.distinct_id
where toDateTime(e.timestamp) >= toDateTime(%(start_date)s) AND toDateTime(e.timestamp) <= toDateTime(%(end_date)s)
AND e.team_id = %(team_id)s {target_query} {filters}
"""

REFERENCE_EVENT_UNIQUE_SQL = """
SELECT DISTINCT 
min({trunc_func}(e.timestamp)) as event_date,
pdi.person_id as person_id
from events e JOIN (SELECT person_id, distinct_id FROM person_distinct_id WHERE team_id = %(team_id)s) pdi on e.distinct_id = pdi.distinct_id
WHERE e.team_id = %(team_id)s {target_query} {filters} 
GROUP BY person_id HAVING
event_date >= toDateTime(%(start_date)s) AND event_date <= toDateTime(%(end_date)s)
"""
