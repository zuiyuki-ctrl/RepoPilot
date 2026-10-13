# RepoPilot 实验逐例对照

| 用例 | Vector | Hybrid | 条件差异 |
|---|---|---|---|
| deduplicate / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |
| statistics / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |
| task-list / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |

## 运行条件核对


deduplicate / repeat=1

    {
      "status": "insufficient_evidence",
      "differences": [],
      "missing": [
        "definition",
        "frozen_contract",
        "index_fingerprint",
        "runtime",
        "runtime.chat_model",
        "runtime.chat_parameters",
        "runtime.context_budget_chars",
        "runtime.embedding_dimensions",
        "runtime.embedding_model",
        "runtime.implementation_sha256",
        "runtime.prompt_templates_sha256",
        "runtime.provider_internal_version",
        "runtime.tool_definitions_sha256",
        "test_image_id"
      ],
      "note": "相同的已记录条件不代表统计显著、供应商内部版本可复现或自动发布许可"
    }

资源差额（candidate - baseline；准备开销排除、墙钟包含人工等待）：

    {
      "tokens": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "missing",
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "wall_time_ms": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "missing",
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "estimated_cost": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "pricing_missing_or_different",
        "currency": null,
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "scope": "task_chat_and_query_embedding; preparation_excluded; wall_time_includes_human_wait",
      "comparison_eligible": false
    }

statistics / repeat=1

    {
      "status": "insufficient_evidence",
      "differences": [],
      "missing": [
        "definition",
        "frozen_contract",
        "index_fingerprint",
        "runtime",
        "runtime.chat_model",
        "runtime.chat_parameters",
        "runtime.context_budget_chars",
        "runtime.embedding_dimensions",
        "runtime.embedding_model",
        "runtime.implementation_sha256",
        "runtime.prompt_templates_sha256",
        "runtime.provider_internal_version",
        "runtime.tool_definitions_sha256",
        "test_image_id"
      ],
      "note": "相同的已记录条件不代表统计显著、供应商内部版本可复现或自动发布许可"
    }

资源差额（candidate - baseline；准备开销排除、墙钟包含人工等待）：

    {
      "tokens": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "missing",
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "wall_time_ms": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "missing",
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "estimated_cost": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "pricing_missing_or_different",
        "currency": null,
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "scope": "task_chat_and_query_embedding; preparation_excluded; wall_time_includes_human_wait",
      "comparison_eligible": false
    }

task-list / repeat=1

    {
      "status": "insufficient_evidence",
      "differences": [],
      "missing": [
        "definition",
        "frozen_contract",
        "index_fingerprint",
        "runtime",
        "runtime.chat_model",
        "runtime.chat_parameters",
        "runtime.context_budget_chars",
        "runtime.embedding_dimensions",
        "runtime.embedding_model",
        "runtime.implementation_sha256",
        "runtime.prompt_templates_sha256",
        "runtime.provider_internal_version",
        "runtime.tool_definitions_sha256",
        "test_image_id"
      ],
      "note": "相同的已记录条件不代表统计显著、供应商内部版本可复现或自动发布许可"
    }

资源差额（candidate - baseline；准备开销排除、墙钟包含人工等待）：

    {
      "tokens": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "missing",
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "wall_time_ms": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "missing",
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "estimated_cost": {
        "baseline": null,
        "candidate": null,
        "absolute": null,
        "relative_percent": null,
        "status": "pricing_missing_or_different",
        "currency": null,
        "valid_pairs": 0,
        "coverage": 0.0
      },
      "scope": "task_chat_and_query_embedding; preparation_excluded; wall_time_includes_human_wait",
      "comparison_eligible": false
    }

## 本批门槛与独立人工采用记录

    {
      "version": 1,
      "verdict": "insufficient_evidence",
      "policy_source": "not_configured",
      "policy": null,
      "checks": [],
      "missing_reasons": [
        "decision_policy_not_configured"
      ],
      "resource_deltas": {
        "tokens": {
          "baseline": null,
          "candidate": null,
          "absolute": null,
          "relative_percent": null,
          "status": "missing",
          "valid_pairs": 0,
          "coverage": 0.0,
          "currency": null,
          "scope": "means_of_same_complete_comparable_started_pairs"
        },
        "estimated_cost": {
          "baseline": null,
          "candidate": null,
          "absolute": null,
          "relative_percent": null,
          "status": "missing",
          "valid_pairs": 0,
          "coverage": 0.0,
          "currency": null,
          "scope": "means_of_same_complete_comparable_started_pairs"
        },
        "wall_time_ms": {
          "baseline": null,
          "candidate": null,
          "absolute": null,
          "relative_percent": null,
          "status": "missing",
          "valid_pairs": 0,
          "coverage": 0.0,
          "currency": null,
          "scope": "means_of_same_complete_comparable_started_pairs"
        }
      },
      "quality": {
        "delta_pp": null,
        "classified_started_pairs": 0,
        "selected_pairs": 3,
        "coverage": 0.0,
        "regressions": 0,
        "scope": "comparable_decided_started_pairs_only_not_whole_batch_success_rate"
      },
      "next_steps": [
        "先补齐冻结条件、验收和启动/资源证据，再按声明批次继续实验。"
      ],
      "limitations": [
        "事后门槛标为探索性，不能追认为预注册验收。",
        "资源差额仅使用同对完整样本；成本是估算，墙钟包含人工等待。",
        "本批符合不证明统计显著或可泛化；不自动采用、发布或推荐 Reranker。"
      ],
      "review": null,
      "decision_sha256": "3217588f8c10b5eae3f23a258a7f85a43037730e3605ceb6f3588edd3c27b9d7"
    }

## 配对变化（独立验收口径）

| 用例 / 重复 | 分类 | 原因 | 仅测试进程双方通过 |
|---|---|---|---|
| deduplicate / 1 | undecided | comparability_evidence_insufficient | True |
| statistics / 1 | undecided | comparability_evidence_insufficient | True |
| task-list / 1 | undecided | comparability_evidence_insufficient | True |

旧记录双方测试进程通过，不代表新版验收成功；未决与不可比不剔除。

    {
      "primary_pairs": 3,
      "classified_pairs": 0,
      "counts": {
        "stayed_success": 0,
        "improved": 0,
        "regressed": 0,
        "both_not_success": 0,
        "undecided": 3,
        "non_comparable": 0
      },
      "classification_coverage": 0.0,
      "scope": "explicit_primary_pairs_only",
      "note": "额外尝试不参与配对统计；未决与不可比保留，不将已判定子集当作批次成功率"
    }

## 口径与限制

- 按预声明 repeat_index 配对；重复运行不选择最好一次，当前样本不足以宣称统计显著提升。
- completed + 关联测试进程通过不是对全部需求的自动语义证明；人工审批仍参与流程。
- 验收结论独立于 completed；缺版本化验收证据为 unknown，成功比例须连同启动边界及覆盖率阅读。
- 规划证据快照不等于完整终态轨迹；not_recorded 或缺文件不等于零次检索。
- 未采集的结构化测试计数、token 和成本为 null；不从字符数估算，不比较人工等待耗时。
- 条件一致仅限已记录输入；旧定义、供应商内部版本或证据缺失为 insufficient_evidence，不能认证全面可复现。

