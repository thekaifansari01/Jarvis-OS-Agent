import copy
import hashlib
import json
import re
import threading
from google.genai import types

from core.logger.logger import logger


_TYPE_MAP = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
    "object": types.Type.OBJECT,
}

_ROUTE_LOCK = threading.RLock()
_TOOL_ROUTE_MAP = {}


def _sanitize_identifier(text):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", str(text or "").strip())
    return cleaned or "unknown"


def register_tool_route(full_name, server_name, raw_tool_name):
    with _ROUTE_LOCK:
        _TOOL_ROUTE_MAP[full_name] = (server_name, raw_tool_name)


def resolve_mcp_tool_name(full_name):
    if not isinstance(full_name, str):
        return None, None
    with _ROUTE_LOCK:
        mapped = _TOOL_ROUTE_MAP.get(full_name)
    if mapped:
        return mapped
    parts = full_name.split("__", 2)
    if len(parts) == 3 and parts[0] == "mcp":
        return parts[1], parts[2]
    return None, None


def clear_tool_routes():
    with _ROUTE_LOCK:
        _TOOL_ROUTE_MAP.clear()

def clear_server_tool_routes(server_name):
    removed_names = set()
    with _ROUTE_LOCK:
        to_delete = [
            full_name
            for full_name, (srv, _) in _TOOL_ROUTE_MAP.items()
            if srv == server_name
        ]
        for full_name in to_delete:
            _TOOL_ROUTE_MAP.pop(full_name, None)
            removed_names.add(full_name)
    return removed_names


def _deref_schema(node, defs, seen=None):
    if not isinstance(node, dict):
        return {}
    if seen is None:
        seen = set()

    if "$ref" in node and isinstance(node["$ref"], str):
        ref_str = node["$ref"]
        ref_key = ref_str.split("/")[-1]
        if ref_key in defs and ref_key not in seen:
            merged = copy.deepcopy(defs[ref_key])
            for k, v in node.items():
                if k != "$ref":
                    merged[k] = v
            return _deref_schema(merged, defs, seen | {ref_key})

    if "allOf" in node and isinstance(node["allOf"], list):
        combined = {k: v for k, v in node.items() if k != "allOf"}
        props = dict(combined.get("properties") or {})
        reqs = list(combined.get("required") or [])
        for sub in node["allOf"]:
            resolved_sub = _deref_schema(sub, defs, seen)
            if isinstance(resolved_sub, dict):
                if resolved_sub.get("type") and not combined.get("type"):
                    combined["type"] = resolved_sub["type"]
                if resolved_sub.get("description") and not combined.get("description"):
                    combined["description"] = resolved_sub["description"]
                if isinstance(resolved_sub.get("properties"), dict):
                    props.update(resolved_sub["properties"])
                if isinstance(resolved_sub.get("required"), list):
                    for r in resolved_sub["required"]:
                        if r not in reqs:
                            reqs.append(r)
        if props:
            combined["type"] = "object"
            combined["properties"] = props
        if reqs:
            combined["required"] = reqs
        return _deref_schema(combined, defs, seen)

    if "anyOf" in node or "oneOf" in node:
        variants = node.get("anyOf") or node.get("oneOf") or []
        parent_desc = node.get("description")
        parent_default = node.get("default")
        if isinstance(variants, list):
            for v in variants:
                if isinstance(v, dict) and v.get("type") != "null":
                    resolved_v = _deref_schema(copy.deepcopy(v), defs, seen)
                    if parent_desc and not resolved_v.get("description"):
                        resolved_v["description"] = parent_desc
                    if parent_default is not None and "default" not in resolved_v:
                        resolved_v["default"] = parent_default
                    return resolved_v

    result = dict(node)
    if isinstance(result.get("properties"), dict):
        result["properties"] = {
            k: _deref_schema(v, defs, seen)
            for k, v in result["properties"].items()
            if isinstance(k, str)
        }
    if isinstance(result.get("items"), dict):
        result["items"] = _deref_schema(result["items"], defs, seen)
    return result


