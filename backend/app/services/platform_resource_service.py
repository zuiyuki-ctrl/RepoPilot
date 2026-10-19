"""Stored observation summaries with explicit unknown scope; no live prices/config."""
from types import SimpleNamespace
from ..schemas.process_agent import ProcessTraceEvent
from .request_observation_service import collect_request_observations
from .evaluation_metrics_service import resource_metrics


def run_resources(run, events, *, gateway=None):
    native, external, refs = [], [], []
    invalid = False
    for event in events:
        if event.event_type.startswith(('MODEL_CALL_', 'EMBEDDING_CALL_')):
            refs.append(event.sequence)
            wrapper = event.payload
            payload = wrapper.get('native') if isinstance(wrapper, dict) else None
            if (not isinstance(payload, dict) or not isinstance(payload.get('call_id'), str)
                    or not payload['call_id'] or wrapper.get('legacy_task_id') != str(run.legacy_task_id)):
                invalid = True
                continue
            native.append(SimpleNamespace(sequence=event.sequence, node_name=wrapper.get('node_name'),
                event_type=event.event_type, payload=payload))
        elif event.event_type == 'PROCESS_TRACE':
            try:
                trace = ProcessTraceEvent.model_validate(event.payload)
                if trace.run_id != str(run.id):
                    raise ValueError('Wrong Run')
            except ValueError:
                invalid = True
                continue
            if trace.kind == 'model_call':
                refs.append(event.sequence)
                external.append((event.sequence, trace))
    rows = collect_request_observations(native)
    for sequence, trace in external:
        counts = (trace.input_tokens, trace.output_tokens, trace.total_tokens)
        valid = all(type(n) is int and n >= 0 for n in counts) and counts[0] + counts[1] == counts[2]
        rows.append(dict(call_id=trace.call_id or '', kind='chat', phase='process_agent',
            started_sequences=[], finished_sequences=[sequence], completeness='recorded' if trace.call_id else 'ambiguous',
            observation=dict(call_id=trace.call_id, request_attempted=True,
                usage_status='complete' if valid else 'partial',
                usage=dict(input_tokens=trace.input_tokens, output_tokens=trace.output_tokens, total_tokens=trace.total_tokens))))
    # Revalidate totals rather than trusting a reported usage_status flag.
    for row in rows:
        obs = row.get('observation')
        if not isinstance(obs, dict):
            continue
        usage = obs.get('usage')
        if not isinstance(usage, dict):
            obs['usage'], obs['usage_status'] = {}, 'invalid'
            continue
        keys = ('input_tokens', 'total_tokens') if row['kind'] == 'embedding' else ('input_tokens', 'output_tokens', 'total_tokens')
        values = [usage.get(key) for key in keys]
        if (not all(type(n) is int and n >= 0 for n in values)
                or (row['kind'] == 'chat' and values[0]+values[1] != values[2])):
            obs['usage_status'] = 'invalid'
    capabilities = getattr(run, 'capabilities', {}) or {}
    capability = capabilities.get('model_usage') or {}
    # A paired start/end alone cannot prove that the adapter reported every request.
    scope_complete = (run.lifecycle == 'finished' and not invalid and bool(refs)
        and capability.get('validated') is True and capability.get('availability') == 'available'
        and capability.get('expected_records') == capability.get('recorded_records') == len(refs)
        and set(capability.get('evidence_sequences', [])) == set(refs)
        and [e.sequence for e in events] == list(range(1, run.event_sequence+1)))
    metrics = resource_metrics(rows, complete_scope=scope_complete)
    gateway_authoritative = gateway is not None and (gateway['grant_present'] or gateway['call_count'] > 0)
    excluded_reported_calls = 0
    if gateway_authoritative:
        # A grant establishes this Run's model route. Do not add self-reported
        # usage even when its call_id differs (or no ledger call was dispatched).
        excluded_reported_calls = len(rows)
        rows = []
        for call in gateway['items']:
            if not call['real_usage_eligible']:
                continue
            usage = call['usage'] or {}
            rows.append(dict(call_id=call['id'], kind='chat', phase='gateway', completeness='recorded',
                started_sequences=[], finished_sequences=[], observation=dict(
                    request_attempted=True if call['dispatched_at'] is not None else None,
                    usage_status='complete' if call['usage_status'] == 'recorded' else 'missing',
                    duration_ms=call['duration_ms'], usage=dict(input_tokens=usage.get('prompt_tokens'),
                        output_tokens=usage.get('completion_tokens'), total_tokens=usage.get('total_tokens')))))
        metrics = resource_metrics(rows, complete_scope=gateway['real_scope_complete'] and run.lifecycle == 'finished')
    wall = None
    if run.started_at and run.completed_at:
        elapsed = (run.completed_at-run.started_at).total_seconds()*1000
        if elapsed >= 0:
            wall = int(elapsed)
    return dict(tokens=metrics, source='platform_gateway_ledger' if gateway_authoritative else 'agent_reported' if external else 'adapter' if native else 'not_recorded',
        gateway=gateway, excluded_reported_calls=excluded_reported_calls,
        event_sequences=refs, invalid_observations=invalid,
        calls=[dict(call_id=r['call_id'], kind=r['kind'], phase=r['phase'], completeness=r['completeness'],
            started_sequences=r['started_sequences'], finished_sequences=r['finished_sequences']) for r in rows],
        wall_clock_ms=wall, wall_clock_scope='run_started_to_completed_including_human_wait_and_platform_evaluation',
        human_wait_ms=None, cost=dict(status='pricing_missing', total=None, currency=None),
        limitations=['Known token subtotal is not the complete Run total',
            'No events does not prove zero model usage', 'Preparation/index embedding is outside this scope'])


def compare_resources(comparison, resources):
    result = dict(status='recorded', runs=resources, metrics={},
                  cost=dict(status='pricing_missing', total=None, currency=None))
    eligible = [p for p in comparison['pairs'] if p['classification'] in
                ('improved', 'regressed', 'both_passed', 'both_not_passed')]
    for name in ('total_tokens', 'wall_clock_ms'):
        values = []
        pair_ids = []
        for pair in eligible:
            sides = [resources.get(pair[arm]['run_id']) for arm in ('baseline', 'candidate')]
            counts = [(side['tokens']['total_tokens'] if name == 'total_tokens' else side['wall_clock_ms'])
                      if side else None for side in sides]
            if all(value is not None for value in counts):
                values.append(counts)
                pair_ids.append(dict(case_index=pair['case_index'], repetition=pair['repetition']))
        left = sum(v[0] for v in values)/len(values) if values else None
        right = sum(v[1] for v in values)/len(values) if values else None
        result['metrics'][name] = dict(baseline_mean=left, candidate_mean=right,
            delta=right-left if values else None,
            relative_percent=(right-left)*100/left if values and left else None,
            status='recorded' if values else 'unknown', relative_status='baseline_zero' if values and left == 0 else 'recorded' if values else 'unknown',
            valid_pairs=len(values), eligible_pairs=len(eligible), planned_pairs=comparison['summary']['planned_pairs'],
            coverage=len(values)/len(eligible) if eligible else None, pairs=pair_ids)
    return result
