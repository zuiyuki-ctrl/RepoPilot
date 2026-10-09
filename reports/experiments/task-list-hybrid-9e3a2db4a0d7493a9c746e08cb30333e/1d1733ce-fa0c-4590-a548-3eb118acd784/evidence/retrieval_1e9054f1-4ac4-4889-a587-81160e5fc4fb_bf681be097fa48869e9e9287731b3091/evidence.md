# 检索与工具上下文证据

- 任务 ID：1e9054f1-4ac4-4889-a587-81160e5fc4fb
- 证据状态：已记录
- 读取事件数：25；末尾序号：25

这是读取时可见事件的快照；运行中的任务可能继续追加事件。
模型调用成功不等于模型语义上采纳了证据；hash 不能独自重建源码。

实验关联：

    {
      "experiment_id": "1d1733ce-fa0c-4590-a548-3eb118acd784",
      "case_id": "task-list",
      "case_version": "v1",
      "repository_commit": "4629a3a98cb62c989ed4e1e67be9514703b3d346"
    }

读取事件前的任务状态与配置快照：

    {
      "id": "1e9054f1-4ac4-4889-a587-81160e5fc4fb",
      "repository_id": "3e42f873-e95b-4881-a3d2-ad36b4d396d2",
      "status": "awaiting_review",
      "run_config": {
        "schema_version": 1,
        "retrieval_policy": "hybrid",
        "max_tool_calls": 4
      }
    }


## 工具调用 1


    {
      "call_id": "0f4854c6-763b-4423-8038-c432c5f8bf6c",
      "tool_call_id": "call_56aaa318efa949d28f89b649",
      "tool_name": "search_code",
      "event_sequences": [
        4,
        5,
        6,
        7
      ]
    }

检索事件序号：6；结果范围为工具返回 Top-K。

    {
      "query": "list_tasks",
      "effective_query": "list_tasks",
      "requested_strategy": "hybrid",
      "retrieval_strategy": "hybrid",
      "top_k": 5,
      "retrieval_parameters": {
        "index_version": null,
        "embedding_model": "text-embedding-v4",
        "rrf_rank_constant": 60,
        "embedding_dimensions": 1024,
        "hybrid_candidate_limit": 20
      },
      "diagnostics": {
        "overlap_count": 5,
        "vector_candidate_count": 5,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 5
      }
    }

返回 5 条命中，以下保持原顺序：

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
    }


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
    }


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
    }


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
    }


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

预算后消息事件序号：7

    {
      "attempt": 1,
      "call_id": "0f4854c6-763b-4423-8038-c432c5f8bf6c",
      "sources": [
        {
          "file_id": "8b0d84df-acc6-4933-b875-92d202b81fed",
          "chunk_id": "f1781bbf-1d6c-4c0b-8837-a74db0804808",
          "end_line": 15,
          "file_hash": null,
          "file_path": "task_list.py",
          "source_id": "S1",
          "start_line": 1,
          "symbol_name": "list_tasks",
          "content_chars": 450,
          "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "e95d2ad1-68e7-4ae9-884e-67c61e42b91b",
          "end_line": 37,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S2",
          "start_line": 34,
          "symbol_name": "test_input_is_not_modified",
          "content_chars": 164,
          "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "eb88f0ce-ceed-4442-a006-f1462b1f41db",
          "end_line": 31,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S3",
          "start_line": 19,
          "symbol_name": "test_filter_and_pagination",
          "content_chars": 475,
          "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "28fc1986-098c-4e28-bbd4-1a0cb4577a26",
          "end_line": 43,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S4",
          "start_line": 40,
          "symbol_name": "test_invalid_pagination",
          "content_chars": 206,
          "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "90c6c8d7-8408-4c70-85ab-25acf105c075",
          "end_line": 16,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S5",
          "start_line": 8,
          "symbol_name": "tasks",
          "content_chars": 262,
          "content_sha256": "9e3c87255d878df25093a85bd07a9283227625aaf2d177fc0e2b06a96248e0d5"
        }
      ],
      "step_id": "tools",
      "sequence": 7,
      "attempted": true,
      "has_error": false,
      "tool_name": "search_code",
      "disposition": "accepted",
      "tool_call_id": "call_56aaa318efa949d28f89b649",
      "content_chars": 4267,
      "trace_version": 1,
      "content_sha256": "887f275ecbae7a0dcf18816d2660b58f136e606af371312057a22108c062b5a4",
      "reserved_chars": 34,
      "schema_version": 1,
      "tool_message_index": 0,
      "prepared_result_chars": 4267,
      "remaining_chars_after": 35733,
      "remaining_chars_before": 40000
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "e046ac6e-fefa-4242-ba85-8ec875517e9e",
        "node_name": "model",
        "started_sequence": 12,
        "finished_sequence": 13,
        "outcome": "completed"
      },
      {
        "call_id": "8013ad74-d512-4031-965a-4a53f47e6a9f",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "927e8640-b4d8-4ec0-9093-1c3b2309dd4c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 2


    {
      "call_id": "353c049b-3fe6-495d-b53a-f164210326db",
      "tool_call_id": "call_efca363e5e4a4bd5a4bc0dc0",
      "tool_name": "search_code",
      "event_sequences": [
        8,
        9,
        10,
        11
      ]
    }

检索事件序号：10；结果范围为工具返回 Top-K。

    {
      "query": "task_list.py 分页 offset limit ValueError",
      "effective_query": "task_list.py 分页 offset limit ValueError",
      "requested_strategy": "hybrid",
      "retrieval_strategy": "hybrid",
      "top_k": 5,
      "retrieval_parameters": {
        "index_version": null,
        "embedding_model": "text-embedding-v4",
        "rrf_rank_constant": 60,
        "embedding_dimensions": 1024,
        "hybrid_candidate_limit": 20
      },
      "diagnostics": {
        "overlap_count": 0,
        "vector_candidate_count": 5,
        "final_keyword_hit_count": 0,
        "keyword_candidate_count": 0
      }
    }

返回 5 条命中，以下保持原顺序：

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
    }


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
    }


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
    }


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
    }


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

