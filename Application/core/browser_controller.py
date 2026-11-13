"""Translate controller input into virtual keyboard and mouse events."""


class VirtualKeyboard:
    def __init__(self):
        from evdev import UInput, UInputError, ecodes

        self.ecodes = ecodes
        self.keys = {
            "up": ecodes.KEY_UP,
            "down": ecodes.KEY_DOWN,
            "left": ecodes.KEY_LEFT,
            "right": ecodes.KEY_RIGHT,
            "select": ecodes.KEY_ENTER,
            "back": ecodes.KEY_ESC,
            "next_tab": ecodes.KEY_TAB,
            "previous_tab": ecodes.KEY_TAB,
        }
        self.text_keys = {
            **{char: (getattr(ecodes, f"KEY_{char.upper()}"), False) for char in "abcdefghijklmnopqrstuvwxyz0123456789"},
            " ": (ecodes.KEY_SPACE, False),
        }
        for key_name, normal, shifted in (
            ("APOSTROPHE", "'", '"'), ("COMMA", ",", "<"), ("DOT", ".", ">"),
            ("MINUS", "-", "_"), ("SLASH", "/", "?"), ("SEMICOLON", ";", ":"),
            ("EQUAL", "=", "+"), ("BACKSLASH", "\\", "|"), ("GRAVE", "`", "~"),
            ("LEFTBRACE", "[", "{"), ("RIGHTBRACE", "]", "}"),
        ):
            key = getattr(ecodes, f"KEY_{key_name}")
            self.text_keys[normal] = (key, False)
            self.text_keys[shifted] = (key, True)
        for char, digit in zip("!@#$%^&*()", "1234567890"):
            self.text_keys[char] = (getattr(ecodes, f"KEY_{digit}"), True)
        self.text_keys.update({char.upper(): (key, True) for char, (key, _) in list(self.text_keys.items())
                               if char in "abcdefghijklmnopqrstuvwxyz"})
        try:
            self.device = UInput(
                {ecodes.EV_KEY: list({*self.keys.values(), ecodes.KEY_LEFTSHIFT,
                                      *(key for key, _ in self.text_keys.values())})},
                name="Titans Launcher virtual keyboard",
            )
        except UInputError as error:
            raise OSError(str(error)) from error

    def handle_action(self, action):
        key = self.keys.get(action)
        if key is None:
            return
        shift = action == "previous_tab"
        if shift:
            self.device.write(self.ecodes.EV_KEY, self.ecodes.KEY_LEFTSHIFT, 1)
        self.device.write(self.ecodes.EV_KEY, key, 1)
        self.device.syn()
        self.device.write(self.ecodes.EV_KEY, key, 0)
        if shift:
            self.device.write(self.ecodes.EV_KEY, self.ecodes.KEY_LEFTSHIFT, 0)
        self.device.syn()

    def type_text(self, text):
        unsupported = next((character for character in text if character not in self.text_keys), None)
        if unsupported is not None:
            raise ValueError(f"Cannot type character {unsupported!r} in the active application.")
        for character in text:
            key, shift = self.text_keys[character]
            if shift:
                self.device.write(self.ecodes.EV_KEY, self.ecodes.KEY_LEFTSHIFT, 1)
            self.device.write(self.ecodes.EV_KEY, key, 1)
            self.device.syn()
            self.device.write(self.ecodes.EV_KEY, key, 0)
            if shift:
                self.device.write(self.ecodes.EV_KEY, self.ecodes.KEY_LEFTSHIFT, 0)
            self.device.syn()

    def close(self):
        self.device.close()


class BrowserController(VirtualKeyboard):
    def __init__(self):
        from evdev import UInput, UInputError

        super().__init__()
        try:
            self.mouse = UInput(
                {
                    self.ecodes.EV_KEY: [self.ecodes.BTN_LEFT, self.ecodes.BTN_RIGHT],
                    self.ecodes.EV_REL: [self.ecodes.REL_X, self.ecodes.REL_Y],
                },
                name="Titans Launcher browser mouse",
            )
        except (OSError, UInputError) as error:
            self.device.close()
            raise OSError(str(error)) from error
        self.mouse_buttons = {self.ecodes.BTN_LEFT: False, self.ecodes.BTN_RIGHT: False}
        self.mouse_remainder = [0.0, 0.0]

    def handle_pointer(self, x, y, left_trigger, right_trigger):
        changed = False
        for index, (value, axis) in enumerate(((x, self.ecodes.REL_X), (y, self.ecodes.REL_Y))):
            magnitude = max(0.0, (abs(value) - 0.18) / 0.82)
            movement = (1 if value >= 0 else -1) * magnitude * magnitude * 18
            self.mouse_remainder[index] += movement
            pixels = int(self.mouse_remainder[index])
            self.mouse_remainder[index] -= pixels
            if pixels:
                self.mouse.write(self.ecodes.EV_REL, axis, pixels)
                changed = True

        for button, value in (
            (self.ecodes.BTN_LEFT, right_trigger),
            (self.ecodes.BTN_RIGHT, left_trigger),
        ):
            pressed = value >= (0.4 if self.mouse_buttons[button] else 0.5)
            if pressed != self.mouse_buttons[button]:
                self.mouse.write(self.ecodes.EV_KEY, button, int(pressed))
                self.mouse_buttons[button] = pressed
                changed = True
        if changed:
            self.mouse.syn()

    def close(self):
        self.mouse.close()
        super().close()
