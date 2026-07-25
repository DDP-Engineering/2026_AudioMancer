<!--
Copyright (c) 2026 DDP Engineering
This software is licensed under the GNU Affero General Public License v3.0
(AGPL-3.0) with additional Non-Commercial restriction.
See the LICENSE.txt and LICENSE_NC.txt files for full license details.
-->
# Plan: Simplificare metadata Speech Blocks (un singur document)

**Status:** draft, pentru execuție prin fluxul agentic (`/agentic-development`)
**Autor plan:** Eng. Dan Dumitru Pasare
**Data:** 2026-07-24
**Model de referință:** commit `1d8e718` „Simplified metadata for character discovery"
și consolidarea din AI Translate (`translated_text.json`).

---

## 1. Obiectiv

Reduce persistența operației **Speech Blocks** de la **3 fișiere** la **1 singur
document autoritar** `speech_blocks.json`, eliminând redundanța dintre raport și
stare și copia integrală a textului sursă. Comportamentul funcțional (generare,
reluare/resume, resplit pe chunk, aprobări, export, sync manifest) rămâne
identic.

Non-obiectiv: nicio schimbare de logică AI, de prompturi, de format al blocului
individual sau de UI vizibil operatorului.

---

## 2. Stare curentă (ce se salvează azi)

Folder operație `70_speech_blocks/`, constante în `config.py:344-350`:

| Fișier | Rol | Observație |
|---|---|---|
| `speech_blocks.json` (`SPEECH_BLOCKS_OUTPUT_FILE_NAME`) | listă blocuri | singura sursă de adevăr reală |
| `speech_blocks_report.json` (`SPEECH_BLOCKS_REPORT_FILE_NAME`) | rezumat/statistici | ~integral derivabil din blocuri |
| `speech_blocks_state.json` (`SPEECH_BLOCKS_STATE_FILE_NAME`) | stare/resume | duplică raportul + copie integrală surse |

Redundanțe confirmate:
- `source_language`, `source_kind`, `ai_profile_id`, `token_usage`,
  `budget_metadata`, `warnings`, numărătorile — scrise în **raport ȘI** în
  `state.metadata` (`speech_blocks_report_state_service.py:88` și `:190`).
- `state.metadata.source_chunks` = **copie integrală a textului tuturor
  chunk-urilor** (`speech_blocks_report_state_service.py:201-208`).
- `resume_checkpoint` repetă `source_language`, `ai_profile_id`,
  `budget_metadata`, `fingerprint` (`:214-225`).

Câmpuri „reale" (ne-derivabile) care TREBUIE păstrate: `token_usage`,
`budget_metadata`, `ai_profile_id`, `source.language`, `source.kind`,
`source.fingerprint`, `additional_speech_block_instructions`,
`scene_ambience_settings`, `speech_blocks_response_contract`, `log_relative_path`
și cursorii de resume (`next_chunk_index`, `active_chunk_id`,
`next_segment_index`, `completed_segment_count`, `run_token`).

---

## 3. Documentul țintă `speech_blocks.json`

Un obiect unic, validat strict (set fix de câmpuri de nivel 1, ca la
`_CHARACTER_DOCUMENT_FIELDS`):

```jsonc
{
  "status": "running | review_pending | completed | failed | cancelled",
  "source": { "kind": "original|translated", "language": "ro", "fingerprint": "…" },
  "ai_profile_id": "…",
  "instructions": "…",                 // fost additional_speech_block_instructions
  "scene_ambience": { "enabled": bool, … },
  "response_contract": "direct_blocks | atomic_unit_selection | narrator_boundary_ids",
  "token_usage": { … },
  "budget_metadata": { … },
  "checkpoint": {                       // non-null doar cât rulează / la resume
    "next_chunk_index": int,
    "active_chunk_id": "…",
    "next_segment_index": int|null,
    "completed_segment_count": int|null,
    "run_token": "…",                   // = started_at
    "log_relative_path": "…"
  },
  "failure": null,
  "blocks": [ { …bloc, format neschimbat… } ]
}
```

**Recalculat la citire (NU se persistă):** `stage_status`, `processed_chunk_count`,
`total_chunk_count`, `speech_block_count`, `approved_block_count`,
`total_block_count`, `warning_count`, lista `warnings`, `progress_current/total`.

**Eliminat definitiv:** `state.metadata.source_chunks` (copia de text). Sursele
se re-rezolvă din upstream (`chunks_text.json` sau `translated_text.json`) prin
`resolve_source_chunks()`, exact ca la Character Discovery care a renunțat la
snapshot și păstrează doar `fingerprint`.

---

## 4. Modificări cod, fișier cu fișier

### 4.1 `config.py`
- Șterge toate cele trei constante: `SPEECH_BLOCKS_OUTPUT_FILE_NAME`,
  `SPEECH_BLOCKS_REPORT_FILE_NAME`, `SPEECH_BLOCKS_STATE_FILE_NAME`.
- Introdu **`SPEECH_BLOCKS_DOCUMENT_FILE_NAME = "speech_blocks.json"`** (decis),
  aliniat cu `CHARACTERS_DOCUMENT_FILE_NAME`.
- Consumatorii care refereau vechea constantă `SPEECH_BLOCKS_OUTPUT_FILE_NAME`
  (`project_export_service.py:122`, `audio_blocks_service.py:3301`,
  `operation_runtime_service.py:88`) trec pe `SPEECH_BLOCKS_DOCUMENT_FILE_NAME`.

