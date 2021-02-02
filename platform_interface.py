import hid
import threading
from led_processing import LedProcessor
import numpy as np
from keyboard_input import KeyboardInput

class PlatformInterface():
    def enumerate(self):
        devices = [d for d in hid.enumerate(self.USB_VID, self.USB_PID)]
        return devices

    def launch(self, serial, sensitivities):
        if serial == None:
            serial = '0'
        self.h = hid.device()
        try:
            self.h.open(self.USB_VID, self.USB_PID, serial_number=serial)
        except:
            return 0
        if self.h.get_product_string() == 'RE:Flex Dance Pad':
            self.is_running = True
            self.setup(sensitivities)
            return 1
        else:
            self.is_running = False
            return 0

    def assign_led_files(self, led_files):
        self.led_files = led_files
        self.led_sources = [
            LedProcessor.from_file(self.led_files[0], 90),
            LedProcessor.from_file(self.led_files[1], 180),
            LedProcessor.from_file(self.led_files[2], 0),
            LedProcessor.from_file(self.led_files[3], 270)
        ]

    def setup(self, sensitivities):
        self.sample_counter = 0

        data = self.h.read(64)
        self.organize_data(data)
        self.sum_panel_data(self.panel_data)
        self.keyboard_input = KeyboardInput(self.panel_values, sensitivities)

        directions = ( 'left', 'down', 'up', 'right' )

        self.panels = [ Panel(direction) for direction in directions ]
        self.pressed_on_frame = list(range(4))
        self.led_frame_data = 0
        self.led_data = []
        self.lights_counter = 0

        thread = threading.Thread(target=self.loop, daemon=True)
        thread.start()


    def loop(self):
        while True:
            for led_frame in range(0,16):
                for led_panel in range(0,4):
                    self.lights_counter += 1
                    if self.keyboard_input.is_pressed[led_panel]:
                        self.pressed_on_frame[led_panel] = 1
                    else:
                        self.pressed_on_frame[led_panel] = 0

                    for led_segment in range(0,4):
                        if not self.is_running:
                            return
                        data = self.h.read(64)
                        self.organize_data(data)
                        self.sum_panel_data(self.panel_data)
                        self.keyboard_input.poll_keys(self.panel_values)
                        self.sample_counter += 1
            
                        self.update_led_frame(led_frame, led_segment, led_panel)
                        self.h.write(bytes(self.led_data))

    def update_led_frame(self, led_frame, led_segment, led_panel):
        self.led_frame_data = led_panel << 6 | led_segment << 4 | led_frame

        source = self.led_sources[led_panel]
        segment_data = source.get_segment_data(led_segment)

        panel = self.panels[led_panel]
        panel.framestep(self.keyboard_input.just_pressed[led_panel])
        self.keyboard_input.just_pressed[led_panel] = 0
        brightness = panel.brightness
        
        # brightness = 1.0 if self.pressed_on_frame[led_panel] else 0.1

        self.led_data = [0, self.led_frame_data] + [ clamp(value * brightness) for value in segment_data ]

    def sensor_rate(self):
        polling_rate = self.sample_counter
        self.sample_counter = 0
        return polling_rate
    
    def lights_rate(self):
        polling_rate = self.lights_counter // 4
        self.lights_counter = 0
        return polling_rate

    def stop_loop(self):
        self.is_running = False

    def sum_panel_data(self, panel_data):
        self.panel_values = []
        for panel in range(0, 4):
            self.panel_values.append(0)
            for sensor in range(0, 4):
                self.panel_values[panel] += self.panel_data[sensor + 4 * (panel)]

    def organize_data(self, data):
        self.panel_data = []
        for i in range(0, 32):
            self.panel_data.append(0)
        data_index = 0
        for data_point in data:
            if data_index % 2 == 0:
                self.panel_data[data_index // 2] = data_point
            if data_index % 2 == 1:
                self.panel_data[data_index // 2] |= 0x0FFF & (data_point << 8)
            data_index += 1

    USB_VID = 0x0483 # Vendor ID for I/O Microcontroller
    USB_PID = 0x5750 # Product ID for I/O Microcontroller
    panel_data = []

clamp = lambda x: 255 if x > 255 else 0 if x < 0 else int(x)

class Panel():
    def __init__(self, name):
        self.name = name
        self.brightness_min = 0.1
        self.brightness_max = 1.2

        self.brightness = self.brightness_min
        self.impulse_frames = 0
        self.delta_brightness = 0

        # brightness will go from min to max in impulse_duration frames
        self.up_duration = 6
        self.up_delta = (self.brightness_max - self.brightness_min) / self.up_duration
        self.down_duration = 60
        self.down_delta = - ((self.brightness_max - self.brightness_min) / self.down_duration)

    def framestep(self, just_fired):
        if just_fired:
            self.delta_brightness = self.up_delta
            self.impulse_frames = self.up_duration
        if self.impulse_frames > 0:
            self.impulse_frames -= 1
        else:
            self.delta_brightness = self.down_delta

        self.brightness += self.delta_brightness

        if self.brightness > self.brightness_max: self.brightness = self.brightness_max
        if self.brightness < self.brightness_min: self.brightness = self.brightness_min

if __name__ == "__main__":
    pf = PlatformInterface()