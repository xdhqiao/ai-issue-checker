ISSUE_CONFIRMATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "file_find",
            "description": "Find repository files by a name fragment.",
            "parameters": {"type": "object", "properties": {"query_name": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query_name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_search",
            "description": "Search text or a regular expression in repository source files.",
            "parameters": {"type": "object", "properties": {"search_text": {"type": "string"}, "regex": {"type": "boolean"}, "case_sensitive": {"type": "boolean"}, "limit": {"type": "integer"}}, "required": ["search_text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read numbered lines from a source file. Omit file_path for the current file.",
            "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_definition",
            "description": "Find likely definitions of a symbol.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "Find references to a symbol.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_graph",
            "description": "Find lines that call or define a symbol.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "direction": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_confidences",
            "description": "Submit confidence for Polyspace issues by their zero-based input order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"issue_index": {"type": "integer"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
                            "required": ["issue_index", "confidence"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_done",
            "description": "Finish only after every issue has a submitted confidence.",
            "parameters": {"type": "object", "properties": {"state": {"type": "string", "enum": ["DONE", "FAILED"]}, "summary": {"type": "string"}}, "required": ["state"]},
        },
    },
]


SYSTEM_PROMPT = """You independently verify Polyspace findings against repository source code.
Use the context tools as needed. For every input issue, output a confidence from 0 to 1 that the issue is a real defect (1 means certainly real, 0 means false positive). Submit all values through submit_confidences, preserving the zero-based input order, then call task_done(state=\"DONE\"). Do not infer confidence from severity. Evidence in code must drive the result."""