### 4.2 `speech_blocks_report_state_service.py`
- Înlocuiește `rebuild_report()` + `build_operation_state()` cu:
  - `build_document(...)` — asamblează documentul unic.
  - `project_report(document)` — proiecție compatibilă cu vechiul raport (pentru
    consumatorii care încă cer un „report").
  - `project_operation_state(document, source_chunk_count)` — proiecție a stării
    (`status`/`progress`/`warning_count`/`metadata`/`resume_checkpoint`), model
    `character_operation_summary()`.
  - `warning_records_from_blocks()`, `approved_block_count()` rămân (deja pure).
- Elimină persistarea `source_chunks` din metadata.

### 4.3 `speech_blocks_service.py`
- `load_speech_blocks()` → întoarce `document["blocks"]` (schimbare internă;
  apelanții primesc aceeași listă).
- Adaugă `load_speech_blocks_document()` + `write_speech_blocks_document()` cu
  validare strictă (`_validate_document`, clasă `SpeechBlocksDocumentError`).
- `load_speech_blocks_report()` și `load_operation_state()` devin proiecții peste
  documentul unic (păstrează semnătura publică → zero impact la apelanți).
- `load_input_source_chunks()` → re-rezolvă din upstream (nu mai citește copia).
- Refactorează `_persist_state()` să scrie un singur fișier; elimină
  `_build_operation_state_with_prompt_rules` / dublă scriere.
- Reluarea (`_restore_resume_state`, `_restore_next_speech_blocks_segment_index`)
  citește din `document["checkpoint"]` + `document["source"]["fingerprint"]`.
- `reset_speech_blocks()` / `reset_operation_data` → un singur artefact.

### 4.4 Consumatori externi (proiecție, fără schimbare de semantică)
- `speech_blocks_state_service.py:118-120` — folosește proiecțiile.
- `project_export_service.py:568-571` — idem.
- `project_workspace_service.py:969-986` — citea 3 fișiere pentru reset/sync;
  aliniază la 1 fișier (vezi `git show 1d8e718 -- …project_workspace_service.py`).
- `characters_ui_controller.py:761`, `text_chunking_state_service.py:441`,
  `speech_blocks_ui_controller.py:576` — apelează `load_operation_state()`
  (proiecție) → neschimbate ca apel.
- `operation_runtime_service.py:88-90,116` — actualizează lista de artefacte
  (acum un singur `SPEECH_BLOCKS_DOCUMENT_FILE_NAME`) și maparea de state file
  pentru „speech_blocks".

### 4.5 `audio_blocks_service.py` (downstream)
- Citește azi `speech_blocks.json` ca listă simplă (`:3301`, `load_speech_blocks`).
  Rămâne să consume prin `speech_blocks_service.load_speech_blocks()` (care acum
  întoarce `document["blocks"]`) — nu citi fișierul direct ca listă.

---

## 5. Migrare proiecte existente — **reset & regenerate** (decis)

**Fără cod de migrare, fără citire tolerantă a formatului vechi.** Proiectele cu
artefacte în format vechi se re-rulează prin operația Speech Blocks.

- `load_speech_blocks_document()` validează strict; orice artefact neconform
  (vechiul `speech_blocks.json` ca **listă**, sau lipsa documentului nou) este
  tratat ca **inexistent** → `None`, deci pagina afișează „not started".
- Nu se citesc și nu se convertesc `*_report.json` / `*_state.json` vechi.
- `reset_speech_blocks()` / `reset_operation_data` curăță artefactele rămase
  (inclusiv cele două fișiere legacy dacă mai există în folderul operației), ca
  operatorul să poată regenera curat.
- De documentat în `CHANGELOG.md`: proiectele existente necesită re-rularea
  Speech Blocks (breaking change de persistență).

---

## 6. Teste

- Actualizează `tests/test_speech_blocks_*` și
  `test_speech_blocks_report_state_service.py` la noul document unic.
- Adaugă teste: round-trip scriere/citire document, proiecție raport ==
  raportul vechi pe aceleași blocuri, proiecție state == starea veche,
  resume din `checkpoint`, absența `source_chunks` în artefact, un artefact în
  format vechi (listă) e tratat ca inexistent (`None`), iar `reset` curăță
  fișierele legacy.
- Rulează suita completă și `python-codestyle-audit`.

---

## 7. Documentație

- `.agentic/knowledge/components/Speech_Blocks.md` (sau echivalentul existent) —
  actualizează secțiunea de persistență la 1 fișier.
- `05_SoftwareDocu/AudioMancer_Speech_Blocks_Service.md` — schema documentului.
- `05_SoftwareDocu/AudioMancer_Config_And_Settings.md` — constantele fișier.
- `CHANGELOG.md`.
- Bump versiuni în anteturile `@version` ale fișierelor atinse.

---

## 8. Criterii de acceptare

1. Un singur `speech_blocks.json` scris de operație; `*_report.json` și
   `*_state.json` nu mai sunt create.
2. Artefactul nu mai conține copia textului sursă (`source_chunks`).
3. Generare, resume (chunk + segment), resplit pe chunk, aprobări individuale/all,
   insert/delete bloc, reset — funcționează identic.
4. Export proiect și sync manifest produc aceleași rezumate ca înainte.
5. Blocarea editării personajelor cât timp rulează Speech Blocks
   (`characters_ui_controller`) funcționează.
6. Suită verde + codestyle audit + documentație actualizată.

---

## 9. În afara scopului

- Formatul blocului individual, prompturile, logica AI, UI.
- Consolidarea altor operații (audio_blocks, audio_assembly) — plan separat dacă
  se dorește, după același tipar.