预算后消息事件序号：11

    {
      "attempt": 1,
      "call_id": "353c049b-3fe6-495d-b53a-f164210326db",
      "sources": [
        {
          "file_id": "8b0d84df-acc6-4933-b875-92d202b81fed",
          "chunk_id": "f1781bbf-1d6c-4c0b-8837-a74db0804808",
          "end_line": 15,
          "file_hash": null,
          "file_path": "task_list.py",
          "source_id": "S6",
          "start_line": 1,
          "symbol_name": "list_tasks",
          "content_chars": 450,
          "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "28fc1986-098c-4e28-bbd4-1a0cb4577a26",
          "end_line": 43,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S7",
          "start_line": 40,
          "symbol_name": "test_invalid_pagination",
          "content_chars": 206,
          "content_sha256": "ff7e2b76d265e77cbd26df327d250daea03154b189248b0921269b51523291af"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "eb88f0ce-ceed-4442-a006-f1462b1f41db",
          "end_line": 31,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S8",
          "start_line": 19,
          "symbol_name": "test_filter_and_pagination",
          "content_chars": 475,
          "content_sha256": "360e78fec35888e0e28466c644dc35939cfbcdf2e4bd4d56d0b63342f64f4b90"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "e95d2ad1-68e7-4ae9-884e-67c61e42b91b",
          "end_line": 37,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S9",
          "start_line": 34,
          "symbol_name": "test_input_is_not_modified",
          "content_chars": 164,
          "content_sha256": "a4224c95ccc009f0cde6486e44f217af0aedbc5e1821b9e676e1434ad069c25c"
        },
        {
          "file_id": "b1fc5e27-e141-419a-a378-2da43f59bead",
          "chunk_id": "90c6c8d7-8408-4c70-85ab-25acf105c075",
          "end_line": 16,
          "file_hash": null,
          "file_path": "tests/test_task_list.py",
          "source_id": "S10",
          "start_line": 8,
          "symbol_name": "tasks",
          "content_chars": 262,
          "content_sha256": "9e3c87255d878df25093a85bd07a9283227625aaf2d177fc0e2b06a96248e0d5"
        }
      ],
      "step_id": "tools",
      "sequence": 11,
      "attempted": true,
      "has_error": false,
      "tool_name": "search_code",
      "disposition": "accepted",
      "tool_call_id": "call_efca363e5e4a4bd5a4bc0dc0",
      "content_chars": 4251,
      "trace_version": 1,
      "content_sha256": "c1c3bab3de27c18a9788549befdca2e6fdaab8628b5a3f9eb31e0a10d596ed41",
      "reserved_chars": 0,
      "schema_version": 1,
      "tool_message_index": 1,
      "prepared_result_chars": 4251,
      "remaining_chars_after": 31482,
      "remaining_chars_before": 35733
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "e046ac6e-fefa-4242-ba85-8ec875517e9e",
        "node_name": "model",
        "started_sequence": 12,
        "finished_sequence": 13,
        "outcome": "completed"
      },
      {
        "call_id": "8013ad74-d512-4031-965a-4a53f47e6a9f",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "927e8640-b4d8-4ec0-9093-1c3b2309dd4c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 3


    {
      "call_id": "c4eb59b8-8626-4522-bd43-2b3415006384",
      "tool_call_id": "call_c2efabae615249ce9212ad4f",
      "tool_name": "read_source",
      "event_sequences": [
        14,
        15,
        16
      ]
    }

检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。
预算后消息事件序号：16

    {
      "attempt": 1,
      "call_id": "c4eb59b8-8626-4522-bd43-2b3415006384",
      "sources": [
        {
          "file_id": null,
          "chunk_id": null,
          "end_line": 15,
          "file_hash": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f",
          "file_path": "task_list.py",
          "source_id": "S11",
          "start_line": 1,
          "symbol_name": null,
          "content_chars": 450,
          "content_sha256": "2bcc1a76ad665ab96ec71789ff24baae6db9d98464e1abb6a7e9283a4d37aa5f"
        }
      ],
      "step_id": "tools",
      "sequence": 16,
      "attempted": true,
      "has_error": false,
      "tool_name": "read_source",
      "disposition": "accepted",
      "tool_call_id": "call_c2efabae615249ce9212ad4f",
      "content_chars": 744,
      "trace_version": 1,
      "content_sha256": "b02bd3b13ddb782c2bfeeba080555c31828ecb71ecfeb1b9565eac5d72b3b3e3",
      "reserved_chars": 34,
      "schema_version": 1,
      "tool_message_index": 2,
      "prepared_result_chars": 744,
      "remaining_chars_after": 30738,
      "remaining_chars_before": 31482
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "8013ad74-d512-4031-965a-4a53f47e6a9f",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "927e8640-b4d8-4ec0-9093-1c3b2309dd4c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 4


    {
      "call_id": "c90c21a1-4663-4298-930f-c1edee8c4169",
      "tool_call_id": "call_9bc37570c9444bb5acc7294f",
      "tool_name": "read_source",
      "event_sequences": [
        17,
        18,
        19
      ]
    }

检索结果摘要：未记录（源码读取、跳过或失败也可能没有检索事件）。
预算后消息事件序号：19

    {
      "attempt": 1,
      "call_id": "c90c21a1-4663-4298-930f-c1edee8c4169",
      "sources": [
        {
          "file_id": null,
          "chunk_id": null,
          "end_line": 43,
          "file_hash": "82dc949554c0a262566d7cdcee6ee21b272ab6468381213633916a36e8f94552",
          "file_path": "tests/test_task_list.py",
          "source_id": "S12",
          "start_line": 1,
          "symbol_name": null,
          "content_chars": 1203,
          "content_sha256": "82dc949554c0a262566d7cdcee6ee21b272ab6468381213633916a36e8f94552"
        }
      ],
      "step_id": "tools",
      "sequence": 19,
      "attempted": true,
      "has_error": false,
      "tool_name": "read_source",
      "disposition": "accepted",
      "tool_call_id": "call_9bc37570c9444bb5acc7294f",
      "content_chars": 1600,
      "trace_version": 1,
      "content_sha256": "c4d9335a3f245805d377d535400fdf7f5b9a2e0810aee81f2876adaed6e00960",
      "reserved_chars": 0,
      "schema_version": 1,
      "tool_message_index": 3,
      "prepared_result_chars": 1600,
      "remaining_chars_after": 29138,
      "remaining_chars_before": 30738
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "8013ad74-d512-4031-965a-4a53f47e6a9f",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "927e8640-b4d8-4ec0-9093-1c3b2309dd4c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 模型调用清单


    {
      "call_id": "a17eef72-d9a4-44d2-a4ca-175d72cef3b0",
      "node_name": "model",
      "started_sequence": 2,
      "finished_sequence": 3,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "e046ac6e-fefa-4242-ba85-8ec875517e9e",
      "node_name": "model",
      "started_sequence": 12,
      "finished_sequence": 13,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "8013ad74-d512-4031-965a-4a53f47e6a9f",
      "node_name": "model",
      "started_sequence": 20,
      "finished_sequence": 21,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "927e8640-b4d8-4ec0-9093-1c3b2309dd4c",
      "node_name": "plan",
      "started_sequence": 22,
      "finished_sequence": 23,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }

