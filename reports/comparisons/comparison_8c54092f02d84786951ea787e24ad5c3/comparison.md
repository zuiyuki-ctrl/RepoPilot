# RepoPilot 实验逐例对照

| 用例 | Vector | Hybrid | 条件差异 |
|---|---|---|---|
| deduplicate / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |
| statistics / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |
| task-list / v1 | completed / exit=0 | completed / exit=0 | 已记录字段未发现差异；非全面认证 |

## 口径与限制

- 每个配置每例仅一次运行，模型查询可能不同，不能宣称统计显著提升。
- completed + 关联测试进程通过不是对全部需求的自动语义证明；人工审批仍参与流程。
- 未计算通用任务成功率；额外准备失败和未完成记录单列，未知状态不填成功或失败。
- 规划证据快照不等于完整终态轨迹；not_recorded 或缺文件不等于零次检索。
- 未采集的结构化测试计数、token 和成本为 null；不从字符数估算，不比较人工等待耗时。
- 当前可比性只核对已保存用例、测试 hash、预算、镜像标签及超时；镜像 digest、完整生成参数和索引版本不齐，不能认证所有条件一致。

## deduplicate / hybrid / primary

    {
      "experiment_id": "6ce17de7-ad33-4232-bac6-5c1d673d326d",
      "task_id": "a2574e05-f9a8-4257-94b9-c6d4153d4f61",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 31
    }

