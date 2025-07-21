#!/usr/bin/env python3
"""
Scaffold a gRPC-enabled Spring Boot project from an existing REST-based application.
Reads config from JSON/YAML to parameterize:
  - existing_rest_project_root
  - existing_build_gradle
  - proto_file_path
  - output_dir
  - ignore patterns
  - extra_copy entries (with optional `when` conditions)
  - impl_base_package (optional): Java package for dummy service implementations
  - add_ai_capability (optional bool): whether to include AI starter & config
  - skip_gradle_build (optional bool): if true, skip running `./gradlew clean build`

It then:
  1. Copies the legacy project
  2. Resolves any `apply from: "$projectDir/..."`
  3. Injects gRPC/protobuf plugin & dependencies,
     adds the Protobuf Gradle plugin classpath under buildscript.dependencies
  4. Appends `protobuf { ... }` codegen block
  5. Updates `java.srcDirs` in root-level sourceSets.main
  6. Copies extra files/folders conditionally
  7. Generates dummy `{Service}GrpcImpl` classes
  8. Injects AI config into application.yaml if enabled
  9. Optionally runs Gradle build
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


def load_config(path):
    with open(path) as f:
        if path.lower().endswith(('.yaml', '.yml')):
            if not yaml:
                raise RuntimeError("PyYAML is required for YAML configs")
            return yaml.safe_load(f)
        return json.load(f)


def copy_project(src, dst, ignore_patterns):
    def _ignore(_, names):
        drop = []
        for n in names:
            for pat in ignore_patterns:
                if re.search(pat, n):
                    drop.append(n)
                    break
        return set(drop)

    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)
    print(f"Copied legacy project from {src} to {dst}")


def resolve_apply_from_scripts(src_root, dst_root, build_gradle_src):
    pattern = re.compile(r"apply\s+from:\s*['\"](?:\$?(?:projectDir|rootDir)/)?([^'\"]+\.gradle)['\"]")
    with open(build_gradle_src) as bgf:
        for ln in bgf:
            m = pattern.search(ln)
            if not m:
                continue
            rel = m.group(1)
            src_script = os.path.join(src_root, rel)
            dst_script = os.path.join(dst_root, rel)
            if os.path.isfile(src_script):
                os.makedirs(os.path.dirname(dst_script), exist_ok=True)
                shutil.copy(src_script, dst_script)
                print(f"Copied referenced Gradle script: {rel}")
            else:
                print(f"Warning: referenced Gradle script not found: {rel}")


def inject_grpc_settings(build_gradle, add_ai=False):
    lines = open(build_gradle).read().splitlines(keepends=True)
    out = []
    in_buildscript = False
    in_bs = False
    injected_cp = False
    in_root_deps = False

    for ln in lines:
        # New-style plugins DSL
        if ln.startswith('plugins {'):
            out.append(ln)
            indent = re.match(r"(\s*)", ln).group(1)
            out.append(f"{indent}    id 'com.google.protobuf' version '0.9.4'\n")
            continue
        # buildscript.dependencies sub-block (4-space indent)
        if ln.startswith('    dependencies {') and in_buildscript:
            in_bs = True
            out.append(ln)
            continue
        if in_bs:
            out.append(ln)
            if not injected_cp and ln.strip().startswith('classpath'):
                indent = re.match(r"(\s*)", ln).group(1)
                out.append(f"{indent}classpath 'com.google.protobuf:com.google.protobuf.gradle.plugin:0.9.5'\n")
                injected_cp = True
            if ln.strip() == '}':
                in_bs = False
            continue
        # buildscript block start/end
        if 'buildscript' in ln and '{' in ln:
            in_buildscript = True;
            out.append(ln);
            continue
        if in_buildscript and '}' in ln:
            in_buildscript = False;
            out.append(ln);
            continue

        # root-level dependencies (no leading space)
        if ln.startswith('dependencies {'):
            in_root_deps = True
            out.append(ln)
            out.extend([
                "    // gRPC dependencies added by generator started\n",
                "    implementation 'net.devh:grpc-spring-boot-starter:3.0.0.RELEASE'\n",
                "    implementation 'io.grpc:grpc-stub:1.57.2'\n",
                "    implementation 'io.grpc:grpc-protobuf:1.57.2'\n",
                "    implementation 'com.google.protobuf:protobuf-java:3.25.5'\n",
                "    implementation 'com.google.protobuf:protobuf-java-util:3.25.5'\n"
                "    // gRPC dependencies added by generator ends\n",
            ])
            if add_ai:
                out.extend([
                    "    // AI starter added by generator\n",
                    "    implementation 'org.springframework.ai:spring-ai-openai-spring-boot-starter:0.8.1'\n"
                ])
            continue
        if in_root_deps:
            out.append(ln)
            if ln.strip() == '}': in_root_deps = False
            continue

        # old-style apply plugin
        if "apply plugin:" in ln and "org.springframework.boot" in ln:
            out.append(ln)
            out.append("\n// -- gRPC support added by generator\n")
            out.append("apply plugin: 'com.google.protobuf'\n")
            continue

        # default copy
        out.append(ln)

    with open(build_gradle, 'w') as f:
        f.writelines(out)
    print(f"Injected buildscript classpath + plugin id + root deps{' + AI' if add_ai else ''} into {build_gradle}")


def inject_protobuf_config(build_gradle):
    block = r"""
