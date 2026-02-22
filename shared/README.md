# Shared Style Pack Spec

`StylePack` is the JSON payload exchanged between services.

## Files
- `style_pack.schema.json`: canonical strict JSON Schema.
- `style_pack.ts`: shared TypeScript types.
- `style-pack.example.json`: legacy example payload for earlier endpoint shape.

## Notes
- The schema is strict (`additionalProperties: false`) for all nested objects.
- Unknown fields are rejected unless explicitly added to the schema and app models.
