import argparse
import openai
import yaml
import os
import re
from collections import defaultdict


def clean_proto_content(raw_content):
    """
    Extracts the .proto content strictly between ```proto and ``` markdown fences.

    Args:
        raw_content (str): The raw string content received from the OpenAI API.

    Returns:
        str: The cleaned .proto content, or the raw content if fences are not found.
    """
    # Robust cleanup: Extract content strictly between ```protobuf and ```
    match = re.search(r"```protobuf\n(.*?)```", raw_content, re.DOTALL)
    match1 = re.search(r"```proto\n(.*?)```", raw_content, re.DOTALL)
    match_generic = re.search(r"```(?:\w+)?\n(.*?)```", raw_content, re.DOTALL)  # Generic code block

    if match:
        return match.group(1).strip()
    elif match1:
        return match1.group(1).strip()
    elif match_generic:
        # If no specific proto/protobuf block, try a generic code block
        return match_generic.group(1).strip()
    else:
        # If no markdown fences are found, return the raw content, assuming it's already clean
        return raw_content.strip()


def camel_case(s):
    """Converts a string to PascalCase (for gRPC service names)."""
    if not s:
        return ""
    # Replace non-alphanumeric with spaces, then title case each word, then join
    s = re.sub(r'[^a-zA-Z0-9]', ' ', s)
    return ''.join(word.capitalize() for word in s.split())


def extract_unique_tags(openapi_spec):
    """
    Extracts all unique tags from an OpenAPI specification.

    Args:
        openapi_spec (dict): The parsed OpenAPI specification.

    Returns:
        set: A set of unique tag names.
    """
    unique_tags = set()
    paths = openapi_spec.get('paths', {})
    for path_item in paths.values():
        for method_obj in path_item.values():
            if isinstance(method_obj, dict): # Ensure it's an operation object
                tags = method_obj.get('tags')
                if tags:
                    for tag in tags:
                        unique_tags.add(tag)
    return sorted(list(unique_tags)) # Sort for consistent prompt generation


