import argparse
import subprocess
import os
import yaml

def convert_openapi_to_proto_with_tool(openapi_spec_path, output_proto_path, package_name_hint, service_name_base_hint, annotate=False, googleapis_path=None):
    """
    Converts an OpenAPI specification file into a gRPC .proto file using openapi2proto.
    Optionally, validates the generated proto file using protoc with googleapis imports.

    Args:
        openapi_spec_path (str): Path to the OpenAPI YAML/JSON file.
        output_proto_path (str): Path where the generated .proto file will be saved.
        package_name_hint (str): A hint for the desired Protobuf package name.
                                 openapi2proto infers this, or uses OpenAPI extensions.
        service_name_base_hint (str): A hint for the desired gRPC service name.
                                      openapi2proto derives service names from OpenAPI tags.
        annotate (bool): Whether to include google.api.http options for grpc-gateway.
        googleapis_path (str, optional): Path to the cloned googleapis repository.
                                        Required if 'annotate' is True and you compile the generated proto.
    """
    if not os.path.exists(openapi_spec_path):
        print(f"Error: OpenAPI spec file not found at {openapi_spec_path}")
        return

    # --- Step 1: Generate the .proto file using openapi2proto ---
    command_openapi2proto = [
        "openapi2proto",
        "-spec", openapi_spec_path,
        "-out", output_proto_path,
    ]
    if annotate:
        command_openapi2proto.append("-annotate")

    print(f"\n--- Running openapi2proto command: {' '.join(command_openapi2proto)} ---")
    try:
        result = subprocess.run(
            command_openapi2proto,
            check=True,
            text=True,
            capture_output=True
        )
        print(f"Successfully converted OpenAPI to proto. Output saved to {output_proto_path}")
        if result.stderr:
            print("openapi2proto stderr (warnings/info):\n", result.stderr)

    except FileNotFoundError:
        print("Error: 'openapi2proto' command not found.")
        print("Please ensure openapi2proto is installed and accessible in your system's PATH.")
        print("Install it using: go install github.com/NYTimes/openapi2proto/cmd/openapi2proto@latest")
        return
    except subprocess.CalledProcessError as e:
        print(f"Error during openapi2proto conversion: {e}")
        print(f"Command: {e.cmd}")
        print(f"Return Code: {e.returncode}")
        print(f"Stdout:\n{e.stdout}")
        print(f"Stderr:\n{e.stderr}")
        return
    except Exception as e:
        print(f"An unexpected error occurred during openapi2proto call: {e}")
        return

    # --- Step 2: Validate the generated .proto file using protoc (if annotate is true and googleapis_path is provided) ---
    if annotate and googleapis_path:
        print(f"\n--- Validating generated proto with protoc for imports... ---")

        # Determine the directory of the output_proto_path
        proto_dir = os.path.dirname(output_proto_path)
        if not proto_dir: # If output_proto_path is just a filename (e.g., "demo.proto"), it's in current dir
            proto_dir = "." # Use current directory

        command_protoc_validate = [
            "protoc",
            f"--proto_path={proto_dir}",        # Path to the directory containing your generated proto
            f"--proto_path={googleapis_path}",  # Path to the cloned googleapis repository
            f"--descriptor_set_out={output_proto_path}.pb", # Output a file descriptor set for validation
            output_proto_path                   # The proto file to compile/validate
        ]

        try:
            result_protoc = subprocess.run(
                command_protoc_validate,
                check=True,
                text=True,
                capture_output=True
            )
            print(f"Validation successful: '{output_proto_path}' can resolve all imports.")
            # Clean up the generated .pb file
            if os.path.exists(f"{output_proto_path}.pb"):
                os.remove(f"{output_proto_path}.pb")
                print(f"Removed temporary descriptor set: {output_proto_path}.pb")

            if result_protoc.stdout:
                pass # protoc outputs compilation info to stdout if successful, often verbose
            if result_protoc.stderr:
                print("protoc stderr (warnings/info):\n", result_protoc.stderr)
        except FileNotFoundError:
            print("Error: 'protoc' command not found.")
            print("Please ensure the Protocol Buffer compiler (protoc) is installed and in your PATH.")
            print("Install it via Homebrew: `brew install protobuf` (macOS)")
            return
        except subprocess.CalledProcessError as e:
            print(f"Validation failed for '{output_proto_path}': {e}")
            print(f"Command: {e.cmd}")
            print(f"Return Code: {e.returncode}")
            print(f"Stdout:\n{e.stdout}")
            print(f"Stderr:\n{e.stderr}")
            print("\nThis error indicates that 'protoc' failed to compile the .proto file.")
            print("Common causes: incorrect --proto_path (if imports fail) or syntax errors in the generated proto.")
            print(f"Ensure that '{googleapis_path}' is the correct path to the cloned googleapis repository and that the proto file is within one of the --proto_path directories.")
            return
        except Exception as e:
            print(f"An unexpected error occurred during protoc validation: {e}")
            return
    elif annotate and not googleapis_path:
        print("\nWarning: '--annotate' was used but '--googleapis_path' was not provided. "
              "The generated .proto file might have unresolved imports if compiled by 'protoc' later without the correct path.")
    elif not annotate:
        print("\nSkipping protoc validation as '--annotate' flag was not set (no google/api imports expected).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert OpenAPI (Swagger) spec to gRPC Protobuf (.proto) using nytimes/openapi2proto. "
                    "Creates separate gRPC services based on OpenAPI tags."
    )
    parser.add_argument("openapi_file", type=str,
                        help="Path to the OpenAPI YAML/JSON file.")

    parser.add_argument("--output_proto_file", type=str,
                        required=True,
                        help="Path where the generated .proto file will be saved.")
    parser.add_argument("--package_name", type=str,
                        required=True,
                        help="Desired Protobuf package name (e.g., com.mastercard.hackathon). "
                             "Note: openapi2proto infers this, or uses OpenAPI extensions like x-proto-package for better control.")
    parser.add_argument("--service_name_base", type=str,
                        required=True,
                        help="A base name for the gRPC services. openapi2proto typically derives service names from OpenAPI tags. This argument acts as documentation/hint.")
    parser.add_argument("--annotate", action="store_true",
                        help="Include (google.api.http) options for grpc-gateway in the generated .proto file.")
    parser.add_argument("--googleapis_path", type=str,
                        help="Path to the cloned googleapis repository (e.g., /Users/yourname/src/googleapis). "
                             "Required if --annotate is used and you need to validate/compile the generated proto.")

    args = parser.parse_args()

    openapi_file = args.openapi_file
    output_proto_file = args.output_proto_file
    package_name_hint = args.package_name
    service_name_base_hint = args.service_name_base
    annotate = args.annotate
    googleapis_path = args.googleapis_path

    print("\n--- Hi, I'm a MACS assistant. I'm using 'nytimes/openapi2proto' to migrate your OpenAPI spec into gRPC Protobuf.---")
    print(f"\n\n--- Started working on converting {openapi_file} spec into grpc message.---")

    convert_openapi_to_proto_with_tool(
        openapi_file,
        output_proto_file,
        package_name_hint,
        service_name_base_hint,
        annotate,
        googleapis_path
    )