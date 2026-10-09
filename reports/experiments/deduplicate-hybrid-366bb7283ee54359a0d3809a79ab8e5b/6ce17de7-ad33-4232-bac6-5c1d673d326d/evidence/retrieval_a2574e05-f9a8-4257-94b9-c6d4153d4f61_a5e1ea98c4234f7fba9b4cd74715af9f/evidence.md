# 检索与工具上下文证据

- 任务 ID：a2574e05-f9a8-4257-94b9-c6d4153d4f61
- 证据状态：已记录
- 读取事件数：25；末尾序号：25

这是读取时可见事件的快照；运行中的任务可能继续追加事件。
模型调用成功不等于模型语义上采纳了证据；hash 不能独自重建源码。

实验关联：

    {
      "experiment_id": "6ce17de7-ad33-4232-bac6-5c1d673d326d",
      "case_id": "deduplicate",
      "case_version": "v1",
      "repository_commit": "38093c2aca961bcaebbffcd864fc1859844829fd"
    }

读取事件前的任务状态与配置快照：

    {
      "id": "a2574e05-f9a8-4257-94b9-c6d4153d4f61",
      "repository_id": "45e1d17d-bab1-44ef-b053-b268f67c27f9",
      "status": "awaiting_review",
      "run_config": {
        "schema_version": 1,
        "retrieval_policy": "hybrid",
        "max_tool_calls": 4
      }
    }


## 工具调用 1


    {
      "call_id": "0903d25b-f1d1-4c23-ab0f-cf2034da9d3c",
      "tool_call_id": "call_156e63a85f6a4f55b6003948",
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
      "query": "deduplicate_by_key",
      "effective_query": "deduplicate_by_key",
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
        "overlap_count": 7,
        "vector_candidate_count": 7,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 7
      }
    }

返回 5 条命中，以下保持原顺序：

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
    }


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
    }


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
    }


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
    }


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

预算后消息事件序号：7

    {
      "attempt": 1,
      "call_id": "0903d25b-f1d1-4c23-ab0f-cf2034da9d3c",
      "sources": [
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "6fa5f86d-2279-4eec-bc38-b5a8bffd6257",
          "end_line": 17,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S1",
          "start_line": 8,
          "symbol_name": "test_keeps_first_complete_record",
          "content_chars": 339,
          "content_sha256": "51060bf6385ebac47c5d53286735df7c32a2bd1a13ede6860b7763afe230b07e"
        },
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "388416c6-0302-4a30-a6cd-7f7fc9807310",
          "end_line": 43,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S2",
          "start_line": 41,
          "symbol_name": "test_missing_key_raises",
          "content_chars": 139,
          "content_sha256": "96f3fdc996ed04799ab960f42c4690d128b8b6293cc1f86f2db170bbad87e75f"
        },
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "5d7cd1c9-7954-4fc4-93c9-a2df6880b09d",
          "end_line": 27,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S3",
          "start_line": 25,
          "symbol_name": "test_custom_key_keeps_first_record",
          "content_chars": 196,
          "content_sha256": "45966c633d46ab0e922ab89113897dc066d68fb999df71f4fbe0f1fa7d76f221"
        },
        {
          "file_id": "dd0602b1-84ab-49a5-bfd5-bb6b5c535993",
          "chunk_id": "d8eced2e-47b8-4c29-9a86-12f0bec1a075",
          "end_line": 5,
          "file_hash": null,
          "file_path": "deduplicate.py",
          "source_id": "S4",
          "start_line": 1,
          "symbol_name": "deduplicate_by_key",
          "content_chars": 190,
          "content_sha256": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135"
        },
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "8baeea99-99f3-43dc-bac4-1a39683921b1",
          "end_line": 38,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S5",
          "start_line": 34,
          "symbol_name": "test_input_is_not_modified",
          "content_chars": 212,
          "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b"
        }
      ],
      "step_id": "tools",
      "sequence": 7,
      "attempted": true,
      "has_error": false,
      "tool_name": "search_code",
      "disposition": "accepted",
      "tool_call_id": "call_156e63a85f6a4f55b6003948",
      "content_chars": 3810,
      "trace_version": 1,
      "content_sha256": "1d495436ad9e6d515affa0346828ea8da5f851c0abd151ce107099eb16e0581a",
      "reserved_chars": 34,
      "schema_version": 1,
      "tool_message_index": 0,
      "prepared_result_chars": 3810,
      "remaining_chars_after": 36190,
      "remaining_chars_before": 40000
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "88268e5b-3d80-4984-88c1-c6d44c338946",
        "node_name": "model",
        "started_sequence": 12,
        "finished_sequence": 13,
        "outcome": "completed"
      },
      {
        "call_id": "1c51f955-0ea2-4216-9a65-2f9e529fc36a",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "84f875a6-2eda-4d8c-a64e-456326f06059",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 2


    {
      "call_id": "d4d6f305-0794-4cd4-a12a-3597169388ac",
      "tool_call_id": "call_babe6cc4897e4e6eaea1d338",
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
      "query": "deduplicate.py",
      "effective_query": "deduplicate.py",
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
        "overlap_count": 7,
        "vector_candidate_count": 7,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 7
      }
    }

