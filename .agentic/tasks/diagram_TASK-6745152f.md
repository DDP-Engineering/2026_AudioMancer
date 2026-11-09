# TASK-6745152f diagrams

The task journal's design is authoritative.

## Structure

Changed: translation_ai_service. Reused: llm_provider_service, ai_translation_service.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    batch["ai_translation_service"] --> adapter["translation_ai_service"]:::changed
    adapter --> provider["llm_provider_service"]
```

## Sequence

```mermaid
sequenceDiagram
    participant A as translation_ai_service
    participant P as llm_provider_service
    A->>P: Translate fragment
    P-->>A: JSON reply
    opt Valid JSON with different paragraph count
        A->>P: Retry same fragment with exact count
        P-->>A: Corrected reply
    end
```

## State

```mermaid
stateDiagram-v2
    [*] --> ValidateReply
    ValidateReply --> Accepted: Matching valid reply
    ValidateReply --> Failed: Invalid shape
    ValidateReply --> Retry: Paragraph count differs
    Retry --> Accepted: Matching valid reply
    Retry --> Failed: Invalid shape or count still differs
```
