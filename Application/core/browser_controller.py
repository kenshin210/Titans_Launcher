"""Translate launcher controller actions into keyboard input for browser shortcuts."""


class BrowserController:
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
        try:
            self.device = UInput(
                {ecodes.EV_KEY: [*set(self.keys.values()), ecodes.KEY_LEFTSHIFT]},
                name="Titans Launcher browser controller",
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

    def close(self):
        self.device.close()
