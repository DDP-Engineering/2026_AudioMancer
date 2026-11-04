# TASK-f46ffa1a diagrams

Illustrates `## Design` in `TASK-f46ffa1a.md`. The Design text is authoritative.

Node classification: HomeProjectPage, home_ui_controller and operation_runtime_service = changed; project_options_service = added; project_workspace_service, import_service and AiTranslationPage = reused unchanged. MainWindow wiring is changed but omitted for clarity.

## Structure

```mermaid
flowchart LR
    classDef added fill:#e1f5ee,stroke:#0f6e56
    classDef changed fill:#faeeda,stroke:#854f0b
    classDef removed stroke-dasharray:4 3
    page["HomeProjectPage"]:::changed ==> home["home_ui_controller"]:::changed
    home ==> translation["AiTranslationPage"]
    home ==> options["project_options_service"]:::added
    options ==> runtime["operation_runtime_service"]:::changed
    options ==> workspace["project_workspace_service"]
    options ==> importer["import_service"]
```

## Sequence

```mermaid
sequenceDiagram
    participant Operator
    participant Home as home_ui_controller
    participant Translation as AiTranslationPage
    participant Options as project_options_service
    participant Files as project workspace
    Operator->>Home: select different mode or language
    Home->>Translation: flush_pending_translation_edit
    Translation-->>Home: latest edit saved and timer stopped
    Home->>Options: plan_project_options_change
    Options->>Files: read manifest and collect owned artifacts
    Files-->>Options: actual persisted impact
    Options-->>Home: immutable change plan
    Home->>Operator: confirm actual impact when required
    alt accepted
        Home->>Options: apply_project_options_change(plan)
        Options->>Files: stage originals and publish options
        Files-->>Options: persisted result or recoverable failure
        Options-->>Home: saved manifest or restored error
        Home-->>Operator: refresh saved selectors and progress
    else cancelled
        Home-->>Operator: restore saved selectors
    end
```

## State

```mermaid
stateDiagram-v2
    [*] --> ExistingProject
    ExistingProject --> CollectingInputs: New Project
    CollectingInputs --> ExistingProject: cancel or failure
    CollectingInputs --> ReadyProject: publish copied source and options
    ReadyProject --> PlanningChange: select different option
    PlanningChange --> ReadyProject: same value or cancelled
    PlanningChange --> PublishingChange: confirmed or empty language impact
    PublishingChange --> ReadyProject: saved with affected results reset
    PublishingChange --> ReadyProject: failure with originals restored
```
