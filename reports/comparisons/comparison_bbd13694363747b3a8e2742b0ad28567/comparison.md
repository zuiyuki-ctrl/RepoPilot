# RepoPilot 实验逐例对照

| 用例 | Vector | Hybrid | 条件差异 |
|---|---|---|---|
| task-list / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |

## 运行条件核对


task-list / repeat=1

    {
      "status": "insufficient_evidence",
      "differences": [],
      "missing": [
        "runtime.provider_internal_version"
      ],
      "note": "相同的已记录条件不代表统计显著、供应商内部版本可复现或自动发布许可"
    }

资源差额（candidate - baseline；准备开销排除、墙钟包含人工等待）：

    {
      "tokens": {
        "baseline": "18014",
        "candidate": "19097",
        "absolute": "1083",
        "relative_percent": "6.011990673920284223381814145",
        "status": "recorded",
        "valid_pairs": 1,
        "coverage": 1.0
      },
      "wall_time_ms": {
        "baseline": "439785",
        "candidate": "430394",
        "absolute": "-9391",
        "relative_percent": "-2.135361597144059028843639506",
        "status": "recorded",
        "valid_pairs": 1,
        "coverage": 1.0
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
        "selected_pairs": 1,
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
      "decision_sha256": "22fa2a3ac8546d7ef7d9dd9be7b2879514699003f1102cf3774b7dfe04740dc2"
    }

## 配对变化（独立验收口径）

| 用例 / 重复 | 分类 | 原因 | 仅测试进程双方通过 |
|---|---|---|---|
| task-list / 1 | undecided | comparability_evidence_insufficient | True |

旧记录双方测试进程通过，不代表新版验收成功；未决与不可比不剔除。

    {
      "primary_pairs": 1,
      "classified_pairs": 0,
      "counts": {
        "stayed_success": 0,
        "improved": 0,
        "regressed": 0,
        "both_not_success": 0,
        "undecided": 1,
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
        "runs": 1,
        "metrics_recorded_runs": 1,
        "started_runs": 1,
        "total_tokens": {
          "mean": 18014.0,
          "valid_runs": 1,
          "coverage": 1.0
        },
        "wall_clock_ms_including_human_wait": {
          "mean": 439785.0,
          "valid_runs": 1,
          "coverage": 1.0
        },
        "start_unknown_runs": 0,
        "acceptance_passed_runs": 1,
        "acceptance_unknown_started_runs": 0,
        "provisional_success_rate": 1.0,
        "final_success_rate": 1.0,
        "structured_test_runs": 1,
        "test_count_coverage": 1.0,
        "test_pass_rate_micro": 1.0,
        "all_reported_tests_passed_ratio": 1.0,
        "test_ratio_note": "仅说明报告中的测试，未证明必需测试未漏跑或需求验收完成"
      },
      "hybrid": {
        "runs": 1,
        "metrics_recorded_runs": 1,
        "started_runs": 1,
        "total_tokens": {
          "mean": 19097.0,
          "valid_runs": 1,
          "coverage": 1.0
        },
        "wall_clock_ms_including_human_wait": {
          "mean": 430394.0,
          "valid_runs": 1,
          "coverage": 1.0
        },
        "start_unknown_runs": 0,
        "acceptance_passed_runs": 1,
        "acceptance_unknown_started_runs": 0,
        "provisional_success_rate": 1.0,
        "final_success_rate": 1.0,
        "structured_test_runs": 1,
        "test_count_coverage": 1.0,
        "test_pass_rate_micro": 1.0,
        "all_reported_tests_passed_ratio": 1.0,
        "test_ratio_note": "仅说明报告中的测试，未证明必需测试未漏跑或需求验收完成"
      }
    }

## task-list / vector / primary

    {
      "experiment_id": "c1a22071-0dac-4998-86bc-923179fbae25",
      "task_id": "302c289e-852f-47af-bdd6-01dfdbef6f8c",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 37,
      "token_usage": {
        "scope_complete": true,
        "observed_calls": 7,
        "known_not_attempted": 0,
        "attempted_calls": 7,
        "unknown_attempt_calls": 0,
        "usage_known_calls": 7,
        "usage_expected_calls": 7,
        "usage_coverage": 1.0,
        "known_total_tokens": 18014,
        "total_tokens": 18014,
        "token_fields": {
          "input_tokens": {
            "known_subtotal": 16416,
            "recorded_calls": 7
          },
          "output_tokens": {
            "known_subtotal": 1598,
            "recorded_calls": 5
          },
          "cached_input_tokens": {
            "known_subtotal": 1024,
            "recorded_calls": 5
          },
          "reasoning_output_tokens": {
            "known_subtotal": 0,
            "recorded_calls": 0
          }
        },
        "request_duration_ms_known_sum": 20145,
        "duration_known_calls": 7,
        "duration_note": "请求耗时之和，不是运行墙钟时间；不累加嵌套工具 span",
        "status": "complete"
      },
      "cost": {
        "kind": "estimate",
        "pricing": null,
        "known_subtotal": null,
        "total": null,
        "priced_calls": 0,
        "unpriced_calls": 0,
        "status": "pricing_missing"
      },
      "acceptance": {
        "outcome": "passed",
        "reason": "declared_test_contract_satisfied",
        "rule_version": "task-list-tests-v1",
        "contract_sha256": "fd8557bdea2fb625166130de811d2ffe2c9daeb56907506dc649c0ab17c5551d",
        "test_run_id": "e6569c5a-da48-400b-b1d5-459e19805de4",
        "report_sha256": "c4904686d2a6b73cdfa4bd6c44c8a534b4973b722f440c5cfd1672716af19767",
        "scope": "predeclared_automated_tests_only"
      },
      "repeat_index": 1,
      "definition": {
        "schema_version": 1,
        "suite_id": "core-platform-pipeline",
        "suite_version": "v1",
        "config_version": "v1",
        "repeat_index": 1,
        "changed_parameter": "retrieval_policy",
        "baseline": "vector",
        "candidate": "hybrid",
        "max_tool_calls": 4,
        "max_retries": 1,
        "test_timeout_seconds": 120,
        "intervention_policy": "approve_generated_candidate_only",
        "acceptance": {
          "version": "task-list-tests-v1",
          "required_tests": [
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-0-expected_ids0]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-1-expected_ids1]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[None-2-1-expected_ids2]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[running-2-0-expected_ids3]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-10-expected_ids4]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_input_is_not_modified"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_invalid_pagination[0-0]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_invalid_pagination[2--1]"
            }
          ],
          "baseline_failure_tests": [
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-0-expected_ids0]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-1-expected_ids1]"
            }
          ],
          "manual_criteria": []
        }
      },
      "preparation_resources": {
        "scope": "preparation_index",
        "resources": {
          "scope_complete": true,
          "observed_calls": 1,
          "known_not_attempted": 0,
          "attempted_calls": 1,
          "unknown_attempt_calls": 0,
          "usage_known_calls": 1,
          "usage_expected_calls": 1,
          "usage_coverage": 1.0,
          "known_total_tokens": 443,
          "total_tokens": 443,
          "token_fields": {
            "input_tokens": {
              "known_subtotal": 443,
              "recorded_calls": 1
            },
            "output_tokens": {
              "known_subtotal": 0,
              "recorded_calls": 0
            },
            "cached_input_tokens": {
              "known_subtotal": 0,
              "recorded_calls": 0
            },
            "reasoning_output_tokens": {
              "known_subtotal": 0,
              "recorded_calls": 0
            }
          },
          "request_duration_ms_known_sum": 1311,
          "duration_known_calls": 1,
          "duration_note": "请求耗时之和，不是运行墙钟时间；不累加嵌套工具 span",
          "status": "complete"
        },
        "cost": {
          "kind": "estimate",
          "pricing": null,
          "known_subtotal": null,
          "total": null,
          "priced_calls": 0,
          "unpriced_calls": 0,
          "status": "pricing_missing"
        }
      }
    }