def call_openai_for_proto_conversion(openapi_spec_str, openai_api_key, package_name, service_name_base, model_name, unique_tags):
    """
    Calls the OpenAI API to convert OpenAPI spec to proto content.

    Args:
        openapi_spec_str (str): The OpenAPI YAML specification as a string.
        openai_api_key (str): Your OpenAI API key.
        package_name (str): The desired package name for the .proto file.
        service_name_base (str): A base name for the gRPC service if no tags or for untagged ops.
        model_name (str): The OpenAI model to use for the conversion.
        unique_tags (list): A list of unique tags found in the OpenAPI spec.

    Returns:
        str: The raw content received from OpenAI, or None if an error occurs.
    """
    openai.api_key = openai_api_key

    # Generate service names based on unique tags
    service_instructions = []
    if unique_tags:
        for tag in unique_tags:
            # Convert tag to PascalCase for service name
            grpc_service_name = camel_case(tag) + "Service"
            service_instructions.append(f"- For operations tagged with '{tag}', create a gRPC service named `{grpc_service_name}`.")
        # Add instruction for operations without explicit tags
        service_instructions.append(f"- For any operations without explicit tags, group them under a general service named `{camel_case(service_name_base)}`.")
    else:
        # If no tags, use the provided base service name
        service_instructions.append(f"- Create a single gRPC service named `{camel_case(service_name_base)}` for all operations.")

    service_instructions_str = "\n    ".join(service_instructions)


    prompt = f"""
    You are an expert in API design, specifically in converting RESTful OpenAPI specifications to gRPC .proto definitions.
    Convert the following OpenAPI (Swagger) YAML specification into a gRPC .proto file.

    Follow these guidelines for the .proto file generation:
    1.  Use `syntax = "proto3";`.
    2.  Define a `package` name: `{package_name}`.
    3.  Map OpenAPI schemas to `message` definitions. **Define messages once and reuse them across services.**
    4.  Map OpenAPI paths and HTTP methods to gRPC `service` and `rpc` definitions.
        **IMPORTANT: Create separate gRPC services based on OpenAPI `tags`.**
        {service_instructions_str}
        Ensure service names are in PascalCase (e.g., `UserService`, `ProductService`).
    5.  For `rpc` methods, use appropriate request and response messages.
    6.  Ensure data types are correctly mapped (e.g., `string`, `int32`, `bool`, `bytes`).
    7.  For array types in OpenAPI, use `repeated` in proto.
    8.  For `additionalProperties: true` in OpenAPI, use `google.protobuf.Struct` or `map<string, string>` if the value types are consistent, otherwise `google.protobuf.Any`. For simplicity, if the example shows simple key-value pairs, use `map<string, string>`.
    9.  Include comments in the .proto file where necessary, especially for complex mappings or design decisions.
    10. Ensure all fields have appropriate numerical tags.
    11. Handle optional fields by making them not `required` in OpenAPI and just defining them in proto.
    12. For error handling, define a common `ErrorDetails` message and use it in `rpc` responses if applicable, or rely on gRPC status codes. For this conversion, just define the `ErrorDetails` message.
    13. **Standard Message Definitions for Common Patterns:**
        - If an RPC method has no explicit response body in OpenAPI (e.g., a 204 No Content response), define a custom empty message called `Empty` and use it as the response message.
        - For RPCs that correspond to REST endpoints taking a single path parameter or query parameter that uniquely identifies a resource (e.g., `/resources/{{id}}`), define a dedicated request message for that parameter. This message should be named `[ResourceName]IdRequest` (e.g., `DigitalCardIdRequest`) and contain a single `string` field named `id` (or the specific parameter name like `digitalCardId`).
        - **Path Parameter to Message Field Mapping in the body:** For RPCs corresponding to PUT/PATCH semantics of REST endpoints that has path parameters (e.g., `/cards/{{digitalCardId}}`) and a request body both, ensure path parameters are included as explicit fields within the relevant gRPC request body message. meaning both should be there in message. (e.g., for rpc `UpdateCardByDigitalCardId` message `CardUpdateDetails` would contain both `{{digitalCardId}}` field and the update message fields).
    14. **Handling Array Responses in RPCs:**
        - If an OpenAPI endpoint returns an array or list of items (e.g., `responses: {{ '200': {{ schema: {{ type: array, items: {{ $ref: '#/components/schemas/CardDetails' }} }} }} }}`), the corresponding gRPC RPC should return a **stream of the message type** (e.g., `returns (stream CardDetails)`).
        - Alternatively, if it's a unary RPC that needs to return a list in a single response, define a new wrapper message that contains a `repeated` field for the list (e.g., `message CardDetailsList {{ repeated CardDetails cards = 1; }}` and then `returns (CardDetailsList)`).
        - **Crucially, do NOT use `repeated` directly in the RPC return signature (e.g., `returns (repeated CardDetails)` is incorrect).
    15. **Output Structure:** The final `.proto` file should contain the package definition, then all necessary message definitions, followed by all service definitions.

    Here is the OpenAPI YAML specification:

    ```yaml
    {openapi_spec_str}
    ```

    Generate only the .proto file content. Do not include any conversational text or explanations outside the .proto content.
    """

    print(f"\nIt's in progress. Hang on!")
    try:
        response = openai.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system",
                 "content": "You are a helpful assistant that converts OpenAPI specs to gRPC proto files."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"OpenAI API Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during OpenAI call: {e}")
        return None


