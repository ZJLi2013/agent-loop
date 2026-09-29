---
name: gen-ppt
description: >-
  Generates or restyles concise 16:9 PowerPoint decks with python-pptx.
  Use when the user asks to create, update, or polish a PPT/PPTX, presentation,
  slide deck, roadmap, or architecture diagram, or names gen-ppt.
disable-model-invocation: true
---

# Generate PowerPoint

Write a deck-specific generator with `python-pptx`. Shared canvas, palette, and
shape helpers live in `scripts/ppt_style.py`.

## Workflow

1. Read the source and name the deck's one-sentence conclusion, the audience,
   and the output path.
2. If a deck already exists, inspect its size, text, pictures, and order before
   changing it. Keep diagrams and images that still carry information.
3. Draft an outline. Each slide states one claim in its title. Drop slides that
   only repeat background.
4. Put the generator next to the output, or where the user asked. Add this
   skill's `scripts` directory to `sys.path` and import `ppt_style`.
5. Write the `.pptx`. Render it to images or PDF when a renderer exists, and
   look at every slide.
6. Fix clipping, overlap, weak hierarchy, type below 8.5 pt, uneven spacing,
   and claims the source does not support. Regenerate and look again.
7. Return the generator path and the deck path. Say whether the slides were
   actually rendered.

## Visual system

Default style is in [STYLE.md](STYLE.md): 16:9, white canvas, Aptos, a navy /
blue / teal / green / orange palette, and a fixed title block (kicker, claim,
one-line subtitle).

If the user supplies a deck, brand, or palette, follow that instead of the
default. Do not invent a second theme inside one deck.

- Prefer native shapes, connectors, and text over screenshots of text.
- Align diagrams to a grid. One flow direction. Label an arrow only when the
  payload matters.
- Bold is for short labels, not for whole paragraphs.
- Footer links are small and sit at the lower right.

## Content

- The title is the conclusion. Do not add a trailing "summary" box that repeats it.
- Concrete nouns and verbs. Cut scene-setting and repeated qualifiers.
- Card title: one line. Card body: at most three short lines.
- Three to five groups per slide.
- Diagram for relationships, timeline for sequence, cards for comparison.
  Do not pour prose into decorative boxes.
- Only facts from the user or from material you checked. Mark unknown values.
  Do not invent metrics, dates, links, or status.
- Reuse plots, screenshots, and diagrams the user supplied. Do not generate
  decorative images.

## Primitives

```python
from ppt_style import (
    BLUE,
    GREEN,
    ORANGE,
    TEAL,
    add_blank_slide,
    arrow,
    box,
    link,
    new_deck,
    place_picture,
    rule,
    text_box,
    title,
)
```

One named function per slide. Keep the words and the geometry at the call site.

## Verification

- Re-open the file with `python-pptx`: expected slide count, 13.333 × 7.5 in.
- Render with PowerPoint, LibreOffice, or whatever is installed, and inspect
  the montage at normal size.
- Clipped text, overlap, off-slide objects, unreadable labels, or a stretched
  image means the deck failed.
- When updating a deck, source path and output path must differ.

Serialization without a render is not visual verification. Say so if no
renderer is available.
