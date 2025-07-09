import openai
import yaml
import os
import re # Import the regular expression module

def clean_proto_content(raw_content):
    """
    Extracts the .proto content strictly between ```proto and ``` markdown fences.
    
    Args:
        raw_content (str): The raw string content received from the OpenAI API.

    Returns:
        str: The cleaned .proto content, or the raw content if fences are not found.
    """
    # Robust cleanup: Extract content strictly between ```proto and ```
    match = re.search(r"```proto\n(.*?)```", raw_content, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        # Fallback if the expected markdown fences are not found
        print("Warning: Could not find expected '```protobuf' and '```' fences. Returning raw content.")
        return raw_content

def call_openai_for_proto_conversion(openapi_spec_str, openai_api_key):
    """
    Calls the OpenAI API to convert OpenAPI spec to proto content.

    Args:
        openapi_spec_str (str): The OpenAPI YAML specification as a string.
        openai_api_key (str): Your OpenAI API key.

    Returns:
        str: The raw content received from OpenAI, or None if an error occurs.
    """
    openai.api_key = openai_api_key

    prompt = f"""
    You are an expert in API design, specifically in converting RESTful OpenAPI specifications to gRPC .proto definitions.
    Convert the following OpenAPI (Swagger) YAML specification into a gRPC .proto file.

    Follow these guidelines for the .proto file generation:
    1.  Use `syntax = "proto3";`.
    2.  Define a `package` name (e.g., `com.mastercard.hackathon`).
    3.  Map OpenAPI schemas to `message` definitions.
    4.  Map OpenAPI paths and HTTP methods to a `service` and `rpc` definitions.
        **IMPORTANT:** Name the gRPC service `HackathonService`.
    5.  For `rpc` methods, use appropriate request and response messages.
    6.  Ensure data types are correctly mapped (e.g., `string`, `int32`, `bool`, `bytes`).
    7.  For array types in OpenAPI, use `repeated` in proto.
    8.  For `additionalProperties: true` in OpenAPI, use `google.protobuf.Struct` or `map<string, string>` if the value types are consistent, otherwise `google.protobuf.Any`. For simplicity, if the example shows simple key-value pairs, use `map<string, string>`.
    9.  Include comments in the .proto file where necessary, especially for complex mappings or design decisions.
    10. Ensure all fields have appropriate numerical tags.
    11. Handle optional fields by making them not `required` in OpenAPI and just defining them in proto.
    12. For error handling, define a common `ErrorDetails` message and use it in `rpc` responses if applicable, or rely on gRPC status codes. For this conversion, just define the `ErrorDetails` message.
    13. **Custom Message Requirement:**
        - Define a new message called `DigitalCardIdRequest` with a single `string` field named `digitalCardId`.
        - Use `DigitalCardIdRequest` as the request message for `rpc GetCardByDigitalCardId` and `rpc DeleteCardByDigitalCardId`.
        - Define a new empty message called `Empty` (if not already defined by `google.protobuf.Empty`).
        - Use this custom `Empty` message as the response for `rpc DeleteCardByDigitalCardId`.
    Here is the OpenAPI YAML specification:

    ```yaml
    {openapi_spec_str}
    ```

    Generate only the .proto file content. Do not include any conversational text or explanations outside the .proto content.
    """

    print("Sending request to OpenAI API...")
    try:
        response = openai.chat.completions.create(
            model="gpt-4",  # You can use "gpt-3.5-turbo" for faster but potentially less accurate results
            messages=[
                {"role": "system", "content": "You are a helpful assistant that converts OpenAPI specs to gRPC proto files."},
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

def convert_openapi_to_proto(openapi_spec_path, output_proto_path, openai_api_key, skip_openai_call=False, raw_content_for_cleanup=None):
    """
    Converts an OpenAPI (Swagger) specification file into a gRPC .proto file.
    Can optionally skip the OpenAI API call and use provided raw content for cleanup.

    Args:
        openapi_spec_path (str): Path to the OpenAPI YAML file.
        output_proto_path (str): Path where the generated .proto file will be saved.
        openai_api_key (str): Your OpenAI API key.
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

    raw_proto_content = None
    if not skip_openai_call:
        raw_proto_content = call_openai_for_proto_conversion(openapi_spec_str, openai_api_key)
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
    openapi_file = '/Users/mani/hackathon/spring-hackathon-service/src/main/resources/cards.yaml'
    output_proto_file = 'cards.proto' # Keeping the output file name consistent
    
    openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please set the OPENAI_API_KEY environment variable with your OpenAI API key.")
    else:
        # --- Option 1: Call OpenAI API and then clean (standard workflow) ---
        print("\n--- Hi, I'm a MACS AI assitant. I can migrate the exsiting openapi spec into grpc message.---")
        print(f"--- Started working on converting  {openapi_file} spec into grpc message.---")

        #convert_openapi_to_proto(openapi_file, output_proto_file, openai_key)

        # --- Option 2: Skip OpenAI API call and only run cleanup on a predefined string ---
        # This is useful for debugging the cleanup logic without incurring API costs.
        # print("\n--- Running cleanup only (skipping OpenAI API call) ---")
        
        # # Read content from cards.proto for cleanup
        proto_file_for_cleanup_path = 'cards.proto'
        read_content_for_cleanup = None
        if os.path.exists(proto_file_for_cleanup_path):
            try:
                with open(proto_file_for_cleanup_path, 'r') as f:
                    read_content_for_cleanup = f.read()
                #print(f"Read content from {proto_file_for_cleanup_path} for cleanup.")
            except Exception as e:
                print(f"Error reading {proto_file_for_cleanup_path}: {e}")
        else:
            print(f"Error: {proto_file_for_cleanup_path} not found. Cannot perform cleanup without content.")

        if read_content_for_cleanup:
            convert_openapi_to_proto(
                openapi_file, # Still needs this for file existence check, but won't read it for prompt
                'cards_double_checked_file.proto', # Output to a new file to distinguish
                openai_key, # API key still needed by function signature, but won't be used if skip_openai_call=True
                skip_openai_call=True,
                raw_content_for_cleanup=read_content_for_cleanup
            )
        else:
            print("Skipping cleanup only option due to missing content.")