## 指标与覆盖率

    {
      "vector": {
        "runs": 3,
        "metrics_recorded_runs": 0,
        "started_runs": 0,
        "total_tokens": {
          "mean": null,
          "valid_runs": 0,
          "coverage": 0.0
        },
        "wall_clock_ms_including_human_wait": {
          "mean": null,
          "valid_runs": 0,
          "coverage": 0.0
        },
        "start_unknown_runs": 3,
        "acceptance_passed_runs": 0,
        "acceptance_unknown_started_runs": 0,
        "provisional_success_rate": null,
        "final_success_rate": null,
        "structured_test_runs": 0,
        "test_count_coverage": 0.0,
        "test_pass_rate_micro": null,
        "all_reported_tests_passed_ratio": null,
        "test_ratio_note": "仅说明报告中的测试，未证明必需测试未漏跑或需求验收完成"
      },
      "hybrid": {
        "runs": 3,
        "metrics_recorded_runs": 0,
        "started_runs": 0,
        "total_tokens": {
          "mean": null,
          "valid_runs": 0,
          "coverage": 0.0
        },
        "wall_clock_ms_including_human_wait": {
          "mean": null,
          "valid_runs": 0,
          "coverage": 0.0
        },
        "start_unknown_runs": 3,
        "acceptance_passed_runs": 0,
        "acceptance_unknown_started_runs": 0,
        "provisional_success_rate": null,
        "final_success_rate": null,
        "structured_test_runs": 0,
        "test_count_coverage": 0.0,
        "test_pass_rate_micro": null,
        "all_reported_tests_passed_ratio": null,
        "test_ratio_note": "仅说明报告中的测试，未证明必需测试未漏跑或需求验收完成"
      }
    }

## deduplicate / hybrid / primary

    {
      "experiment_id": "6ce17de7-ad33-4232-bac6-5c1d673d326d",
      "task_id": "a2574e05-f9a8-4257-94b9-c6d4153d4f61",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 31,
      "token_usage": null,
      "cost": null,
      "acceptance": {
        "outcome": "unknown",
        "reason": "legacy_definition_missing",
        "rule_version": null
      },
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/deduplicate-hybrid-366bb7283ee54359a0d3809a79ab8e5b/6ce17de7-ad33-4232-bac6-5c1d673d326d/preparation.json)

    sha256: c15a8a7cd5d510d10e03b0257bb98f823ee4aabf724d6a040b01dabef32632e1

[report](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/deduplicate-hybrid-366bb7283ee54359a0d3809a79ab8e5b/6ce17de7-ad33-4232-bac6-5c1d673d326d/operations/d02f3ad3-84c3-4371-8e01-2787faddf321/task_a2574e05-f9a8-4257-94b9-c6d4153d4f61_20261009T032022076141Z.json)

    sha256: b9fa77d85ff1140f11afea5d088eb47fcd1631d93b643acfd091d747cfb26f69

[evidence](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/deduplicate-hybrid-366bb7283ee54359a0d3809a79ab8e5b/6ce17de7-ad33-4232-bac6-5c1d673d326d/evidence/retrieval_a2574e05-f9a8-4257-94b9-c6d4153d4f61_a5e1ea98c4234f7fba9b4cd74715af9f/evidence.json)

    sha256: ac37a09c4a98d6a29fef7faacb40ad6a9b33ecb0b001f3676cd57a70744b728f

测试输出（原文；不将其解析成结构化计数）：

    ......                                                                   [100%]
    6 passed in 0.08s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "64e3ecb8df0382c428076fc3ee6b0692e968fa9b4e77ee432cbea66a3c8149ce",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 31,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "ef9d2f9c-a41b-4e78-92e4-6a526c8c668a",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "89c7adc088146b13eb32f959ca8ad0156cff9ba2589e8ebe74c04d0d0182b1b2",
            "sha256": "1a02ef52589ec9e273ae15b43b233e2f31cc01cd68f9d9d3c30504e8920eb7ce"
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "3744349f8f2beb6bd5eb8fe1100df5bf8041d66cffa63e93bb497b899c5d4abd",
            "changed_files": [
              "deduplicate.py"
            ],
            "untracked_files": [],
            "truncated": false,
            "scope": "terminal_saved_diff_only"
          }
        },
        {
          "id": "acceptance",
          "source": "comparison.acceptance",
          "value": {
            "outcome": "unknown",
            "reason": "legacy_definition_missing",
            "rule_version": null
          }
        },
        {
          "id": "retrieval:6",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 6,
            "query": "deduplicate_by_key",
            "requested_strategy": "hybrid",
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "diagnostics": {
              "overlap_count": 7,
              "vector_candidate_count": 7,
              "final_keyword_hit_count": 5,
              "keyword_candidate_count": 7
            },
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": 60,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": 20
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "6fa5f86d-2279-4eec-bc38-b5a8bffd6257",
                "end_line": 17,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.032018442622950824,
                "source_id": null,
                "start_line": 8,
                "symbol_name": "test_keeps_first_complete_record",
                "vector_rank": 1,
                "keyword_rank": 4,
                "content_chars": 339,
                "keyword_score": 0.1,
                "content_sha256": "51060bf6385ebac47c5d53286735df7c32a2bd1a13ede6860b7763afe230b07e",
                "vector_distance": 0.15722415319753114
              },
              {
                "rank": 2,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "388416c6-0302-4a30-a6cd-7f7fc9807310",
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.03200204813108039,
                "source_id": null,
                "start_line": 41,
                "symbol_name": "test_missing_key_raises",
                "vector_rank": 3,
                "keyword_rank": 2,
                "content_chars": 139,
                "keyword_score": 0.11666667,
                "content_sha256": "96f3fdc996ed04799ab960f42c4690d128b8b6293cc1f86f2db170bbad87e75f",
                "vector_distance": 0.18510536132986433
              },
              {
                "rank": 3,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "5d7cd1c9-7954-4fc4-93c9-a2df6880b09d",
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.03149801587301587,
                "source_id": null,
                "start_line": 25,
                "symbol_name": "test_custom_key_keeps_first_record",
                "vector_rank": 4,
                "keyword_rank": 3,
                "content_chars": 196,
                "keyword_score": 0.10714286,
                "content_sha256": "45966c633d46ab0e922ab89113897dc066d68fb999df71f4fbe0f1fa7d76f221",
                "vector_distance": 0.18648885569042684
              },
              {
                "rank": 4,
                "file_id": "dd0602b1-84ab-49a5-bfd5-bb6b5c535993",
                "chunk_id": "d8eced2e-47b8-4c29-9a86-12f0bec1a075",
                "end_line": 5,
                "file_hash": null,
                "file_path": "deduplicate.py",
                "rrf_score": 0.03131881575727918,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "deduplicate_by_key",
                "vector_rank": 7,
                "keyword_rank": 1,
                "content_chars": 190,
                "keyword_score": 0.3,
                "content_sha256": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135",
                "vector_distance": 0.20019745826721191
              },
              {
                "rank": 5,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "8baeea99-99f3-43dc-bac4-1a39683921b1",
                "end_line": 38,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.031054405392392875,
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "vector_rank": 2,
                "keyword_rank": 7,
                "content_chars": 212,
                "keyword_score": 0.1,
                "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b",
                "vector_distance": 0.1837906727915587
              }
            ]
          }
        },
        {
          "id": "retrieval:10",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 10,
            "query": "deduplicate.py",
            "requested_strategy": "hybrid",
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "diagnostics": {
              "overlap_count": 7,
              "vector_candidate_count": 7,
              "final_keyword_hit_count": 5,
              "keyword_candidate_count": 7
            },
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": 60,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": 20
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "388416c6-0302-4a30-a6cd-7f7fc9807310",
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.032266458495966696,
                "source_id": null,
                "start_line": 41,
                "symbol_name": "test_missing_key_raises",
                "vector_rank": 1,
                "keyword_rank": 3,
                "content_chars": 139,
                "keyword_score": 0.10714286,
                "content_sha256": "96f3fdc996ed04799ab960f42c4690d128b8b6293cc1f86f2db170bbad87e75f",
                "vector_distance": 0.23854728822267524
              },
              {
                "rank": 2,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "394454b9-cbea-4ee7-bd08-18aeea831942",
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.03225806451612903,
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_empty_list",
                "vector_rank": 2,
                "keyword_rank": 2,
                "content_chars": 75,
                "keyword_score": 0.11111111,
                "content_sha256": "c51f5ff695edf1b632acc7a5fc5e0aeca639c11b33bc673c36252a81a678477e",
                "vector_distance": 0.25855944331166647
              },
              {
                "rank": 3,
                "file_id": "dd0602b1-84ab-49a5-bfd5-bb6b5c535993",
                "chunk_id": "d8eced2e-47b8-4c29-9a86-12f0bec1a075",
                "end_line": 5,
                "file_hash": null,
                "file_path": "deduplicate.py",
                "rrf_score": 0.03131881575727918,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "deduplicate_by_key",
                "vector_rank": 7,
                "keyword_rank": 1,
                "content_chars": 190,
                "keyword_score": 0.2,
                "content_sha256": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135",
                "vector_distance": 0.3180930600845542
              },
              {
                "rank": 4,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "8baeea99-99f3-43dc-bac4-1a39683921b1",
                "end_line": 38,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.031024531024531024,
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "vector_rank": 3,
                "keyword_rank": 6,
                "content_chars": 212,
                "keyword_score": 0.10416667,
                "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b",
                "vector_distance": 0.27610889900054425
              },
              {
                "rank": 5,
                "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
                "chunk_id": "12b4e183-dda4-45de-b895-0fd989d16ccf",
                "end_line": 22,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "rrf_score": 0.031009615384615385,
                "source_id": null,
                "start_line": 20,
                "symbol_name": "test_distinct_records_keep_input_order",
                "vector_rank": 5,
                "keyword_rank": 4,
                "content_chars": 157,
                "keyword_score": 0.10454546,
                "content_sha256": "4cbd83d7d5321f14e1bcc6a7e0ce307515aa3cb508ff6b2808eee9afcd58162d",
                "vector_distance": 0.28153703455736534
              }
            ]
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "usable_structured_test_report"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "deduplicate_by_key",
      "sequence": 6,
      "diagnostics": {
        "overlap_count": 7,
        "vector_candidate_count": 7,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 7
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_keeps_first_complete_record",
          "vector_rank": 1,
          "keyword_rank": 4
        },
        {
          "rank": 2,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_missing_key_raises",
          "vector_rank": 3,
          "keyword_rank": 2
        },
        {
          "rank": 3,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_custom_key_keeps_first_record",
          "vector_rank": 4,
          "keyword_rank": 3
        },
        {
          "rank": 4,
          "file_path": "deduplicate.py",
          "symbol_name": "deduplicate_by_key",
          "vector_rank": 7,
          "keyword_rank": 1
        },
        {
          "rank": 5,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": 2,
          "keyword_rank": 7
        }
      ]
    }

    {
      "query": "deduplicate.py",
      "sequence": 10,
      "diagnostics": {
        "overlap_count": 7,
        "vector_candidate_count": 7,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 7
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_missing_key_raises",
          "vector_rank": 1,
          "keyword_rank": 3
        },
        {
          "rank": 2,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_empty_list",
          "vector_rank": 2,
          "keyword_rank": 2
        },
        {
          "rank": 3,
          "file_path": "deduplicate.py",
          "symbol_name": "deduplicate_by_key",
          "vector_rank": 7,
          "keyword_rank": 1
        },
        {
          "rank": 4,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": 3,
          "keyword_rank": 6
        },
        {
          "rank": 5,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_distinct_records_keep_input_order",
          "vector_rank": 5,
          "keyword_rank": 4
        }
      ]
    }