// -- Protobuf codegen config added by generator
protobuf {
    protoc { artifact = 'com.google.protobuf:protoc:3.25.5' }
    plugins { grpc { artifact = 'io.grpc:protoc-gen-grpc-java:1.57.2' } }
    generateProtoTasks { all().each { t -> t.plugins { grpc {} } } }
}
"""
    with open(build_gradle, 'a') as f:
        f.write("\n" + block)
    print(f"Appended protobuf codegen config to {build_gradle}")


def inject_source_sets(build_gradle):
    lines = open(build_gradle).read().splitlines(keepends=True)
    out = []
    in_ss = in_main = in_java = False
    dm = dj = 0

    for ln in lines:
        m = re.match(r"(\s*)sourceSets\.main\.java\.srcDir", ln)
        if m:
            out.append(ln)
            indent = m.group(1)
            for p in ["$generatedSrcDir/src/main/java",
                      "build/generated/source/proto/main/grpc",
                      "build/generated/source/proto/main/java",
                      "src/main/proto"]:
                out.append(f"{indent}sourceSets.main.java.srcDir '{p}'\n")
            continue

        if not in_ss:
            out.append(ln)
            if "sourceSets" in ln and "{" in ln:
                in_ss = True
            continue

        if in_ss and not in_main:
            out.append(ln)
            if "main" in ln and "{" in ln:
                in_main, dm = True, 1
            continue

        if in_main and not in_java:
            out.append(ln)
            if "java" in ln and "{" in ln:
                in_java, dj = True, 1
            continue

        if in_java:
            arr = re.match(r"(\s*)(srcDirs\s*=\s*\[)(.*)(\])", ln)
            if arr:
                i, pre, ex, suf = arr.groups()
                comb = f"{i}{pre}{ex}, '$generatedSrcDir/src/main/java', 'build/generated/source/proto/main/grpc', 'build/generated/source/proto/main/java', 'src/main/proto'{suf}\n"
                out.append(comb)
            elif "srcDir" in ln:
                out.append(ln)
                indent = re.match(r"(\s*)", ln).group(1)
                for p in ["$generatedSrcDir/src/main/java",
                          "build/generated/source/proto/main/grpc",
                          "build/generated/source/proto/main/java",
                          "src/main/proto"]:
                    out.append(f"{indent}srcDir '{p}'\n")
            else:
                out.append(ln)

            dj += ln.count('{') - ln.count('}')
            if dj == 0:
                in_java = False
            continue

        out.append(ln)
        dm += ln.count('{') - ln.count('}')
        if dm == 0:
            in_main = in_ss = False

    with open(build_gradle, 'w') as f:
        f.writelines(out)
    print(f"Updated sourceSets in {build_gradle}")


def inject_application_yaml(root):
    res = os.path.join(root, 'src', 'main', 'resources')
    block = [
        '  ai:\n',
        '    openai:\n',
        '      api-key: "6feefb40-7d91-4e55-98d4-99e541f6a6bf"\n',
        '      chat:\n',
        '        base-url: http://localhost:11434\n',
        '        options:\n',
        '          model: llama3\n',
        '          temperature: 0.7\n'
    ]
    for name in ('application.yaml', 'application.yml'):
        path = os.path.join(res, name)
        if os.path.exists(path):
            lines = open(path).read().splitlines(keepends=True)
            out = []
            for ln in lines:
                out.append(ln)
                if ln.strip() == "spring:":
                    out.extend(block)
            with open(path, 'w') as f:
                f.writelines(out)
            print(f"Injected AI config into {path}")
            return
    os.makedirs(res, exist_ok=True)
    path = os.path.join(res, 'application.yaml')
    with open(path, 'w') as f:
        f.write("spring:\n")
        f.writelines(block)
    print(f"Created {path} with AI config")


def copy_extras(extras, root, cfg):
    for item in extras:
        if item.get('when') and not getattr(cfg, item['when'], False):
            continue
        src = item['src']
        dst = os.path.join(root, item.get('dest', ''))
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
        print(f"Copied extra {src} -> {dst}")


def generate_service_impls(root, base_pkg, proto_path):
    services = []
    java_pkg = None
    with open(proto_path) as pf:
        for ln in pf:
            m = re.match(r"\s*option\s+java_package\s*=\s*\"([^\"]+)\"", ln)
            if m: java_pkg = m.group(1)
            m2 = re.match(r"\s*service\s+(\w+)\s*\{", ln)
            if m2: services.append(m2.group(1))
    if not java_pkg:
        with open(proto_path) as pf:
            for ln in pf:
                m = re.match(r"\s*package\s+([\w\.]+);", ln)
                if m: java_pkg = m.group(1); break

    pkg_path = base_pkg.split('.')
    tgt = os.path.join(root, 'src', 'main', 'java', *pkg_path)
    os.makedirs(tgt, exist_ok=True)
    for svc in services:
        cls = svc + 'GrpcImpl'
        fp = os.path.join(tgt, cls + '.java')
        with open(fp, 'w') as f:
            f.write(f"package {base_pkg};\n\n")
            f.write("import net.devh.boot.grpc.server.service.GrpcService;\n")
            if java_pkg:
                f.write(f"import {java_pkg}.{svc}Grpc;\n\n")
            else:
                f.write("\n")
            f.write("@GrpcService\n")
            f.write(f"public class {cls} extends {svc}Grpc.{svc}ImplBase " "{\n")
            f.write("    // TODO: implement RPC methods\n}\n")
        print(f"Generated dummy impl: {fp}")


def prepare_output_dir(path):
    p = os.path.dirname(path) or '.'
    os.makedirs(p, exist_ok=True)
    if os.path.exists(path):
        shutil.rmtree(path)


def generate(cfg: SimpleNamespace):
    out = cfg.output_dir
    prepare_output_dir(out)

    copy_project(cfg.existing_rest_project_root, out, getattr(cfg, 'ignore', []))
    resolve_apply_from_scripts(cfg.existing_rest_project_root, out, cfg.existing_build_gradle)

    gradle_f = os.path.join(out, 'build.gradle')
    shutil.copy(cfg.existing_build_gradle, gradle_f)

    inject_grpc_settings(gradle_f, getattr(cfg, 'add_ai_capability', False))
    inject_protobuf_config(gradle_f)
    inject_source_sets(gradle_f)

    proto_dst = os.path.join(out, 'src', 'main', 'proto')
    os.makedirs(proto_dst, exist_ok=True)
    shutil.copy(cfg.proto_file_path, proto_dst)

    if getattr(cfg, 'extra_copy', []):
        copy_extras(cfg.extra_copy, out, cfg)

    # if getattr(cfg, 'impl_base_package', None):
    #     generate_service_impls(out, cfg.impl_base_package, cfg.proto_file_path)

    if getattr(cfg, 'add_ai_capability', False):
        inject_application_yaml(out)

    if not getattr(cfg, 'skip_gradle_build', False):
        subprocess.run(['./gradlew', 'clean', 'build', '--quiet'], cwd=out, check=True)
        print(f"gRPC project built at {out}")
    else:
        print(f"Skipped Gradle build; project staged at {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config-file', required=True)
    args = p.parse_args()
    cfg = load_config(args.config_file)
    generate(SimpleNamespace(**cfg))


if __name__ == '__main__':
    main()
