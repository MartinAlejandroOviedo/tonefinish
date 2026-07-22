# Dataset para IA

Esta carpeta guarda la documentacion y datos que usara la IA para generar prompts de Suno.

Formato actual: JSONL.

Archivo principal:
- `suno.jsonl`

Cada linea debe ser un objeto JSON independiente. Campos usados por el dataset curado:
- `id`
- `text`
- `section_title`
- `source`
- `topic`
- `intent`
- `word_count`
- `difficulty`

La tab `Suno Prompts` apunta por defecto a `dataset/suno.jsonl`.