[preparation](file:///D:/RepoPilot/reports/experiments/deduplicate-hybrid-366bb7283ee54359a0d3809a79ab8e5b/6ce17de7-ad33-4232-bac6-5c1d673d326d/preparation.json)

    sha256: c15a8a7cd5d510d10e03b0257bb98f823ee4aabf724d6a040b01dabef32632e1

[report](file:///D:/RepoPilot/reports/experiments/deduplicate-hybrid-366bb7283ee54359a0d3809a79ab8e5b/6ce17de7-ad33-4232-bac6-5c1d673d326d/operations/d02f3ad3-84c3-4371-8e01-2787faddf321/task_a2574e05-f9a8-4257-94b9-c6d4153d4f61_20261009T032022076141Z.json)

    sha256: b9fa77d85ff1140f11afea5d088eb47fcd1631d93b643acfd091d747cfb26f69

[evidence](file:///D:/RepoPilot/reports/experiments/deduplicate-hybrid-366bb7283ee54359a0d3809a79ab8e5b/6ce17de7-ad33-4232-bac6-5c1d673d326d/evidence/retrieval_a2574e05-f9a8-4257-94b9-c6d4153d4f61_a5e1ea98c4234f7fba9b4cd74715af9f/evidence.json)

    sha256: ac37a09c4a98d6a29fef7faacb40ad6a9b33ecb0b001f3676cd57a70744b728f

测试输出（原文；不将其解析成结构化计数）：

    ......                                                                   [100%]
    6 passed in 0.08s

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
      "completion_event_sequence": 33
    }

[preparation](file:///D:/RepoPilot/reports/experiments/deduplicate-vector-343a16f8da4e459998c7be8a499a0909/a9851347-d41f-40b9-a004-83cb2632f0f9/preparation.json)

    sha256: 9b42682a380c7ce4ed6552da1126e56a09a30f53e1d2a5bd441c996368b80052

[report](file:///D:/RepoPilot/reports/experiments/deduplicate-vector-343a16f8da4e459998c7be8a499a0909/a9851347-d41f-40b9-a004-83cb2632f0f9/operations/3e7d5fb3-7482-4a5a-b699-ca30980516ff/task_6d272d44-74a8-4d1f-b3a0-074f008b5165_20261009T030817215478Z.json)

    sha256: c0ab1a30589a2228655d3ac9182c6b7688bd22cd7dd4b2ebad91a444ef6135a6

[evidence](file:///D:/RepoPilot/reports/experiments/deduplicate-vector-343a16f8da4e459998c7be8a499a0909/a9851347-d41f-40b9-a004-83cb2632f0f9/evidence/retrieval_6d272d44-74a8-4d1f-b3a0-074f008b5165_6b8b89746f19471f844a1abde2c9ac79/evidence.json)

    sha256: e62c5e4e88585e1c92b34c35c1b0c24fb8a66ec707a0b72bcc1650f4b7eba5d7

测试输出（原文；不将其解析成结构化计数）：

    ......                                                                   [100%]
    6 passed in 0.09s

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
      "completion_event_sequence": 31
    }

[preparation](file:///D:/RepoPilot/reports/experiments/statistics-hybrid-a253cbfe46e348f089ebd6837b5b7c1b/b2fb749c-a1f3-4b47-bea3-5b9f96f75091/preparation.json)

    sha256: e77d0d6079be3d931fdd7c90eeefcb11d1da1bde43c540e1756b1295d152f4ff

[report](file:///D:/RepoPilot/reports/experiments/statistics-hybrid-a253cbfe46e348f089ebd6837b5b7c1b/b2fb749c-a1f3-4b47-bea3-5b9f96f75091/operations/82bc1ff5-576b-4d52-9eab-cffbc85add34/task_67540362-f4aa-4d68-b034-d6d640964a27_20261009T131845913217Z.json)

    sha256: d1455347ab1d479e9e84eb75dc4ce28be18defe11202e950e0dc6f6cdaf7078a

[evidence](file:///D:/RepoPilot/reports/experiments/statistics-hybrid-a253cbfe46e348f089ebd6837b5b7c1b/b2fb749c-a1f3-4b47-bea3-5b9f96f75091/evidence/retrieval_67540362-f4aa-4d68-b034-d6d640964a27_ff678e8312ac4f4ba79d83fcaabd135f/evidence.json)

    sha256: d61de7f0be55f2a184128d6d102b7f29587249c95194a32ca4985ad21110f107

测试输出（原文；不将其解析成结构化计数）：

    ............                                                             [100%]
    12 passed in 0.11s

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
      "completion_event_sequence": 31
    }

[preparation](file:///D:/RepoPilot/reports/experiments/statistics-vector-e2ae07c6c8bc41b08725195c8269e988/c35757bb-fee0-45e3-8744-8ee23194fa31/preparation.json)

    sha256: 9806863fddb9d55753e70e66ebebd13821a306b66fabbf9e57d3ae9a6ae446a7

[report](file:///D:/RepoPilot/reports/experiments/statistics-vector-e2ae07c6c8bc41b08725195c8269e988/c35757bb-fee0-45e3-8744-8ee23194fa31/operations/35792bdd-a5b2-4a6f-a6c9-f6e1ec4426c6/task_9532cc66-4349-473d-bdf5-696cbad1a083_20261009T033215561324Z.json)

    sha256: 2c2c5ec3b5935b711e410fca760033ac95eec54507d21985c2184e1857194145

[evidence](file:///D:/RepoPilot/reports/experiments/statistics-vector-e2ae07c6c8bc41b08725195c8269e988/c35757bb-fee0-45e3-8744-8ee23194fa31/evidence/retrieval_9532cc66-4349-473d-bdf5-696cbad1a083_2ff54a4e258a44918e8145ad534968f3/evidence.json)

    sha256: 7fb45916013a6408cf3b9509e161b224997a6274f42c2ac6a2a279361b657d34

测试输出（原文；不将其解析成结构化计数）：

    ............                                                             [100%]
    12 passed in 0.10s

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
      "completion_event_sequence": 25
    }

[preparation](file:///D:/RepoPilot/reports/experiments/1050c45d-458e-41bf-a4d7-cd5ce1f897b2/preparation.json)

    sha256: 10b117a9296faf93822150cdd9da1efc4f5594e4bc44ed2a094f19fddb210208

[report](file:///D:/RepoPilot/reports/experiments/1050c45d-458e-41bf-a4d7-cd5ce1f897b2/operations/16a5aac1-0b7d-46ff-9828-0e904a9103ed/task_f58111a3-4d12-49d9-8d04-665fd512f53a_20261008T123957657305Z.json)

    sha256: 9862bcc0b906b1b17d6b0367b967b71982e3857cf1a0142aa4c378fd85a71401

[evidence](file:///D:/RepoPilot/reports/experiments/1050c45d-458e-41bf-a4d7-cd5ce1f897b2/evidence/retrieval_f58111a3-4d12-49d9-8d04-665fd512f53a_2d426355bc0a47a2bf07a14dabcccf3a/evidence.json)

    sha256: c54e31dd2df58bee514c3dcae625327d2bf70baadb4559a46bc6364d53771c70

测试输出（原文；不将其解析成结构化计数）：

    ........                                                                 [100%]
    8 passed in 0.09s

检索证据：not_recorded


## task-list / hybrid / primary

    {
      "experiment_id": "1d1733ce-fa0c-4590-a548-3eb118acd784",
      "task_id": "1e9054f1-4ac4-4889-a587-81160e5fc4fb",
      "status": "completed",
      "preparation_stage": "create_task",
      "preparation_error_type": null,
      "retry_count": 0,
      "completion_event_sequence": 31
    }

[preparation](file:///D:/RepoPilot/reports/experiments/task-list-hybrid-9e3a2db4a0d7493a9c746e08cb30333e/1d1733ce-fa0c-4590-a548-3eb118acd784/preparation.json)

    sha256: 88cf1c770fb34e68d1116df35a19dd8f077840f23dc1ccc472028dd2341039b4

[report](file:///D:/RepoPilot/reports/experiments/task-list-hybrid-9e3a2db4a0d7493a9c746e08cb30333e/1d1733ce-fa0c-4590-a548-3eb118acd784/operations/936953c5-35fa-41a6-b6f6-461e50260a39/task_1e9054f1-4ac4-4889-a587-81160e5fc4fb_20261008T160743527639Z.json)

    sha256: db62fbe84847734789e0d78b9a35c8a78b07699e50d014da6cc7f5ca6ba5d022

[evidence](file:///D:/RepoPilot/reports/experiments/task-list-hybrid-9e3a2db4a0d7493a9c746e08cb30333e/1d1733ce-fa0c-4590-a548-3eb118acd784/evidence/retrieval_1e9054f1-4ac4-4889-a587-81160e5fc4fb_bf681be097fa48869e9e9287731b3091/evidence.json)

    sha256: a131713d7b2e695631e23634214ab985842150ce2c136174a6af85c7428e3deb

测试输出（原文；不将其解析成结构化计数）：

    ........                                                                 [100%]
    8 passed in 0.09s

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
      "completion_event_sequence": null
    }

[preparation](file:///D:/RepoPilot/reports/experiments/4ee78fc6-f4bb-48d8-a5c6-0e85cc1378a7/preparation.json)

    sha256: bc9f91dffc23973a8220e59020f34d40371552bda60accc107fa342bbb378960

检索证据：未提供


## task-list / vector / additional

    {
      "experiment_id": "d3c43986-e97b-42ca-a631-f599ee76bd4f",
      "task_id": null,
      "status": "preparation_error",
      "preparation_stage": "inspect_workspace",
      "preparation_error_type": "ValueError",
      "retry_count": null,
      "completion_event_sequence": null
    }

[preparation](file:///D:/RepoPilot/reports/experiments/d3c43986-e97b-42ca-a631-f599ee76bd4f/preparation.json)

    sha256: 215af330f3af0ff3c929433caf376c4d0e2ff111d14a2af380f0402852187b50

检索证据：未提供

