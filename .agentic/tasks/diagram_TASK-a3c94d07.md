# TASK-a3c94d07 diagrams
Illustrates the journal Design.

## Structure
Map: UI and orchestrator changed; document, planner, adapter, and publication added; provider unchanged.
```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    ui["Translation page and controller"]:::changed --> run["ai_translation_service"]:::changed
    run ==> doc["translation.document"]:::added
    run ==> plan["translation.planning"]:::added
    run ==> adapter["translation_ai_service"]:::added
    adapter ==> llm["llm_provider_service"]
    run ==> pub["translation_publication_service"]:::added
```

## Sequence
```mermaid
sequenceDiagram
    participant UI as Translation controller
    participant Run as ai_translation_service
    participant AI as translation_ai_service
    participant Store as translation_publication_service
    UI->>Run: Start or resume
    loop Pending chunks
        Run->>AI: Translate and validate bounded fragments
        AI-->>Run: Complete translated chunk
        Run->>Run: Atomic checkpoint
    end
    Run->>Store: Publish document, manifest and effects
    Store-->>Run: Published or recovered
    Run-->>UI: Refresh or show failure
```

## State
```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> Failed: setup, request or publication failure
    Running --> Cancelled: cancellation
    Failed --> Running: resume
    Cancelled --> Running: resume
    Running --> Review: complete chunk coverage
    Review --> Approved: explicit approval with current source
    Approved --> Review: edit or unverified legacy source
    Approved --> Pending: source changed
    Pending --> Running: translate affected chunks
```
