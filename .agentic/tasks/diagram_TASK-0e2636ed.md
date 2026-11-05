# TASK-0e2636ed diagrams

Illustrates Design in TASK-0e2636ed.md; Design is authoritative.

## Structure

Node map: app.main and page integration changed; TextInteractionController added;
QApplication, native editors and locale catalog reused unchanged as APIs.

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    app["app.main"]:::changed ==> filter["TextInteractionController"]:::added
    qt["QApplication"] ==> filter
    filter ==> editor["QLineEdit / QPlainTextEdit / QTextEdit"]
    filter ==> locale["ui_state_service.translate"]
    pages["Chunking / Characters pages"]:::changed --> editor
```

## Sequence

```mermaid
sequenceDiagram
    participant Editor as Text control
    participant Filter as TextInteractionController
    participant Prompt as QInputDialog
    participant Document as QTextDocument
    Editor->>Filter: Ctrl+F
    Filter->>Prompt: localized query with selection
    Prompt-->>Filter: accepted text or cancel
    alt accepted nonempty text
        Filter->>Document: find literal query, wrap once
        Document-->>Filter: cursor or no match
        Filter->>Editor: select match or preserve prior selection
    end
```

## State

```mermaid
stateDiagram-v2
    [*] --> ReadOnly: read-only preview
    [*] --> Editable: editable input
    ReadOnly --> Editable: existing Edit action
    Editable --> ReadOnly: existing Save or Cancel
    ReadOnly --> ReadOnly: copy or search
    Editable --> Editable: native editing or search
```

These are existing Qt editability states; only their available menu actions change.