## deduplicate / vector / primary

    {
      "experiment_id": "a9851347-d41f-40b9-a004-83cb2632f0f9",
      "task_id": "6d272d44-74a8-4d1f-b3a0-074f008b5165",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 33,
      "token_usage": null,
      "cost": null,
      "acceptance": {
        "outcome": "unknown",
        "reason": "legacy_definition_missing",
        "rule_version": null
      },
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/deduplicate-vector-343a16f8da4e459998c7be8a499a0909/a9851347-d41f-40b9-a004-83cb2632f0f9/preparation.json)

    sha256: 9b42682a380c7ce4ed6552da1126e56a09a30f53e1d2a5bd441c996368b80052

[report](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/deduplicate-vector-343a16f8da4e459998c7be8a499a0909/a9851347-d41f-40b9-a004-83cb2632f0f9/operations/3e7d5fb3-7482-4a5a-b699-ca30980516ff/task_6d272d44-74a8-4d1f-b3a0-074f008b5165_20261009T030817215478Z.json)

    sha256: c0ab1a30589a2228655d3ac9182c6b7688bd22cd7dd4b2ebad91a444ef6135a6

[evidence](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/deduplicate-vector-343a16f8da4e459998c7be8a499a0909/a9851347-d41f-40b9-a004-83cb2632f0f9/evidence/retrieval_6d272d44-74a8-4d1f-b3a0-074f008b5165_6b8b89746f19471f844a1abde2c9ac79/evidence.json)

    sha256: e62c5e4e88585e1c92b34c35c1b0c24fb8a66ec707a0b72bcc1650f4b7eba5d7

