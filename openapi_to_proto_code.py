#!/usr/bin/env python3
import argparse
import yaml
import re
from collections import defaultdict
from typing import Optional, Tuple, List, Dict


def resolve_ref(ref: str, spec: dict) -> dict:
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
    # for field names
    return re.sub(r'[^A-Za-z0-9_]', '_', name)


def sanitize_tag(tag: str) -> str:
    # remove any chars illegal in service names
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

        # map property (object with additionalProperties)
        elif isinstance(val, dict) and val.get("type") == "object" and "additionalProperties" in val:
            ap = val["additionalProperties"]
            # if additionalProperties is a schema object
            if isinstance(ap, dict):
                vtype = map_type(ap.get("type", "string"))
            # if additionalProperties is boolean true/false
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
    out = []
    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        out.append(generate_message_from_schema(name, schema, spec))
    return out


def extract_body_schema(op: dict, spec: dict) -> Optional[dict]:
    rb = op.get("requestBody")
    if not rb:
        return None
    if "$ref" in rb:
        rb = resolve_ref(rb["$ref"], spec)
    return rb.get("content", {}) \
        .get("application/json", {}) \
        .get("schema")


def extract_response_schema(op: dict, spec: dict) -> Tuple[str, Optional[dict]]:
    for code in ("200", "201", "default"):
        resp = op.get("responses", {}).get(code)
        if not resp:
            continue
        if "$ref" in resp:
            resp = resolve_ref(resp["$ref"], spec)
        content = resp.get("content", {}).get("application/json", {})
        schema = content.get("schema")
        if schema:
            if "$ref" in schema:
                return schema["$ref"].split("/")[-1], None
            else:
                return f"{op.get('operationId', code)}Response", schema
        break
    return "Empty", None


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

    # group by OpenAPI tags
    for path, methods in spec.get("paths", {}).items():
        for m, op in methods.items():
            if m.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            tag = op.get("tags", [base_service])[0]
            tag_map[tag].append((path, m.lower(), op))

    services: List[str] = []
    for tag, ops in tag_map.items():
        svc_name = sanitize_tag(tag)
        svc_lines = [f"service {svc_name}Service {{"]
        for path, method, op in ops:
            rpc = op.get("operationId") or f"{method}_{path}"

            # gather parameters
            params = []
            for p in op.get("parameters", []):
                if "$ref" in p:
                    pname = p["$ref"].split("/")[-1]
                    params.append(all_params.get(pname, {}))
                else:
                    params.append(p)
            in_params = [p for p in params if p.get("in") in ("path", "query", "header")]

            # --- request type ---
            body_schema = extract_body_schema(op, spec)
            if body_schema:
                rb = op["requestBody"]
                if "$ref" in rb:
                    ref = resolve_ref(rb["$ref"], spec)
                    sch = ref["content"]["application/json"]["schema"]
                    body_type = sch["$ref"].split("/")[-1]
                else:
                    body_type = f"{rpc}Body"

                if in_params:
                    req_name = f"{rpc}Request"
                    msg = [f"message {req_name} {{"]
                    idx = 1
                    for p in in_params:
                        sch = p.get("schema", {}) or {}
                        if "$ref" in sch:
                            ftype = sch["$ref"].split("/")[-1]
                        else:
                            ftype = map_type(sch.get("type", "string"))
                        msg.append(f"  {ftype} {safe_name(p['name'])} = {idx};")
                        idx += 1
                    msg.append(f"  {body_type} body = {idx};")
                    msg.append("}")
                    extras[req_name] = "\n".join(msg)
                    req_type = req_name
                else:
                    req_type = body_type

                if body_schema and not ("$ref" in rb):
                    extras[body_type] = generate_message_from_schema(body_type, body_schema, spec)

            elif in_params:
                req_name = f"{rpc}Request"
                extras[req_name] = generate_param_message(req_name, in_params)
                req_type = req_name
            else:
                req_type = "Empty"

            # --- response type ---
            res_type, inline = extract_response_schema(op, spec)
            if inline:
                extras[res_type] = generate_message_from_schema(res_type, inline, spec)

            # --- emit RPC with HTTP annotations ---
            svc_lines.append(f"  rpc {rpc} ({req_type}) returns ({res_type}) {{")
            svc_lines.append(f"    option (google.api.http) = {{")
            svc_lines.append(f'      {method}: "{path}"')
            if method in ("post", "put", "patch"):
                body_field = "body" if in_params else "*"
                svc_lines.append(f'      body: "{body_field}"')
            svc_lines.append("    };")
            svc_lines.append("  }")
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
    parser.add_argument("input", help="Path to OpenAPI YAML file")
    parser.add_argument("--package", default="api", help="`package` name in the .proto")
    parser.add_argument("--service", default="Default", help="Base gRPC service name for untagged ops")
    parser.add_argument("--output", default="output.proto", help="Output .proto filename")
    args = parser.parse_args()

    with open(args.input, "r") as f:
        spec = yaml.safe_load(f)

    proto = generate_proto(spec, args.package, args.service)
    with open(args.output, "w") as out:
        out.write(proto)
    print(f"✅ Generated {args.output}")


if __name__ == "__main__":
    main()
