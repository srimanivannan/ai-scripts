import ollama
import json
import yaml
import os
import re  # Import the regular expression module
import argparse


def clean_proto_content(raw_content):
    """
    Extracts the .proto content strictly between ```protobuf or ```proto markdown fences.

    Args:
        raw_content (str): The raw string content received from the LLM.

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


def call_ollama_for_proto_conversion(openapi_spec_str, model_name="llama3"):
    """
    Calls the Ollama API to convert OpenAPI spec to proto content.

    Args:
        openapi_spec_str (str): The OpenAPI YAML/JSON specification as a string.
        model_name (str): The name of the Ollama model to use (e.g., "llama3", "codellama").

    Returns:
        str: The raw content received from Ollama, or None if an error occurs.
    """
    print(f"\nIt's in progress. Hang on!")

    # The prompt guides the LLM on how to perform the conversion.
    # It's crucial to be as specific as possible about the desired output format and mapping.
    # Retaining the specific rules from your original prompt.
    prompt = f"""
    You are an expert in API design and Protobuf. Your task is to convert the following OpenAPI (Swagger) 
    specification into a gRPC Protobuf (.proto) specification.

    Here are the rules for conversion:
    1. Use `syntax = "proto3";`.
    2. Define a `package` name (e.g., `com.mastercard.hackathon`).
    3. **Map ALL OpenAPI schemas (objects) and `$ref` references to distinct, top-level Protobuf `message` definitions within the package.**
        For example, if OpenAPI has a schema for `BillingAddress`, define a `message BillingAddress {{ ... }}` at the top level, not nested inside another message.
    4. Map OpenAPI paths and HTTP methods to a `service` and `rpc` definitions.
        **IMPORTANT:** Name the gRPC service `HackathonService`.
    5. **Standard Message Definitions for Common Patterns:**
        - **If an RPC method has no explicit response body in OpenAPI (e.g., a 204 No Content response), define a custom empty message called `Empty` and use it as the response message.**
        - **For RPCs that correspond to REST endpoints taking a single path parameter or query parameter that uniquely identifies a resource (e.g., `/resources/{id}`), ALWAYS define a dedicated request message for that parameter. This message should be named `[ResourceName]IdRequest` (e.g., `DigitalCardIdRequest`) and contain a single `string` field named `id` (or the specific parameter name like `digitalCardId`). Do NOT use primitive types (like `string` or `int32`) directly as RPC arguments.**
        - **Path Parameter to Message Field Mapping in the body:** For RPCs corresponding to PUT/PATCH semantics of REST endpoints that have path parameters (e.g., `/items/{{itemId}}/update`) AND a request body, ensure path parameters are included as explicit fields within the relevant gRPC request body message. Meaning both should be there in message. (e.g., for rpc `UpdateCardByDigitalCardId` message `CardUpdateDetails` would contain both `{{digitalCardId}}` field and the update message fields).
    6. Handling Array Responses in RPCs:
        - **If an OpenAPI endpoint returns an array or list of items (e.g., `responses: {{ '200': {{ schema: {{ type: array, items: {{ $ref: '#/components/schemas/CardDetails' }} }} }} }}`), the corresponding gRPC RPC should return a `stream` of the message type (e.g., `returns (stream CardDetails)`).**
        - **Alternatively, if it's a unary RPC that needs to return a list in a single response, define a new wrapper message that contains a `repeated` field for the list (e.g., `message CardDetailsList {{ repeated CardDetails cards = 1; }}` and then `returns (CardDetailsList)`).**
        - **Crucially, do NOT use `repeated` directly in the RPC return signature (e.g., `returns (repeated CardDetails)` is incorrect).**
    7. Required Imports for Google's Well-Known Types:
        - If `google.protobuf.Empty` is used, include `import "google/protobuf/empty.proto";` at the top of the file.
        - If `google.protobuf.Timestamp` is used, include `import "google/protobuf/timestamp.proto";` at the top of the file.
        - If `google.protobuf.Struct` or `google.protobuf.Any` are used, include `import "google/protobuf/struct.proto";` or `import "google/protobuf/any.proto";` respectively.
    8. **For `rpc` methods, use appropriate request and response messages. **Each RPC method must have exactly one request message and one response message.**
    9. Ensure data types are correctly mapped (e.g., `string`, `int32`, `bool`, `bytes`).
    10. For array types in OpenAPI, use `repeated` in proto.
    11. For `additionalProperties: true` in OpenAPI, use `google.protobuf.Struct` or `map<string, string>` if the value types are consistent, otherwise `google.protobuf.Any`. For simplicity, if the example shows simple key-value pairs, use `map<string, string>`.
    12. Include comments in the .proto file where necessary, especially for complex mappings or design decisions.
    13. Ensure all fields have appropriate numerical tags.
    14. Handle optional fields by making them not `required` in OpenAPI and just defining them in proto.
    15. For error handling, define a common `ErrorDetails` message and use it in rpc responses if applicable, or rely on gRPC status codes. For this conversion, just define the `ErrorDetails` message.

    Here is the OpenAPI YAML specification:

    ```yaml
    {openapi_spec_str}
    ```

    Generate only the .proto file content. Do not include any conversational text or explanations outside the .proto content.
    """  # Corrected: Using openapi_spec_str directly in the f-string

    try:
        response = ollama.chat(
            model=model_name,
            messages=[
                {'role': 'user', 'content': prompt}
            ],
            stream=False,  # Get the complete response at once
            options={
                'temperature': 0.7,
                'num_predict': 2000  # Max tokens for Ollama
            }
        )
        return response['message']['content'].strip()
    except ollama.ResponseError as e:
        print(f"Error communicating with Ollama: {e}")
        print("Please ensure the Ollama server is running and the model is available.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during Ollama call: {e}")
        return None


def convert_openapi_to_proto(openapi_file_path, output_proto_file_path, model_name="llama3", skip_ollama_call=False,
                             raw_content_for_cleanup=None):
    """
    Converts an OpenAPI (Swagger) specification file into a gRPC .proto file.
    Can optionally skip the Ollama API call and use provided raw content for cleanup.

    Args:
        openapi_file_path (str): Path to the OpenAPI YAML/JSON file.
        output_proto_file_path (str): Path where the generated .proto file will be saved.
        model_name (str): The name of the Ollama model to use.
        skip_ollama_call (bool): If True, skips the Ollama API call and uses raw_content_for_cleanup.
        raw_content_for_cleanup (str, optional): Raw content to be cleaned if skip_ollama_call is True.
    """
    try:
        with open(openapi_file_path, 'r') as f:
            if openapi_file_path.endswith('.json'):
                openapi_spec = json.load(f)
            elif openapi_file_path.endswith('.yaml') or openapi_file_path.endswith('.yml'):
                openapi_spec = yaml.safe_load(f)
            else:
                print("Error: Input file must be a .json, .yaml, or .yml file.")
                return
        openapi_spec_str = yaml.dump(openapi_spec, indent=2)  # Ensure YAML string for prompt
    except FileNotFoundError:
        print(f"Error: OpenAPI spec file not found at '{openapi_file_path}'")
        return
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        print(f"Error parsing OpenAPI spec file: {e}")
        return

    raw_proto_content = None
    if not skip_ollama_call:
        raw_proto_content = call_ollama_for_proto_conversion(openapi_spec_str, model_name)
    elif raw_content_for_cleanup is not None:
        raw_proto_content = raw_content_for_cleanup
    else:
        print("Error: When skip_ollama_call is True, raw_content_for_cleanup must be provided.")
        return

    if raw_proto_content:
        proto_content = clean_proto_content(raw_proto_content)
        with open(output_proto_file_path, 'w') as f:
            f.write(proto_content)
        print(f"Done! Successfully migrated content and saved to {output_proto_file_path}")
    else:
        print("No content to process. Exiting.")


if __name__ == "__main__":
    # Specify the path to your OpenAPI spec file here.
    # Example: openapi_file = "path/to/your/api_spec.yaml"
    # openapi_file = "/Users/e117686/repos/hackathon/spring-hackathon-service/src/main/resources/cards.yaml" # <--- Update this path to your actual OpenAPI file

    # output_proto_file = "output_api.proto" # You can change the output file name

    parser = argparse.ArgumentParser(description="Convert OpenAPI (Swagger) spec to gRPC Protobuf (.proto)")
    parser.add_argument("openapi_file", type=str, help="Path to the OpenAPI YAML/JSON file.")
    parser.add_argument("--output_proto_file", type=str, default="output_api.proto",
                        help="Path where the generated .proto file will be saved (default: output_api.proto).")
    parser.add_argument("--model", type=str, default="llama3",
                        help="The Ollama model to use for conversion (default: llama3).")

    args = parser.parse_args()

    openapi_file = args.openapi_file
    output_proto_file = args.output_proto_file
    model_name = args.model

    # --- Option 1: Call Ollama API and then clean (standard workflow) ---
    print("\n--- Hi, I'm a MACS assistant. I can migrate the existing openapi spec into grpc message.---")
    print(f"\n--- Started working on converting {openapi_file} spec into grpc message.---")
    convert_openapi_to_proto(openapi_file, output_proto_file, model_name="llama3")

    # --- Option 2: Skip Ollama API call and only run cleanup on a predefined string ---
    # This is useful for debugging the cleanup logic without incurring API costs.
    # print("\n--- Running cleanup only (skipping Ollama API call) ---")
    # proto_file_for_cleanup_path = 'cards.proto' # Assuming you have a dummy cards.proto here
    # read_content_for_cleanup = None
    # if os.path.exists(proto_file_for_cleanup_path):
    #     try:
    #         with open(proto_file_for_cleanup_path, 'r') as f:
    #             read_content_for_cleanup = f.read()
    #         print(f"Read content from {proto_file_for_cleanup_path} for cleanup.")
    #     except Exception as e:
    #         print(f"Error reading {proto_file_for_cleanup_path}: {e}")
    # else:
    #     print(f"Error: {proto_file_for_cleanup_path} not found. Cannot perform cleanup without content.")

    # if read_content_for_cleanup:
    #     convert_openapi_to_proto(
    #         openapi_file, # Still needs this for file existence check, but won't read it for prompt
    #         'cards_double_checked_file.proto', # Output to a new file to distinguish
    #         model_name="llama3", # Model name still needed by function signature
    #         skip_ollama_call=True,
    #         raw_content_for_cleanup=read_content_for_cleanup
    #     )
    # else:
    #     print("Skipping cleanup only option due to missing content.")