测试输出（原文；不将其解析成结构化计数）：

    ......                                                                   [100%]
    6 passed in 0.09s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "a9a332d0154a0f64946038cced2579681c8b438011aa32b935fcef3f04513ac9",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 33,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "7bba202b-cc52-4eda-a580-f2745c228982",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "3e21b655464ae48529c86c0e705acbda566af96c7909f69efdd175149e1048ce",
            "sha256": "6e286e668077342c3155e49c78769d6182fc279bcd3f6b2b1bd8e79e184f49b6"
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "631a3cd704e1ec4c39907da2fc9319e6e9185ab637f3c8c7a21f6cab8b1e2202",
            "changed_files": [
              "deduplicate.py"
            ],
            "untracked_files": [],
            "truncated": false,
            "scope": "terminal_saved_diff_only"
          }
        },
        {
          "id": "acceptance",
          "source": "comparison.acceptance",
          "value": {
            "outcome": "unknown",
            "reason": "legacy_definition_missing",
            "rule_version": null
          }
        },
        {
          "id": "retrieval:6",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 6,
            "query": "deduplicate_by_key 按指定字段去重 保留第一次出现的记录",
            "requested_strategy": "vector",
            "retrieval_strategy": "vector",
            "top_k": 5,
            "diagnostics": null,
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": null,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": null
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "ec9fc5fe-13b7-4662-a21a-44c8292ccb30",
                "distance": 0.2804933786392161,
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 25,
                "symbol_name": "test_custom_key_keeps_first_record",
                "content_chars": 196,
                "content_sha256": "45966c633d46ab0e922ab89113897dc066d68fb999df71f4fbe0f1fa7d76f221"
              },
              {
                "rank": 2,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "f15a6604-3e28-48db-b673-7161803570d6",
                "distance": 0.2836769223213145,
                "end_line": 22,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 20,
                "symbol_name": "test_distinct_records_keep_input_order",
                "content_chars": 157,
                "content_sha256": "4cbd83d7d5321f14e1bcc6a7e0ce307515aa3cb508ff6b2808eee9afcd58162d"
              },
              {
                "rank": 3,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "fe01cbb5-4ceb-46de-832c-4397547f2342",
                "distance": 0.2866080361552268,
                "end_line": 17,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 8,
                "symbol_name": "test_keeps_first_complete_record",
                "content_chars": 339,
                "content_sha256": "51060bf6385ebac47c5d53286735df7c32a2bd1a13ede6860b7763afe230b07e"
              },
              {
                "rank": 4,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "d0293325-2828-4579-95c9-56b7f6276ce6",
                "distance": 0.29936832189559437,
                "end_line": 38,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "content_chars": 212,
                "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b"
              },
              {
                "rank": 5,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "0e8b9a10-4b80-4c18-bfd2-9b5cfc0d6553",
                "distance": 0.30080127716063954,
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_empty_list",
                "content_chars": 75,
                "content_sha256": "c51f5ff695edf1b632acc7a5fc5e0aeca639c11b33bc673c36252a81a678477e"
              }
            ]
          }
        },
        {
          "id": "retrieval:10",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 10,
            "query": "deduplicate.py",
            "requested_strategy": "vector",
            "retrieval_strategy": "vector",
            "top_k": 5,
            "diagnostics": null,
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": null,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": null
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "807f0018-02ee-4042-851c-ed298dfd1629",
                "distance": 0.23854728822267524,
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 41,
                "symbol_name": "test_missing_key_raises",
                "content_chars": 139,
                "content_sha256": "96f3fdc996ed04799ab960f42c4690d128b8b6293cc1f86f2db170bbad87e75f"
              },
              {
                "rank": 2,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "0e8b9a10-4b80-4c18-bfd2-9b5cfc0d6553",
                "distance": 0.25855944331166647,
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_empty_list",
                "content_chars": 75,
                "content_sha256": "c51f5ff695edf1b632acc7a5fc5e0aeca639c11b33bc673c36252a81a678477e"
              },
              {
                "rank": 3,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "d0293325-2828-4579-95c9-56b7f6276ce6",
                "distance": 0.27610889900054425,
                "end_line": 38,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "content_chars": 212,
                "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b"
              },
              {
                "rank": 4,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "fe01cbb5-4ceb-46de-832c-4397547f2342",
                "distance": 0.28091004859328716,
                "end_line": 17,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 8,
                "symbol_name": "test_keeps_first_complete_record",
                "content_chars": 339,
                "content_sha256": "51060bf6385ebac47c5d53286735df7c32a2bd1a13ede6860b7763afe230b07e"
              },
              {
                "rank": 5,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "f15a6604-3e28-48db-b673-7161803570d6",
                "distance": 0.28153703455736534,
                "end_line": 22,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 20,
                "symbol_name": "test_distinct_records_keep_input_order",
                "content_chars": 157,
                "content_sha256": "4cbd83d7d5321f14e1bcc6a7e0ce307515aa3cb508ff6b2808eee9afcd58162d"
              }
            ]
          }
        },
        {
          "id": "retrieval:16",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 16,
            "query": "def deduplicate_by_key 实现 去重逻辑",
            "requested_strategy": "vector",
            "retrieval_strategy": "vector",
            "top_k": 5,
            "diagnostics": null,
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": null,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": null
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "0e8b9a10-4b80-4c18-bfd2-9b5cfc0d6553",
                "distance": 0.2641547164824761,
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_empty_list",
                "content_chars": 75,
                "content_sha256": "c51f5ff695edf1b632acc7a5fc5e0aeca639c11b33bc673c36252a81a678477e"
              },
              {
                "rank": 2,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "f15a6604-3e28-48db-b673-7161803570d6",
                "distance": 0.2900091832870719,
                "end_line": 22,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 20,
                "symbol_name": "test_distinct_records_keep_input_order",
                "content_chars": 157,
                "content_sha256": "4cbd83d7d5321f14e1bcc6a7e0ce307515aa3cb508ff6b2808eee9afcd58162d"
              },
              {
                "rank": 3,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "ec9fc5fe-13b7-4662-a21a-44c8292ccb30",
                "distance": 0.2998707711773638,
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 25,
                "symbol_name": "test_custom_key_keeps_first_record",
                "content_chars": 196,
                "content_sha256": "45966c633d46ab0e922ab89113897dc066d68fb999df71f4fbe0f1fa7d76f221"
              },
              {
                "rank": 4,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "d0293325-2828-4579-95c9-56b7f6276ce6",
                "distance": 0.3009202897000127,
                "end_line": 38,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "content_chars": 212,
                "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b"
              },
              {
                "rank": 5,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "fe01cbb5-4ceb-46de-832c-4397547f2342",
                "distance": 0.30530581788139965,
                "end_line": 17,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 8,
                "symbol_name": "test_keeps_first_complete_record",
                "content_chars": 339,
                "content_sha256": "51060bf6385ebac47c5d53286735df7c32a2bd1a13ede6860b7763afe230b07e"
              }
            ]
          }
        },
        {
          "id": "retrieval:20",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 20,
            "query": "seen keys dict comprehensions return records",
            "requested_strategy": "vector",
            "retrieval_strategy": "vector",
            "top_k": 5,
            "diagnostics": null,
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": null,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": null
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "ac346efb-48e6-4ea3-a203-6c5111681c49",
                "chunk_id": "a7139957-887d-4656-9083-5fb288a68f38",
                "distance": 0.27695016402303063,
                "end_line": 5,
                "file_hash": null,
                "file_path": "deduplicate.py",
                "source_id": null,
                "start_line": 1,
                "symbol_name": "deduplicate_by_key",
                "content_chars": 190,
                "content_sha256": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135"
              },
              {
                "rank": 2,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "fe01cbb5-4ceb-46de-832c-4397547f2342",
                "distance": 0.3232269488803434,
                "end_line": 17,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 8,
                "symbol_name": "test_keeps_first_complete_record",
                "content_chars": 339,
                "content_sha256": "51060bf6385ebac47c5d53286735df7c32a2bd1a13ede6860b7763afe230b07e"
              },
              {
                "rank": 3,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "f15a6604-3e28-48db-b673-7161803570d6",
                "distance": 0.3259886114610897,
                "end_line": 22,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 20,
                "symbol_name": "test_distinct_records_keep_input_order",
                "content_chars": 157,
                "content_sha256": "4cbd83d7d5321f14e1bcc6a7e0ce307515aa3cb508ff6b2808eee9afcd58162d"
              },
              {
                "rank": 4,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "ec9fc5fe-13b7-4662-a21a-44c8292ccb30",
                "distance": 0.33119495735228566,
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 25,
                "symbol_name": "test_custom_key_keeps_first_record",
                "content_chars": 196,
                "content_sha256": "45966c633d46ab0e922ab89113897dc066d68fb999df71f4fbe0f1fa7d76f221"
              },
              {
                "rank": 5,
                "file_id": "0d2dad9d-02db-4eff-97c9-f5a967c582e7",
                "chunk_id": "d0293325-2828-4579-95c9-56b7f6276ce6",
                "distance": 0.35566278032508136,
                "end_line": 38,
                "file_hash": null,
                "file_path": "tests/test_deduplicate.py",
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "content_chars": 212,
                "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b"
              }
            ]
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "usable_structured_test_report"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "deduplicate_by_key 按指定字段去重 保留第一次出现的记录",
      "sequence": 6,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_custom_key_keeps_first_record",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_distinct_records_keep_input_order",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_keeps_first_complete_record",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_empty_list",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }

    {
      "query": "deduplicate.py",
      "sequence": 10,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_missing_key_raises",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_empty_list",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_keeps_first_complete_record",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_distinct_records_keep_input_order",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }

    {
      "query": "def deduplicate_by_key 实现 去重逻辑",
      "sequence": 16,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_empty_list",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_distinct_records_keep_input_order",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_custom_key_keeps_first_record",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_keeps_first_complete_record",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }

    {
      "query": "seen keys dict comprehensions return records",
      "sequence": 20,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "deduplicate.py",
          "symbol_name": "deduplicate_by_key",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_keeps_first_complete_record",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_distinct_records_keep_input_order",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_custom_key_keeps_first_record",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_deduplicate.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }


## statistics / hybrid / primary

    {
      "experiment_id": "b2fb749c-a1f3-4b47-bea3-5b9f96f75091",
      "task_id": "67540362-f4aa-4d68-b034-d6d640964a27",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 31,
      "token_usage": null,
      "cost": null,
      "acceptance": {
        "outcome": "unknown",
        "reason": "legacy_definition_missing",
        "rule_version": null
      },
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/statistics-hybrid-a253cbfe46e348f089ebd6837b5b7c1b/b2fb749c-a1f3-4b47-bea3-5b9f96f75091/preparation.json)

    sha256: e77d0d6079be3d931fdd7c90eeefcb11d1da1bde43c540e1756b1295d152f4ff

[report](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/statistics-hybrid-a253cbfe46e348f089ebd6837b5b7c1b/b2fb749c-a1f3-4b47-bea3-5b9f96f75091/operations/82bc1ff5-576b-4d52-9eab-cffbc85add34/task_67540362-f4aa-4d68-b034-d6d640964a27_20261009T131845913217Z.json)

    sha256: d1455347ab1d479e9e84eb75dc4ce28be18defe11202e950e0dc6f6cdaf7078a

[evidence](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/statistics-hybrid-a253cbfe46e348f089ebd6837b5b7c1b/b2fb749c-a1f3-4b47-bea3-5b9f96f75091/evidence/retrieval_67540362-f4aa-4d68-b034-d6d640964a27_ff678e8312ac4f4ba79d83fcaabd135f/evidence.json)

    sha256: d61de7f0be55f2a184128d6d102b7f29587249c95194a32ca4985ad21110f107

测试输出（原文；不将其解析成结构化计数）：

    ............                                                             [100%]
    12 passed in 0.11s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "ea512783ac43a10c81f0186fc3784247fa0a46a649ff15c1919992eb18f757df",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 31,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "9e4e2d21-ce67-4a0d-86cc-452a45ce89e0",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "b84bd8b979dee9c010cc05b65acb1f0fd9b23d92e5379e9bf3e60913ade6d7cb",
            "sha256": "d2695cb816d41bbe755637644ecd1e2869386d5ff9cf0e17160e175f961469c3"
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "c4bce0118eb802d7c199b555fa18c39a0b05276e8fd47fb8f9a4c0ff25506644",
            "changed_files": [
              "statistics.py"
            ],
            "untracked_files": [],
            "truncated": false,
            "scope": "terminal_saved_diff_only"
          }
        },
        {
          "id": "acceptance",
          "source": "comparison.acceptance",
          "value": {
            "outcome": "unknown",
            "reason": "legacy_definition_missing",
            "rule_version": null
          }
        },
        {
          "id": "retrieval:6",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 6,
            "query": "summarize_tasks",
            "requested_strategy": "hybrid",
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "diagnostics": {
              "overlap_count": 11,
              "vector_candidate_count": 12,
              "final_keyword_hit_count": 5,
              "keyword_candidate_count": 11
            },
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": 60,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": 20
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "254e95fa-700e-478d-a4bd-387dcf4d0ec2",
                "chunk_id": "5a2aeaf1-45e2-455f-b28b-ca4c62c36bca",
                "end_line": 5,
                "file_hash": null,
                "file_path": "statistics.py",
                "rrf_score": 0.032266458495966696,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "summarize_tasks",
                "vector_rank": 3,
                "keyword_rank": 1,
                "content_chars": 168,
                "keyword_score": 0.25,
                "content_sha256": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d",
                "vector_distance": 0.30969977378845215
              },
              {
                "rank": 2,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "621213b8-e2f9-4424-a0d9-3ba33acc8d42",
                "end_line": 50,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.03225806451612903,
                "source_id": null,
                "start_line": 47,
                "symbol_name": "test_original_input_unchanged",
                "vector_rank": 2,
                "keyword_rank": 2,
                "content_chars": 133,
                "keyword_score": 0.2,
                "content_sha256": "bdc4514fdedf9eb7cec8160f249e7122c10a36a1320c5204a9661aca0c65a3b4",
                "vector_distance": 0.30124926567077637
              },
              {
                "rank": 3,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "bee0798f-455f-4154-b129-3cc6017debce",
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.032018442622950824,
                "source_id": null,
                "start_line": 26,
                "symbol_name": "test_original_behavior",
                "vector_rank": 1,
                "keyword_rank": 4,
                "content_chars": 109,
                "keyword_score": 0.15,
                "content_sha256": "f33f038c7c2103f0e386f563790430f0f262936d6903bf38766af52a7ce17094",
                "vector_distance": 0.28665781021118164
              },
              {
                "rank": 4,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "8c77b6cc-77e9-4c42-898b-9cb07de97874",
                "end_line": 56,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.03149801587301587,
                "source_id": null,
                "start_line": 53,
                "symbol_name": "test_filtered_input_unchanged",
                "vector_rank": 4,
                "keyword_rank": 3,
                "content_chars": 153,
                "keyword_score": 0.2,
                "content_sha256": "6d1e7cab4525ce5a117428d75eb26b06e67e3ef0da7d109f03b0e84a823638c0",
                "vector_distance": 0.3596482276916504
              },
              {
                "rank": 5,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "c398c298-7c11-44a1-a59f-1e833ea5c618",
                "end_line": 40,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.030536130536130537,
                "source_id": null,
                "start_line": 39,
                "symbol_name": "test_empty_original",
                "vector_rank": 5,
                "keyword_rank": 6,
                "content_chars": 97,
                "keyword_score": 0.1,
                "content_sha256": "1d4ae1a44ad66966f51417904754a83a2bbac84ebbd7e54fe9f6e64d16fdb5f2",
                "vector_distance": 0.36578426855159574
              }
            ]
          }
        },
        {
          "id": "retrieval:10",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 10,
            "query": "statistics.py count total_duration",
            "requested_strategy": "hybrid",
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "diagnostics": {
              "overlap_count": 6,
              "vector_candidate_count": 12,
              "final_keyword_hit_count": 5,
              "keyword_candidate_count": 6
            },
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": 60,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": 20
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "c398c298-7c11-44a1-a59f-1e833ea5c618",
                "end_line": 40,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.03252247488101534,
                "source_id": null,
                "start_line": 39,
                "symbol_name": "test_empty_original",
                "vector_rank": 1,
                "keyword_rank": 2,
                "content_chars": 97,
                "keyword_score": 0.008333334,
                "content_sha256": "1d4ae1a44ad66966f51417904754a83a2bbac84ebbd7e54fe9f6e64d16fdb5f2",
                "vector_distance": 0.3866233642883109
              },
              {
                "rank": 2,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "4f21058b-16bd-4f6c-94c3-afecea9996dd",
                "end_line": 36,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.03131881575727918,
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_optional_status",
                "vector_rank": 7,
                "keyword_rank": 1,
                "content_chars": 323,
                "keyword_score": 0.009090909,
                "content_sha256": "b01db22ce858ad77c5a23dbbbb473c3570799c3a27f924dbfaa50b22e32e3b8f",
                "vector_distance": 0.46167859206667994
              },
              {
                "rank": 3,
                "file_id": "254e95fa-700e-478d-a4bd-387dcf4d0ec2",
                "chunk_id": "5a2aeaf1-45e2-455f-b28b-ca4c62c36bca",
                "end_line": 5,
                "file_hash": null,
                "file_path": "statistics.py",
                "rrf_score": 0.03125763125763126,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "summarize_tasks",
                "vector_rank": 5,
                "keyword_rank": 3,
                "content_chars": 168,
                "keyword_score": 0.0076923077,
                "content_sha256": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d",
                "vector_distance": 0.4347325563430786
              },
              {
                "rank": 4,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "bee0798f-455f-4154-b129-3cc6017debce",
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.03125,
                "source_id": null,
                "start_line": 26,
                "symbol_name": "test_original_behavior",
                "vector_rank": 4,
                "keyword_rank": 4,
                "content_chars": 109,
                "keyword_score": 0.007142857,
                "content_sha256": "f33f038c7c2103f0e386f563790430f0f262936d6903bf38766af52a7ce17094",
                "vector_distance": 0.4165268540382385
              },
              {
                "rank": 5,
                "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
                "chunk_id": "6bf566ca-e6d6-4edd-9770-7bb10fd68b0c",
                "end_line": 60,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "rrf_score": 0.030303030303030304,
                "source_id": null,
                "start_line": 59,
                "symbol_name": "test_unfiltered_does_not_require_status",
                "vector_rank": 6,
                "keyword_rank": 6,
                "content_chars": 132,
                "keyword_score": 0.005263158,
                "content_sha256": "91b6f7dcaa81e72695eb488e6fed821482331d3011cb8300b48f5a90953832fa",
                "vector_distance": 0.4385598040485489
              }
            ]
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "usable_structured_test_report"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "summarize_tasks",
      "sequence": 6,
      "diagnostics": {
        "overlap_count": 11,
        "vector_candidate_count": 12,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 11
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "statistics.py",
          "symbol_name": "summarize_tasks",
          "vector_rank": 3,
          "keyword_rank": 1
        },
        {
          "rank": 2,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_original_input_unchanged",
          "vector_rank": 2,
          "keyword_rank": 2
        },
        {
          "rank": 3,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_original_behavior",
          "vector_rank": 1,
          "keyword_rank": 4
        },
        {
          "rank": 4,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_filtered_input_unchanged",
          "vector_rank": 4,
          "keyword_rank": 3
        },
        {
          "rank": 5,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_empty_original",
          "vector_rank": 5,
          "keyword_rank": 6
        }
      ]
    }

    {
      "query": "statistics.py count total_duration",
      "sequence": 10,
      "diagnostics": {
        "overlap_count": 6,
        "vector_candidate_count": 12,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 6
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_empty_original",
          "vector_rank": 1,
          "keyword_rank": 2
        },
        {
          "rank": 2,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_optional_status",
          "vector_rank": 7,
          "keyword_rank": 1
        },
        {
          "rank": 3,
          "file_path": "statistics.py",
          "symbol_name": "summarize_tasks",
          "vector_rank": 5,
          "keyword_rank": 3
        },
        {
          "rank": 4,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_original_behavior",
          "vector_rank": 4,
          "keyword_rank": 4
        },
        {
          "rank": 5,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_unfiltered_does_not_require_status",
          "vector_rank": 6,
          "keyword_rank": 6
        }
      ]
    }


