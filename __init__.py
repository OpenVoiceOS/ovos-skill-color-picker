import re
from typing import Set

from ovos_bus_client.message import Message

from ovos_color_parser import sRGBAColor, color_from_description, get_contrasting_black_or_white
from ovos_color_parser.matching import is_hex_code_valid, lookup_name
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills.ovos import OVOSSkill


class ColorPickerSkill(OVOSSkill):

    def _slot_blacklist(self, lang: str) -> Set[str]:
        """Return the values that may not fill the {color} slot for ``lang``.

        Reads ``color.blacklist`` and resolves any ``<voc>`` reference to the
        matching vocabulary file, so a demonstrative pronoun cannot be looked
        up as if it were a named color.
        """
        path = self.find_resource("color.blacklist", lang=lang)
        if not path:
            return set()
        terms: Set[str] = set()
        with open(path) as blacklist:
            for line in blacklist:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                voc = re.match(r"^<(.+)>$", line)
                if voc:
                    terms.update(v.lower() for v in self.voc_list(voc.group(1), lang=lang))
                else:
                    terms.add(line.lower())
        return terms

    @intent_handler("request_color_by_name.intent")
    def handle_request_color_by_name(self, message: Message):
        """Handle requests that name a color.

        Example: 'What color is burly wood' or 'Show me the color teal'

        The open {color} slot can also hold a hex code or three RGB values;
        those go to the hex and RGB handlers.
        """
        requested_color = (message.data.get("color") or "").strip()
        self.log.info("Requested color: %s", requested_color)

        # The {color} slot is open text: a demonstrative pronoun ("set the
        # color to that") must not be looked up as a color. The slot-value
        # exclusion in color.blacklist marks such values as non-colors; the
        # engine does not enforce slot .blacklist yet, so reject a blacklisted
        # value here and re-prompt instead of reporting a bogus color.
        if not requested_color or requested_color.lower() in self._slot_blacklist(self.lang):
            self.speak_dialog("color_not_found")
            return

        hex_code = requested_color.replace(" ", "")
        if is_hex_code_valid(hex_code):
            self.handle_request_color_by_hex(message.forward("", {"hex_code": hex_code}))
            return

        values = requested_color.split()
        if len(values) == 3 and all(value.isdigit() for value in values):
            self.handle_request_color_by_rgb(message.forward("", {"rgb": requested_color}))
            return

        color = color_from_description(requested_color, lang=self.lang.split("-")[0],
                                       cast_to_palette=self.settings.get("cast_to_palette", True),
                                       fuzzy=self.settings.get("fuzzy", True))
        if color is None:
            self.speak_dialog("color_not_found")
            return

        self.speak_dialog(
            "report_color_by_name",
            data={
                "color_name": color.name,
                "hex_code": color.hex_str,
                "red_value": color.r,
                "green_value": color.g,
                "blue_value": color.b,
            },
        )
        self.display_single_color(color)

    @intent_handler("request_color_by_hex.intent")
    def handle_request_color_by_hex(self, message: Message):
        """Handle named color requests.

        Example: 'what color has a hex code of bada55'
        """
        # ovos-spec-tools>=1.6.3a1 fixes normalize_for_match() so a direct
        # request_color_by_hex.intent match surfaces the spec-correct
        # underscored key "hex_code" (same key the internal forward() from
        # handle_request_color_by_name sets).
        requested_hex_code = (message.data.get("hex_code") or "").replace(" ", "")
        self.log.info("Requested color: %s", requested_hex_code)
        if not is_hex_code_valid(requested_hex_code):
            self.speak_dialog("color_not_found")
            return

        color = sRGBAColor.from_hex_str(requested_hex_code)
        try:
            color.name = lookup_name(color, lang=self.lang.split("-")[0])
        except ValueError:
            # color is not named
            pass

        if color.name:
            self.speak_dialog(
                "report_color_by_hex_name_known",
                data={
                    "color_name": color.name,
                    "red_value": color.r,
                    "green_value": color.g,
                    "blue_value": color.b,
                }
            )
        else:
            self.speak_dialog(
                "report_color_by_hex_name_not_known",
                data={
                    "red_value": color.r,
                    "green_value": color.g,
                    "blue_value": color.b,
                }
            )

    @intent_handler("request_color_by_rgb.intent")
    def handle_request_color_by_rgb(self, message: Message):
        """
        Handle RGB color requests

        Example: what color has the RGB value of 172 172 172
        """
        try:
            r, g, b = (message.data.get("rgb") or "").split()
            color = sRGBAColor(int(r), int(g), int(b))
        except ValueError:
            self.speak_dialog("color_not_found")
            return

        try:
            color.name = lookup_name(color, lang=self.lang.split("-")[0])
        except ValueError:
            # color is not named
            pass

        if color.name is None:
            self.speak_dialog(
                "report_color_by_rgb_name_not_known",
                data={"hex_code": color.hex_str,
                      "red_value": color.r,
                      "green_value": color.g,
                      "blue_value": color.b}
            )
        else:
            speakable_hex_code = color.hex_str  # TODO
            self.speak_dialog(
                "report_color_by_rgb_name_known",
                data={
                    "color_name": color.name,
                    "hex_code": speakable_hex_code
                }
            )

    def display_single_color(self, color: sRGBAColor):
        """Display details of a single color"""
        self.gui["colorName"] = color.name.title()
        self.gui["colorHex"] = color.hex_str.upper()
        self.gui["colorRGB"] = f"RGB: {color.r}, {color.g}, {color.b}"
        self.gui["textColor"] = get_contrasting_black_or_white(color.hex_str.upper()).hex_str.upper()
        self.gui.show_page("single-color")

