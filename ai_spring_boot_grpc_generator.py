import os
import shutil
import sys # Import sys to check Python version

def copy_directory_robust(src, dest):
    """
    Copies a directory from src to dest, handling cases where dest already exists.
    This function provides a workaround for Python versions older than 3.8
    which do not support the `dirs_exist_ok` argument in shutil.copytree.
    It ensures the destination directory is clean before copying.
    """
    if os.path.exists(dest):
        if os.path.isdir(dest):
            # If the destination directory exists, remove it to ensure a clean copy.
            # This emulates the behavior of dirs_exist_ok=True by allowing overwrite.
            print(f"Removing existing directory {dest} before copying.")
            shutil.rmtree(dest)
        else:
            # If dest exists but is a file (unexpected), remove it.
            print(f"Removing existing file {dest} (unexpected) before copying.")
            os.remove(dest)
    
    # Now, copy the directory. The destination should not exist at this point.
    shutil.copytree(src, dest)
    print(f"Successfully copied directory from {src} to {dest}")


def generate_spring_boot_grpc_project(
    project_name,
    group_id,
    artifact_id,
    java_version,
    spring_boot_version,
    proto_file_path,
    output_dir,
    existing_yaml_path,
    existing_liqubase_file, # New parameter for Liquibase file
    existing_entities_dir,
    existing_repositories_dir,
    existing_domain_dir=None, # Optional, as not all projects have a separate 'domain' package
    existing_adapter_dir=None # Optional, same as above
):
    """
    Generates a seed Spring Boot gRPC project with Gradle, Java 17,
    and PostgreSQL JPA dependency, using a provided .proto file.
    It copies existing application.yaml, Entities, Repositories, Domain,
    and Adapter files/directories from specified paths.

    Args:
        project_name (str): The name of the Spring Boot project.
        group_id (str): The Maven/Gradle group ID (e.g., com.example).
        artifact_id (str): The Maven/Gradle artifact ID (e.g., my-grpc-service).
        java_version (str): The Java version (e.g., '17').
        spring_boot_version (str): The Spring Boot version (e.g., '3.2.0').
        proto_file_path (str): Path to the generated .proto file.
        output_dir (str): Directory where the new project will be created.
        existing_yaml_path (str): Path to the existing application.yaml file.
        existing_liqubase_file (str): Path to the existing Liquibase SQL file (e.g., 1-datasource.sql).
        existing_entities_dir (str): Path to the directory containing existing JPA Entity classes.
        existing_repositories_dir (str): Path to the directory containing existing JPA Repository interfaces.
        existing_domain_dir (str, optional): Path to the directory containing existing domain classes.
        existing_adapter_dir (str, optional): Path to the directory containing existing adapter classes.
    """

    base_path = os.path.join(output_dir, project_name)
    # The main Java path where new and copied Java files will reside
    main_java_base_path = os.path.join(base_path, 'src/main/java', *group_id.split('.'))
    main_resources_path = os.path.join(base_path, 'src/main/resources')
    proto_target_path = os.path.join(base_path, 'src/main/proto')

    # Create base directory structure
    os.makedirs(main_java_base_path, exist_ok=True)
    os.makedirs(main_resources_path, exist_ok=True)
    os.makedirs(proto_target_path, exist_ok=True)

    print(f"Creating project structure in: {base_path}")

    # 1. Copy the .proto file
    if os.path.exists(proto_file_path):
        shutil.copy(proto_file_path, proto_target_path)
        print(f"Copied {os.path.basename(proto_file_path)} to {proto_target_path}")
    else:
        print(f"Error: Proto file not found at {proto_file_path}. Please ensure it exists.")
        return

    # 2. Copy existing application.yaml
    if os.path.exists(existing_yaml_path):
        shutil.copy(existing_yaml_path, main_resources_path)
        print(f"Copied {os.path.basename(existing_yaml_path)} to {main_resources_path}")
    else:
        print(f"Error: Existing application.yaml not found at {existing_yaml_path}. Skipping.")

    # 2.1 Copy existing Liquibase SQL file
    if os.path.exists(existing_liqubase_file):
        # Ensure the db/changelog directory exists within resources
        liquibase_target_dir = os.path.join(main_resources_path, 'db', 'changelog')
        os.makedirs(liquibase_target_dir, exist_ok=True)
        shutil.copy(existing_liqubase_file, liquibase_target_dir)
        print(f"Copied {os.path.basename(existing_liqubase_file)} to {liquibase_target_dir}")
    else:
        print(f"Error: Existing Liquibase file not found at {existing_liqubase_file}. Skipping.")


    # 3. Copy existing Entities
    # target_entities_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'model')
    # if os.path.exists(existing_entities_dir) and os.path.isdir(existing_entities_dir):
    #     os.makedirs(os.path.dirname(target_entities_path), exist_ok=True) # Ensure parent dir exists
    #     copy_directory_robust(existing_entities_dir, target_entities_path)
    # else:
    #     print(f"Error: Existing entities directory not found or not a directory at {existing_entities_dir}. Skipping entity copy.")

    # 4. Copy existing Repositories
    # target_repositories_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'repository')
    # if os.path.exists(existing_repositories_dir) and os.path.isdir(existing_repositories_dir):
    #     os.makedirs(os.path.dirname(target_repositories_path), exist_ok=True) # Ensure parent dir exists
    #     copy_directory_robust(existing_repositories_dir, target_repositories_path)
    # else:
    #     print(f"Error: Existing repositories directory not found or not a directory at {existing_repositories_dir}. Skipping repository copy.")

    # 5. Copy existing Domain (Optional)
    if existing_domain_dir:
        target_domain_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'domain')
        if os.path.exists(existing_domain_dir) and os.path.isdir(existing_domain_dir):
            os.makedirs(os.path.dirname(target_domain_path), exist_ok=True) # Ensure parent dir exists
            copy_directory_robust(existing_domain_dir, target_domain_path)
        else:
            print(f"Warning: Existing domain directory not found or not a directory at {existing_domain_dir}. Skipping domain copy.")

    # 6. Copy existing Adapter (Optional)
    if existing_adapter_dir:
        target_adapter_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'adapter')
        if os.path.exists(existing_adapter_dir) and os.path.isdir(existing_adapter_dir):
            os.makedirs(os.path.dirname(target_adapter_path), exist_ok=True) # Ensure parent dir exists
            copy_directory_robust(existing_adapter_dir, target_adapter_path)
        else:
            print(f"Warning: Existing adapter directory not found or not a directory at {existing_adapter_dir}. Skipping adapter copy.")


    # build.gradle
    build_gradle_content = f"""
plugins {{
    id 'java'
    id 'org.springframework.boot' version '{spring_boot_version}'
    id 'io.spring.dependency-management' version '1.1.4'
    id 'com.google.protobuf' version '0.9.4' // gRPC plugin
}}

group = '{group_id}'
version = '0.0.1-SNAPSHOT'

repositories {{
    mavenCentral()
}}

java {{
    sourceCompatibility = '{java_version}'
    targetCompatibility = '{java_version}'
}}

dependencies {{
    // Spring Boot Starters
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.postgresql:postgresql:42.7.7' // PostgreSQL Driver
    implementation 'org.liquibase:liquibase-core' // Liquibase dependency

    implementation 'io.grpc:grpc-services' // For gRPC reflection
    
    // lombok
    compileOnly 'org.projectlombok:lombok:1.18.30'
    annotationProcessor 'org.projectlombok:lombok:1.18.30'
    testCompileOnly 'org.projectlombok:lombok:1.18.30'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.30'

    // gRPC dependencies
    implementation 'net.devh:grpc-spring-boot-starter:3.0.0.RELEASE'
    implementation 'io.grpc:grpc-stub'
    implementation 'io.grpc:grpc-protobuf'
    compileOnly 'org.apache.tomcat:annotations-api:6.0.53'

    // Protobuf utilities
    implementation 'com.google.protobuf:protobuf-java-util'

    //jasypt
    implementation 'com.github.ulisesbocchio:jasypt-spring-boot-starter:2.1.2'

    // Testing
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'net.devh:grpc-client-spring-boot-starter:3.0.0.RELEASE'
    testImplementation 'io.grpc:grpc-testing'
    testImplementation 'org.assertj:assertj-core:3.14.0'
}}

protobuf {{
    protoc {{
        artifact = "com.google.protobuf:protoc:3.25.5" // Use a compatible protoc version
    }}
    plugins {{
        grpc {{
            artifact = "io.grpc:protoc-gen-grpc-java:1.63.0" // Use a compatible grpc-java version
        }}
    }}
    generateProtoTasks {{
        all()*.plugins {{
            grpc {{}}
        }}
    }}
}}

// Ensure generated proto sources are included in compilation
sourceSets {{
    main {{
        java {{
            srcDirs 'build/generated/source/proto/main/grpc'
            srcDirs 'build/generated/source/proto/main/java'
        }}
    }}
}}

tasks.named('test') {{
    useJUnitPlatform()
}}
"""
    with open(os.path.join(base_path, 'build.gradle'), 'w') as f:
        f.write(build_gradle_content)

    # settings.gradle
    settings_gradle_content = f"rootProject.name = '{project_name}'"
    with open(os.path.join(base_path, 'settings.gradle'), 'w') as f:
        f.write(settings_gradle_content)

    # Main Spring Boot Application Class
    #app_class_name = ''.join(word.capitalize() for word in artifact_id.split('-')) + 'Application'
    app_class_name = 'Application'
    main_app_content = f"""
package {group_id}.{artifact_id.replace('-', '')};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class {app_class_name} {{

    public static void main(String[] args) {{
        SpringApplication.run({app_class_name}.class, args);
    }}

}}
"""
    # Create the main application package path
    app_package_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''))
    os.makedirs(app_package_path, exist_ok=True)
    with open(os.path.join(app_package_path, f'{app_class_name}.java'), 'w') as f:
        f.write(main_app_content)

    # Placeholder gRPC Service Implementation (example)
    # This will need to be adapted based on the actual proto file content
    service_impl_name = "HackathonServiceGrpcImpl" # Example name, adjust based on your proto service name
    service_impl_content = f"""
package {group_id}.{artifact_id.replace('-', '')}.service;

// Import generated gRPC classes based on your proto package
// Example: import com.tokenization_service.CardCreationRequest;
// Example: import com.tokenization_service.CardTokenizationResponse;
// Example: import com.tokenization_service.TokenizationServiceGrpc;
import io.grpc.stub.StreamObserver;
import net.devh.boot.grpc.server.service.GrpcService;

// TODO: Replace with actual imports from your generated proto classes
// import com.tokenization_service.CardCreationRequest;
// import com.tokenization_service.CardTokenizationResponse;
// import com.tokenization_service.TokenizationServiceGrpc;

// TODO: You will need to manually import the generated gRPC service base class here
// For example: public class {{service_impl_name}} extends TokenizationServiceGrpc.TokenizationServiceGrpcImplBase {{
// And also the request/response messages.

@GrpcService
public class {{service_impl_name}} {{ // TODO: Extend the generated gRPC service base class here

    // TODO: Inject your existing services/repositories here
    // private final CardRepository cardRepository;
    // public {{service_impl_name}}(CardRepository cardRepository) {{ this.cardRepository = cardRepository; }}

    // TODO: Implement actual logic for gRPC methods based on your .proto file
    // Example for createCardToken:
    /*
    @Override
    public void createCardToken(CardCreationRequest request, StreamObserver<CardTokenizationResponse> responseObserver) {{
        // Map gRPC request to your domain/entity objects
        // Save using your repository
        // Map saved entity/domain object back to gRPC response
        System.out.println("Received createCardToken request: " + request);

        // For now, just return a dummy response
        CardTokenizationResponse response = CardTokenizationResponse.newBuilder()
            .setToken("dummy-token-123")
            .setTokenUniqueReference("dummy-ref-456")
            .setDigitalCardId("dummy-digital-id-789")
            .setTokenExpiry("1225")
            .setCardStatus("ACTIVE")
            .setConsumerId(request.getConsumerId())
            .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }}
    */

    // TODO: Add implementations for other RPC methods defined in your .proto file
    // Remember to import the necessary gRPC messages and your own domain/service classes.
}}
"""
    service_package_path = os.path.join(app_package_path, 'service')
    os.makedirs(service_package_path, exist_ok=True)
    with open(os.path.join(service_package_path, f'{service_impl_name}.java'), 'w') as f:
        f.write(service_impl_content)

    print(f"\nSpring Boot gRPC project '{project_name}' generated successfully in '{base_path}'.")
    print("\n*** IMPORTANT NEXT STEPS ***")
    print("1.  **Review Copied Files:** Verify that all your existing `application.yaml`, `Entities`, `Repositories`, `Domain`, and `Adapter` files/packages have been copied correctly into the new project structure.")
    print("    - Ensure their package declarations match the new project's base package (e.g., `package com.example.tokenizationservice.model;`). You might need to adjust these manually.")
    print("2.  **Implement gRPC Services:** Open `src/main/java/{group_id.replace('.', '/')}/{artifact_id.replace('-', '')}/service/{service_impl_name}.java`.")
    print("    - **Crucially:** You need to manually add the `extends` clause to the service implementation class (e.g., `extends TokenizationServiceGrpc.TokenizationServiceGrpcImplBase`).")
    print("    - Import the generated gRPC request/response messages (e.g., `com.tokenization_service.CardCreationRequest`).")
    print("    - Implement the gRPC methods by mapping incoming gRPC requests to your existing domain/entity objects, using your copied repositories/services, and then mapping the results back to gRPC response messages.")
    print("3.  **Database Configuration:** Ensure your copied `application.yaml` contains the correct PostgreSQL database configuration.")
    print("4.  **Build & Run:**")
    print(f"    a. Navigate to the project directory: `cd {base_path}`")
    print("    b. Build the project (this will also generate gRPC Java sources): `./gradlew build`")
    print("    c. Run the application: `./gradlew bootRun`")
    print("5.  **Dependencies:** If your existing project uses other dependencies (e.g., Lombok, MapStruct), add them to the `build.gradle` file.")
    print("6.  **Error Handling:** Integrate gRPC status codes and error handling into your service implementations.")

