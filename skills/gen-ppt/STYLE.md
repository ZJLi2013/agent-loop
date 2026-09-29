# Default presentation style

Use this unless the user already has a deck or a palette. One deck, one theme.

## Canvas and typography

- Canvas: 13.333 × 7.5 in (16:9).
- Typeface: Aptos.
- Content bounds: x = 0.70–12.62 in; y = 0.26–6.65 in.
- Kicker: x 0.68, y 0.26, 9 pt, bold, blue, uppercase.
- Title: x 0.68, y 0.52, 27 pt, bold, navy.
- Subtitle: x 0.70, y 1.05, 11.5 pt, gray.
- Main content begins near y 1.55–1.70.
- Footer links sit at y 7.05 and align right.

## Palette

Color encodes a role. Do not spend a hue on decoration.

| Token | RGB | Role |
|---|---:|---|
| `NAVY` | 16, 42, 67 | Titles, conclusions |
| `BLUE` | 71, 96, 255 | Primary structure |
| `BLUE_DARK` | 47, 66, 190 | Small blue labels |
| `TEAL` | 0, 151, 167 | Links, secondary flow |
| `GREEN` | 23, 143, 94 | Accepted, done, positive |
| `ORANGE` | 231, 122, 58 | Risk, cost, boundary |
| `GRAY` | 91, 107, 121 | Supporting text, neutral lines |
| `LIGHT_BLUE` | 237, 241, 255 | Primary card fill |
| `LIGHT_TEAL` | 232, 248, 248 | Teal card fill |
| `LIGHT_GREEN` | 234, 247, 240 | Green card fill |
| `LIGHT_ORANGE` | 255, 244, 234 | Orange card fill |
| `LIGHT_GRAY` | 244, 246, 248 | Neutral card fill |

## Layout patterns

### Title slide

- Kicker and a short accent rule at y 2.05–2.48.
- Main claim at 40 pt, at most two lines.
- Subtitle at 17 pt.
- Three compact cards in the bottom third.

### Comparison

- Three equal cards across the upper half.
- Two wider cards below for the pair being contrasted.
- One centered conclusion at the bottom.

### Problem to decision

- Repeated rows, same height.
- Neutral problem card, short arrow, colored decision card, one sentence.

### System overview

- Stacked subsystem cards on one side.
- One source diagram on the other.
- One short invariant under the stack.

### Flow

- The shared contract sits above the flow.
- Left-to-right cards and straight connectors.
- Variants sit below in two large cards.
- One invariant centered near the bottom.

### Timeline

- Keep the standard title block.
- A real timeline artifact fills the remaining width.
- Recolor the artifact to this palette when practical.

## Geometry

- 0.25–0.45 in between neighboring groups.
- Repeated cards share width, height, and y.
- Rounded cards: pale fill, 1.4 pt outline, no shadow.
- Connectors: 1.5–2 pt, visible arrowhead.
- Images keep aspect ratio and sit centered in their rectangle.
- Do not stretch an image to both the allotted width and height.

## Density

- One claim per slide.
- Usually 30–70 words outside diagrams.
- Card title 13–15 pt; detail 10.5–11 pt.
- At most three lines of detail in a card.
- More than five primary groups means split the slide or cut a group.
