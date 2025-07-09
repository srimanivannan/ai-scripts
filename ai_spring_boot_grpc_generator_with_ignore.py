import os
import shutil
import sys # Import sys to check Python version

def copy_directory_robust(src, dest, ignore_patterns=None):
    """
    Copies a directory from src to dest, handling cases where dest already exists.
    It also allows ignoring specific files or directories based on ignore_patterns.

    Args:
        src (str): Source directory path.
        dest (str): Destination directory path.
        ignore_patterns (list of str, optional): A list of file/directory names
                                                 to ignore during copying.
                                                 Example: ['SecurityConfiguration.java', 'temp_dir']
    """
    if ignore_patterns is None:
        ignore_patterns = []

    def ignore_func(directory, contents):
        """
        This function is passed to shutil.copytree's 'ignore' argument.
        It's called for each directory being copied and returns a list of
        items (files/directories) within 'contents' that should be ignored.
        """
        ignored_items = []
        for item in contents:
            if item in ignore_patterns:
                ignored_items.append(item)
        if ignored_items:
            print(f"Ignoring items in {directory}: {', '.join(ignored_items)}")
        return ignored_items

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
    
    # Now, copy the directory with the ignore function
    shutil.copytree(src, dest, ignore=ignore_func)
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
    existing_liqubase_file,
    existing_liqubase_change_log_file,
    existing_entities_dir,
    existing_repositories_dir,
    existing_domain_dir=None, # Optional, as not all projects have a separate 'domain' package
    existing_adapter_dir=None, # Optional, same as above
    ignore_entities=None, # New parameter for ignoring files/folders in entities dir
    ignore_repositories=None, # New parameter for ignoring files/folders in repositories dir
    ignore_domain=None, # New parameter for ignoring files/folders in domain dir
    ignore_adapter=None # New parameter for ignoring files/folders in adapter dir
):
    """
    Generates a seed Spring Boot gRPC project with Gradle, Java 17,
    and PostgreSQL JPA dependency, using a provided .proto file.
    It copies existing application.yaml, Entities, Repositories, Domain,
    and Adapter files/directories from specified paths, with ignore capabilities.

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
        existing_liqubase_change_log_file (str): Path to the existing Liquibase change log file (e.g., db.changelog-master.yaml).
        existing_entities_dir (str): Path to the directory containing existing JPA Entity classes.
        existing_repositories_dir (str): Path to the directory containing existing JPA Repository interfaces.
        existing_domain_dir (str, optional): Path to the directory containing existing domain classes.
        existing_adapter_dir (str, optional): Path to the directory containing existing adapter classes.
        ignore_entities (list of str, optional): List of file/folder names to ignore in the entities directory.
        ignore_repositories (list of str, optional): List of file/folder names to ignore in the repositories directory.
        ignore_domain (list of str, optional): List of file/folder names to ignore in the domain directory.
        ignore_adapter (list of str, optional): List of file/folder names to ignore in the adapter directory.
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

    # 2.2 Copy existing Liquibase change log file
    if os.path.exists(existing_liqubase_change_log_file):
        # Ensure the db/changelog directory exists within resources
        liquibase_target_dir = os.path.join(main_resources_path, 'db', 'changelog')
        os.makedirs(liquibase_target_dir, exist_ok=True)
        shutil.copy(existing_liqubase_change_log_file, liquibase_target_dir)
        print(f"Copied {os.path.basename(existing_liqubase_change_log_file)} to {liquibase_target_dir}")
    else:
        print(f"Error: Existing Liquibase change log file not found at {existing_liqubase_change_log_file}. Skipping.")


    # 3. Copy existing Entities
    # target_entities_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'model')
    # if os.path.exists(existing_entities_dir) and os.path.isdir(existing_entities_dir):
    #     os.makedirs(os.path.dirname(target_entities_path), exist_ok=True) # Ensure parent dir exists
    #     copy_directory_robust(existing_entities_dir, target_entities_path, ignore_patterns=ignore_entities)
    # else:
    #     print(f"Error: Existing entities directory not found or not a directory at {existing_entities_dir}. Skipping entity copy.")

    # 4. Copy existing Repositories
    # target_repositories_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'repository')
    # if os.path.exists(existing_repositories_dir) and os.path.isdir(existing_repositories_dir):
    #     os.makedirs(os.path.dirname(target_repositories_path), exist_ok=True) # Ensure parent dir exists
    #     copy_directory_robust(existing_repositories_dir, target_repositories_path, ignore_patterns=ignore_repositories)
    # else:
    #     print(f"Error: Existing repositories directory not found or not a directory at {existing_repositories_dir}. Skipping repository copy.")

    # 5. Copy existing Domain (Optional)
    if existing_domain_dir:
        target_domain_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'domain')
        if os.path.exists(existing_domain_dir) and os.path.isdir(existing_domain_dir):
            os.makedirs(os.path.dirname(target_domain_path), exist_ok=True) # Ensure parent dir exists
            copy_directory_robust(existing_domain_dir, target_domain_path, ignore_patterns=ignore_domain)
        else:
            print(f"Warning: Existing domain directory not found or not a directory at {existing_domain_dir}. Skipping domain copy.")

    # 6. Copy existing Adapter (Optional)
    if existing_adapter_dir:
        target_adapter_path = os.path.join(main_java_base_path, artifact_id.replace('-', ''), 'adapter')
        if os.path.exists(existing_adapter_dir) and os.path.isdir(existing_adapter_dir):
            os.makedirs(os.path.dirname(target_adapter_path), exist_ok=True) # Ensure parent dir exists
            copy_directory_robust(existing_adapter_dir, target_adapter_path, ignore_patterns=ignore_adapter)
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
    implementation 'com.google.protobuf:protobuf-java-util:3.25.5'

    //jasypt
    implementation 'com.github.ulisesbocchio:jasypt-spring-boot-starter:2.1.2'

    // Testing
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'net.devh:grpc-client-spring-boot-starter:3.0.0.RELEASE'
    testImplementation 'io.grpc:grpc-testing:1.73.0'
    testImplementation 'org.assertj:assertj-core:3.14.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
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

tasks.named('test', Test) {{
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
import com.ulisesbocchio.jasyptspringboot.annotation.EnableEncryptableProperties;

@SpringBootApplication
@EnableEncryptableProperties
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

import com.mastercard.hackathon.Cards.CardCreationRequest;
import com.mastercard.hackathon.Cards.CardDetails;
import com.mastercard.hackathon.Cards.CardSearchRequest;
import com.mastercard.hackathon.Cards.CardTokenizationResponse;
import com.mastercard.hackathon.Cards.CardUpdateDetails;
import com.mastercard.hackathon.Cards.DigitalCardIdRequest;
import com.mastercard.hackathon.Cards.Empty;
import com.mastercard.hackathon.HackathonServiceGrpc;
import com.mastercard.hackathon.adapter.datastore.repository.JpaCardEntityRepository;

import io.grpc.stub.StreamObserver;
import net.devh.boot.grpc.server.service.GrpcService;

@GrpcService
public class HackathonServiceGrpcImpl extends HackathonServiceGrpc.HackathonServiceImplBase {{

  private final JpaCardEntityRepository jpaCardEntityRepository;

  public HackathonServiceGrpcImpl(JpaCardEntityRepository jpaCardEntityRepository) {{
    this.jpaCardEntityRepository = jpaCardEntityRepository;
  }}


  @Override
  public void createCardToken(CardCreationRequest request,
      StreamObserver<CardTokenizationResponse> responseObserver) {{
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

  @Override
  public void searchCards(CardSearchRequest request, StreamObserver<CardDetails> responseObserver) {{
    super.searchCards(request, responseObserver);
  }}

  @Override
  public void getCardByDigitalCardId(DigitalCardIdRequest request,
      StreamObserver<CardDetails> responseObserver) {{
    super.getCardByDigitalCardId(request, responseObserver);
  }}

  @Override
  public void updateCardByDigitalCardId(CardUpdateDetails request,
      StreamObserver<CardDetails> responseObserver) {{
    super.updateCardByDigitalCardId(request, responseObserver);
  }}

  @Override
  public void deleteCardByDigitalCardId(DigitalCardIdRequest request,
      StreamObserver<Empty> responseObserver) {{
    super.deleteCardByDigitalCardId(request, responseObserver);
  }}
}}
"""
    service_package_path = os.path.join(app_package_path, 'service')
    os.makedirs(service_package_path, exist_ok=True)
    with open(os.path.join(service_package_path, f'{service_impl_name}.java'), 'w') as f:
        f.write(service_impl_content)

    print(f"\nSpring Boot gRPC project '{project_name}' generated successfully in '{base_path}'.")
    #print("\n*** IMPORTANT NEXT STEPS ***")
    # print("1.  **Review Copied Files:** Verify that all your existing `application.yaml`, `Entities`, `Repositories`, `Domain`, and `Adapter` files/packages have been copied correctly into the new project structure.")
    # print("    - Ensure their package declarations match the new project's base package (e.g., `package com.example.tokenizationservice.model;`). You might need to adjust these manually.")
    # print("2.  **Implement gRPC Services:** Open `src/main/java/{group_id.replace('.', '/')}/{artifact_id.replace('-', '')}/service/{service_impl_name}.java`.")
    # print("    - **Crucially:** You need to manually add the `extends` clause to the service implementation class (e.g., `extends TokenizationServiceGrpc.TokenizationServiceGrpcImplBase`).")
    # print("    - Import the generated gRPC request/response messages (e.g., `com.tokenization_service.CardCreationRequest`).")
    # print("    - Implement the gRPC methods by mapping incoming gRPC requests to your existing domain/entity objects, using your copied repositories/services, and then mapping the results back to gRPC response messages.")
    # print("3.  **Database Configuration:** Ensure your copied `application.yaml` contains the correct PostgreSQL database configuration.")
    # print("4.  **Build & Run:**")
    # print(f"    a. Navigate to the project directory: `cd {base_path}`")
    # print("    b. Build the project (this will also generate gRPC Java sources): `./gradlew build`")
    # print("    c. Run the application: `./gradlew bootRun`")
    # print("5.  **Dependencies:** If your existing project uses other dependencies (e.g., Lombok, MapStruct), add them to the `build.gradle` file.")
    # print("6.  **Error Handling:** Integrate gRPC status codes and error handling into your service implementations.")

