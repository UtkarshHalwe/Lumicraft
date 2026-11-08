# LumiCraft

A Blender addon that adds an advanced lighting engine for Area Lights — soft edges, barn doors, gobo projection, and live two-way Shader Editor sync.

## Features

- **Soft Edges** — unlimited softness with rectangle, rounded rect, and disk falloff shapes
- **Corner Rounding** — smooth corner curvature on rectangular lights
- **Barn Doors** — 4-way linear flap cuts with per-side independent softness and invert mode
- **Gobo Projection** — image texture projection with location X/Y panning, scale, rotation, and softness linking
- **Emission Control** — live-synced strength slider with two-way Shader Editor read/write
- **Target Lock** — auto Track-To constraint to aim the light at any object
- **Shadow Tint Helper** *(experimental)* — cinematic colored shadow tinting via a modular node group

## Requirements

- Blender 4.0+
- Cycles or any renderer that supports Blender's light node tree

## Installation

1. Download `lumicraft.py`
2. In Blender: `Edit > Preferences > Add-ons > Install`
3. Select `lumicraft.py` and enable **LumiCraft**

## Usage

Select any **Area Light**, go to **Properties > Light Data**. The LumiCraft panel appears at the bottom.

Click **Enable Smooth Light** to activate the node graph. All controls update live and stay in sync with the Shader Editor.

## License

MIT — see [LICENSE](LICENSE)