## statistics / vector / primary

    {
      "experiment_id": "c35757bb-fee0-45e3-8744-8ee23194fa31",
      "task_id": "9532cc66-4349-473d-bdf5-696cbad1a083",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 31,
      "token_usage": null,
      "cost": null,
      "acceptance": {
        "outcome": "unknown",
        "reason": "legacy_definition_missing",
        "rule_version": null
      },
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/statistics-vector-e2ae07c6c8bc41b08725195c8269e988/c35757bb-fee0-45e3-8744-8ee23194fa31/preparation.json)

    sha256: 9806863fddb9d55753e70e66ebebd13821a306b66fabbf9e57d3ae9a6ae446a7

[report](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/statistics-vector-e2ae07c6c8bc41b08725195c8269e988/c35757bb-fee0-45e3-8744-8ee23194fa31/operations/35792bdd-a5b2-4a6f-a6c9-f6e1ec4426c6/task_9532cc66-4349-473d-bdf5-696cbad1a083_20261009T033215561324Z.json)

    sha256: 2c2c5ec3b5935b711e410fca760033ac95eec54507d21985c2184e1857194145

[evidence](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/statistics-vector-e2ae07c6c8bc41b08725195c8269e988/c35757bb-fee0-45e3-8744-8ee23194fa31/evidence/retrieval_9532cc66-4349-473d-bdf5-696cbad1a083_2ff54a4e258a44918e8145ad534968f3/evidence.json)

    sha256: 7fb45916013a6408cf3b9509e161b224997a6274f42c2ac6a2a279361b657d34

