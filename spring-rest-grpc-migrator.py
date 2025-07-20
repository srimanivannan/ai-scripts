#!/usr/bin/env python3
"""
Scaffold a gRPC-enabled Spring Boot project from an existing REST-based application.
Reads config from JSON/YAML to parameterize:
  - existing_rest_project_root
  - existing_build_gradle
  - proto_file_path
  - output_dir
  - ignore patterns
  - extra_copy entries
  - impl_base_package (optional): Java package for dummy service implementations

It then:
  1. Copies the legacy project cleanly
  2. Injects gRPC/protobuf plugin and dependencies
     (both plugins {} and apply plugin syntax)
  3. Appends the `protobuf { ... }` codegen configuration block
  4. Updates java.srcDirs in existing sourceSets.main
  5. Copies extra files/folders
  6. Parses the .proto file to generate dummy `{Service}GrpcImpl` classes
     annotated with `@GrpcService` under `impl_base_package`
  7. Runs Gradle build to compile all sources
"""
import os
import shutil
import argparse
import re
import subprocess
import json
from types import SimpleNamespace

# Optional YAML support
try:
    import yaml
except ImportError:
    yaml = None


def load_config(config_path):
    with open(config_path) as f:
        if config_path.lower().endswith(('.yaml', '.yml')):
            if yaml is None:
                raise RuntimeError("PyYAML is required for YAML config.")
            return yaml.safe_load(f)
        return json.load(f)


def copy_project(src_dir, dest_dir, ignore_patterns):
    def _ignore(_, names):
        ignored = []
        for name in names:
            for pat in ignore_patterns:
                if re.search(pat, name):
                    ignored.append(name)
                    break
        return set(ignored)

    shutil.copytree(src_dir, dest_dir, ignore=_ignore)
    print(f"Copied legacy project from {src_dir} to {dest_dir}")


def inject_grpc_settings(build_file_path):
    lines = open(build_file_path).read().splitlines(keepends=True)
    out = []
    in_plugins = False
    depth_plugins = 0
    for line in lines:
        if re.match(r"\s*plugins\s*\{", line):
            in_plugins, depth_plugins = True, 1
            out.append(line)
            continue
        if in_plugins:
            open_b, close_b = line.count('{'), line.count('}')
            if close_b and depth_plugins == 1:
                indent = re.match(r"(\s*)", line).group(1)
                out.append(indent + "\tid 'com.google.protobuf' version '0.8.19'\n")
                in_plugins = False
                out.append(line)
            else:
                out.append(line)
                depth_plugins += open_b - close_b
            continue
        out.append(line)
        if re.match(r"\s*apply plugin:\s*['\"]org\.springframework\.boot['\"]", line):
            out.append("\n// -- gRPC support added by generator\n")
            out.append("apply plugin: 'com.google.protobuf'\n")
        if re.match(r"\s*dependencies\s*\{", line):
            out.append("    // gRPC dependencies added by generator\n")
            out.append("    implementation 'net.devh:grpc-spring-boot-starter:3.0.0.RELEASE'\n")
            out.append("    implementation 'io.grpc:grpc-stub:1.57.2'\n")
            out.append("    implementation 'io.grpc:grpc-protobuf:1.57.2'\n")
            out.append("    implementation 'com.google.protobuf:protobuf-java:3.25.5'\n")
            out.append("    implementation 'com.google.protobuf:protobuf-java-util:3.25.5'\n")
    with open(build_file_path, 'w') as f:
        f.writelines(out)
    print(f"Injected gRPC plugin and dependencies into {build_file_path}")


def inject_protobuf_config(build_file_path):
    config_block = r"""
// -- Protobuf codegen config added by generator
protobuf {
    protoc { artifact = 'com.google.protobuf:protoc:3.25.5' }
    plugins { grpc { artifact = 'io.grpc:protoc-gen-grpc-java:1.57.2' } }
    generateProtoTasks { all().each { task -> task.plugins { grpc {} } } }
}
"""
    with open(build_file_path, 'a') as f:
        f.write('\n' + config_block)
    print(f"Appended protobuf codegen config to {build_file_path}")


