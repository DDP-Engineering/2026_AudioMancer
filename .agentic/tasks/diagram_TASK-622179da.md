# TASK-622179da diagrams

Illustrates the Design in TASK-622179da.md.

## Structure

Changed: speech_blocks_service, SpeechBlocksPage, speech_blocks_normalization_service.
Added: speech_blocks_generation_service.
Reused: llm_provider_service, speech_blocks_narrator_split_service.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    page["SpeechBlocksPage"]:::changed --> service["speech_blocks_service"]:::changed
    service ==> generation["speech_blocks_generation_service"]:::added
    generation ==> provider["llm_provider_service"]
    generation ==> narrator["speech_blocks_narrator_split_service"]
    generation ==> normalization["speech_blocks_normalization_service"]:::changed
```

## Sequence

```mermaid
sequenceDiagram
    participant service as speech_blocks_service
    participant generator as speech_blocks_generation_service
    participant provider as llm_provider_service
    service->>generator: Generate from next_source_offset
    generator->>provider: Send next source slice
    provider-->>generator: Return proposed blocks
    generator-->>service: Checkpoint blocks and source offset
    generator-->>service: Return complete chunk after optional ambience
```

## State

```mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Active: Begin chunk
    Active --> Active: Checkpoint source offset
    Active --> Interrupted: Cancel
    Interrupted --> Active: Resume exact offset
    Active --> Covered: Publish speech and optional ambience
    Active --> Skipped: Speech provider refusal
```
