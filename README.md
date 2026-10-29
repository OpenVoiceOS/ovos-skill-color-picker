# <img src="https://raw.githack.com/FortAwesome/Font-Awesome/master/svgs/solid/palette.svg" card_color="#22A7F0" width="50" height="50" style="vertical-align:bottom"/> Color Picker
Look up colors by voice. The skill uses [ovos-color-parser](https://github.com/OpenVoiceOS/ovos-color-parser) to find the hex and RGB values for standard color names.

## About
Ask for a color by name. The skill returns the hex and RGB values for any standard color name.

<p float="left">
  <img src="screenshots/screenshot-color-fire-brick.png" width="300" alt="Screenshot of Fire Brick request" />
  <img src="screenshots/screenshot-color-light-sea-green.png" width="300" alt="Screenshot of Light Sea Green request" />
</p>

## Examples
* "What is the hex value for {color}"
* "Show me the color {color}"

## Entity hints

The skill ships `locale/<lang>/entities/color.entity`, listing common color names ("red", "teal", "fire brick", "light sea green", ...) for the `{color}` slot. These are hints, not a closed list: a color name not on the list still fills the slot and is looked up by [ovos-color-parser](https://github.com/OpenVoiceOS/ovos-color-parser); listed names simply match with more confidence. `ovos-workshop` (>=9.5.0a1) registers every shipped `.entity` file automatically when the skill's language resources are loaded, so nothing needs to be configured for this.

## Credits
krisgesling

## Category
**Information**

## Tags
#Color picker
#Hex
#Rgb
#Css3

