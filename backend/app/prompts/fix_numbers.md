Some scenes of a results-video script break the rule that numbers may only appear as placeholders. Rewrite ONLY the listed scenes so that:

- every problem listed for a scene is gone: no digits, no number words (million, billion, percent, hundred, thousand / مليون، مليار، بالمئة، ألف), no unknown placeholders;
- figures that have a matching placeholder in PLACEHOLDERS are written as that placeholder, e.g. `{{revenue}}`;
- figures with no placeholder are described in words without a number ("sharply lower") or removed;
- for Arabic scenes, the scene uses exactly the placeholders listed in `required_placeholders`;
- the meaning, tone and approximate length stay the same.

Return only JSON: {"scenes": [{"id": "s2", "text": "..."}]}, one entry per listed scene, in the scene's language.
