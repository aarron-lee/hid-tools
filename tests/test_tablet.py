#!/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021 Benjamin Tissoires <benjamin.tissoires@gmail.com>
# Copyright (c) 2021 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from . import base
from hidtools.util import BusType
import libevdev
import logging
import pytest

logger = logging.getLogger('hidtools.test.tablet')


class Data(object):
    pass


class Pen(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.confidence = True
        self.tipswitch = False
        self.tippressure = 15
        self.azimuth = 0
        self.inrange = True
        self.width = 10
        self.height = 10
        self.barrelswitch = False
        self.invert = False
        self.eraser = False
        self.x_tilt = False
        self.y_tilt = False
        self.twist = 0


class PenDigitizer(base.UHIDTestDevice):
    def __init__(self, name, rdesc_str=None, rdesc=None, application='Pen', physical='Stylus', input_info=(BusType.USB, 1, 2), evdev_name_suffix=None):
        super().__init__(name, application, rdesc_str, rdesc, input_info)
        self.physical = physical
        self.cur_application = application
        if evdev_name_suffix is not None:
            self.name += evdev_name_suffix

        self.fields = []
        for r in self.parsed_rdesc.input_reports.values():
            if r.application_name == self.application:
                physicals = [f.physical_name for f in r]
                if self.physical not in physicals and None not in physicals:
                    continue
                self.fields = [f.usage_name for f in r]

    def event(self, pen):
        rs = []
        r = self.create_report(application=self.cur_application, data=pen)
        self.call_input_event(r)
        rs.append(r)
        return rs

    def get_report(self, req, rnum, rtype):
        if rtype != self.UHID_FEATURE_REPORT:
            return (1, [])

        rdesc = None
        for v in self.parsed_rdesc.feature_reports.values():
            if v.report_ID == rnum:
                rdesc = v

        if rdesc is None:
            return (1, [])

        return (1, [])

    def set_report(self, req, rnum, rtype, data):
        if rtype != self.UHID_FEATURE_REPORT:
            return 1

        rdesc = None
        for v in self.parsed_rdesc.feature_reports.values():
            if v.report_ID == rnum:
                rdesc = v

        if rdesc is None:
            return 1

        return 1


class BaseTest:
    class TestTablet(base.BaseTestCase.TestUhid):
        def create_device(self):
            raise Exception('please reimplement me in subclasses')

        def post(self, uhdev, pen):
            r = uhdev.event(pen)
            events = uhdev.next_sync_events()
            self.debug_reports(r, uhdev, events)
            return events

        def test_hover(self):
            """Pen goes from out of range to in-range, without the intent
            to erase"""
            uhdev = self.uhdev
            evdev = uhdev.get_evdev()

            p = Pen(50, 60)
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 1) in events
            assert evdev.value[libevdev.EV_ABS.ABS_X] == 50
            assert evdev.value[libevdev.EV_ABS.ABS_Y] == 60

            p.inrange = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 0) in events

        def test_contact(self):
            """Pen goes from out of range to in-range, without the intent
            to erase, then touch/release"""
            uhdev = self.uhdev
            evdev = uhdev.get_evdev()

            p = Pen(50, 60)
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 1) in events
            assert evdev.value[libevdev.EV_ABS.ABS_X] == 50
            assert evdev.value[libevdev.EV_ABS.ABS_Y] == 60

            p.tipswitch = True
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1) in events

            p.tipswitch = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0) in events

            p.inrange = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 0) in events

        def assertName(self, uhdev):
            evdev = uhdev.get_evdev()
            assert evdev.name == uhdev.name + ' Stylus'

        def test_scribble(self):
            """Pen touches, then scribble on screen
               Actual reporting from the device: hid=TIPSWITCH,INRANGE (code=TOUCH,TOOL_PEN):
                 { 0, 1 } <- hover
                 { 1, 1 } <- touch-down
                 { 1, 1 } <- still touch, scribble on the screen
                 { 0, 1 } <- liftoff
                 { 0, 0 } <- leaves
            """

            uhdev = self.uhdev
            evdev = uhdev.get_evdev()

            p = Pen(50, 60)
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 1) in events
            assert evdev.value[libevdev.EV_ABS.ABS_X] == 50
            assert evdev.value[libevdev.EV_ABS.ABS_Y] == 60

            p.tipswitch = True
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1) in events

            p.x += 1
            p.y -= 1
            events = self.post(uhdev, p)
            assert len(events) == 3  # X, Y, SYN
            assert libevdev.InputEvent(libevdev.EV_ABS.ABS_X, 51) in events
            assert libevdev.InputEvent(libevdev.EV_ABS.ABS_Y, 59) in events

            p.tipswitch = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0) in events

            p.inrange = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 0) in events

        @pytest.mark.skip_if_uhdev(lambda uhdev: 'Barrel Switch' not in uhdev.fields,
                                   'Device not compatible, missing Barrel Switch usage')
        def test_primary_button(self):
            """Primary button (stylus) pressed, reports as pressed even while hovering.
               Actual reporting from the device: hid=TIPSWITCH,BARRELSWITCH,INRANGE (code=TOUCH,STYLUS,PEN):
                 { 0, 0, 1 } <- hover
                 { 0, 1, 1 } <- primary button pressed
                 { 0, 1, 1 } <- liftoff
                 { 0, 0, 0 } <- leaves
            """

            uhdev = self.uhdev
            evdev = uhdev.get_evdev()

            p = Pen(50, 60)
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 1) in events
            assert evdev.value[libevdev.EV_ABS.ABS_X] == 50
            assert evdev.value[libevdev.EV_ABS.ABS_Y] == 60
            assert not evdev.value[libevdev.EV_KEY.BTN_STYLUS]

            p.barrelswitch = True
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_STYLUS, 1) in events

            p.x += 1
            p.y -= 1
            events = self.post(uhdev, p)
            assert len(events) == 3  # X, Y, SYN
            assert libevdev.InputEvent(libevdev.EV_ABS.ABS_X, 51) in events
            assert libevdev.InputEvent(libevdev.EV_ABS.ABS_Y, 59) in events

            p.barrelswitch = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_STYLUS, 0) in events

            p.inrange = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 0) in events

        @pytest.mark.skip_if_uhdev(lambda uhdev: 'Barrel Switch' not in uhdev.fields,
                                   'Device not compatible, missing Barrel Switch usage')
        def test_contact_primary_button(self):
            """Primary button (stylus) pressed, reports as pressed even while hovering.
               Actual reporting from the device: hid=TIPSWITCH,BARRELSWITCH,INRANGE (code=TOUCH,STYLUS,PEN):
                 { 0, 0, 1 } <- hover
                 { 0, 1, 1 } <- primary button pressed
                 { 1, 1, 1 } <- touch-down
                 { 1, 1, 1 } <- still touch, scribble on the screen
                 { 0, 1, 1 } <- liftoff
                 { 0, 0, 0 } <- leaves
            """

            uhdev = self.uhdev
            evdev = uhdev.get_evdev()

            p = Pen(50, 60)
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 1) in events
            assert evdev.value[libevdev.EV_ABS.ABS_X] == 50
            assert evdev.value[libevdev.EV_ABS.ABS_Y] == 60
            assert not evdev.value[libevdev.EV_KEY.BTN_STYLUS]

            p.barrelswitch = True
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_STYLUS, 1) in events

            p.tipswitch = True
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 1) in events
            assert evdev.value[libevdev.EV_KEY.BTN_STYLUS]

            p.x += 1
            p.y -= 1
            events = self.post(uhdev, p)
            assert len(events) == 3  # X, Y, SYN
            assert libevdev.InputEvent(libevdev.EV_ABS.ABS_X, 51) in events
            assert libevdev.InputEvent(libevdev.EV_ABS.ABS_Y, 59) in events

            p.tipswitch = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, 0) in events

            p.barrelswitch = False
            p.inrange = False
            events = self.post(uhdev, p)
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, 0) in events
            assert libevdev.InputEvent(libevdev.EV_KEY.BTN_STYLUS, 0) in events


