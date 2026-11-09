# TASK-a68ffabe diagrams

The task journal's design is authoritative.

## Structure

Changed: CharactersPage, characters_ui_controller, character_discovery_service.
Reused: approved translation resolver, characters.json.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    page["CharactersPage"]:::changed --> controller["characters_ui_controller"]:::changed
    controller --> service["character_discovery_service"]:::changed
    service --> resolver["resolve_approved_translation"]
    service --> artifact[("characters.json")]
```

## Sequence

```mermaid
sequenceDiagram
    participant S as character_discovery_service
    participant P as llm_provider_service
    participant D as characters.json
    S->>P: Discover candidates in current window
    P-->>S: Candidates and citations
    S->>D: Candidates and next window start
    Note over S,D: Resume retains overlap
    S->>P: Synthesize candidate with reserved ID
    S->>D: Save profile with source evidence
```

## State

```mermaid
stateDiagram-v2
    [*] --> Discovery
    Discovery --> Interrupted: Cancel or provider error
    Interrupted --> Discovery: Resume at next planned window
    Discovery --> Synthesis: Last window checkpointed
    Synthesis --> Review: Profiles saved
    Review --> Draft: Edit Character
    Draft --> Review: Save or discard
```