[preparation](file:///D:/RepoPilot/reports/experiments/day7-task-list-vector-d5d8d3e625f24eba9a1a4e99abda4b11/c1a22071-0dac-4998-86bc-923179fbae25/preparation.json)

    sha256: 61bc6556332152526ad9eb0770664491059d1ca6b2138b7b9caf10a1768eba40

[report](file:///D:/RepoPilot/reports/experiments/day7-task-list-vector-d5d8d3e625f24eba9a1a4e99abda4b11/c1a22071-0dac-4998-86bc-923179fbae25/operations/de08c55b-6746-49df-8341-f46ad25688af/task_302c289e-852f-47af-bdd6-01dfdbef6f8c_20261013T143528729021Z.json)

    sha256: ba97435493b1587193b295733bbbb0baf228538fe34cfcc032070e970838c5c1

[evidence](file:///D:/RepoPilot/reports/experiments/day7-task-list-vector-d5d8d3e625f24eba9a1a4e99abda4b11/c1a22071-0dac-4998-86bc-923179fbae25/evidence/retrieval_302c289e-852f-47af-bdd6-01dfdbef6f8c_b8b063076cf447688f96703b423b4505/evidence.json)

    sha256: 7652b7b3ac9235c06cc0a6fb44086e9ad134108107550133f3258dcb07ce72ea

测试输出（原文；不将其解析成结构化计数）：

    ........                                                                 [100%]
    ----------------- generated xml file: /test-results/junit.xml ------------------
    8 passed in 0.10s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "2064ef289536225061a5bee1fe51bd0b68ed1462fe9534deff5d9e90394e5b3e",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 37,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "e6569c5a-da48-400b-b1d5-459e19805de4",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "6440929c94fcdbb9d29a5876b43471229c1e19eb9edb53185fb27fee3b734fe9",
            "sha256": "d6c77147880d6dcdc5baed2f11eac1af8aeb3ffd1d85935bccd54214e7fbf96c"
          }
        },
        {
          "id": "test_report",
          "source": "report.test_run.test_report",
          "value": {
            "sha256": "c4904686d2a6b73cdfa4bd6c44c8a534b4973b722f440c5cfd1672716af19767",
            "nonpassing_tests": []
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "9836d541f3774b458ad88986297b4db4fc11f1e8e82f04e0cb3da9bed2f36938",
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
            "outcome": "passed",
            "reason": "declared_test_contract_satisfied",
            "rule_version": "task-list-tests-v1",
            "contract_sha256": "fd8557bdea2fb625166130de811d2ffe2c9daeb56907506dc649c0ab17c5551d",
            "test_run_id": "e6569c5a-da48-400b-b1d5-459e19805de4",
            "report_sha256": "c4904686d2a6b73cdfa4bd6c44c8a534b4973b722f440c5cfd1672716af19767",
            "scope": "predeclared_automated_tests_only"
          }
        },
        {
          "id": "retrieval:8",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 8,
            "query": "list_tasks 状态筛选 分页 偏移 ValueError",
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
                "file_id": "2a5f5fb1-b2a7-4c17-a2ef-9af885ccf4e9",
                "chunk_id": "447029fc-1cdb-4dad-806e-6c17e69a5b0b",
                "distance": 0.19652986526489258,
                "end_line": 15,
                "file_hash": null,
                "file_path": "task_list.py",
                "source_id": null,
                "start_line": 1,
                "symbol_name": "list_tasks",
                "content_chars": 450,
                "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f"
              },
              {
                "rank": 2,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "9a233717-8906-450e-ba77-b0727a350b92",
                "distance": 0.2602974772453308,
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 40,
                "symbol_name": "test_invalid_pagination",
                "content_chars": 206,
                "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af"
              },
              {
                "rank": 3,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "c4ede149-8d56-4994-8a2e-d8e869ca8648",
                "distance": 0.28319469489987514,
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 19,
                "symbol_name": "test_filter_and_pagination",
                "content_chars": 475,
                "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90"
              },
              {
                "rank": 4,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "ce374807-b861-4ce6-9e47-afeb669eaf28",
                "distance": 0.3023878751761976,
                "end_line": 37,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "content_chars": 164,
                "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c"
              },
              {
                "rank": 5,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "1e3062a9-e115-4425-9faa-141bb8cf7fe7",
                "distance": 0.38592059780113286,
                "end_line": 16,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 8,
                "symbol_name": "tasks",
                "content_chars": 262,
                "content_sha256": "9e3c87255d878df25093a85bd07a9283227625aaf2d177fc0e2b06a96248e0d5"
              }
            ]
          }
        },
        {
          "id": "retrieval:14",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 14,
            "query": "task_list.py list_tasks pagination offset limit status filter",
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
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "c4ede149-8d56-4994-8a2e-d8e869ca8648",
                "distance": 0.1922932851751541,
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 19,
                "symbol_name": "test_filter_and_pagination",
                "content_chars": 475,
                "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90"
              },
              {
                "rank": 2,
                "file_id": "2a5f5fb1-b2a7-4c17-a2ef-9af885ccf4e9",
                "chunk_id": "447029fc-1cdb-4dad-806e-6c17e69a5b0b",
                "distance": 0.19837979073464207,
                "end_line": 15,
                "file_hash": null,
                "file_path": "task_list.py",
                "source_id": null,
                "start_line": 1,
                "symbol_name": "list_tasks",
                "content_chars": 450,
                "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f"
              },
              {
                "rank": 3,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "9a233717-8906-450e-ba77-b0727a350b92",
                "distance": 0.19873211380040945,
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 40,
                "symbol_name": "test_invalid_pagination",
                "content_chars": 206,
                "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af"
              },
              {
                "rank": 4,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "ce374807-b861-4ce6-9e47-afeb669eaf28",
                "distance": 0.27828290229192376,
                "end_line": 37,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "content_chars": 164,
                "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c"
              },
              {
                "rank": 5,
                "file_id": "ce4ea110-2a7b-4246-9825-ce59f6b5295c",
                "chunk_id": "1e3062a9-e115-4425-9faa-141bb8cf7fe7",
                "distance": 0.3345474599706344,
                "end_line": 16,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "source_id": null,
                "start_line": 8,
                "symbol_name": "tasks",
                "content_chars": 262,
                "content_sha256": "9e3c87255d878df25093a85bd07a9283227625aaf2d177fc0e2b06a96248e0d5"
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
      "missing_evidence": [],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "list_tasks 状态筛选 分页 偏移 ValueError",
      "sequence": 8,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "task_list.py",
          "symbol_name": "list_tasks",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_invalid_pagination",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_filter_and_pagination",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "tasks",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }

    {
      "query": "task_list.py list_tasks pagination offset limit status filter",
      "sequence": 14,
      "diagnostics": null,
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_filter_and_pagination",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "task_list.py",
          "symbol_name": "list_tasks",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_invalid_pagination",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": null,
          "keyword_rank": null
        },
        {
          "rank": 5,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "tasks",
          "vector_rank": null,
          "keyword_rank": null
        }
      ]
    }