################################################################################
#
# Windows 7 compatible devices
#
################################################################################
# class TestEgalax_capacitive_0eef_7224(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test egalax-capacitive_0eef_7224',
#                             rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 15 00 25 01 81 02 09 51 75 05 95 01 16 00 00 26 10 00 81 02 09 47 75 01 95 01 15 00 25 01 81 02 05 01 09 30 75 10 95 01 55 0d 65 33 35 00 46 34 49 26 ff 7f 81 02 09 31 75 10 95 01 55 0d 65 33 35 00 46 37 29 26 ff 7f 81 02 05 0d 09 55 25 08 75 08 95 01 b1 02 c0 c0 05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 20 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 75 01 81 03 05 01 09 30 75 10 95 01 a4 55 0d 65 33 36 00 00 46 34 49 16 00 00 26 ff 0f 81 02 09 31 16 00 00 26 ff 0f 36 00 00 46 37 29 81 02 b4 c0 c0 05 0d 09 0e a1 01 85 05 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x0eef, 0x7224),
#                             evdev_name_suffix=' Touchscreen')
#
#
# class TestEgalax_capacitive_0eef_72fa(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test egalax-capacitive_0eef_72fa',
#                             rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 15 00 25 01 81 02 09 51 75 05 95 01 16 00 00 26 10 00 81 02 09 47 75 01 95 01 15 00 25 01 81 02 05 01 09 30 75 10 95 01 55 0d 65 33 35 00 46 72 22 26 ff 7f 81 02 09 31 75 10 95 01 55 0d 65 33 35 00 46 87 13 26 ff 7f 81 02 05 0d 09 55 25 08 75 08 95 01 b1 02 c0 c0 05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 20 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 75 01 81 03 05 01 09 30 75 10 95 01 a4 55 0d 65 33 36 00 00 46 72 22 16 00 00 26 ff 0f 81 02 09 31 16 00 00 26 ff 0f 36 00 00 46 87 13 81 02 b4 c0 c0 05 0d 09 0e a1 01 85 05 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x0eef, 0x72fa),
#                             evdev_name_suffix=' Touchscreen')
#
#
# class TestEgalax_capacitive_0eef_7336(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test egalax-capacitive_0eef_7336',
#                             rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 15 00 25 01 81 02 09 51 75 05 95 01 16 00 00 26 10 00 81 02 09 47 75 01 95 01 15 00 25 01 81 02 05 01 09 30 75 10 95 01 55 0d 65 33 35 00 46 c1 20 26 ff 7f 81 02 09 31 75 10 95 01 55 0d 65 33 35 00 46 c2 18 26 ff 7f 81 02 05 0d 09 55 25 08 75 08 95 01 b1 02 c0 c0 05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 20 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 75 01 81 03 05 01 09 30 75 10 95 01 a4 55 0d 65 33 36 00 00 46 c1 20 16 00 00 26 ff 0f 81 02 09 31 16 00 00 26 ff 0f 36 00 00 46 c2 18 81 02 b4 c0 c0 05 0d 09 0e a1 01 85 05 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x0eef, 0x7336),
#                             evdev_name_suffix=' Touchscreen')
#
#
# class TestEgalax_capacitive_0eef_7337(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test egalax-capacitive_0eef_7337',
#                             rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 15 00 25 01 81 02 09 51 75 05 95 01 16 00 00 26 10 00 81 02 09 47 75 01 95 01 15 00 25 01 81 02 05 01 09 30 75 10 95 01 55 0d 65 33 35 00 46 ae 17 26 ff 7f 81 02 09 31 75 10 95 01 55 0d 65 33 35 00 46 c3 0e 26 ff 7f 81 02 05 0d 09 55 25 08 75 08 95 01 b1 02 c0 c0 05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 20 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 75 01 81 03 05 01 09 30 75 10 95 01 a4 55 0d 65 33 36 00 00 46 ae 17 16 00 00 26 ff 0f 81 02 09 31 16 00 00 26 ff 0f 36 00 00 46 c3 0e 81 02 b4 c0 c0 05 0d 09 0e a1 01 85 05 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x0eef, 0x7337),
#                             evdev_name_suffix=' Touchscreen')
#
#
# class TestEgalax_capacitive_0eef_7349(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test egalax-capacitive_0eef_7349',
#                             rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 15 00 25 01 81 02 09 51 75 05 95 01 16 00 00 26 10 00 81 02 09 47 75 01 95 01 15 00 25 01 81 02 05 01 09 30 75 10 95 01 55 0d 65 33 35 00 46 34 49 26 ff 7f 81 02 09 31 75 10 95 01 55 0d 65 33 35 00 46 37 29 26 ff 7f 81 02 05 0d 09 55 25 08 75 08 95 01 b1 02 c0 c0 05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 20 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 75 01 81 03 05 01 09 30 75 10 95 01 a4 55 0d 65 33 36 00 00 46 34 49 16 00 00 26 ff 0f 81 02 09 31 16 00 00 26 ff 0f 36 00 00 46 37 29 81 02 b4 c0 c0 05 0d 09 0e a1 01 85 05 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x0eef, 0x7349),
#                             evdev_name_suffix=' Touchscreen')
#
#
# class TestEgalax_capacitive_0eef_73f4(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test egalax-capacitive_0eef_73f4',
#                             rdesc='05 0d 09 04 a1 01 85 04 09 22 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 09 32 15 00 25 01 81 02 09 51 75 05 95 01 16 00 00 26 10 00 81 02 09 47 75 01 95 01 15 00 25 01 81 02 05 01 09 30 75 10 95 01 55 0d 65 33 35 00 46 96 4e 26 ff 7f 81 02 09 31 75 10 95 01 55 0d 65 33 35 00 46 23 2c 26 ff 7f 81 02 05 0d 09 55 25 08 75 08 95 01 b1 02 c0 c0 05 01 09 01 a1 01 85 01 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 01 75 06 81 01 05 01 09 30 09 31 16 00 00 26 ff 0f 36 00 00 46 ff 0f 66 00 00 75 10 95 02 81 02 c0 c0 06 00 ff 09 01 a1 01 09 01 15 00 26 ff 00 85 03 75 08 95 3f 81 02 06 00 ff 09 01 15 00 26 ff 00 75 08 95 3f 91 02 c0 05 0d 09 04 a1 01 85 02 09 20 a1 00 09 42 09 32 15 00 25 01 95 02 75 01 81 02 95 06 75 01 81 03 05 01 09 30 75 10 95 01 a4 55 0d 65 33 36 00 00 46 96 4e 16 00 00 26 ff 0f 81 02 09 31 16 00 00 26 ff 0f 36 00 00 46 23 2c 81 02 b4 c0 c0 05 0d 09 0e a1 01 85 05 09 22 a1 00 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x0eef, 0x73f4),
#                             evdev_name_suffix=' Touchscreen')
#
#  bogus: BTN_TOOL_PEN is not emitted
# class TestIrtouch_6615_0070(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test irtouch_6615_0070',
#                             rdesc='05 01 09 02 a1 01 85 10 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 95 02 75 01 81 02 95 06 81 03 05 01 09 30 09 31 15 00 26 ff 7f 75 10 95 02 81 02 c0 c0 05 0d 09 04 a1 01 85 30 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 09 30 26 ff 7f 55 0f 65 11 35 00 46 51 02 75 10 95 01 81 02 09 31 35 00 46 73 01 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 09 51 75 08 95 01 81 02 05 01 09 30 26 ff 7f 55 0f 65 11 35 00 46 51 02 75 10 95 01 81 02 09 31 35 00 46 73 01 81 02 c0 05 0d 09 54 15 00 26 02 00 75 08 95 01 81 02 85 03 09 55 15 00 26 ff 00 75 08 95 01 b1 02 c0 05 0d 09 0e a1 01 85 02 09 52 09 53 15 00 26 ff 00 75 08 95 02 b1 02 c0 05 0d 09 02 a1 01 85 20 09 20 a1 00 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 03 05 01 09 30 26 ff 7f 55 0f 65 11 35 00 46 51 02 75 10 95 01 81 02 09 31 35 00 46 73 01 81 02 85 01 06 00 ff 09 01 75 08 95 01 b1 02 c0 c0',
#                             input_info=(BusType.USB, 0x6615, 0x0070))


