"""协议 v1 的观测摘要规则；前端不重算层级，也不把声明当证据。"""
from ..schemas.platform_run import CapabilityEvidence, ObservationSummary

FIELDS = ('execution', 'tests', 'diff', 'model_usage', 'tool_trace',
          'retrieval', 'context', 'planning', 'reflection')
LAYERS = (('L0', FIELDS[:3]), ('L1', FIELDS[3:5]), ('L2', FIELDS[5:]))


def summarize_observation(capabilities: dict) -> ObservationSummary:
    unknown = set(capabilities) - set(FIELDS)
    if unknown:
        raise ValueError('Unknown capability fields')
    fields = {name: CapabilityEvidence.model_validate(capabilities.get(name, {})) for name in FIELDS}

    def covered(name):
        value = fields[name]
        if value.availability != 'available' or not value.evidence_sequences:
            return False
        # 可选阶段未发生，必须有明确记录；不能由缺事件推断。
        if value.occurrence == 'not_occurred':
            return name in ('tool_trace', 'retrieval', 'context', 'planning', 'reflection')
        return (value.occurrence == 'occurred' and value.expected_records is not None
                and value.expected_records > 0 and value.recorded_records == value.expected_records)

    level = 'unknown'
    for label, names in LAYERS:
        if not all(covered(name) for name in names):
            break
        level = label
    # 完整 L0 不等于完整 L2。已声明的更深层能力缺失则摘要仍标 partial。
    complete = level != 'unknown' and all(covered(name) for name, value in fields.items() if value.declared)
    return ObservationSummary(level=level, completeness='complete' if complete else 'partial', capabilities=fields)
