# TASK-c20ea841 diagrams

Illustrates the design in TASK-c20ea841.md.

## Structure

Changed nodes: voice previews, Speech Blocks budget, Audio Blocks and runtime selection.
Reused node: VoiceWeaver REST.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    preview["profile_generation_request and voice_target_generation_request"]:::changed ==> model["voiceweaver_runtime_service.resolve_tts_model"]:::changed
    speech["resolve_narrator_only_budget"]:::changed ==> model
    audio["_build_generation_context"]:::changed ==> model
    audio --> rest["VoiceWeaver REST"]
    preview --> rest
```

## Sequence

```mermaid
sequenceDiagram
    participant A as Audio Blocks
    participant S as resolve_tts_model
    participant V as VoiceWeaver
    A->>S: Inventory, clone, narration language
    S-->>A: Selected model and compatible language
    A->>V: Load selected model when needed
    alt Qwen
        A->>V: Prepare or reuse clone prompt
        A->>V: Synthesize from prompt
    else Other clone model
        A->>V: Synthesize from WAV and transcript
    end
    A->>V: Download completed audio
```

## State

Not drawn: model selection leaves the operation lifecycle and persisted states as they are.
