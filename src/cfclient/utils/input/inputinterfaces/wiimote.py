# -*- coding: utf-8 -*-
import logging
from threading import Thread
import time

try:
    import cwiid
except ImportError as e:
    raise Exception("Missing cwiid (wiimote) driver {}".format(e))

logger = logging.getLogger(__name__)

MODULE_MAIN = "WiimoteReader"
MODULE_NAME = "WII"


class _Reader(object):
    # needs attributes:
    # - name
    # - limit_rp
    # - limit_thrust
    # - limit_yaw
    # - open

    def devices(self):
        """List all the available connections"""
        raise NotImplementedError

    def open(self, device_id):
        """
        Initialize the reading and open the device with deviceId and set the
        mapping for axis/buttons using the inputMap
        """
        return

    def close(self, device_id):
        return

    def read(self, device_id):
        """Read input from the selected device."""
        raise NotImplementedError


TWO = 1
ONE = 2
B = 4
A = 8
MINUS = 16
HOME = 128
LEFT = 256
RIGHT = 512
DOWN = 1024
UP = 2048
PLUS = 4096


class HandleWiimote(Thread):

    def __init__(self, reader, wii, *args):
        super(HandleWiimote, self).__init__(*args)
        self.reader = reader
        self.wii = wii
        self.daemon = True

    def run(self):
        logger.info("\n\nRUNNING THREAD!\n\n\n")
        t_delta = 100
        move_delta = .3
        max_move = 8
        min_sample = .1
        max_sample = .01
        sample = min_sample
        while True:
            button = self.wii.state['buttons']
            pitch = self.reader.data['pitch']
            roll = self.reader.data['roll']
            if button & ONE:
                logger.info("UP!! {}".format(self.reader.data['thrust']))
                self.reader.data['thrust'] += t_delta
            if button & TWO:
                logger.info("DOWN!! {}".format(self.reader.data['thrust']))
                self.reader.data['thrust'] -= t_delta * 3
                if self.reader.data['thrust'] < -1:
                    self.reader.data['thrust'] = -1
            if button & RIGHT:
                logger.info("RIGHT PITCH {}".format(pitch))
                self.reader.data['pitch'] = min(max_move, pitch + move_delta)
            if button & LEFT:
                logger.info("LEFT PITCH {}".format(pitch))
                self.reader.data['pitch'] = max(-max_move, pitch - move_delta)
            if button & UP:
                logger.info("UP ROLL {}".format(roll))
                self.reader.data['roll'] = max(-max_move, roll - move_delta)
            if button & DOWN:
                logger.info("DOWN ROLL {}".format(roll))
                self.reader.data['roll'] = min(max_move, roll + move_delta)
            if button & B:
                # KILL
                self.reader.data['thrust'] = -1

            if button:
                sample = max(max_sample, sample / 3)
            else:
                sample = min(min_sample, sample * 3)
                self.adjust()
            time.sleep(sample)

    def adjust(self):
        pitch = self.reader.data['pitch']
        if pitch > 1.2:
            self.reader.data['pitch'] -= 1
        elif pitch < -1.2:
            self.reader.data['pitch'] += 1
        else:
            self.reader.data['pitch'] = 0
        roll = self.reader.data['roll']
        if roll > 1.2:
            self.reader.data['roll'] -= 1
        elif roll < -1.2:
            self.reader.data['roll'] += 1
        else:
            self.reader.data['roll'] = 0


class WiimoteReader(_Reader):
    name = MODULE_NAME

    def __init__(self):
        self.limit_rp = False
        self.limit_thrust = False
        self.limit_yaw = False

        print("Press 1 + 2 to connect wii")
        time.sleep(1)
        self.wm = cwiid.Wiimote()
        self.wm.rpt_mode = cwiid.RPT_BTN
        logger.info("FOUND WIIMOTE")
        self.data = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                     "thrust": -1.0, "estop": False, "exit": False,
                     "assistedControl": False, "alt1": False, "alt2": False,
                     "pitchNeg": False, "rollNeg": False,
                     "pitchPos": False, "rollPos": False}
        self.wii_thread = HandleWiimote(self, self.wm)
        self.wii_thread.start()

    def read(self, dev_id):
        return self.data

    def devices(self):
        """List all the available connections"""
        return [{"id": 0, "name": "WII@{}".format(self.wm)}]
