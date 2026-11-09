# TASK-b87d0a4d diagrams

Illustrates the Design in TASK-b87d0a4d.md.

## Structure

Changed: CharacterVoicesPage, character_voices_ui_controller, character_voices_service.
Reused: replace_project_files, invalidate_audio_blocks_for_voice_targets.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    page["CharacterVoicesPage"]:::changed --> controller["character_voices_ui_controller"]:::changed
    controller --> service["character_voices_service"]:::changed
    service ==> replace["replace_project_files"]
    controller --> invalidate["invalidate_audio_blocks_for_voice_targets"]
```

## Sequence

```mermaid
sequenceDiagram
    participant controller as character_voices_ui_controller
    participant worker as _generate_and_store_character_samples
    participant service as store_target_sample
    controller->>worker: Start batch with completed ID list
    worker->>service: Publish sample pair
    service-->>worker: Publication succeeded
    worker->>worker: Record target ID
    worker-->>controller: Batch completes or stops
    controller->>controller: Invalidate recorded IDs
```

## State

```mermaid
stateDiagram-v2
    [*] --> Viewing
    Viewing --> Draft: Edit
    Draft --> Viewing: Cancel
    Draft --> Viewing: Save succeeds
    Draft --> Draft: Save rejected or failed
```