返回 5 条命中，以下保持原顺序：

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
    }


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
    }


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
    }


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
    }


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

预算后消息事件序号：11

    {
      "attempt": 1,
      "call_id": "d4d6f305-0794-4cd4-a12a-3597169388ac",
      "sources": [
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "388416c6-0302-4a30-a6cd-7f7fc9807310",
          "end_line": 43,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S6",
          "start_line": 41,
          "symbol_name": "test_missing_key_raises",
          "content_chars": 139,
          "content_sha256": "96f3fdc996ed04799ab960f42c4690d128b8b6293cc1f86f2db170bbad87e75f"
        },
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "394454b9-cbea-4ee7-bd08-18aeea831942",
          "end_line": 31,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S7",
          "start_line": 30,
          "symbol_name": "test_empty_list",
          "content_chars": 75,
          "content_sha256": "c51f5ff695edf1b632acc7a5fc5e0aeca639c11b33bc673c36252a81a678477e"
        },
        {
          "file_id": "dd0602b1-84ab-49a5-bfd5-bb6b5c535993",
          "chunk_id": "d8eced2e-47b8-4c29-9a86-12f0bec1a075",
          "end_line": 5,
          "file_hash": null,
          "file_path": "deduplicate.py",
          "source_id": "S8",
          "start_line": 1,
          "symbol_name": "deduplicate_by_key",
          "content_chars": 190,
          "content_sha256": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135"
        },
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "8baeea99-99f3-43dc-bac4-1a39683921b1",
          "end_line": 38,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S9",
          "start_line": 34,
          "symbol_name": "test_input_is_not_modified",
          "content_chars": 212,
          "content_sha256": "ab8c84ec910dc0e70bb0d7b0869b715765dba5ed43dc29f51b256ea8625f441b"
        },
        {
          "file_id": "891b8973-2094-4c25-b02c-4e5e0d86ccb7",
          "chunk_id": "12b4e183-dda4-45de-b895-0fd989d16ccf",
          "end_line": 22,
          "file_hash": null,
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S10",
          "start_line": 20,
          "symbol_name": "test_distinct_records_keep_input_order",
          "content_chars": 157,
          "content_sha256": "4cbd83d7d5321f14e1bcc6a7e0ce307515aa3cb508ff6b2808eee9afcd58162d"
        }
      ],
      "step_id": "tools",
      "sequence": 11,
      "attempted": true,
      "has_error": false,
      "tool_name": "search_code",
      "disposition": "accepted",
      "tool_call_id": "call_babe6cc4897e4e6eaea1d338",
      "content_chars": 3449,
      "trace_version": 1,
      "content_sha256": "cd3dc79c65b1db52bbb972518ff379253bd7c098be0dcf5f5f369503dd348d5d",
      "reserved_chars": 0,
      "schema_version": 1,
      "tool_message_index": 1,
      "prepared_result_chars": 3449,
      "remaining_chars_after": 32741,
      "remaining_chars_before": 36190
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "88268e5b-3d80-4984-88c1-c6d44c338946",
        "node_name": "model",
        "started_sequence": 12,
        "finished_sequence": 13,
        "outcome": "completed"
      },
      {
        "call_id": "1c51f955-0ea2-4216-9a65-2f9e529fc36a",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "84f875a6-2eda-4d8c-a64e-456326f06059",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 3


    {
      "call_id": "457cbc2d-468c-41a7-b819-ef433a9d86e6",
      "tool_call_id": "call_fe913673fa8c4ba7bb89e2f2",
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
      "call_id": "457cbc2d-468c-41a7-b819-ef433a9d86e6",
      "sources": [
        {
          "file_id": null,
          "chunk_id": null,
          "end_line": 5,
          "file_hash": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135",
          "file_path": "deduplicate.py",
          "source_id": "S11",
          "start_line": 1,
          "symbol_name": null,
          "content_chars": 190,
          "content_sha256": "24d6a2501a91b044a14a9db0fdbe34614318b7a560231e3be7a46c3558150135"
        }
      ],
      "step_id": "tools",
      "sequence": 16,
      "attempted": true,
      "has_error": false,
      "tool_name": "read_source",
      "disposition": "accepted",
      "tool_call_id": "call_fe913673fa8c4ba7bb89e2f2",
      "content_chars": 454,
      "trace_version": 1,
      "content_sha256": "142f0ccc5419ad1b3c9d3375b2b439546e696b569077175db4febcf3b946383f",
      "reserved_chars": 34,
      "schema_version": 1,
      "tool_message_index": 2,
      "prepared_result_chars": 454,
      "remaining_chars_after": 32287,
      "remaining_chars_before": 32741
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "1c51f955-0ea2-4216-9a65-2f9e529fc36a",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "84f875a6-2eda-4d8c-a64e-456326f06059",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 4


    {
      "call_id": "6a0ec822-0995-415a-b5db-f82055f8212b",
      "tool_call_id": "call_4156be09161e46d9891ccb00",
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
      "call_id": "6a0ec822-0995-415a-b5db-f82055f8212b",
      "sources": [
        {
          "file_id": null,
          "chunk_id": null,
          "end_line": 43,
          "file_hash": "cbc9724b0faa9ccb8bae8dcc562f7b40b2728cbc3eeb6a2e9c68f3d1de5cafdb",
          "file_path": "tests/test_deduplicate.py",
          "source_id": "S12",
          "start_line": 1,
          "symbol_name": null,
          "content_chars": 1232,
          "content_sha256": "cbc9724b0faa9ccb8bae8dcc562f7b40b2728cbc3eeb6a2e9c68f3d1de5cafdb"
        }
      ],
      "step_id": "tools",
      "sequence": 19,
      "attempted": true,
      "has_error": false,
      "tool_name": "read_source",
      "disposition": "accepted",
      "tool_call_id": "call_4156be09161e46d9891ccb00",
      "content_chars": 1673,
      "trace_version": 1,
      "content_sha256": "959b06e5cf39bd91bfc126561f75eaba575afd3ff7a52d6482cace78c8ed0bb1",
      "reserved_chars": 0,
      "schema_version": 1,
      "tool_message_index": 3,
      "prepared_result_chars": 1673,
      "remaining_chars_after": 30614,
      "remaining_chars_before": 32287
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "1c51f955-0ea2-4216-9a65-2f9e529fc36a",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "84f875a6-2eda-4d8c-a64e-456326f06059",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 模型调用清单


    {
      "call_id": "8d1ead53-2b82-4f77-9f51-877c37a05788",
      "node_name": "model",
      "started_sequence": 2,
      "finished_sequence": 3,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "88268e5b-3d80-4984-88c1-c6d44c338946",
      "node_name": "model",
      "started_sequence": 12,
      "finished_sequence": 13,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "1c51f955-0ea2-4216-9a65-2f9e529fc36a",
      "node_name": "model",
      "started_sequence": 20,
      "finished_sequence": 21,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "84f875a6-2eda-4d8c-a64e-456326f06059",
      "node_name": "plan",
      "started_sequence": 22,
      "finished_sequence": 23,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }

