#!/usr/bin/env python3
import argparse, yaml, re
from collections import defaultdict
from typing import Optional, Tuple, List, Dict


def resolve_ref(ref: str, spec: dict) -> dict:
    node = spec
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def map_type(openapi_type: str) -> str:
    return {"string": "string", "integer": "int32", "number": "double", "boolean": "bool"}.get(openapi_type, "string")


def safe_name(n: str) -> str:
    return re.sub(r'[^A-Za-z0-9_]', '_', n)


def sanitize_tag(tag: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', tag)


# --- schema → message -------------------------------------------------------

def generate_message_from_schema(name: str, schema: dict, spec: dict) -> str:
    lines = [f"message {name} {{"]
    props = schema.get("properties", {}) or {}
    idx = 1
    for prop, val in props.items():
        field = safe_name(prop)
        if isinstance(val, dict) and "$ref" in val:
            typ = val["$ref"].split("/")[-1]
        elif isinstance(val, dict) and val.get("type") == "array":
            items = val.get("items", {})
            if isinstance(items, dict) and "$ref" in items:
                typ = items["$ref"].split("/")[-1]
            else:
                typ = map_type(items.get("type", "string"))
            lines.append(f"  repeated {typ} {field} = {idx};");
            idx += 1;
            continue
        elif isinstance(val, dict) and val.get("type") == "object" and "additionalProperties" in val:
            ap = val["additionalProperties"]
            vtype = map_type(ap.get("type")) if isinstance(ap, dict) else "string"
            lines.append(f"  map<string, {vtype}> {field} = {idx};");
            idx += 1;
            continue
        else:
            typ = map_type(val.get("type", "string")) if isinstance(val, dict) else "string"
        lines.append(f"  {typ} {field} = {idx};");
        idx += 1
    lines.append("}")
    return "\n".join(lines)


def generate_schema_messages(spec: dict) -> List[str]:
    return [
        generate_message_from_schema(n, s, spec)
        for n, s in spec.get("components", {}).get("schemas", {}).items()
    ]


def find_json_schema(content: dict) -> Optional[dict]:
    for media, obj in content.items():
        if "application/json" in media:
            return obj.get("schema")
    return None


def extract_body_schema(op: dict, spec: dict) -> Optional[dict]:
    rb = op.get("requestBody")
    if not rb: return None
    if "$ref" in rb: rb = resolve_ref(rb["$ref"], spec)
    return find_json_schema(rb.get("content", {}))


def extract_response_schema(op: dict, spec: dict) -> Tuple[str, Optional[dict]]:
    # pick first 2xx, else default
    success = None
    for code, obj in op.get("responses", {}).items():
        try:
            if 200 <= int(code) < 300:
                success = obj;
                break
        except:
            pass
    success = success or op.get("responses", {}).get("default")
    if not success: return "Empty", None
    if "$ref" in success: success = resolve_ref(success["$ref"], spec)
    schema = find_json_schema(success.get("content", {}))
    if not schema: return "Empty", None
    if isinstance(schema, dict) and schema.get("type") == "array":
        return f"{op['operationId']}Response", schema
    if isinstance(schema, dict) and "$ref" in schema:
        return schema["$ref"].split("/")[-1], None
    return f"{op['operationId']}Response", schema


def generate_param_message(name: str, params: List[dict]) -> str:
    lines = [f"message {name} {{"];
    idx = 1
    for p in params:
        sch = p.get("schema", {}) or {}
        if "$ref" in sch:
            ftype = sch["$ref"].split("/")[-1]
        else:
            ftype = map_type(sch.get("type", "string"))
        lines.append(f"  {ftype} {safe_name(p['name'])} = {idx};");
        idx += 1
    lines.append("}")
    return "\n".join(lines)


# --- services & RPCs ---------------------------------------------------------

def generate_services(spec: dict, base: str) -> Tuple[List[str], Dict[str, str]]:
    all_params = spec.get("components", {}).get("parameters", {})
    tag_map = defaultdict(list)
    extras: Dict[str, str] = {}

    # group by tag
    for path, meths in spec.get("paths", {}).items():
        for m, op in meths.items():
            method = m.lower()
            if method not in ("get", "post", "put", "patch", "delete"): continue
            tag = op.get("tags", [base])[0]
            tag_map[tag].append((path, method, op))

    services = []
    for tag, ops in tag_map.items():
        svc = sanitize_tag(tag)
        lines = [f"service {svc}Service {{"]
        for path, method, op in ops:
            rpc = op.get("operationId") or f"{method}_{path}"
            # parameters
            params = []
            for p in op.get("parameters", []):
                if "$ref" in p:
                    name = p["$ref"].split("/")[-1]
                    params.append(all_params.get(name, {}))
                else:
                    params.append(p)
            in_params = [p for p in params if p.get("in") in ("path", "query", "header")]

            # request
            body = extract_body_schema(op, spec)
            if body:
                if isinstance(body, dict) and "$ref" in body:
                    btype = body["$ref"].split("/")[-1]
                else:
                    btype = f"{rpc}Body"
                if in_params:
                    req = f"{rpc}Request"
                    msg = [f"message {req} {{"];
                    idx = 1
                    for p in in_params:
                        sch = p.get("schema", {}) or {}
                        ftype = sch["$ref"].split("/")[-1] if "$ref" in sch else map_type(sch.get("type", "string"))
                        msg.append(f"  {ftype} {safe_name(p['name'])} = {idx};");
                        idx += 1
                    msg.append(f"  {btype} body = {idx};");
                    msg.append("}")
                    extras[req] = "\n".join(msg)
                    req_type = req
                else:
                    req_type = btype
                if not (isinstance(body, dict) and "$ref" in body):
                    extras[btype] = generate_message_from_schema(btype, body, spec)
            elif in_params:
                req = f"{rpc}Request"
                extras[req] = generate_param_message(req, in_params)
                req_type = req
            else:
                req_type = "Empty"

            # response
            res_type, inline = extract_response_schema(op, spec)
            if inline:
                if isinstance(inline, dict) and inline.get("type") == "array":
                    itm = inline.get("items", {})
                    itype = itm["$ref"].split("/")[-1] if ("$ref" in itm) else map_type(itm.get("type", "string"))
                    wrapper = [f"message {res_type} {{",
                               f"  repeated {itype} items = 1;",
                               "}"]
                    extras[res_type] = "\n".join(wrapper)
                else:
                    extras[res_type] = generate_message_from_schema(res_type, inline, spec)

            # emit rpc + HTTP option
            lines.append(f"  rpc {rpc} ({req_type}) returns ({res_type}) {{")
            lines.append("    option (google.api.http) = {")
            lines.append(f'      {method}: "{path}"')
            # always emit body mapping now
            if method in ("post", "put", "patch"):
                lines.append('      body: "body"')
            else:  # GET & DELETE (and any others)
                lines.append('      body: "*"')
            lines.append("    };")
            lines.append("  }")

        lines.append("}")
        services.append("\n".join(lines))

    return services, extras


# --- build full proto --------------------------------------------------------

def generate_proto(spec: dict, pkg: str, base: str) -> str:
    parts = [
        'syntax = "proto3";',
        f'package {pkg};',
        'import "google/protobuf/empty.proto";',
        'import "google/api/http.proto";',
        'import "google/api/annotations.proto";',
        "",
        "message Empty {}",
        ""
    ]
    parts += generate_schema_messages(spec)
    parts.append("")
    svcs, extras = generate_services(spec, base)
    parts += extras.values()
    parts.append("")
    parts += svcs
    return "\n".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", help="OpenAPI file")
    p.add_argument("--package", default="api")
    p.add_argument("--service", default="Default")
    p.add_argument("--output", default="output.proto")
    args = p.parse_args()

    spec = yaml.safe_load(open(args.input))
    proto = generate_proto(spec, args.package, args.service)
    open(args.output, "w").write(proto)
    print(f"SUCCESS! Generated {args.output}")


if __name__ == "__main__":
    main()
