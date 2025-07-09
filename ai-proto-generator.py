import openai
import yaml
import os
import re  # Import the regular expression module


def convert_openapi_to_proto(openapi_spec_path, output_proto_path, openai_api_key):
    """
    Converts an OpenAPI (Swagger) specification file into a gRPC .proto file
    using the OpenAI API.

    Args:
        openapi_spec_path (str): Path to the OpenAPI YAML file.
        output_proto_path (str): Path where the generated .proto file will be saved.
        openai_api_key (str): Your OpenAI API key.
    """
    openai.api_key = openai_api_key

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
                {"role": "system",
                 "content": "You are a helpful assistant that converts OpenAPI specs to gRPC proto files."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        raw_proto_content = response.choices[0].message.content.strip()

        # Robust cleanup: Extract content strictly between ```proto and ```
        match = re.search(r"```proto\n(.*?)```", raw_proto_content, re.DOTALL)
        if match:
            proto_content = match.group(1).strip()
        else:
            # Fallback if the expected markdown fences are not found
            print("Warning: Could not find expected '```proto' and '```' fences. Saving raw content.")
            proto_content = raw_proto_content

        with open(output_proto_path, 'w') as f:
            f.write(proto_content)
        print(f"Successfully converted OpenAPI spec to {output_proto_path}")

    except openai.APIError as e:
        print(f"OpenAI API Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    openapi_file = '/Users/mani/hackathon/spring-hackathon-service/src/main/resources/cards.yaml'
    output_proto_file = 'cards.proto'

    openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please set the OPENAI_API_KEY environment variable with your OpenAI API key.")
    else:
        convert_openapi_to_proto(openapi_file, output_proto_file, openai_key)