## task-list / hybrid / primary

    {
      "experiment_id": "dcc0e13f-d19a-4823-b6b6-93cbca712806",
      "task_id": "1704cb77-8250-4126-825e-034006062975",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 37,
      "token_usage": {
        "scope_complete": true,
        "observed_calls": 7,
        "known_not_attempted": 0,
        "attempted_calls": 7,
        "unknown_attempt_calls": 0,
        "usage_known_calls": 7,
        "usage_expected_calls": 7,
        "usage_coverage": 1.0,
        "known_total_tokens": 19097,
        "total_tokens": 19097,
        "token_fields": {
          "input_tokens": {
            "known_subtotal": 17522,
            "recorded_calls": 7
          },
          "output_tokens": {
            "known_subtotal": 1575,
            "recorded_calls": 5
          },
          "cached_input_tokens": {
            "known_subtotal": 1024,
            "recorded_calls": 5
          },
          "reasoning_output_tokens": {
            "known_subtotal": 0,
            "recorded_calls": 0
          }
        },
        "request_duration_ms_known_sum": 16907,
        "duration_known_calls": 7,
        "duration_note": "请求耗时之和，不是运行墙钟时间；不累加嵌套工具 span",
        "status": "complete"
      },
      "cost": {
        "kind": "estimate",
        "pricing": null,
        "known_subtotal": null,
        "total": null,
        "priced_calls": 0,
        "unpriced_calls": 0,
        "status": "pricing_missing"
      },
      "acceptance": {
        "outcome": "passed",
        "reason": "declared_test_contract_satisfied",
        "rule_version": "task-list-tests-v1",
        "contract_sha256": "c89389ea2b4281674f78505171744f67468f8c62a44cc979ace62e945cf539fd",
        "test_run_id": "d5fac977-10f6-48c5-a0cd-f5dfaa8d83c0",
        "report_sha256": "cf9d4c2d68f5be2cadd6635ca5173e36891b33e527f92fc9ef9ae3d9ce6a9a4c",
        "scope": "predeclared_automated_tests_only"
      },
      "repeat_index": 1,
      "definition": {
        "schema_version": 1,
        "suite_id": "core-platform-pipeline",
        "suite_version": "v1",
        "config_version": "v1",
        "repeat_index": 1,
        "changed_parameter": "retrieval_policy",
        "baseline": "vector",
        "candidate": "hybrid",
        "max_tool_calls": 4,
        "max_retries": 1,
        "test_timeout_seconds": 120,
        "intervention_policy": "approve_generated_candidate_only",
        "acceptance": {
          "version": "task-list-tests-v1",
          "required_tests": [
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-0-expected_ids0]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-1-expected_ids1]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[None-2-1-expected_ids2]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[running-2-0-expected_ids3]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-10-expected_ids4]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_input_is_not_modified"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_invalid_pagination[0-0]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_invalid_pagination[2--1]"
            }
          ],
          "baseline_failure_tests": [
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-0-expected_ids0]"
            },
            {
              "classname": "tests.test_task_list",
              "name": "test_filter_and_pagination[completed-2-1-expected_ids1]"
            }
          ],
          "manual_criteria": []
        }
      },
      "preparation_resources": {
        "scope": "preparation_index",
        "resources": {
          "scope_complete": true,
          "observed_calls": 1,
          "known_not_attempted": 0,
          "attempted_calls": 1,
          "unknown_attempt_calls": 0,
          "usage_known_calls": 1,
          "usage_expected_calls": 1,
          "usage_coverage": 1.0,
          "known_total_tokens": 443,
          "total_tokens": 443,
          "token_fields": {
            "input_tokens": {
              "known_subtotal": 443,
              "recorded_calls": 1
            },
            "output_tokens": {
              "known_subtotal": 0,
              "recorded_calls": 0
            },
            "cached_input_tokens": {
              "known_subtotal": 0,
              "recorded_calls": 0
            },
            "reasoning_output_tokens": {
              "known_subtotal": 0,
              "recorded_calls": 0
            }
          },
          "request_duration_ms_known_sum": 6084,
          "duration_known_calls": 1,
          "duration_note": "请求耗时之和，不是运行墙钟时间；不累加嵌套工具 span",
          "status": "complete"
        },
        "cost": {
          "kind": "estimate",
          "pricing": null,
          "known_subtotal": null,
          "total": null,
          "priced_calls": 0,
          "unpriced_calls": 0,
          "status": "pricing_missing"
        }
      }
    }

