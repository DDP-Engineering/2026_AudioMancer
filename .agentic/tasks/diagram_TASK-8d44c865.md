# TASK-8d44c865 diagrams

Illustrates the Design in TASK-8d44c865.md.

## Structure

Changed: AISettingsPage, ai_backend_service, ai_budget_service, llm_provider_service. Reused: provider and workflows as facade consumers.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    settings["AISettingsPage"]:::changed --> probe["ai_backend_service"]:::changed
    probe --> provider["Backend"]
    settings ==> budget["ai_budget_service"]:::changed
    workflow["LLM workflow"] --> budget
    workflow --> chat["llm_provider_service"]:::changed
    chat --> provider
```

## Sequence

```mermaid
sequenceDiagram
    participant U as AISettingsPage
    participant P as ai_backend_service
    participant W as LLM workflow
    participant B as ai_budget_service
    participant C as llm_provider_service
    participant S as Backend
    U->>P: Probe selected model
    P->>S: Read model and loaded context
    S-->>P: Report known limits
    P-->>U: Show limits and configured budget
    W->>B: Compute effective request budget
    B-->>W: Context and output reservation
    W->>C: Request structured result
    C->>S: Send planned output limit
```

## State

```mermaid
stateDiagram-v2
    [*] --> Unknown
    Unknown --> Known: Probe reports matching loaded instance
    Known --> Unknown: Model or endpoint changes
    Known --> Unknown: Successful probe reports no matching instance
    Known --> Known: Refresh matching instance or retain last success on failure
```
