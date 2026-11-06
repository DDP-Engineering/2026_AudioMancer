# TASK-5e2c5ab3 diagrams

Illustrates `## Design` in `TASK-5e2c5ab3.md`. The Design text is authoritative.

## Structure

Map: core, input, adapter, edits and publication added; orchestrators, persistence, state and controller changed; provider and downstream services reused.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    ui["text_chunking_ui_controller"]:::changed --> run["Chunking orchestrators"]:::changed
    run ==> core["chunking pure core"]:::added
    run ==> input["chunking_input_service"]:::added
    run ==> adapter["chunking_ai_service"]:::added
    adapter ==> provider["llm_provider_service"]
    ui ==> edit["chunking_edit_service"]:::added
    edit ==> pub["chunking_publication_service"]:::added
    run ==> pub
    run --> persist["chunking_document_service"]:::changed
    state["text_chunking_state_service"]:::changed --> persist
    edit --> impact["selective downstream services"]
```

## Sequence

```mermaid
sequenceDiagram
    participant UI as text_chunking_ui_controller
    participant Run as chunk_text
    participant Core as chunking core
    participant Store as chunking_document_service
    participant Pub as chunking_publication_service
    UI->>Run: confirmed regeneration
    Run->>Core: plan and validate source ranges
    loop remaining paragraphs
        Run->>Store: write replacement checkpoint
    end
    Run->>Pub: publish completed result
    Pub->>Pub: stage files, move originals, replace
    Pub-->>Run: success or restored originals
    Run-->>UI: completed report
    UI->>UI: reload manifest
```

## State

```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> Cancelled: cancel and checkpoint
    Running --> Failed: caught failure
    Cancelled --> Running: validated resume
    Failed --> Running: validated resume
    Running --> Completed: recoverable publication
    Completed --> Replacement: confirmed regeneration
    Replacement --> Completed: successful publication
    Replacement --> Pending: failure or cancellation
    Pending --> Replacement: resume verified prefix
    note right of Pending
        Published completed result remains available
    end note
```
