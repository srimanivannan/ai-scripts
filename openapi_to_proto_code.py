#!/usr/bin/env python3
import argparse
import yaml
import re
from collections import defaultdict
from typing import Optional, Tuple, List, Dict


def resolve_ref(ref: str, spec: dict) -> dict:
    """Resolve a JSON Reference (e.g. "#/components/schemas/Address")."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for p in parts:
        node = node[p]
    return node


def map_type(openapi_type: str) -> str:
    return {
        "string": "string",
        "integer": "int32",
        "number": "double",
        "boolean": "bool",
    }.get(openapi_type, "string")


def safe_name(name: str) -> str:
    # Field names must be valid identifiers
    return re.sub(r'[^A-Za-z0-9_]', '_', name)


def sanitize_tag(tag: str) -> str:
    # Service names must be Alnum only
    return re.sub(r'[^A-Za-z0-9]', '', tag)


def generate_message_from_schema(name: str, schema: dict, spec: dict) -> str:
    lines = [f"message {name} {{"]
    props = schema.get("properties", {}) or {}
    idx = 1
    for prop, val in props.items():
        field = safe_name(prop)

        # $ref property
        if isinstance(val, dict) and "$ref" in val:
            typ = val["$ref"].split("/")[-1]

        # array property
        elif isinstance(val, dict) and val.get("type") == "array":
            items = val.get("items", {})
            if isinstance(items, dict) and "$ref" in items:
                typ = items["$ref"].split("/")[-1]
            else:
                typ = map_type(items.get("type", "string"))
            lines.append(f"  repeated {typ} {field} = {idx};")
            idx += 1
            continue

        # map property
        elif isinstance(val, dict) and val.get("type") == "object" and "additionalProperties" in val:
            ap = val["additionalProperties"]
            if isinstance(ap, dict):
                vtype = map_type(ap.get("type", "string"))
            else:
                vtype = "string"
            lines.append(f"  map<string, {vtype}> {field} = {idx};")
            idx += 1
            continue

        # simple property
        else:
            typ = map_type(val.get("type", "string")) if isinstance(val, dict) else "string"

        lines.append(f"  {typ} {field} = {idx};")
        idx += 1

    lines.append("}")
    return "\n".join(lines)


def generate_schema_messages(spec: dict) -> List[str]:
    return [
        generate_message_from_schema(name, schema, spec)
        for name, schema in spec.get("components", {}).get("schemas", {}).items()
    ]


def find_json_schema(content_block: dict) -> Optional[dict]:
    for media, media_obj in content_block.items():
        if media.startswith("application/json"):
            return media_obj.get("schema")
    return None


def extract_body_schema(op: dict, spec: dict) -> Optional[dict]:
    rb = op.get("requestBody")
    if not rb:
        return None
    if "$ref" in rb:
        rb = resolve_ref(rb["$ref"], spec)
    return find_json_schema(rb.get("content", {}))


def extract_response_schema(op: dict, spec: dict) -> Tuple[str, Optional[dict]]:
    """
    Pick the first 2xx response, or default. Returns (messageName, inlineSchema?).
    """
    responses = op.get("responses", {})
    # 1) find a 2xx response by integer or string code
    success_resp = None
    for code_key, resp in responses.items():
        try:
            code_int = int(code_key)
        except:
            continue
        if 200 <= code_int < 300:
            success_resp = resp
            break
    # 2) fallback to 'default' if none found
    if not success_resp:
        success_resp = responses.get("default")
    if not success_resp:
        return "Empty", None

    if "$ref" in success_resp:
        success_resp = resolve_ref(success_resp["$ref"], spec)

    schema = find_json_schema(success_resp.get("content", {}))
    if not schema:
        return "Empty", None

    if isinstance(schema, dict) and "$ref" in schema:
        # direct reference
        return schema["$ref"].split("/")[-1], None
    else:
        # inline schema → create a new message
        msg_name = f"{op.get('operationId', 'Response')}Response"
        return msg_name, schema


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


def generate_services(
        spec: dict,
        base_service: str
) -> Tuple[List[str], Dict[str, str]]:
    all_params = spec.get("components", {}).get("parameters", {})
    tag_map: defaultdict = defaultdict(list)
    extras: Dict[str, str] = {}

    # group by tags
    for path, methods in spec.get("paths", {}).items():
        for m, op in methods.items():
            if m.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            tag = op.get("tags", [base_service])[0]
            tag_map[tag].append((path, m.lower(), op))

    services = []
    for tag, ops in tag_map.items():
        svc_name = sanitize_tag(tag)
        svc_lines = [f"service {svc_name}Service {{"]
        for path, method, op in ops:
            rpc = op.get("operationId") or f"{method}_{path.replace('/', '_').replace('{', '').replace('}', '')}"

            # parameters
            params = []
            for p in op.get("parameters", []):
                if "$ref" in p:
                    pname = p["$ref"].split("/")[-1]
                    params.append(all_params.get(pname, {}))
                else:
                    params.append(p)
            in_params = [p for p in params if p.get("in") in ("path", "query", "header")]

            # request body
            body_schema = extract_body_schema(op, spec)
            if body_schema:
                # determine body type
                if isinstance(body_schema, dict) and "$ref" in body_schema:
                    body_type = body_schema["$ref"].split("/")[-1]
                else:
                    body_type = f"{rpc}Body"

                # merge params + body?
                if in_params:
                    req_name = f"{rpc}Request"
                    msg_lines = [f"message {req_name} {{"]
                    idx = 1
                    for p in in_params:
                        sch = p.get("schema", {}) or {}
                        if "$ref" in sch:
                            ftype = sch["$ref"].split("/")[-1]
                        else:
                            ftype = map_type(sch.get("type", "string"))
                        msg_lines.append(f"  {ftype} {safe_name(p['name'])} = {idx};")
                        idx += 1
                    msg_lines.append(f"  {body_type} body = {idx};")
                    msg_lines.append("}")
                    extras[req_name] = "\n".join(msg_lines)
                    req_type = req_name
                else:
                    req_type = body_type

                # inline only → generate the Body message
                if not (isinstance(body_schema, dict) and "$ref" in body_schema):
                    extras[body_type] = generate_message_from_schema(body_type, body_schema, spec)

            elif in_params:
                req_name = f"{rpc}Request"
                extras[req_name] = generate_param_message(req_name, in_params)
                req_type = req_name
            else:
                req_type = "Empty"

            # response
            res_type, inline = extract_response_schema(op, spec)
            if inline:
                extras[res_type] = generate_message_from_schema(res_type, inline, spec)

            # emit RPC
            svc_lines.append(f"  rpc {rpc} ({req_type}) returns ({res_type});")
        svc_lines.append("}")
        services.append("\n".join(svc_lines))

    return services, extras


def generate_proto(
        spec: dict,
        package: str,
        base: str
) -> str:
    parts = [
        'syntax = "proto3";',
        f'package {package};',
        'import "google/protobuf/empty.proto";',
        'import "google/api/http.proto";',
        'import "google/api/annotations.proto";',
        "",
        "message Empty {}",
        ""
    ]
    parts += generate_schema_messages(spec)
    parts.append("")
    services, extras = generate_services(spec, base)
    parts += extras.values()
    parts.append("")
    parts += services
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="OpenAPI → gRPC + HTTP Proto Generator")
    parser.add_argument("input", help="OpenAPI YAML file")
    parser.add_argument("--package", default="api", help="`package` in .proto")
    parser.add_argument("--service", default="Default", help="base ServiceName if no tags")
    parser.add_argument("--output", default="output.proto", help="Output .proto path")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        spec = yaml.safe_load(f)

    proto = generate_proto(spec, args.package, args.service)
    with open(args.output, "w") as outp:
        outp.write(proto)
    print(f"SUCCESS! Generated {args.output}")


if __name__ == "__main__":
    main()
