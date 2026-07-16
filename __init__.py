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

    @intent_handler("request-color.intent")
    def handle_request_color(self, message: Message):
        """Handle requests for color where the color format is unknown.

        Example: 'What color is _________'
        """
        requested_color = message.data.get("requested_color")
        if is_hex_code_valid(requested_color.replace(" ", "")):
            message = message.forward("", {"hex_code": requested_color.replace(" ", "")})
            self.handle_request_color_by_hex(message)
            return

        try:
            r, g, b = requested_color.split()
            message = message.forward("", {"rgb": requested_color})
            self.handle_request_color_by_rgb(message)
            return
        except:  # not rgb
            pass

        message = message.forward("", {"color": requested_color})
        self.handle_request_color_by_name(message)

    @intent_handler("request-color-by-name.intent")
    def handle_request_color_by_name(self, message: Message):
        """Handle named color requests.

        Example: 'Show me the color burly wood'
        """
        requested_color = message.data.get("color") or ""
        self.log.info("Requested color: %s", requested_color)

        # The {color} slot is open text: a demonstrative pronoun ("set the
        # color to that") must not be looked up as a color. The slot-value
        # exclusion in color.blacklist marks such values as non-colors; the
        # engine does not enforce slot .blacklist yet, so reject a blacklisted
        # value here and re-prompt instead of reporting a bogus color.
        excluded = self._slot_blacklist(self.lang)
        if requested_color.strip().lower() in excluded:
            self.speak_dialog("color-not-found")
            return

        color = color_from_description(requested_color, lang=self.lang.split("-")[0],
                                       cast_to_palette=self.settings.get("cast_to_palette", True),
                                       fuzzy=self.settings.get("fuzzy", True))
        if color is None:
            self.speak_dialog("color-not-found")
            return

        self.speak_dialog(
            "report-color-by-name",
            data={
                "color_name": color.name,
                "hex_code": color.hex_str,
                "red_value": color.r,
                "green_value": color.g,
                "blue_value": color.b,
            },
        )
        self.display_single_color(color)

    @intent_handler("request-color-by-hex.intent")
    def handle_request_color_by_hex(self, message: Message):
        """Handle named color requests.

        Example: 'what color has a hex code of bada55'
        """
        requested_hex_code = message.data.get("hex_code").replace(" ", "")
        self.log.info("Requested color: %s", requested_hex_code)
        if not is_hex_code_valid(requested_hex_code):
            self.speak_dialog("color-not-found")
            return

        color = sRGBAColor.from_hex_str(requested_hex_code)
        try:
            color.name = lookup_name(color, lang=self.lang.split("-")[0])
        except ValueError:
            # color is not named
            pass

        if color.name:
            self.speak_dialog(
                "report-color-by-hex-name-known",
                data={
                    "color_name": color.name,
                    "red_value": color.r,
                    "green_value": color.g,
                    "blue_value": color.b,
                }
            )
        else:
            self.speak_dialog(
                "report-color-by-hex-name-not-known",
                data={
                    "red_value": color.r,
                    "green_value": color.g,
                    "blue_value": color.b,
                }
            )

    @intent_handler("request-color-by-rgb.intent")
    def handle_request_color_by_rgb(self, message: Message):
        """
        Handle RGB color requests

        Example: what color has the RGB value of 172 172 172
        """
        try:
            r, g, b = message.data["rgb"].split()
            color = sRGBAColor(r, g, b)
        except ValueError:
            self.speak_dialog("color-not-found")
            return

        try:
            color.name = lookup_name(color, lang=self.lang.split("-")[0])
        except ValueError:
            # color is not named
            pass

        if color.name is None:
            self.speak_dialog(
                "report-color-by-rgb-name-not-known",
                data={"red_value": color.r,
                      "green_value": color.g,
                      "blue_value": color.b}
            )
        else:
            speakable_hex_code = color.hex_str  # TODO
            self.speak_dialog(
                "report-color-by-rgb-name-known",
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

