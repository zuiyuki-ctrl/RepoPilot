"""Bounded public projection of stored events; never load workspace or raw requests."""
import math
from ..db.session import SessionLocal
from ..db.repositories import platform_run_repo as repo
from ..schemas.platform_run import RunEventRead


def fields(names):
    return dict.fromkeys(names.split())


REFERENCE = fields('chunk_id file_id file_path symbol_name start_line end_line content_sha256 content_chars source_id file_hash rank distance score rrf_score vector_rank keyword_rank vector_distance keyword_score tool_message_index tool_call_id')
USAGE = fields('input_tokens output_tokens total_tokens cached_input_tokens reasoning_output_tokens')
OBSERVATION = {
    **fields('observation_version call_id request_kind request_attempted request_status failure_stage error_type requested_model response_model response_id finish_reason http_status started_at completed_at duration_ms usage_status validation_stage operation_status'),
    'usage': USAGE,
}
DETAIL = {
    **fields('schema_version trace_version protocol_version call_id tool_call_id step_id attempt tool_name duration_ms error_type recoverable allow_tools model response_type tool_call_count arguments_chars scope lifecycle execution_status version stage next_stage cleanup_status error_code writers_stopped checkpoint_id kind payload_sha256 snapshot_hash exit_code timed_out protocol_error trace_status outcome reason evidence_sha256 rule_sha256 run_id event_id content_sha256 content_chars input_tokens output_tokens total_tokens query effective_query top_k requested_strategy retrieval_strategy strategy_overridden hit_count result_scope disposition attempted prepared_result_chars remaining_chars_before reserved_chars remaining_chars_after tool_message_index has_error action remaining_chars available_chars result_chars used_calls max_tool_calls'),
    'model_observation': OBSERVATION,
    'hits': [REFERENCE], 'sources': [REFERENCE], 'tool_context': [REFERENCE],
    'system_prompt_sha256': [None],
    'diagnostics': fields('vector_candidate_count keyword_candidate_count overlap_count final_keyword_hit_count'),
    'retrieval_parameters': fields('embedding_model embedding_dimensions rrf_rank_constant hybrid_candidate_limit index_version'),
    'plan': {**fields('summary'), 'steps': [{**fields('id description verification'), 'files': [None], 'source_ids': [None]}]},
    'decision': {**fields('diagnosis should_retry'), 'actions': [fields('file_path instruction')]},
}


def project(value, shape, flags, budget):
    """Known keys only, bounded strings/lists and total scalar characters per event."""
    if budget[0] <= 0:
        flags.add('truncated')
        return None
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            flags.add('invalid'); return None
        return {key: project(value[key], child, flags, budget)
                for key, child in shape.items() if key in value}
    if isinstance(shape, list):
        if not isinstance(value, list):
            flags.add('invalid'); return None
        if len(value) > 50:
            flags.add('truncated')
        return [project(item, shape[0], flags, budget) for item in value[:50]]
    if isinstance(value, str):
        length = min(2000, budget[0])
        if len(value) > length:
            flags.add('truncated')
        budget[0] -= min(len(value), length)
        return value[:length]
    if value is None or type(value) in (int, bool) or (type(value) is float and math.isfinite(value)):
        budget[0] -= 32
        return value
    flags.add('invalid')
    return None


def trace_event(event):
    result = RunEventRead.model_validate(event).model_dump(mode='json')
    flags = set()
    payload = event.payload
    result.update(legacy_task_id=None, legacy_sequence=None, node_name=None)
    if isinstance(payload, dict) and 'native' in payload:
        wrapper = project(payload, fields('legacy_task_id legacy_sequence node_name'), flags, [1000])
        result.update(wrapper)
        payload = payload['native']
    result['details'] = project(payload, DETAIL, flags, [20000]) or {}
    result['detail_status'] = 'invalid' if 'invalid' in flags else ('projected' if result['details'] else 'metadata_only')
    result['truncated'] = 'truncated' in flags
    # A platform timestamp is ingestion time, not the external Agent occurrence time.
    result['timestamp_semantics'] = 'platform_recorded_at'
    return result


def list_trace(run_id, *, after_sequence=0, limit=50, through_sequence=None):
    if after_sequence < 0 or not 1 <= limit <= 100 or (through_sequence is not None and through_sequence < after_sequence):
        raise ValueError('Invalid trace pagination')
    with SessionLocal() as session:
        run = repo.get_run(session, run_id)
        if run is None:
            return None
        boundary = min(run.event_sequence, through_sequence) if through_sequence is not None else run.event_sequence
        events = repo.list_events(session, run_id, after_sequence=after_sequence, limit=limit,
                                  through_sequence=boundary)
        items = [trace_event(event) for event in events]
        cursor = items[-1]['sequence'] if items else after_sequence
        return dict(items=items, next_after_sequence=cursor, through_sequence=boundary,
                    has_more=bool(items) and cursor < boundary,
                    scope='stored_event_projection', source='live')
