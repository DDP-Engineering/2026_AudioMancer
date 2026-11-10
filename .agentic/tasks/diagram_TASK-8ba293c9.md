# TASK-8ba293c9 diagrams

Illustrates `## Design` in `TASK-8ba293c9.md`.

## Structure

Changed: audio_blocks_service, audio_assembly_service, speech_blocks_service.
Added: audio_assembly_plan, audio_assembly_wav.
Reused: pcm_codec.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    audio["audio_blocks_service"]:::changed --> assembly["audio_assembly_service"]:::changed
    speech["speech_blocks_service"]:::changed --> audio
    assembly ==> plan["audio_assembly_plan"]:::added
    assembly ==> wav["audio_assembly_wav"]:::added
    wav ==> codec["pcm_codec"]
```

## Sequence

```mermaid
sequenceDiagram
    participant service as audio_assembly_service
    participant plan as audio_assembly_plan
    participant writer as audio_assembly_wav
    service->>service: Validate source WAVs and anchors
    service->>plan: Build ordered output groups
    plan-->>service: Output plan
    service->>service: Reuse valid checkpoint outputs
    service->>writer: Render and publish each pending WAV
    writer-->>service: Completed output or preserved prior WAV
```

## State

```mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Rendering: Start pending output
    Rendering --> Published: Replace with complete candidate
    Rendering --> Pending: Cancel or fail
    Published --> Reused: Matching valid WAV at resume
    Published --> Pending: Output missing or invalid
```
