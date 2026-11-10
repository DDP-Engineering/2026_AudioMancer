# TASK-05698d38 diagrams

Illustrates the Design in TASK-05698d38.md.

## Structure

Changed: Home, Project Export, Snapshot. Added: text projection and ZIP writer. Reused: runner and text persistence.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    home["home_ui_controller"]:::changed ==> runner["operation_runner_controller"]
    runner ==> exports["project_export_service"]:::changed
    exports ==> text["project_export_text_service"]:::added
    exports ==> persist["persistence_service"]
    exports ==> zip["archive_writer"]:::added
    snapshot["project_snapshot_service"]:::changed ==> zip
```

## Sequence

```mermaid
sequenceDiagram
    participant H as home_ui_controller
    participant R as operation_runner_controller
    participant E as project_export_service
    participant W as archive_writer
    H->>R: Start stage ZIP worker
    R->>E: Export selected archive
    E->>E: Validate generated Assembly WAVs
    E->>W: Write verified members and manifest
    W-->>E: Published ZIP path
    E-->>R: Publication and partial count
    R-->>H: Show completion
```

## State

```mermaid
stateDiagram-v2
    [*] --> Inspecting
    Inspecting --> Unavailable: No usable WAV
    Inspecting --> Writing: Usable WAVs
    Writing --> Partial: Incomplete report or omissions
    Writing --> Complete: Complete report and all WAVs exported
    Writing --> Cancelled: Cancel before publication
    Writing --> Failed: Write error
```