def _convert_schema(js, defs=None):
    if not isinstance(js, dict):
        return types.Schema(type=types.Type.STRING)

    if defs is None:
        defs = {}
        if isinstance(js.get("$defs"), dict):
            defs.update(js["$defs"])
        if isinstance(js.get("definitions"), dict):
            defs.update(js["definitions"])
        js = _deref_schema(js, defs)

    t = js.get("type")
    if isinstance(t, list):
        chosen = None
        for candidate in t:
            if isinstance(candidate, str) and candidate.lower() != "null":
                chosen = candidate
                break
        t = chosen or "string"
    if not isinstance(t, str):
        if isinstance(js.get("properties"), dict):
            t = "object"
        elif "items" in js:
            t = "array"
        else:
            t = "string"
    t = t.lower()

    schema_type = _TYPE_MAP.get(t, types.Type.STRING)
    kwargs = {"type": schema_type}

    desc_parts = []
    desc = js.get("description")
    if isinstance(desc, str) and desc.strip():
        desc_parts.append(desc.strip())
    if "default" in js and js["default"] is not None:
        desc_parts.append(f"(default: {js['default']})")
    if desc_parts:
        kwargs["description"] = " ".join(desc_parts)[:500]

    enum_vals = js.get("enum")
    if isinstance(enum_vals, list) and schema_type == types.Type.STRING:
        cleaned = [str(x) for x in enum_vals if isinstance(x, (str, int, float, bool))]
        if cleaned:
            kwargs["enum"] = cleaned

    if t == "array":
        items_js = js.get("items")
        if isinstance(items_js, dict):
            kwargs["items"] = _convert_schema(items_js, defs=defs)
        elif isinstance(items_js, list) and items_js and isinstance(items_js[0], dict):
            kwargs["items"] = _convert_schema(items_js[0], defs=defs)
        else:
            kwargs["items"] = types.Schema(type=types.Type.STRING)
    elif t == "object":
        props = js.get("properties")
        converted = {}
        if isinstance(props, dict):
            for k, v in props.items():
                if isinstance(k, str):
                    converted[k] = _convert_schema(v, defs=defs)
        kwargs["properties"] = converted
        req = js.get("required")
        if isinstance(req, list):
            req_clean = [
                str(x)
                for x in req
                if isinstance(x, str) and str(x) in converted
            ]
            if req_clean:
                kwargs["required"] = req_clean

    try:
        return types.Schema(**kwargs)
    except Exception as e:
        logger.warning(f"MCP schema conversion fallback: {e}")
        return types.Schema(type=types.Type.STRING)


def _build_full_tool_name(server_name, raw_name):
    safe_server = _sanitize_identifier(server_name)
    safe_tool = _sanitize_identifier(raw_name)
    candidate = f"mcp__{safe_server}__{safe_tool}"
    if len(candidate) <= 60:
        return candidate
    digest = hashlib.md5(f"{server_name}:{raw_name}".encode("utf-8")).hexdigest()[:6]
    prefix = candidate[:53].rstrip("_")
    return f"{prefix}_{digest}"


def _convert_single_tool(server_name, tool):
    raw_name = getattr(tool, "name", None)
    if not raw_name or not isinstance(raw_name, str):
        return None

    full_name = _build_full_tool_name(server_name, raw_name)
    register_tool_route(full_name, server_name, raw_name)

    description = getattr(tool, "description", "") or ""
    description = str(description).strip()
    if description:
        description = f"[MCP:{server_name}] {description}"[:500]
    else:
        description = f"[MCP:{server_name}] Execute tool '{raw_name}'"

    input_schema = getattr(tool, "inputSchema", None)
    if input_schema is None:
        input_schema = getattr(tool, "input_schema", None)

    if not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}}
    else:
        input_schema = copy.deepcopy(input_schema)

    input_schema["type"] = "object"
    if not isinstance(input_schema.get("properties"), dict):
        input_schema["properties"] = {}

    parameters = _convert_schema(input_schema)

    return types.FunctionDeclaration(
        name=full_name,
        description=description,
        parameters=parameters,
    )


def convert_mcp_tools(server_name, tools):
    declarations = []
    if not tools:
        return declarations
    for tool in tools:
        try:
            decl = _convert_single_tool(server_name, tool)
            if decl is not None:
                declarations.append(decl)
        except Exception as e:
            name = getattr(tool, "name", "?")
            logger.error(f"MCP tool conversion failed ({server_name}/{name}): {e}")
    return declarations


def format_tool_result(result, server_name):
    if result is None:
        return f"Observation: [ERROR] [MCP:{server_name}] Empty result"

    try:
        content_items = list(getattr(result, "content", None) or [])
    except Exception:
        content_items = []

    is_error = bool(getattr(result, "isError", False))

    parts = []
    for item in content_items:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
            continue

        resource = getattr(item, "resource", None)
        if resource is not None:
            res_text = getattr(resource, "text", None)
            res_uri = getattr(resource, "uri", "")
            if res_text is not None:
                header = f"[Resource: {res_uri}]\n" if res_uri else ""
                parts.append(f"{header}{res_text}")
                continue

        mime = getattr(item, "mimeType", None) or getattr(item, "mime_type", None)
        data = getattr(item, "data", None)
        if data is not None:
            data_len = len(str(data))
            parts.append(f"[media content: {mime or 'unknown'}, {data_len} bytes]")
            continue

        parts.append(str(item))

    structured = getattr(result, "structuredContent", None)
    if structured and not parts:
        try:
            parts.append(json.dumps(structured, ensure_ascii=False, indent=2))
        except Exception:
            parts.append(str(structured))

    body = "\n".join(parts).strip() if parts else "Tool executed successfully (no text output)."

    if is_error:
        return f"Observation: [ERROR] [MCP:{server_name}] {body}"
    return f"Observation: [MCP:{server_name}] {body}"