# 检索与工具上下文证据

- 任务 ID：67540362-f4aa-4d68-b034-d6d640964a27
- 证据状态：已记录
- 读取事件数：25；末尾序号：25

这是读取时可见事件的快照；运行中的任务可能继续追加事件。
模型调用成功不等于模型语义上采纳了证据；hash 不能独自重建源码。

实验关联：

    {
      "experiment_id": "b2fb749c-a1f3-4b47-bea3-5b9f96f75091",
      "case_id": "statistics",
      "case_version": "v1",
      "repository_commit": "2890105ac01d778cb853c033ad34d839f5f8dfd7"
    }

读取事件前的任务状态与配置快照：

    {
      "id": "67540362-f4aa-4d68-b034-d6d640964a27",
      "repository_id": "caafaee0-3662-45da-80db-112a1881a8c1",
      "status": "awaiting_review",
      "run_config": {
        "schema_version": 1,
        "retrieval_policy": "hybrid",
        "max_tool_calls": 4
      }
    }


## 工具调用 1


    {
      "call_id": "a60b2ef1-3bce-4a71-85cd-1ee07e8bffae",
      "tool_call_id": "call_936cf63563a940b383033520",
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
      "query": "summarize_tasks",
      "effective_query": "summarize_tasks",
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
        "overlap_count": 11,
        "vector_candidate_count": 12,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 11
      }
    }

返回 5 条命中，以下保持原顺序：

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
    }


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
    }


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
    }


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
    }


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

预算后消息事件序号：7

    {
      "attempt": 1,
      "call_id": "a60b2ef1-3bce-4a71-85cd-1ee07e8bffae",
      "sources": [
        {
          "file_id": "254e95fa-700e-478d-a4bd-387dcf4d0ec2",
          "chunk_id": "5a2aeaf1-45e2-455f-b28b-ca4c62c36bca",
          "end_line": 5,
          "file_hash": null,
          "file_path": "statistics.py",
          "source_id": "S1",
          "start_line": 1,
          "symbol_name": "summarize_tasks",
          "content_chars": 168,
          "content_sha256": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "621213b8-e2f9-4424-a0d9-3ba33acc8d42",
          "end_line": 50,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S2",
          "start_line": 47,
          "symbol_name": "test_original_input_unchanged",
          "content_chars": 133,
          "content_sha256": "bdc4514fdedf9eb7cec8160f249e7122c10a36a1320c5204a9661aca0c65a3b4"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "bee0798f-455f-4154-b129-3cc6017debce",
          "end_line": 27,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S3",
          "start_line": 26,
          "symbol_name": "test_original_behavior",
          "content_chars": 109,
          "content_sha256": "f33f038c7c2103f0e386f563790430f0f262936d6903bf38766af52a7ce17094"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "8c77b6cc-77e9-4c42-898b-9cb07de97874",
          "end_line": 56,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S4",
          "start_line": 53,
          "symbol_name": "test_filtered_input_unchanged",
          "content_chars": 153,
          "content_sha256": "6d1e7cab4525ce5a117428d75eb26b06e67e3ef0da7d109f03b0e84a823638c0"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "c398c298-7c11-44a1-a59f-1e833ea5c618",
          "end_line": 40,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S5",
          "start_line": 39,
          "symbol_name": "test_empty_original",
          "content_chars": 97,
          "content_sha256": "1d4ae1a44ad66966f51417904754a83a2bbac84ebbd7e54fe9f6e64d16fdb5f2"
        }
      ],
      "step_id": "tools",
      "sequence": 7,
      "attempted": true,
      "has_error": false,
      "tool_name": "search_code",
      "disposition": "accepted",
      "tool_call_id": "call_936cf63563a940b383033520",
      "content_chars": 3283,
      "trace_version": 1,
      "content_sha256": "09abe863794377cad8397f9a14d7fbbc3d1bc19489b5ad435c0f22cb29cc8c0b",
      "reserved_chars": 34,
      "schema_version": 1,
      "tool_message_index": 0,
      "prepared_result_chars": 3283,
      "remaining_chars_after": 36717,
      "remaining_chars_before": 40000
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "2b28342f-f858-4650-8643-bbc4c890b576",
        "node_name": "model",
        "started_sequence": 12,
        "finished_sequence": 13,
        "outcome": "completed"
      },
      {
        "call_id": "42c034fb-32e6-4f2b-be73-2074a2e9d5f9",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "ffb4583b-2169-49e3-889f-934da758222c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 2


    {
      "call_id": "b9d9c8f3-e93c-450d-8fce-ce49805fa2e8",
      "tool_call_id": "call_80ef39dcaa164f9fb1035795",
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
      "query": "statistics.py count total_duration",
      "effective_query": "statistics.py count total_duration",
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
        "overlap_count": 6,
        "vector_candidate_count": 12,
        "final_keyword_hit_count": 5,
        "keyword_candidate_count": 6
      }
    }