测试输出（原文；不将其解析成结构化计数）：

    ............                                                             [100%]
    12 passed in 0.10s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "c8bb1388329c40efecc9c0945b2ce99fb852f7309ae16cb41ba512da416dff07",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 31,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "a037537b-c8f5-437e-92b7-3c85cb635489",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "68f2fe0cb1f215ff99daecfa13fb65c302c1c6e9f32d168fc08904988b9dbe0d",
            "sha256": "9cf1a308799276daeb0207c4b3fa272a55e7d36e7dd3359eb0296b6d2b91fcfd"
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "455cf6410d8e5441bbfc29cb74fd870a349aa74128b2ed0c4bc462f2da4cacb1",
            "changed_files": [
              "statistics.py"
            ],
            "untracked_files": [],
            "truncated": false,
            "scope": "terminal_saved_diff_only"
          }
        },
        {
          "id": "acceptance",
          "source": "comparison.acceptance",
          "value": {
            "outcome": "unknown",
            "reason": "legacy_definition_missing",
            "rule_version": null
          }
        },
        {
          "id": "retrieval:6",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 6,
            "query": "summarize_tasks count total_duration",
            "requested_strategy": "vector",
            "retrieval_strategy": "vector",
            "top_k": 5,
            "diagnostics": null,
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": null,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": null
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "eb37cb9a-2715-48cf-a843-d231f395981c",
                "chunk_id": "a8ea7e9b-3ac6-46c2-b82e-add299392d9c",
                "distance": 0.15567421913146973,
                "end_line": 5,
                "file_hash": null,
                "file_path": "statistics.py",
                "source_id": null,
                "start_line": 1,
                "symbol_name": "summarize_tasks",
                "content_chars": 168,
                "content_sha256": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d"
              },
              {
                "rank": 2,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "078b06da-7c09-4cf7-a9d6-c1d98b9d6e6d",
                "distance": 0.1583845615386963,
                "end_line": 27,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 26,
                "symbol_name": "test_original_behavior",
                "content_chars": 109,
                "content_sha256": "f33f038c7c2103f0e386f563790430f0f262936d6903bf38766af52a7ce17094"
              },
              {
                "rank": 3,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "e6ccc6ee-fcdd-4ed1-a4b6-68b2d15b2b6d",
                "distance": 0.1810211891240232,
                "end_line": 40,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 39,
                "symbol_name": "test_empty_original",
                "content_chars": 97,
                "content_sha256": "1d4ae1a44ad66966f51417904754a83a2bbac84ebbd7e54fe9f6e64d16fdb5f2"
              },
              {
                "rank": 4,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "0cedae3a-d1cc-4722-9dd9-24464d8f67c4",
                "distance": 0.2122089989309892,
                "end_line": 36,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_optional_status",
                "content_chars": 323,
                "content_sha256": "b01db22ce858ad77c5a23dbbbb473c3570799c3a27f924dbfaa50b22e32e3b8f"
              },
              {
                "rank": 5,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "a8d30772-5884-4807-b8fc-cc19df8b5e58",
                "distance": 0.21948188543319702,
                "end_line": 65,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 63,
                "symbol_name": "test_missing_duration_still_raises",
                "content_chars": 130,
                "content_sha256": "d7255fe55f813452b86b6bd1e10f2d19411ca183df7545a4d45b316ae0c1d95b"
              }
            ]
          }
        },
        {
          "id": "retrieval:10",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 10,
            "query": "statistics.py task status duration",
            "requested_strategy": "vector",
            "retrieval_strategy": "vector",
            "top_k": 5,
            "diagnostics": null,
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": null,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": null
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "a8d30772-5884-4807-b8fc-cc19df8b5e58",
                "distance": 0.3107264267532268,
                "end_line": 65,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 63,
                "symbol_name": "test_missing_duration_still_raises",
                "content_chars": 130,
                "content_sha256": "d7255fe55f813452b86b6bd1e10f2d19411ca183df7545a4d45b316ae0c1d95b"
              },
              {
                "rank": 2,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "58d20d7e-465f-4618-87a7-e15aa239826f",
                "distance": 0.31585443019865,
                "end_line": 75,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 73,
                "symbol_name": "test_filtered_missing_duration_raises",
                "content_chars": 153,
                "content_sha256": "e7716306f2a8f6045a3f58099518e814780a133d7f6bca8e4f66305eadc96117"
              },
              {
                "rank": 3,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "5111dfe2-ecb6-43bd-91f9-ad0a2d2b0e37",
                "distance": 0.3241249339357125,
                "end_line": 60,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 59,
                "symbol_name": "test_unfiltered_does_not_require_status",
                "content_chars": 132,
                "content_sha256": "91b6f7dcaa81e72695eb488e6fed821482331d3011cb8300b48f5a90953832fa"
              },
              {
                "rank": 4,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "0cedae3a-d1cc-4722-9dd9-24464d8f67c4",
                "distance": 0.32699022728261906,
                "end_line": 36,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 30,
                "symbol_name": "test_optional_status",
                "content_chars": 323,
                "content_sha256": "b01db22ce858ad77c5a23dbbbb473c3570799c3a27f924dbfaa50b22e32e3b8f"
              },
              {
                "rank": 5,
                "file_id": "edfb0051-53d0-43dd-b859-c23a3ed992af",
                "chunk_id": "6824dce4-377e-4dfa-a255-ec0fc4594742",
                "distance": 0.3316939275447066,
                "end_line": 70,
                "file_hash": null,
                "file_path": "tests/test_statistics.py",
                "source_id": null,
                "start_line": 68,
                "symbol_name": "test_filtered_missing_status_raises",
                "content_chars": 143,
                "content_sha256": "cc815fa548d012abc9bfa222cd71cf5b503f0c0afa419cbfa4d5b7062155c199"
              }
            ]
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "usable_structured_test_report"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "summarize_tasks count total_duration",
      "sequence": 6,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "statistics.py",
          "symbol_name": "summarize_tasks",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_original_behavior",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_empty_original",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_optional_status",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_missing_duration_still_raises",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }

    {
      "query": "statistics.py task status duration",
      "sequence": 10,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_missing_duration_still_raises",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_filtered_missing_duration_raises",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_unfiltered_does_not_require_status",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_optional_status",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_statistics.py",
          "symbol_name": "test_filtered_missing_status_raises",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }


## task-list / vector / primary

    {
      "experiment_id": "1050c45d-458e-41bf-a4d7-cd5ce1f897b2",
      "task_id": "f58111a3-4d12-49d9-8d04-665fd512f53a",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 25,
      "token_usage": null,
      "cost": null,
      "acceptance": {
        "outcome": "unknown",
        "reason": "legacy_definition_missing",
        "rule_version": null
      },
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/1050c45d-458e-41bf-a4d7-cd5ce1f897b2/preparation.json)

    sha256: 10b117a9296faf93822150cdd9da1efc4f5594e4bc44ed2a094f19fddb210208

[report](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/1050c45d-458e-41bf-a4d7-cd5ce1f897b2/operations/16a5aac1-0b7d-46ff-9828-0e904a9103ed/task_f58111a3-4d12-49d9-8d04-665fd512f53a_20261008T123957657305Z.json)

    sha256: 9862bcc0b906b1b17d6b0367b967b71982e3857cf1a0142aa4c378fd85a71401

[evidence](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/1050c45d-458e-41bf-a4d7-cd5ce1f897b2/evidence/retrieval_f58111a3-4d12-49d9-8d04-665fd512f53a_2d426355bc0a47a2bf07a14dabcccf3a/evidence.json)

    sha256: c54e31dd2df58bee514c3dcae625327d2bf70baadb4559a46bc6364d53771c70

测试输出（原文；不将其解析成结构化计数）：

    ........                                                                 [100%]
    8 passed in 0.09s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "7cd30e69a4af426a3916aeaae3cfc15ce39d0c0090644f11e0df87db50155db3",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 25,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "54a99c2d-aaa0-4364-871f-89efc2fdf319",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "171c70a0dd6bb66a2022a54a20ee2ecb53293ddec106b32f41c841589abd0cd3",
            "sha256": "508ed1cc36b7557e5dab6dd3739a7e65a6281399a25a8e0c12525d3497eb3eab"
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "55ef7278e72afa9988a4584e9a3301bd6a3f5eadc0900290fcf9eb4bd6c2214b",
            "changed_files": [
              "task_list.py"
            ],
            "untracked_files": [],
            "truncated": false,
            "scope": "terminal_saved_diff_only"
          }
        },
        {
          "id": "acceptance",
          "source": "comparison.acceptance",
          "value": {
            "outcome": "unknown",
            "reason": "legacy_definition_missing",
            "rule_version": null
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "usable_structured_test_report",
        "retrieval_trace"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：not_recorded


## task-list / hybrid / primary

    {
      "experiment_id": "1d1733ce-fa0c-4590-a548-3eb118acd784",
      "task_id": "1e9054f1-4ac4-4889-a587-81160e5fc4fb",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 31,
      "token_usage": null,
      "cost": null,
      "acceptance": {
        "outcome": "unknown",
        "reason": "legacy_definition_missing",
        "rule_version": null
      },
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/task-list-hybrid-9e3a2db4a0d7493a9c746e08cb30333e/1d1733ce-fa0c-4590-a548-3eb118acd784/preparation.json)

    sha256: 88cf1c770fb34e68d1116df35a19dd8f077840f23dc1ccc472028dd2341039b4

[report](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/task-list-hybrid-9e3a2db4a0d7493a9c746e08cb30333e/1d1733ce-fa0c-4590-a548-3eb118acd784/operations/936953c5-35fa-41a6-b6f6-461e50260a39/task_1e9054f1-4ac4-4889-a587-81160e5fc4fb_20261008T160743527639Z.json)

    sha256: db62fbe84847734789e0d78b9a35c8a78b07699e50d014da6cc7f5ca6ba5d022

[evidence](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/task-list-hybrid-9e3a2db4a0d7493a9c746e08cb30333e/1d1733ce-fa0c-4590-a548-3eb118acd784/evidence/retrieval_1e9054f1-4ac4-4889-a587-81160e5fc4fb_bf681be097fa48869e9e9287731b3091/evidence.json)

    sha256: a131713d7b2e695631e23634214ab985842150ce2c136174a6af85c7428e3deb

测试输出（原文；不将其解析成结构化计数）：

    ........                                                                 [100%]
    8 passed in 0.09s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "2fb60c7e60da01c3dd292a5c159f18c03b645662cacb8633bb6c172e3cd7429c",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 31,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "3b9a844d-1623-46c2-9184-4ada45d81394",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "a62303ad559fe3e63b81adb8c245d191da5b80b511689d444045df83760ffee2",
            "sha256": "983aa5f90e82664debcf6a4b441b8486ed9c7d351e4c2ddc46bea556cb1b2ba5"
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "e91f2db9288e700df81b028112647b48838a911e743cc39103d4511479179fa4",
            "changed_files": [
              "task_list.py"
            ],
            "untracked_files": [],
            "truncated": false,
            "scope": "terminal_saved_diff_only"
          }
        },
        {
          "id": "acceptance",
          "source": "comparison.acceptance",
          "value": {
            "outcome": "unknown",
            "reason": "legacy_definition_missing",
            "rule_version": null
          }
        },
        {
          "id": "retrieval:6",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 6,
            "query": "list_tasks",
            "requested_strategy": "hybrid",
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "diagnostics": {
              "overlap_count": 5,
              "vector_candidate_count": 5,
              "final_keyword_hit_count": 5,
              "keyword_candidate_count": 5
            },
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": 60,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": 20
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "8b0d84df-acc6-4933-b875-92d202b81fed",
                "chunk_id": "f1781bbf-1d6c-4c0b-8837-a74db0804808",
                "end_line": 15,
                "file_hash": null,
                "file_path": "task_list.py",
                "rrf_score": 0.03278688524590164,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "list_tasks",
                "vector_rank": 1,
                "keyword_rank": 1,
                "content_chars": 450,
                "keyword_score": 0.35384616,
                "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f",
                "vector_distance": 0.35721328003485564
              },
              {
                "rank": 2,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "e95d2ad1-68e7-4ae9-884e-67c61e42b91b",
                "end_line": 37,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.03225806451612903,
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "vector_rank": 2,
                "keyword_rank": 2,
                "content_chars": 164,
                "keyword_score": 0.20769231,
                "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c",
                "vector_distance": 0.41709768772124833
              },
              {
                "rank": 3,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "eb88f0ce-ceed-4442-a006-f1462b1f41db",
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.03149801587301587,
                "source_id": null,
                "start_line": 19,
                "symbol_name": "test_filter_and_pagination",
                "vector_rank": 3,
                "keyword_rank": 4,
                "content_chars": 475,
                "keyword_score": 0.11678571,
                "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90",
                "vector_distance": 0.4334232986134219
              },
              {
                "rank": 4,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "28fc1986-098c-4e28-bbd4-1a0cb4577a26",
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.03125763125763126,
                "source_id": null,
                "start_line": 40,
                "symbol_name": "test_invalid_pagination",
                "vector_rank": 5,
                "keyword_rank": 3,
                "content_chars": 206,
                "keyword_score": 0.11984127,
                "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af",
                "vector_distance": 0.4489562779042877
              },
              {
                "rank": 5,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "90c6c8d7-8408-4c70-85ab-25acf105c075",
                "end_line": 16,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.031009615384615385,
                "source_id": null,
                "start_line": 8,
                "symbol_name": "tasks",
                "vector_rank": 4,
                "keyword_rank": 5,
                "content_chars": 262,
                "keyword_score": 0.05,
                "content_sha256": "9e3c87255d878df25093a85bd07a9283227625aaf2d177fc0e2b06a96248e0d5",
                "vector_distance": 0.4392340517500518
              }
            ]
          }
        },
        {
          "id": "retrieval:10",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 10,
            "query": "task_list.py 分页 offset limit ValueError",
            "requested_strategy": "hybrid",
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "diagnostics": {
              "overlap_count": 0,
              "vector_candidate_count": 5,
              "final_keyword_hit_count": 0,
              "keyword_candidate_count": 0
            },
            "retrieval_parameters": {
              "index_version": null,
              "embedding_model": "text-embedding-v4",
              "rrf_rank_constant": 60,
              "embedding_dimensions": 1024,
              "hybrid_candidate_limit": 20
            },
            "hits": [
              {
                "rank": 1,
                "file_id": "8b0d84df-acc6-4933-b875-92d202b81fed",
                "chunk_id": "f1781bbf-1d6c-4c0b-8837-a74db0804808",
                "end_line": 15,
                "file_hash": null,
                "file_path": "task_list.py",
                "rrf_score": 0.01639344262295082,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "list_tasks",
                "vector_rank": 1,
                "keyword_rank": null,
                "content_chars": 450,
                "keyword_score": null,
                "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f",
                "vector_distance": 0.18582607423222364
              },
              {
                "rank": 2,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "28fc1986-098c-4e28-bbd4-1a0cb4577a26",
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.016129032258064516,
                "source_id": null,
                "start_line": 40,
                "symbol_name": "test_invalid_pagination",
                "vector_rank": 2,
                "keyword_rank": null,
                "content_chars": 206,
                "keyword_score": null,
                "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af",
                "vector_distance": 0.18897707396608887
              },
              {
                "rank": 3,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "eb88f0ce-ceed-4442-a006-f1462b1f41db",
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.015873015873015872,
                "source_id": null,
                "start_line": 19,
                "symbol_name": "test_filter_and_pagination",
                "vector_rank": 3,
                "keyword_rank": null,
                "content_chars": 475,
                "keyword_score": null,
                "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90",
                "vector_distance": 0.29840552182296187
              },
              {
                "rank": 4,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "e95d2ad1-68e7-4ae9-884e-67c61e42b91b",
                "end_line": 37,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.015625,
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "vector_rank": 4,
                "keyword_rank": null,
                "content_chars": 164,
                "keyword_score": null,
                "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c",
                "vector_distance": 0.33873033523559104
              },
              {
                "rank": 5,
                "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
                "chunk_id": "90c6c8d7-8408-4c70-85ab-25acf105c075",
                "end_line": 16,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.015384615384615385,
                "source_id": null,
                "start_line": 8,
                "symbol_name": "tasks",
                "vector_rank": 5,
                "keyword_rank": null,
                "content_chars": 262,
                "keyword_score": null,
                "content_sha256": "9e3c87255d878df25093a85bd07a9283227625aaf2d177fc0e2b06a96248e0d5",
                "vector_distance": 0.416087721819408
              }
            ]
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "usable_structured_test_report"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "list_tasks",
      "sequence": 6,
      "diagnostics": {
        "overlap_count": 5,
        "vector_candidate_count": 5,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 5
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "task_list.py",
          "symbol_name": "list_tasks",
          "vector_rank": 1,
          "keyword_rank": 1
        },
        {
          "rank": 2,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": 2,
          "keyword_rank": 2
        },
        {
          "rank": 3,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_filter_and_pagination",
          "vector_rank": 3,
          "keyword_rank": 4
        },
        {
          "rank": 4,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_invalid_pagination",
          "vector_rank": 5,
          "keyword_rank": 3
        },
        {
          "rank": 5,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "tasks",
          "vector_rank": 4,
          "keyword_rank": 5
        }
      ]
    }

    {
      "query": "task_list.py 分页 offset limit ValueError",
      "sequence": 10,
      "diagnostics": {
        "overlap_count": 0,
        "vector_candidate_count": 5,
        "final_keyword_hit_count": 0,
        "keyword_candidate_count": 0
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "task_list.py",
          "symbol_name": "list_tasks",
          "vector_rank": 1,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_invalid_pagination",
          "vector_rank": 2,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_filter_and_pagination",
          "vector_rank": 3,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": 4,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "tasks",
          "vector_rank": 5,
          "keyword_rank": null
        }
      ]
    }


## task-list / vector / additional

    {
      "experiment_id": "4ee78fc6-f4bb-48d8-a5c6-0e85cc1378a7",
      "task_id": null,
      "status": "preparation_incomplete",
      "preparation_stage": "register_repository",
      "preparation_error_type": null,
      "retry_count": null,
      "completion_event_sequence": null,
      "token_usage": null,
      "cost": null,
      "acceptance": null,
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/4ee78fc6-f4bb-48d8-a5c6-0e85cc1378a7/preparation.json)

    sha256: bc9f91dffc23973a8220e59020f34d40371552bda60accc107fa342bbb378960

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "evidence_incomplete",
      "analysis_sha256": "e5c0e102d797b5a497d80a9eb1c514c02c8e06846232fa9e6c5ca566be8d64ff",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "preparation",
          "source": "preparation",
          "value": {
            "stage": "register_repository",
            "status": "preparing",
            "error_type": null
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "not_requested",
      "review": null,
      "missing_evidence": [
        "final_test",
        "terminal_saved_diff",
        "terminal_event",
        "retrieval_trace"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：未提供


## task-list / vector / additional

    {
      "experiment_id": "d3c43986-e97b-42ca-a631-f599ee76bd4f",
      "task_id": null,
      "status": "preparation_error",
      "preparation_stage": "inspect_workspace",
      "preparation_error_type": "ValueError",
      "retry_count": null,
      "completion_event_sequence": null,
      "token_usage": null,
      "cost": null,
      "acceptance": null,
      "repeat_index": 1,
      "definition": null,
      "preparation_resources": null
    }

[preparation](file:///C:/Users/sai_zuisei/RepoPilot/reports/experiments/d3c43986-e97b-42ca-a631-f599ee76bd4f/preparation.json)

    sha256: 215af330f3af0ff3c929433caf376c4d0e2ff111d14a2af380f0402852187b50

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "failure_observed",
      "analysis_sha256": "fe679a263beb4bbfdd6ddf315fe6f5e06262b509dd93f68e0b5d14f7846d87f0",
      "termination_stage": "preparation",
      "observed_stages": [
        "preparation"
      ],
      "facts": [
        {
          "kind": "preparation_failed",
          "evidence_ids": [
            "preparation"
          ]
        }
      ],
      "evidence": [
        {
          "id": "preparation",
          "source": "preparation",
          "value": {
            "stage": "inspect_workspace",
            "status": "error",
            "error_type": "ValueError"
          }
        }
      ],
      "primary_category": "UNKNOWN",
      "secondary_categories": [],
      "source": "rule",
      "classification_scope": "termination_reason_not_proven_root_cause",
      "root_cause_status": "unknown",
      "hypotheses": [],
      "review_status": "unreviewed",
      "review": null,
      "missing_evidence": [
        "final_test",
        "terminal_saved_diff",
        "terminal_event",
        "retrieval_trace"
      ],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：未提供