[preparation](file:///D:/RepoPilot/reports/experiments/day7-task-list-hybrid-48356c09a8c448edba790d283d384489/dcc0e13f-d19a-4823-b6b6-93cbca712806/preparation.json)

    sha256: ad8cd94823a393b1fcc9da582c731c02b4992618acdfef9844c6f6beb7d64916

[report](file:///D:/RepoPilot/reports/experiments/day7-task-list-hybrid-48356c09a8c448edba790d283d384489/dcc0e13f-d19a-4823-b6b6-93cbca712806/operations/b79c62d7-69a4-4d81-8c24-f92d8bf70ae0/task_1704cb77-8250-4126-825e-034006062975_20261013T143537863460Z.json)

    sha256: 0d5a72eb504880c40ab0ae91f283dddf04c34b7e6899e6949abaad4ab1536f50

[evidence](file:///D:/RepoPilot/reports/experiments/day7-task-list-hybrid-48356c09a8c448edba790d283d384489/dcc0e13f-d19a-4823-b6b6-93cbca712806/evidence/retrieval_1704cb77-8250-4126-825e-034006062975_d2b92408072e47dca6503e38e34b8455/evidence.json)

    sha256: af4acf2cfb8f7d8c906a6c2eb216e3b62e8366923215c761fa3aec64925b70a8

测试输出（原文；不将其解析成结构化计数）：

    ........                                                                 [100%]
    ----------------- generated xml file: /test-results/junit.xml ------------------
    8 passed in 0.11s

失败证据分析（阶段不是根因，人工复核不改变验收）：

    {
      "version": 1,
      "status": "no_failure_observed",
      "analysis_sha256": "2f5a0fb04a70a619bad19eb88bc97b0e5ae8eafe9adf897011c301ed816b727e",
      "termination_stage": "unknown",
      "observed_stages": [],
      "facts": [],
      "evidence": [
        {
          "id": "terminal_event",
          "source": "report.completion_event_sequence",
          "value": {
            "sequence": 37,
            "event_type": "TASK_COMPLETED"
          }
        },
        {
          "id": "final_test",
          "source": "report.test_run",
          "value": {
            "id": "d5fac977-10f6-48c5-a0cd-f5dfaa8d83c0",
            "status": "finished",
            "exit_code": 0,
            "timed_out": false,
            "error": null,
            "snapshot_hash": "18b9edc7f926cd59dbd0de31e427de27d11138df9e9208ebdb04151c4b75b653",
            "sha256": "a1487dc30513e6c6f7797f1b68029e5944e4ad9bf382526cd2554fd7731fa482"
          }
        },
        {
          "id": "test_report",
          "source": "report.test_run.test_report",
          "value": {
            "sha256": "cf9d4c2d68f5be2cadd6635ca5173e36891b33e527f92fc9ef9ae3d9ce6a9a4c",
            "nonpassing_tests": []
          }
        },
        {
          "id": "final_diff",
          "source": "report.final_diff",
          "value": {
            "sha256": "f4536e47dd49ce6e91329c5541be7fe380f1eefc16e77266d4d6adcad89527bc",
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
            "outcome": "passed",
            "reason": "declared_test_contract_satisfied",
            "rule_version": "task-list-tests-v1",
            "contract_sha256": "c89389ea2b4281674f78505171744f67468f8c62a44cc979ace62e945cf539fd",
            "test_run_id": "d5fac977-10f6-48c5-a0cd-f5dfaa8d83c0",
            "report_sha256": "cf9d4c2d68f5be2cadd6635ca5173e36891b33e527f92fc9ef9ae3d9ce6a9a4c",
            "scope": "predeclared_automated_tests_only"
          }
        },
        {
          "id": "retrieval:8",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 8,
            "query": "task_list.py list_tasks 状态筛选 分页",
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
                "file_id": "baef5535-c843-486b-8ca8-098ed408c0f0",
                "chunk_id": "c233a641-d4d0-43e1-90b1-2e74695aae88",
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
                "vector_distance": 0.2511114850971542
              },
              {
                "rank": 2,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "f208843e-8137-4d82-9cad-15c18f478695",
                "end_line": 31,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.016129032258064516,
                "source_id": null,
                "start_line": 19,
                "symbol_name": "test_filter_and_pagination",
                "vector_rank": 2,
                "keyword_rank": null,
                "content_chars": 475,
                "keyword_score": null,
                "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90",
                "vector_distance": 0.3353563748831089
              },
              {
                "rank": 3,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "52be0575-3e36-4a0e-af84-8dee9815039d",
                "end_line": 37,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.015873015873015872,
                "source_id": null,
                "start_line": 34,
                "symbol_name": "test_input_is_not_modified",
                "vector_rank": 3,
                "keyword_rank": null,
                "content_chars": 164,
                "keyword_score": null,
                "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c",
                "vector_distance": 0.3625366281707074
              },
              {
                "rank": 4,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "506345ce-a568-48e6-b4dc-9cc8e088c819",
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.015625,
                "source_id": null,
                "start_line": 40,
                "symbol_name": "test_invalid_pagination",
                "vector_rank": 4,
                "keyword_rank": null,
                "content_chars": 206,
                "keyword_score": null,
                "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af",
                "vector_distance": 0.3630726743660171
              },
              {
                "rank": 5,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "34afa47b-d158-4c8c-a50d-ab65dfcf8c40",
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
                "vector_distance": 0.4062609607343941
              }
            ]
          }
        },
        {
          "id": "retrieval:14",
          "source": "evidence.events.RETRIEVAL_COMPLETED",
          "value": {
            "event_sequence": 14,
            "query": "list_tasks status filter pagination offset limit ValueError",
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
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "506345ce-a568-48e6-b4dc-9cc8e088c819",
                "end_line": 43,
                "file_hash": null,
                "file_path": "tests/test_task_list.py",
                "rrf_score": 0.01639344262295082,
                "source_id": null,
                "start_line": 40,
                "symbol_name": "test_invalid_pagination",
                "vector_rank": 1,
                "keyword_rank": null,
                "content_chars": 206,
                "keyword_score": null,
                "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af",
                "vector_distance": 0.1792607689784982
              },
              {
                "rank": 2,
                "file_id": "baef5535-c843-486b-8ca8-098ed408c0f0",
                "chunk_id": "c233a641-d4d0-43e1-90b1-2e74695aae88",
                "end_line": 15,
                "file_hash": null,
                "file_path": "task_list.py",
                "rrf_score": 0.016129032258064516,
                "source_id": null,
                "start_line": 1,
                "symbol_name": "list_tasks",
                "vector_rank": 2,
                "keyword_rank": null,
                "content_chars": 450,
                "keyword_score": null,
                "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f",
                "vector_distance": 0.18918517956909797
              },
              {
                "rank": 3,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "f208843e-8137-4d82-9cad-15c18f478695",
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
                "vector_distance": 0.23574197292325705
              },
              {
                "rank": 4,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "52be0575-3e36-4a0e-af84-8dee9815039d",
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
                "vector_distance": 0.2859224761863083
              },
              {
                "rank": 5,
                "file_id": "68f75f54-3c15-4979-a971-8c702a195569",
                "chunk_id": "34afa47b-d158-4c8c-a50d-ab65dfcf8c40",
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
                "vector_distance": 0.3798036861887726
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
      "missing_evidence": [],
      "limitations": [
        "测试 failure/error/超时不自动证明基础设施、检索或推理根因",
        "反思诊断是模型假设，不是人工确认；Top K 与候选计数不证明候选被排序排除",
        "只使用保存的历史证据；失败报告缺 Diff 时不读取当前工作区补齐"
      ]
    }

检索证据：recorded

    {
      "query": "task_list.py list_tasks 状态筛选 分页",
      "sequence": 8,
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
          "symbol_name": "test_filter_and_pagination",
          "vector_rank": 2,
          "keyword_rank": null
        },
        {
          "rank": 3,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_input_is_not_modified",
          "vector_rank": 3,
          "keyword_rank": null
        },
        {
          "rank": 4,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_invalid_pagination",
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

    {
      "query": "list_tasks status filter pagination offset limit ValueError",
      "sequence": 14,
      "diagnostics": {
        "overlap_count": 0,
        "vector_candidate_count": 5,
        "final_keyword_hit_count": 0,
        "keyword_candidate_count": 0
      },
      "hits": [
        {
          "rank": 1,
          "file_path": "tests/test_task_list.py",
          "symbol_name": "test_invalid_pagination",
          "vector_rank": 1,
          "keyword_rank": null
        },
        {
          "rank": 2,
          "file_path": "task_list.py",
          "symbol_name": "list_tasks",
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

