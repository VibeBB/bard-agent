# Examples

`minimal.en.json` is an English verse-chorus example; `minimal.ja.json` is a
Japanese example (kanji `text` + kana `reading`) using strophic repetition
(`melody_from`). Both are complete schema 0.3 proposals and can be passed to
`--check` or rendered as-is. New songs are fastest to build by copying one of
these and editing it. Both are render-verified in CI.

`smart-kettle.cues.json` is a product cue set (`bard_cue_set` 0.1) with startup, completion,
warning and confirm cues for a piezo buzzer; render it with `scripts/render_cues.py`.