class TestNexio_1870_0100(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test nexio_1870_0100',
                            rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 02 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 7f 81 02 c0 c0 05 0d 09 02 a1 01 85 05 09 20 a1 00 09 42 09 32 15 00 25 01 75 01 95 02 81 02 95 0e 81 03 05 01 26 ff 3f 75 10 95 01 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 c0 06 00 ff 09 01 a1 01 85 06 19 01 29 40 15 00 26 ff 00 75 08 95 40 81 00 19 01 29 40 91 00 c0',
                            input_info=(BusType.USB, 0x1870, 0x0100))


class TestNexio_1870_010d(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test nexio_1870_010d',
                            rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 06 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 7f 81 02 c0 c0 05 0d 09 02 a1 01 85 05 09 20 a1 00 09 42 09 32 15 00 25 01 75 01 95 02 81 02 95 0e 81 03 05 01 26 ff 3f 75 10 95 01 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 c0 06 00 ff 09 01 a1 01 85 06 19 01 29 40 15 00 26 ff 00 75 08 95 3e 81 00 19 01 29 40 91 00 c0',
                            input_info=(BusType.USB, 0x1870, 0x010d))


class TestNexio_1870_0119(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test nexio_1870_0119',
                            rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 a1 02 05 0d 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 95 06 81 03 75 08 09 51 95 01 81 02 05 01 26 ff 3f 75 10 55 0d 65 00 09 30 35 00 46 00 00 81 02 26 ff 3f 09 31 35 00 46 00 00 81 02 26 ff 3f 05 0d 09 48 35 00 26 ff 3f 81 02 09 49 35 00 26 ff 3f 81 02 c0 05 0d 09 54 95 01 75 08 25 02 81 02 85 02 09 55 25 06 b1 02 c0 09 0e a1 01 85 03 09 23 a1 02 09 52 09 53 15 00 25 0a 75 08 95 02 b1 02 c0 c0 05 01 09 02 a1 01 09 01 a1 00 85 04 05 09 95 03 75 01 19 01 29 03 15 00 25 01 81 02 95 01 75 05 81 01 05 01 75 10 95 02 09 30 09 31 15 00 26 ff 7f 81 02 c0 c0 05 0d 09 02 a1 01 85 05 09 20 a1 00 09 42 09 32 15 00 25 01 75 01 95 02 81 02 95 0e 81 03 05 01 26 ff 3f 75 10 95 01 55 0e 65 11 09 30 35 00 46 1e 19 81 02 26 ff 3f 09 31 35 00 46 be 0f 81 02 26 ff 3f c0 c0 06 00 ff 09 01 a1 01 85 06 19 01 29 40 15 00 26 ff 00 75 08 95 3e 81 00 19 01 29 40 91 00 c0',
                            input_info=(BusType.USB, 0x1870, 0x0119))


