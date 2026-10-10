A results-video script is too long. Each video must run no more than three minutes. Shorten the English and Arabic narration so each language fits its word budget.

# Rules
- `max_words_en` and `max_words_ar` are totals across all scenes. Stay under both. Each placeholder counts as the words it reads as (see PLACEHOLDERS).
- Cut repetition, filler and secondary detail first. Keep the main result, the reasons behind it and the outlook.
- Keep every scene and its id. Keep each scene's English and Arabic saying the same thing.
- Keep EVERY placeholder exactly as written, including the double braces: `{{revenue}}` stays `{{revenue}}`. In each scene the English and Arabic must use the same placeholders. You may drop a placeholder only from both languages of that scene together, and never from the `kpis` scene.
- Never write a number yourself: no digits, no number words (million, billion, percent, hundred, thousand / مليون، مليار، بالمئة، ألف، نصف، ضعف), no years or dates.
- Keep the tone: calm broadcast business news; Arabic in formal Modern Standard Arabic (Gulf news style).

# Output
Return only JSON: {"scenes": [{"id": "s1", "en": "...", "ar": "..."}]}, one entry per input scene, same ids.
