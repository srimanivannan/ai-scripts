#!/usr/bin/env python3
import argparse
import yaml
import re
from collections import defaultdict
from typing import Optional, Tuple, List, Dict

# Track generated enums and nested enums to avoid duplicates
enums_defined = set()
nested_enum_defs: List[str] = []


# --- Utilities ---------------------------------------------------------------

def resolve_ref(ref: str, spec: dict) -> dict:
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def map_type(openapi_type: str) -> str:
    return {
        "string": "string",
        "integer": "int32",
        "number": "double",
        "boolean": "bool"
    }.get(openapi_type, "string")


def safe_name(n: str) -> str:
    return re.sub(r'[^A-Za-z0-9_]', '_', n)


def sanitize_tag(tag: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', tag)


def normalize_operation_id(op: str) -> str:
    # map 'retrieve' prefix to 'get' for consistent naming of wrapper messages only
    if op.lower().startswith('retrieve'):
        return 'get' + op[len('retrieve'):]
    return op


def to_camel(s: str) -> str:
    """
    Convert a normalized operationId or schema name to PascalCase.
    """
    parts = re.split(r'[^A-Za-z0-9]+', s)
    return ''.join(p[:1].upper() + p[1:] for p in parts if p)


def is_freeform_object(schema: dict) -> bool:
    return (
            isinstance(schema, dict)
            and schema.get("type") == "object"
            and not schema.get("properties")
            and not schema.get("additionalProperties")
    )


# --- Enum Generation --------------------------------------------------------

def generate_enum(name: str, schema: dict) -> Optional[str]:
    if name in enums_defined:
        return None
    enums_defined.add(name)
    lines = [f"enum {name} {{", f"  {name.upper()}_UNSPECIFIED = 0;"]
    for idx, val in enumerate(schema.get("enum", []), start=1):
        ident = safe_name(val).upper()
        lines.append(f"  {ident} = {idx};")
    lines.append("}")
    return "\n".join(lines)


# --- Message Generation -----------------------------------------------------

def generate_message_from_schema(name: str, schema: dict, spec: dict) -> str:
    if isinstance(schema, dict) and '$ref' in schema:
        schema = resolve_ref(schema['$ref'], spec)

    lines = [f"message {name} {{"]
    idx = 1
    for prop, val in (schema.get("properties") or {}).items():
        field = safe_name(prop)
        # inline enum
        if isinstance(val, dict) and val.get("enum") is not None:
            enum_name = safe_name(prop).capitalize()
            enum_def = generate_enum(enum_name, val)
            if enum_def:
                nested_enum_defs.append(enum_def)
            lines.append(f"  {enum_name} {field} = {idx};")
            idx += 1
            continue
        # $ref
        if isinstance(val, dict) and "$ref" in val:
            typ = val["$ref"].split("/")[-1]
        # array
        elif isinstance(val, dict) and val.get("type") == "array":
            items = val.get("items", {})
            if isinstance(items, dict) and "$ref" in items:
                typ = items["$ref"].split("/")[-1]
            else:
                typ = map_type(items.get("type", "string"))
            lines.append(f"  repeated {typ} {field} = {idx};")
            idx += 1
            continue
        # map
        elif isinstance(val, dict) and val.get("type") == "object" and "additionalProperties" in val:
            ap = val["additionalProperties"]
            vtype = map_type(ap.get("type")) if isinstance(ap, dict) else "string"
            lines.append(f"  map<string, {vtype}> {field} = {idx};")
            idx += 1
            continue
        else:
            typ = map_type(val.get("type", "string")) if isinstance(val, dict) else "string"
        lines.append(f"  {typ} {field} = {idx};")
        idx += 1
    lines.append("}")
    return "\n".join(lines)


def generate_schema_messages(spec: dict) -> List[str]:
    msgs: List[str] = []
    for name, schema in (spec.get("components", {}).get("schemas", {}) or {}).items():
        # top-level enum
        if isinstance(schema, dict) and schema.get("enum") is not None:
            enum_def = generate_enum(name, schema)
            if enum_def:
                msgs.append(enum_def)
        # array wrapper
        elif isinstance(schema, dict) and schema.get("type") == "array":
            items = schema.get("items", {})
            item_type = items.get("$ref", "").split("/")[-1] if isinstance(items,
                                                                           dict) and "$ref" in items else map_type(
                items.get("type", "string"))
            msgs.append(f"message {name} {{\n  repeated {item_type} items = 1;\n}}")
        # freeform object
        elif isinstance(schema, dict) and is_freeform_object(schema):
            continue
        # object
        else:
            msgs.append(generate_message_from_schema(name, schema, spec))
    return msgs


# --- HTTP Body / Response Schema Extraction --------------------------------

def find_json_schema(content: dict) -> Optional[dict]:
    for media, obj in content.items():
        if "application/json" in media:
            return obj.get("schema")
    return None


def extract_body_schema(op: dict, spec: dict) -> Optional[dict]:
    rb = op.get("requestBody")
    if not rb:
        return None
    if "$ref" in rb:
        rb = resolve_ref(rb["$ref"], spec)
    return find_json_schema(rb.get("content", {}))


def extract_response_schema(op: dict, spec: dict) -> Tuple[str, Optional[dict]]:
    # use normalized ID for wrapper naming only
    raw_id = op.get("operationId")
    norm_id = normalize_operation_id(raw_id)
    # find first 2xx response, handling int or str keys
    success = None
    for code, obj in op.get("responses", {}).items():
        if isinstance(code, int):
            code_int = code
        elif isinstance(code, str) and code.isdigit():
            code_int = int(code)
        else:
            continue
        if 200 <= code_int < 300:
            success = obj
            break
    success = success or op.get("responses", {}).get("default")
    if not success:
        return "Empty", None
    if "$ref" in success:
        ref = success["$ref"]
        resolved = resolve_ref(ref, spec)
        if is_freeform_object(resolved):
            return "google.protobuf.Struct", None
        return to_camel(normalize_operation_id(ref.split("/")[-1])), None
    schema = find_json_schema(success.get("content", {}))
    if not schema:
        return "Empty", None
    if schema.get("type") == "array":
        return to_camel(norm_id) + "Response", schema
    return to_camel(norm_id) + "Response", schema


# --- Services and Message Extras --------------------------------------------

def generate_param_message(name: str, params: List[dict]) -> str:
    lines = [f"message {name} {{"]
    idx = 1
    for p in params:
        sch = p.get("schema", {}) or {}
        if "$ref" in sch:
            ftype = sch["$ref"].split("/")[-1]
        else:
            ftype = map_type(sch.get("type", "string"))
        lines.append(f"  {ftype} {safe_name(p['name'])} = {idx};")
        idx += 1
    lines.append("}")
    return "\n".join(lines)


def generate_services(spec: dict, base: str) -> Tuple[List[str], Dict[str, str]]:
    all_params = spec.get("components", {}).get("parameters", {}) or {}
    tag_map = defaultdict(list)
    extras: Dict[str, str] = {}
    for path, meths in spec.get("paths", {}).items():
        for m, op in meths.items():
            method = m.lower()
            if method not in ("get", "post", "put", "patch", "delete"): continue
            tag_map[op.get("tags", [base])[0]].append((path, method, op))

    services = []
    for tag, ops in tag_map.items():
        svc = sanitize_tag(tag)
        lines = [f"service {svc}Service {{"]
        for path, method, op in ops:
            # rpc name is original operationId
            rpc = op.get("operationId")
            raw_id = rpc
            norm_id = normalize_operation_id(raw_id)
            # parameters
            params = []
            for p in op.get("parameters", []):
                params.append(all_params.get(p.get("$ref", "").split("/")[-1], {}) if "$ref" in p else p)
            in_params = [p for p in params if p.get("in") in ("path", "query", "header")]

            # REQUEST TYPE
            body_schema = extract_body_schema(op, spec)
            if body_schema:
                if isinstance(body_schema, dict) and "$ref" in body_schema:
                    ref = body_schema["$ref"].split("/")[-1]
                    req_type = "google.protobuf.Struct" if is_freeform_object(
                        resolve_ref(body_schema["$ref"], spec)) else ref
                elif is_freeform_object(body_schema):
                    req_type = "google.protobuf.Struct"
                else:
                    bname = to_camel(norm_id) + "Body"
                    extras.setdefault(bname, generate_message_from_schema(bname, body_schema, spec))
                    req_type = bname
                if in_params:
                    rname = to_camel(norm_id) + "Request"
                    if rname not in extras:
                        lines_req = [f"message {rname} {{"]
                        i = 1
                        for p in in_params:
                            sch = p.get("schema", {})
                            ftype = sch.get("$ref", "").split("/")[-1] if "$ref" in sch else map_type(
                                sch.get("type", "string"))
                            lines_req.append(f"  {ftype} {safe_name(p['name'])} = {i};")
                            i += 1
                        lines_req.append(f"  {req_type} body = {i};")
                        lines_req.append("}")
                        extras[rname] = "\n".join(lines_req)
                    req_type = rname
            elif in_params:
                rname = to_camel(norm_id) + "Request"
                extras.setdefault(rname, generate_param_message(rname, in_params))
                req_type = rname
            else:
                req_type = "Empty"

            # RESPONSE TYPE
            res_type, inline = extract_response_schema(op, spec)
            if inline:
                if inline.get("type") == "array":
                    items = inline.get("items", {})
                    ity = items.get("$ref", "").split("/")[-1] if "$ref" in items else map_type(
                        items.get("type", "string"))
                    extras.setdefault(res_type, f"message {res_type} {{\n  repeated {ity} items = 1;\n}}")
                else:
                    extras.setdefault(res_type, generate_message_from_schema(res_type, inline, spec))

            # RPC Definition
            lines.append(f"  rpc {rpc} ({req_type}) returns ({res_type}) {{")
            lines.append("    option (google.api.http) = {")
            lines.append(f'      {method}: "{path}"')
            lines.append('      body: "body"' if method in ("post", "put", "patch") else '      body: "*"')
            lines.append("    };")
            lines.append("  }")
        lines.append("}")
        services.append("\n".join(lines))
    return services, extras


# --- Assemble Proto with Deduplication --------------------------------------

def generate_proto(spec: dict, pkg: str, base: str) -> str:
    enums_defined.clear()
    nested_enum_defs.clear()

    header = [
        'syntax = "proto3";',
        f'package {pkg};',
        'import "google/protobuf/empty.proto";',
        'import "google/protobuf/struct.proto";',
        'import "google/api/http.proto";',
        'import "google/api/annotations.proto";',
        "", "message Empty {}", ""
    ]

    schemas = generate_schema_messages(spec)
    services, extras = generate_services(spec, base)
    all_blocks = schemas + nested_enum_defs + list(extras.values()) + services
    seen = set();
    unique = []
    for b in all_blocks:
        first = b.split("\n", 1)[0]
        if first.startswith("message ") or first.startswith("enum "):
            nm = first.split()[1]
            if nm in seen: continue
            seen.add(nm)
        unique.append(b)

    return "\n".join(header + unique)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--package", default="api")
    parser.add_argument("--service", default="Default")
    parser.add_argument("--output", default="output.proto")
    args = parser.parse_args()
    spec = yaml.safe_load(open(args.input))
    proto = generate_proto(spec, args.package, args.service)
    open(args.output, "w").write(proto)
    print(f"SUCCESS! Generated {args.output}")


if __name__ == "__main__":
    main()