def convert_openapi_to_proto(openapi_spec_path, output_proto_path, openai_api_key, package_name, service_name_base, model_name, skip_openai_call=False,
                             raw_content_for_cleanup=None):
    """
    Converts an OpenAPI (Swagger) specification file into a gRPC .proto file.
    Can optionally skip the OpenAI API call and use provided raw content for cleanup.

    Args:
        openapi_spec_path (str): Path to the OpenAPI YAML file.
        output_proto_path (str): Path where the generated .proto file will be saved.
        openai_api_key (str): Your OpenAI API key.
        package_name (str): The desired package name for the .proto file.
        service_name_base (str): A base name for the gRPC service if no tags or for untagged ops.
        model_name (str): The OpenAI model to use for the conversion.
        skip_openai_call (bool): If True, skips the OpenAI API call and uses raw_content_for_cleanup.
        raw_content_for_cleanup (str, optional): Raw content to be cleaned if skip_openai_call is True.
    """
    try:
        with open(openapi_spec_path, 'r') as f:
            openapi_spec = yaml.safe_load(f)
        openapi_spec_str = yaml.dump(openapi_spec, indent=2)
    except FileNotFoundError:
        print(f"Error: OpenAPI spec file not found at {openapi_spec_path}")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing OpenAPI spec file: {e}")
        return

    # Extract unique tags to inform the AI
    unique_tags = extract_unique_tags(openapi_spec)
    print(f"Detected unique tags in OpenAPI spec: {unique_tags if unique_tags else 'None'}")

    raw_proto_content = None
    if not skip_openai_call:
        raw_proto_content = call_openai_for_proto_conversion(
            openapi_spec_str,
            openai_api_key,
            package_name,
            service_name_base, # Renamed to service_name_base as it's not the final service name
            model_name,
            unique_tags
        )
    elif raw_content_for_cleanup is not None:
        raw_proto_content = raw_content_for_cleanup
    else:
        print("Error: When skip_openai_call is True, raw_content_for_cleanup must be provided.")
        return

    if raw_proto_content:
        proto_content = clean_proto_content(raw_proto_content)
        with open(output_proto_path, 'w') as f:
            f.write(proto_content)
        print(f"Done! Successfully migrated content and saved to {output_proto_path}")
    else:
        print("No content to process. Exiting.")


if __name__ == "__main__":
    openai_key = os.getenv("OPENAI_API_KEY")

    parser = argparse.ArgumentParser(
        description="Convert OpenAPI (Swagger) spec to gRPC Protobuf (.proto) with service per tag."
    )
    # openapi_file is a positional argument, inherently mandatory
    parser.add_argument("openapi_file", type=str,
                        help="Path to the OpenAPI YAML/JSON file.")

    # Make these arguments mandatory by setting required=True and removing default
    parser.add_argument("--output_proto_file", type=str,
                        required=True,
                        help="Path where the generated .proto file will be saved.")
    parser.add_argument("--package_name", type=str,
                        required=True,
                        help="Desired Protobuf package name (e.g., com.mastercard.hackathon).")
    parser.add_argument("--base_service_name", type=str,
                        default="DefaultService",
                        help="A base name for the gRPC service if no tags are found, or for untagged operations (e.g., ApiService). If tags are present, services will be generated per tag. (default: DefaultService)")


    # The --model argument remains optional with a default
    parser.add_argument("--model", type=str,
                        default="gpt-4",
                        help="The OpenAI model to use for conversion (default: gpt-4). "
                             "You can use 'gpt-3.5-turbo' for faster but potentially less accurate results.")

    args = parser.parse_args()

    # Accessing arguments
    openapi_file = args.openapi_file
    output_proto_file = args.output_proto_file
    package_name = args.package_name
    base_service_name = args.base_service_name # Changed from service_name to base_service_name
    model_name = args.model

    if not openai_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please set the OPENAI_API_KEY environment variable with your OpenAI API key.")
    else:
        print("\n--- Hi, I'm a MACS assistant. I can migrate the existing OpenAPI spec into gRPC message.---")
        print(f"\n\n--- Started working on converting {openapi_file} spec into gRPC messages based on OpenAPI tags.---")

        convert_openapi_to_proto(
            openapi_file,
            output_proto_file,
            openai_key,
            package_name,
            base_service_name,
            model_name
        )