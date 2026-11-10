# TASK-55cdb3d4 diagrams

Illustrates Design in TASK-55cdb3d4.md.

## Structure

Changed: audio_blocks_service, audio_blocks_artifact_service, AudioBlocksPage.
Added: audio_blocks_generation_service.
Reused: voiceweaver_runtime_service, replace_project_files.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    page["AudioBlocksPage"]:::changed --> service["audio_blocks_service"]:::changed
    service ==> generator["audio_blocks_generation_service"]:::added
    generator ==> runtime["voiceweaver_runtime_service"]
    generator ==> artifact["audio_blocks_artifact_service"]:::changed
    service ==> publisher["replace_project_files"]
```

## Sequence

```mermaid
sequenceDiagram
    participant service as audio_blocks_service
    participant generator as audio_blocks_generation_service
    participant publisher as replace_project_files
    service->>generator: Render candidate WAV
    generator-->>service: Valid WAV in staging
    service->>publisher: Publish WAV, document, cache and project summary
    publisher-->>service: Published or restored original files
```

## State

```mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Active: Generate
    Active --> Active: Checkpoint valid part by ID
    Active --> Interrupted: Cancel or fail
    Interrupted --> Active: Resume valid prefix
    Active --> Published: Publish WAV and metadata
    Published --> Active: Regenerate
```