################################################################################
#
# Windows 8 compatible devices
#
################################################################################

# bogus: application is 'undefined'
# class Testatmel_03eb_8409(BaseTest.TestTablet):
#     def create_device(self):
#         return PenDigitizer('uhid test atmel_03eb_8409', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 35 00 35 00 46 18 06 26 77 0f 09 31 81 02 35 00 35 00 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 48 81 02 09 49 81 02 c0 05 0d 27 ff ff 00 00 75 10 95 01 09 56 81 02 15 00 25 1f 75 05 09 54 95 01 81 02 75 03 25 01 95 01 81 03 75 08 85 02 09 55 25 10 b1 02 06 00 ff 85 05 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 00 a1 01 85 03 09 20 a1 00 15 00 25 01 75 01 95 01 09 42 81 02 09 44 81 02 09 45 81 02 81 03 09 32 81 02 95 03 81 03 05 01 55 0e 65 11 35 00 75 10 95 02 46 c8 0a 26 6f 08 09 30 81 02 46 18 06 26 77 0f 09 31 81 02 05 0d 09 30 15 01 26 ff 00 75 08 95 01 81 02 c0 c0')


class Testatmel_03eb_840b(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test atmel_03eb_840b', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 95 01 81 03 25 1f 75 05 09 51 81 02 05 01 55 0e 65 11 35 00 75 10 95 01 46 00 0a 26 ff 0f 09 30 81 02 09 00 81 03 46 a0 05 26 ff 0f 09 31 81 02 09 00 81 03 05 0d 95 01 75 08 15 00 26 ff 00 46 ff 00 09 00 81 03 09 00 81 03 c0 05 0d 27 ff ff 00 00 75 10 95 01 09 56 81 02 15 00 25 1f 75 05 09 54 95 01 81 02 75 03 25 01 95 01 81 03 75 08 85 02 09 55 25 10 b1 02 06 00 ff 85 05 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 02 a1 01 85 03 09 20 a1 00 15 00 25 01 75 01 95 01 09 42 81 02 09 44 81 02 09 45 81 02 81 03 09 32 81 02 95 03 81 03 05 01 55 0e 65 11 35 00 75 10 95 02 46 00 0a 26 ff 0f 09 30 81 02 46 a0 05 26 ff 0f 09 31 81 02 05 0d 09 30 15 01 26 ff 00 75 08 95 01 81 02 c0 c0')


