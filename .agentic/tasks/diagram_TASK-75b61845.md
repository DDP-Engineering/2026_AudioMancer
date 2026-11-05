# TASK-75b61845 diagrams

Illustrates Design in TASK-75b61845.md. Design is authoritative.

## Structure

Node map: controller, service, analysis and render changed; publication and editing added; AI and project artifacts reused.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    ui["text_cleanup_ui_controller"]:::changed --> service["text_cleanup_service"]:::changed
    service ==> analysis["cleanup.analysis"]:::changed
    service ==> render["cleanup.render"]:::changed
    service ==> edit["cleanup.editing"]:::added
    service --> ai["cleanup_ai_adjudication_service"]
    service ==> publication["cleanup_publication_service"]:::added
    publication ==> project[("Project artifacts and manifest")]
```

## Sequence

```mermaid
sequenceDiagram
    participant UI as text_cleanup_ui_controller
    participant Service as text_cleanup_service
    participant Engine as cleanup
    participant Publish as cleanup_publication_service
    UI->>Service: clean_text(force=True)
    Service->>Engine: analyze and render with cancellation
    Engine-->>Service: validated text and metadata
    Service->>Publish: stage replacement
    Publish->>Publish: back up originals and replace outputs
    alt IO failure
        Publish->>Publish: restore originals
        Publish-->>Service: raise error
    else success
        Publish-->>Service: completed replacement
        Service-->>UI: completed result
    end
```

## State

```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> Paused: cancelled during adjudication
    Paused --> Running: resume compatible answers
    Running --> Finalizing: decisions checkpointed
    Finalizing --> Finalizing: cancelled; resume rendering later
    Finalizing --> Completed: validated publication succeeds
    Finalizing --> Finalizing: publication failure; originals restored
    Completed --> Running: confirmed rerun; previous result retained
```
