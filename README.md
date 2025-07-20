# gRPC Canary Proxy + PCF Integration

Routes gRPC calls between multiple versions of the same service (v1, v2)
Smart traffic split: 90% to v1, 10% to v2
Collects response times, logs, and fallback triggers
flip traffic dynamically [resilency4j or Envoy proxy or Linkerd (for routing)]

| Strength Area                | Why It Stands Out                                                                                            |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 🧠 **AI-Powered**            | You're using GPT to auto-generate `.proto` files from OpenAPI – clearly showcasing AI integration.           |
| 🔁 **Automation**            | You’re automating a real-world, painful process: migrating REST → gRPC (a massive effort in many companies). |
| 💻 **DevX Upgrade**          | It improves developer experience by reducing manual, error-prone migrations.                                 |
| 🧱 **Production-Aware**      | You’ve made it deployable to PCF, use Gradle, Spring Boot 3, and modern DDD — it’s not a toy project.        |
| 📈 **Scalability Potential** | This can grow into a full CI/CD plugin, CLI tool, or platform feature.                                       |


✅ Demo a Before/After Comparison

Show OpenAPI → Proto → gRPC → Working service in 2 minutes.

Highlight "AI-generated spec" and "code generated instantly".

✅ Add a CLI or UI Wrapper

Even a basic Python CLI like:

bash
Copy
Edit
./refactor.py openapi.yaml --out grpc.zip
Makes it feel more like a tool, not just a script.

✅ Bonus: Add REST fallback via grpc-gateway

Proves migration doesn't break old clients.

✅ Focus on "Why This Matters"

Time saved per service (~days).

Tech debt reduction.

Microservice modernization (Spring WebFlux + gRPC).

Less room for human error.


### it’s relevant, practical, and shows real engineering empathy.

### commands

```shell
ghz --insecure \
  --proto /Users/mani/Downloads/grpc-user-refactor_with_ai/src/main/proto/user_service.proto \
  --call com.example.grpc.UserService.GetUser \
  -d '{"id":"123"}' \
  -n 10000 \
  -c 100 \
  localhost:9090
```

```shell
ab -n 10000 -c 100 https://www.mastercard.us/en-us.html
```
### proto generator

```shell
python3 ai-proto-generator.py cards.yaml \
    --output_proto_file cards.proto \
    --package_name com.mastercard.hackathon \
    --base_service_name CommonService
```

```shell
python3 openapi_to_proto_code.py src-composite-checkout.yaml \
         --package com.mastercard.src.ce \
         --service Mani \
         --output src-composite-checkout.proto
```

```shell
python3 openapi_to_proto_code.py address-service.yaml \
         --package com.mastercard.alberta.addressservice \
         --service Address \
         --output address.proto
```

### To generate new grpc folder
```shell
python3 spring-rest-grpc-migrator.py -c config.yaml
```