class Testn_trig_1b96_0c01(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test n_trig_1b96_0c01', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 09 32 81 02 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_0c03(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test n_trig_1b96_0c03', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 15 0a 26 80 25 81 02 09 31 46 b4 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_0f00(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test n_trig_1b96_0f00', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_0f04(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test n_trig_1b96_0f04', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 7f 0b 26 80 25 81 02 09 31 46 78 06 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 7f 0b 26 80 25 81 02 09 31 46 78 06 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 7f 0b 26 80 25 81 02 09 31 46 78 06 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class Testn_trig_1b96_1000(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test n_trig_1b96_1000', rdesc='75 08 15 00 26 ff 00 06 0b ff 09 0b a1 01 95 0f 09 29 85 29 b1 02 95 1f 09 2a 85 2a b1 02 95 3e 09 2b 85 2b b1 02 95 fe 09 2c 85 2c b1 02 96 fe 01 09 2d 85 2d b1 02 95 02 09 48 85 48 b1 02 95 0f 09 2e 85 2e 81 02 95 1f 09 2f 85 2f 81 02 95 3e 09 30 85 30 81 02 95 fe 09 31 85 31 81 02 96 fe 01 09 32 85 32 81 02 75 08 96 fe 0f 09 35 85 35 81 02 c0 05 0d 09 02 a1 01 85 01 09 20 35 00 a1 00 09 32 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 05 81 02 95 03 81 03 05 01 09 30 75 10 95 01 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 b4 05 0d 09 30 26 00 01 81 02 06 00 ff 09 01 81 02 c0 85 0c 06 00 ff 09 0c 75 08 95 06 26 ff 00 b1 02 85 0b 09 0b 95 02 b1 02 85 11 09 11 b1 02 85 15 09 15 95 05 b1 02 85 18 09 18 95 0c b1 02 c0 05 0d 09 04 a1 01 85 03 06 00 ff 09 01 75 10 95 01 15 00 27 ff ff 00 00 81 02 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 01 81 03 09 47 81 02 95 05 81 03 75 10 09 51 27 ff ff 00 00 95 01 81 02 05 01 09 30 75 10 95 02 a4 55 0e 65 11 46 03 0a 26 80 25 81 02 09 31 46 a1 05 26 20 1c 81 02 05 0d 09 48 95 01 26 80 25 81 02 09 49 26 20 1c 81 02 b4 06 00 ff 09 02 75 08 95 04 15 00 26 ff 00 81 02 c0 05 0d 09 54 95 01 75 08 81 02 09 56 75 20 95 01 27 ff ff ff 0f 81 02 85 04 09 55 75 08 95 01 25 0b b1 02 85 0a 06 00 ff 09 03 15 00 b1 02 85 1b 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 01 09 02 a1 01 85 02 09 01 a1 00 05 09 19 01 29 02 15 00 25 01 75 01 95 02 81 02 95 06 81 03 05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 06 c0 c0')


class TestGXTP_27c6_0113(BaseTest.TestTablet):
    def create_device(self):
        return PenDigitizer('uhid test GXTP_27c6_0113', rdesc='05 0d 09 04 a1 01 85 01 09 22 a1 02 55 0e 65 11 35 00 15 00 09 42 25 01 75 01 95 01 81 02 95 07 81 01 95 01 75 08 09 51 81 02 75 10 05 01 26 00 14 46 1f 07 09 30 81 02 26 80 0c 46 77 04 09 31 81 02 05 0d c0 09 22 a1 02 09 42 25 01 75 01 95 01 81 02 95 07 81 01 95 01 75 08 09 51 81 02 75 10 05 01 26 00 14 46 1f 07 09 30 81 02 26 80 0c 46 77 04 09 31 81 02 05 0d c0 09 22 a1 02 09 42 25 01 75 01 95 01 81 02 95 07 81 01 95 01 75 08 09 51 81 02 75 10 05 01 26 00 14 46 1f 07 09 30 81 02 26 80 0c 46 77 04 09 31 81 02 05 0d c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 01 75 08 09 51 95 01 81 02 05 01 26 00 14 75 10 55 0e 65 11 09 30 35 00 46 1f 07 81 02 26 80 0c 46 77 04 09 31 81 02 05 0d c0 09 22 a1 02 09 42 15 00 25 01 75 01 95 01 81 02 95 07 81 01 75 08 09 51 95 01 81 02 05 01 26 00 14 75 10 55 0e 65 11 09 30 35 00 46 1f 07 81 02 26 80 0c 46 77 04 09 31 81 02 05 0d c0 09 54 15 00 25 7f 75 08 95 01 81 02 85 02 09 55 95 01 25 0a b1 02 85 03 06 00 ff 09 c5 15 00 26 ff 00 75 08 96 00 01 b1 02 c0 05 0d 09 02 a1 01 85 08 09 20 a1 00 09 42 09 44 09 3c 09 45 15 00 25 01 75 01 95 04 81 02 95 01 81 03 09 32 81 02 95 02 81 03 95 01 75 08 09 51 81 02 05 01 09 30 75 10 95 01 a4 55 0e 65 11 35 00 26 00 14 46 1f 07 81 42 09 31 26 80 0c 46 77 04 81 42 b4 05 0d 09 30 26 ff 0f 81 02 09 3d 65 14 55 0e 36 d8 dc 46 28 23 16 d8 dc 26 28 23 81 02 09 3e 81 02 c0 c0 06 f0 ff 09 01 a1 01 85 0e 09 01 15 00 25 ff 75 08 95 40 91 02 09 01 15 00 25 ff 75 08 95 40 81 02 c0 05 01 09 06 a1 01 85 04 05 07 09 e3 15 00 25 01 75 01 95 01 81 02 95 07 81 03 c0')