if __name__ == "__main__":
    proto_file = 'cards.proto'

    # --- IMPORTANT: REPLACE THESE WITH YOUR ACTUAL PATHS ---
    existing_rest_project_root = '../spring-hackathon-service'

    existing_yaml_file = os.path.join(existing_rest_project_root, 'src/main/resources/application.yaml')
    existing_liqubase_file = os.path.join(existing_rest_project_root, 'src/main/resources/db/changelog/1-datasource.sql')
    existing_liqubase_change_log_file = os.path.join(existing_rest_project_root, 'src/main/resources/db/changelog/db.changelog-master.yaml')
    existing_entities_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/adapter/datastore/entities')
    existing_repositories_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/adapter/datastore/repository') 
    existing_domain_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/domain') 
    existing_adapter_directory = os.path.join(existing_rest_project_root, 'src/main/java/com/mastercard/hackathon/adapter')
    # --------------------------------------------------------

    # --- Define files/folders to ignore during copying ---
    adapter_ignore_list = ['config', 'delgates', 'Test.java']
    
    # You can define similar lists for other directories if needed
    entities_ignore_list = []
    repositories_ignore_list = []
    domain_ignore_list = []
    # ----------------------------------------------------

    generate_spring_boot_grpc_project(
        project_name='grpc-hackathon-service', # New project name
        group_id='com.mastercard', # New group ID for the gRPC project
        artifact_id='hackathon', # New artifact ID
        java_version='17', # Changed to string '17' for Gradle compatibility
        spring_boot_version='3.2.4', # Or a newer 3.x.x version
        proto_file_path=proto_file,
        output_dir='..', # Current directory, or specify a different path for the new project
        existing_yaml_path=existing_yaml_file,
        existing_liqubase_file=existing_liqubase_file,
        existing_liqubase_change_log_file=existing_liqubase_change_log_file,
        existing_entities_dir=existing_entities_directory,
        existing_repositories_dir=existing_repositories_directory,
        existing_domain_dir=existing_domain_directory, 
        existing_adapter_dir=existing_adapter_directory,
        ignore_entities=entities_ignore_list, # Pass the ignore list
        ignore_repositories=repositories_ignore_list, # Pass the ignore list
        ignore_domain=domain_ignore_list, # Pass the ignore list
        ignore_adapter=adapter_ignore_list # Pass the ignore list
    )