def inject_protobuf_block(build_file_path):
    lines = open(build_file_path).read().splitlines(keepends=True)
    out, in_ss, in_main, in_java = [], False, False, False
    depth_main = depth_java = 0
    for line in lines:
        shortcut = re.match(r"(\s*)sourceSets\.main\.java\.srcDir", line)
        if shortcut:
            out.append(line)
            indent = shortcut.group(1)
            for p in ["$generatedSrcDir/src/main/java",
                      'build/generated/source/proto/main/grpc',
                      'build/generated/source/proto/main/java',
                      'src/main/proto']:
                out.append(f"{indent}sourceSets.main.java.srcDir '{p}'\n")
            continue
        if not in_ss:
            out.append(line)
            if re.match(r"\s*sourceSets\s*\{", line): in_ss = True
            continue
        if in_ss and not in_main:
            out.append(line)
            if re.match(r"\s*main\s*\{", line): in_main, depth_main = True, 1
            continue
        if in_main and not in_java:
            out.append(line)
            if re.match(r"\s*java\s*\{", line): in_java, depth_java = True, 1
            continue
        if in_java:
            m = re.match(r"(\s*)(srcDirs\s*=\s*\[)(.*)(\])", line)
            if m:
                indent, prefix, existing, suffix = m.groups()
                combined = f"{indent}{prefix}{existing}, '$generatedSrcDir/src/main/java', 'build/generated/source/proto/main/grpc', 'build/generated/source/proto/main/java', 'src/main/proto'{suffix}\n"
                out.append(combined)
            elif re.match(r"\s*srcDir\s+['\"].*['\"]", line):
                out.append(line)
                indent = re.match(r"(\s*)", line).group(1)
                for p in ["$generatedSrcDir/src/main/java",
                          'build/generated/source/proto/main/grpc',
                          'build/generated/source/proto/main/java',
                          'src/main/proto']:
                    out.append(f"{indent}srcDir '{p}'\n")
            else:
                out.append(line)
            depth_java += line.count('{') - line.count('}')
            if depth_java == 0: in_java = False
            continue
        out.append(line)
        depth_main += line.count('{') - line.count('}')
        if depth_main == 0: in_main, in_ss = False, False
    with open(build_file_path, 'w') as f:
        f.writelines(out)
    print(f"Updated sourceSets in {build_file_path} to include grpc and proto srcDirs")


def generate_service_impls(out_dir, impl_base_package, proto_file_path):
    # Parse the .proto to find service names and Java package
    services = []
    java_pkg = None
    with open(proto_file_path) as pf:
        for ln in pf:
            m_opt = re.match(r"\s*option\s+java_package\s*=\s*\"([^\"]+)\";", ln)
            if m_opt:
                java_pkg = m_opt.group(1)
            m_svc = re.match(r"\s*service\s+(\w+)\s*\{", ln)
            if m_svc:
                services.append(m_svc.group(1))
    if not java_pkg:
        with open(proto_file_path) as pf:
            for ln in pf:
                m_pkg = re.match(r"\s*package\s+([\w\.]+);", ln)
                if m_pkg:
                    java_pkg = m_pkg.group(1)
                    break
    # Create impl classes under the specified package
    pkg_path = impl_base_package.split('.')
    target_dir = os.path.join(out_dir, 'src', 'main', 'java', *pkg_path)
    os.makedirs(target_dir, exist_ok=True)
    for svc in services:
        cname = svc + 'GrpcImpl'
        fpath = os.path.join(target_dir, cname + '.java')
        with open(fpath, 'w') as f:
            f.write(f"package {impl_base_package};\n\n")
            f.write("import net.devh.boot.grpc.server.service.GrpcService;\n")
            if java_pkg:
                f.write(f"import {java_pkg}.{svc}Grpc;\n\n")
            else:
                f.write("\n")
            f.write("@GrpcService\n")
            f.write(f"public class {cname} extends {svc}Grpc.{svc}ImplBase {{\n")
            f.write("    // TODO: implement RPC methods\n")
            f.write("}\n")
        print(f"Created dummy gRPC impl: {fpath}")


def copy_extras(extras, output_dir):
    for item in extras:
        src = item.get('src');
        dest = os.path.join(output_dir, item.get('dest', ''))
        if not src: continue
        if os.path.isdir(src):
            shutil.copytree(src, dest); print(f"Copied dir {src} -> {dest}")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True); shutil.copy(src, dest); print(
                f"Copied file {src} -> {dest}")


def prepare_output_dir(output_dir):
    parent = os.path.dirname(output_dir) or '.';
    os.makedirs(parent, exist_ok=True)
    if os.path.exists(output_dir): shutil.rmtree(output_dir)


def generate(config):
    out_dir = config.output_dir
    prepare_output_dir(out_dir)
    copy_project(config.existing_rest_project_root, out_dir, getattr(config, 'ignore', []))
    gradle_file = os.path.join(out_dir, 'build.gradle')
    shutil.copy(config.existing_build_gradle, gradle_file)
    inject_grpc_settings(gradle_file)
    inject_protobuf_config(gradle_file)
    inject_protobuf_block(gradle_file)
    # copy proto
    proto_dest = os.path.join(out_dir, 'src', 'main', 'proto')
    os.makedirs(proto_dest, exist_ok=True)
    shutil.copy(config.proto_file_path, proto_dest)
    # extra copy
    if getattr(config, 'extra_copy', []): copy_extras(config.extra_copy, out_dir)
    # generate impls from proto
    if hasattr(config, 'impl_base_package'):
        generate_service_impls(out_dir, config.impl_base_package, config.proto_file_path)
    # final build
    subprocess.run(['./gradlew', 'clean', 'build', '--quiet'], cwd=out_dir, check=True)
    print(f"gRPC project ready at {out_dir}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config-file', required=True)
    args = p.parse_args()
    cfg = load_config(args.config_file)
    generate(SimpleNamespace(**cfg))


if __name__ == '__main__':
    main()
