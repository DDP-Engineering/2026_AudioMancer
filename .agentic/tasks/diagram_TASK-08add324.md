# TASK-08add324 diagrams

The task journal design is authoritative.

## Structure

Changed: narrator controller, definition service, profile generation service.
Reused: project file replacement and narrator voice artifacts.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    ui["narator_voice_ui_controller"]:::changed --> definition["narrator_definition_service"]:::changed
    ui --> generator["narrator_profile_generation_service"]:::changed
    generator --> definition
    definition ==> publication["replace_project_files"]
    publication ==> files[("Narrator document and WAV")]
```

## Sequence

```mermaid
sequenceDiagram
    participant UI as Narrator Voice
    participant S as narrator_definition_service
    participant P as replace_project_files
    UI->>S: Read profile for draft
    UI->>S: Save changed voice or sample
    S->>P: Publish staged WAV and document
    alt Success
        P-->>UI: Refresh and invalidate affected audio
    else Failure
        P-->>UI: Restore old pair and report error
    end
```

## State

```mermaid
stateDiagram-v2
    [*] --> Viewing
    Viewing --> Draft: Edit
    Draft --> Viewing: Discard
    Draft --> Publishing: Save changes
    Viewing --> Publishing: Replace sample
    Publishing --> Viewing: Success
    Publishing --> Draft: Failed edit publication
    Publishing --> Viewing: Failed sample publication
```