if __name__ == "__main__":
    proto_file = 'cards.proto'

    # --- IMPORTANT: REPLACE THESE WITH YOUR ACTUAL PATHS ---
    existing_rest_project_root = '../spring-hackathon-service' # Adjust this path as needed

    existing_yaml_file = os.path.join(existing_rest_project_root, 'src/main/resources/application.yaml')
    existing_liqubase_file = os.path.join(existing_rest_project_root, 'src/main/resources/db/changelog/1-datasource.sql')
    existing_entities_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/adapter/datastore/entities') 
    existing_repositories_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/adapter/datastore/repository') 
    existing_domain_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/domain') 
    existing_adapter_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/adapter')
    # --------------------------------------------------------

    generate_spring_boot_grpc_project(
        project_name='grpc-hackathon-service', # New project name
        group_id='com.mastercard', # New group ID for the gRPC project
        artifact_id='hackathon', # New artifact ID
        java_version='17', # Changed to string '17' for Gradle compatibility
        spring_boot_version='3.2.0', # Or a newer 3.x.x version
        proto_file_path=proto_file,
        output_dir='.', # Current directory, or specify a different path for the new project
        existing_yaml_path=existing_yaml_file,
        existing_liqubase_file=existing_liqubase_file,
        existing_entities_dir=existing_entities_directory,
        existing_repositories_dir=existing_repositories_directory,
        existing_domain_dir=existing_domain_directory, # Pass None if you don't have this package
        existing_adapter_dir=existing_adapter_directory # Pass None if you don't have this package
    )