返回 5 条命中，以下保持原顺序：

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
    }


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
    }


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
    }


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
    }


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

预算后消息事件序号：11

    {
      "attempt": 1,
      "call_id": "b9d9c8f3-e93c-450d-8fce-ce49805fa2e8",
      "sources": [
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "c398c298-7c11-44a1-a59f-1e833ea5c618",
          "end_line": 40,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S6",
          "start_line": 39,
          "symbol_name": "test_empty_original",
          "content_chars": 97,
          "content_sha256": "1d4ae1a44ad66966f51417904754a83a2bbac84ebbd7e54fe9f6e64d16fdb5f2"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "4f21058b-16bd-4f6c-94c3-afecea9996dd",
          "end_line": 36,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S7",
          "start_line": 30,
          "symbol_name": "test_optional_status",
          "content_chars": 323,
          "content_sha256": "b01db22ce858ad77c5a23dbbbb473c3570799c3a27f924dbfaa50b22e32e3b8f"
        },
        {
          "file_id": "254e95fa-700e-478d-a4bd-387dcf4d0ec2",
          "chunk_id": "5a2aeaf1-45e2-455f-b28b-ca4c62c36bca",
          "end_line": 5,
          "file_hash": null,
          "file_path": "statistics.py",
          "source_id": "S8",
          "start_line": 1,
          "symbol_name": "summarize_tasks",
          "content_chars": 168,
          "content_sha256": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "bee0798f-455f-4154-b129-3cc6017debce",
          "end_line": 27,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S9",
          "start_line": 26,
          "symbol_name": "test_original_behavior",
          "content_chars": 109,
          "content_sha256": "f33f038c7c2103f0e386f563790430f0f262936d6903bf38766af52a7ce17094"
        },
        {
          "file_id": "582cba19-f8d5-41fa-83bb-3c32966da4b7",
          "chunk_id": "6bf566ca-e6d6-4edd-9770-7bb10fd68b0c",
          "end_line": 60,
          "file_hash": null,
          "file_path": "tests/test_statistics.py",
          "source_id": "S10",
          "start_line": 59,
          "symbol_name": "test_unfiltered_does_not_require_status",
          "content_chars": 132,
          "content_sha256": "91b6f7dcaa81e72695eb488e6fed821482331d3011cb8300b48f5a90953832fa"
        }
      ],
      "step_id": "tools",
      "sequence": 11,
      "attempted": true,
      "has_error": false,
      "tool_name": "search_code",
      "disposition": "accepted",
      "tool_call_id": "call_80ef39dcaa164f9fb1035795",
      "content_chars": 3498,
      "trace_version": 1,
      "content_sha256": "9d463653af417570b032892c9dc806178d7ed8095a83edcf5ae0bd20223f43d0",
      "reserved_chars": 0,
      "schema_version": 1,
      "tool_message_index": 1,
      "prepared_result_chars": 3498,
      "remaining_chars_after": 33219,
      "remaining_chars_before": 36717
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "2b28342f-f858-4650-8643-bbc4c890b576",
        "node_name": "model",
        "started_sequence": 12,
        "finished_sequence": 13,
        "outcome": "completed"
      },
      {
        "call_id": "42c034fb-32e6-4f2b-be73-2074a2e9d5f9",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "ffb4583b-2169-49e3-889f-934da758222c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 3


    {
      "call_id": "11334a60-6b3e-4504-b7c1-16e3a5ec6d63",
      "tool_call_id": "call_b3832580ef254667b10a23e1",
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
      "call_id": "11334a60-6b3e-4504-b7c1-16e3a5ec6d63",
      "sources": [
        {
          "file_id": null,
          "chunk_id": null,
          "end_line": 60,
          "file_hash": "8b46db49f3963c0ea465765aed3f7a2b0e662c3af467d92715b15abc12b90340",
          "file_path": "tests/test_statistics.py",
          "source_id": "S11",
          "start_line": 1,
          "symbol_name": null,
          "content_chars": 1682,
          "content_sha256": "22a9b736452df13033cc6fe03896d811901c9d28fd706ec716eaa02d7144b34c"
        }
      ],
      "step_id": "tools",
      "sequence": 16,
      "attempted": true,
      "has_error": false,
      "tool_name": "read_source",
      "disposition": "accepted",
      "tool_call_id": "call_b3832580ef254667b10a23e1",
      "content_chars": 2130,
      "trace_version": 1,
      "content_sha256": "6fb82916d46ed32155cb7e337aa16f9c2edd5ee1704c84d96357b65d9cc526b7",
      "reserved_chars": 34,
      "schema_version": 1,
      "tool_message_index": 2,
      "prepared_result_chars": 2130,
      "remaining_chars_after": 31089,
      "remaining_chars_before": 33219
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "42c034fb-32e6-4f2b-be73-2074a2e9d5f9",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "ffb4583b-2169-49e3-889f-934da758222c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 工具调用 4


    {
      "call_id": "0dd6c6b2-c964-4bc4-b550-e8da4c479390",
      "tool_call_id": "call_5e1c1b64c601474e999c987c",
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
      "call_id": "0dd6c6b2-c964-4bc4-b550-e8da4c479390",
      "sources": [
        {
          "file_id": null,
          "chunk_id": null,
          "end_line": 5,
          "file_hash": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d",
          "file_path": "statistics.py",
          "source_id": "S12",
          "start_line": 1,
          "symbol_name": null,
          "content_chars": 168,
          "content_sha256": "96fb804cd72ad01c2b153d6c3f40577687833269e2428070a9088025cff3149d"
        }
      ],
      "step_id": "tools",
      "sequence": 19,
      "attempted": true,
      "has_error": false,
      "tool_name": "read_source",
      "disposition": "accepted",
      "tool_call_id": "call_5e1c1b64c601474e999c987c",
      "content_chars": 437,
      "trace_version": 1,
      "content_sha256": "fd01efa5faffa58c336176f4016220262d66e9fcaf90d5aae60898218ab9e723",
      "reserved_chars": 0,
      "schema_version": 1,
      "tool_message_index": 3,
      "prepared_result_chars": 437,
      "remaining_chars_after": 30652,
      "remaining_chars_before": 31089
    }

关联的后续模型调用尝试（completed / failed / unrecorded）：

    [
      {
        "call_id": "42c034fb-32e6-4f2b-be73-2074a2e9d5f9",
        "node_name": "model",
        "started_sequence": 20,
        "finished_sequence": 21,
        "outcome": "completed"
      },
      {
        "call_id": "ffb4583b-2169-49e3-889f-934da758222c",
        "node_name": "plan",
        "started_sequence": 22,
        "finished_sequence": 23,
        "outcome": "completed"
      }
    ]


## 模型调用清单


    {
      "call_id": "c0c19d04-1de7-4b89-839e-407fc1e8a485",
      "node_name": "model",
      "started_sequence": 2,
      "finished_sequence": 3,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "2b28342f-f858-4650-8643-bbc4c890b576",
      "node_name": "model",
      "started_sequence": 12,
      "finished_sequence": 13,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "42c034fb-32e6-4f2b-be73-2074a2e9d5f9",
      "node_name": "model",
      "started_sequence": 20,
      "finished_sequence": 21,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }


    {
      "call_id": "ffb4583b-2169-49e3-889f-934da758222c",
      "node_name": "plan",
      "started_sequence": 22,
      "finished_sequence": 23,
      "outcome": "completed",
      "context_recorded": true,
      "unmatched_tool_context": []
    }

