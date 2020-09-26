#!/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2017 Benjamin Tissoires <benjamin.tissoires@gmail.com>
# Copyright (c) 2017 Red Hat, Inc.
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

import hidtools.hid
from hidtools.util import BusType
import functools
import os
import select
import struct
import uuid

try:
    import pyudev
except ImportError:
    raise ImportError('UHID is not supported due to missing pyudev dependency')

import logging
logger = logging.getLogger('hidtools.hid.uhid')


class UHIDIncompleteException(Exception):
    """
    An exception raised when a UHIDDevice does not have sufficient
    information to create a kernel device.
    """
    pass


class UHIDDevice(object):
    """
    A uhid device. uhid is a kernel interface to create virtual HID devices
    based on a report descriptor.

    This class also acts as context manager for any :class:`UHIDDevice`
    objects. See :meth:`dispatch` for details.

    .. attribute:: device_nodes

        A list of evdev nodes associated with this HID device. Populating
        this list requires udev events to be processed, ensure that
        :meth:`dispatch` is called and that you wait for some reasonable
        time after creating the device.

    .. attribute:: hidraw_nodes

        A list of hidraw nodes associated with this HID device. Populating
        this list requires udev events to be processed, ensure that
        :meth:`dispatch` is called and that you wait for some reasonable
        time after creating the device.

    .. attribute:: uniq

        A uniq string assigned to this device. This string is autogenerated
        and can be used to reliably identify the device.

    """
    __UHID_LEGACY_CREATE = 0
    _UHID_DESTROY = 1
    _UHID_START = 2
    _UHID_STOP = 3
    _UHID_OPEN = 4
    _UHID_CLOSE = 5
    _UHID_OUTPUT = 6
    __UHID_LEGACY_OUTPUT_EV = 7
    __UHID_LEGACY_INPUT = 8
    _UHID_GET_REPORT = 9
    _UHID_GET_REPORT_REPLY = 10
    _UHID_CREATE2 = 11
    _UHID_INPUT2 = 12
    _UHID_SET_REPORT = 13
    _UHID_SET_REPORT_REPLY = 14

    UHID_FEATURE_REPORT = 0
    UHID_OUTPUT_REPORT = 1
    UHID_INPUT_REPORT = 2

    _polling_functions = {}
    _poll = select.poll()
    _devices = []

    _pyudev_context = None
    _pyudev_monitor = None

    @classmethod
    def dispatch(cls, timeout=None):
        """
        Process any events available on any internally registered file
        descriptor and deal with the events.

        The caller must call this function regularly to make sure things
        like udev events are processed correctly. There's no indicator of
        when to call :meth:`dispatch` yet, call it whenever you're idle.

        :returns: True if data was processed, False otherwise
        """
        had_data = False
        devices = cls._poll.poll(timeout)
        while devices:
            for fd, mask in devices:
                if mask & select.POLLIN:
                    fun = cls._polling_functions[fd]
                    fun()
            devices = cls._poll.poll(timeout)
            had_data = True
        return had_data

    @classmethod
    def _append_fd_to_poll(cls, fd, read_function, mask=select.POLLIN):
        cls._poll.register(fd, mask)
        cls._polling_functions[fd] = read_function

    @classmethod
    def _remove_fd_from_poll(cls, fd):
        cls._poll.unregister(fd)

    @classmethod
    def _init_pyudev(cls):
        if cls._pyudev_context is None:
            cls._pyudev_context = pyudev.Context()
            cls._pyudev_monitor = pyudev.Monitor.from_netlink(cls._pyudev_context)
            cls._pyudev_monitor.start()

            cls._append_fd_to_poll(cls._pyudev_monitor.fileno(),
                                   cls._cls_udev_event_callback)

    @classmethod
    def _cls_udev_event_callback(cls):
        for event in iter(functools.partial(cls._pyudev_monitor.poll, 0.02), None):
            logger.debug(f'udev event: {event.action} -> {event}')

            for d in cls._devices:
                if d.udev_device is not None and d.udev_device.sys_path in event.sys_path:
                    d._udev_event(event)

    def __init__(self):
        self._name = None
        self._phys = ''
        self._rdesc = None
        self.parsed_rdesc = None
        self._info = None
        self._bustype = None
        self._fd = os.open('/dev/uhid', os.O_RDWR)
        self._start = self.start
        self._stop = self.stop
        self._open = self.open
        self._close = self.close
        self._output_report = self.output_report
        self._udev_device = None
        self._ready = False
        self._is_destroyed = False
        self.device_nodes = []
        self.hidraw_nodes = []
        self.uniq = f'uhid_{str(uuid.uuid4())}'
        self._append_fd_to_poll(self._fd, self._process_one_event)
        self._init_pyudev()
        UHIDDevice._devices.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_details):
        if not self._is_destroyed:
            self.destroy()

    def udev_event(self, event):
        """
        Callback invoked on a udev event.
        """
        pass

    def _udev_event(self, event):
        # we do not need to process the udev events if the device is being
        # removed
        if not self._ready:
            return

        if event.action == 'add':
            device = event

            try:
                devname = device.properties['DEVNAME']
                if devname.startswith('/dev/input/event'):
                    self.device_nodes.append(devname)
                elif devname.startswith('/dev/hidraw'):
                    self.hidraw_nodes.append(devname)
            except KeyError:
                pass

        self.udev_event(event)

    @property
    def fd(self):
        """
        The fd to the ``/dev/uhid`` device node
        """
        return self._fd

    @property
    def rdesc(self):
        """
        The device's report descriptor
        """
        return self._rdesc

    @rdesc.setter
    def rdesc(self, rdesc):
        parsed_rdesc = rdesc
        if not isinstance(rdesc, hidtools.hid.ReportDescriptor):
            if isinstance(rdesc, str):
                rdesc = f'XXX {rdesc}'
                parsed_rdesc = hidtools.hid.ReportDescriptor.from_string(rdesc)
            else:
                parsed_rdesc = hidtools.hid.ReportDescriptor.from_bytes(rdesc)
        self.parsed_rdesc = parsed_rdesc
        self._rdesc = parsed_rdesc.bytes

    @property
    def phys(self):
        """
        The device's phys string
        """
        return self._phys

    @phys.setter
    def phys(self, phys):
        self._phys = phys

    @property
    def name(self):
        """
        The devices HID name
        """
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def info(self):
        """
        The devices's bus, vendor ID and product ID as tuple
        """
        return self._info

    @info.setter
    def info(self, info):
        self._info = info
        # In case bus type is passed as 'int', wrap it in BusType.
        self._bustype = info[0] if isinstance(info[0], BusType) else BusType(info[0])

    @property
    def bus(self):
        """
        The device's bus type :class:`hidtools.util.BusType`
        """
        return self._bustype

    @property
    def vid(self):
        """
        The device's 16-bit vendor ID
        """
        return self._info[1]

    @property
    def pid(self):
        """
        The device's 16-bit product ID
        """
        return self._info[2]

    def _call_set_report(self, req, err):
        buf = struct.pack('< L L H',
                          UHIDDevice._UHID_SET_REPORT_REPLY,
                          req,
                          err)
        os.write(self._fd, buf)

    def _call_get_report(self, req, data, err):
        data = bytes(data)
        buf = struct.pack('< L L H H 4096s',
                          UHIDDevice._UHID_GET_REPORT_REPLY,
                          req,
                          err,
                          len(data),
                          data)
        os.write(self._fd, buf)

    def call_input_event(self, data):
        """
        Send an input event from this device.

        :param list data: a list of 8-bit integers representing the HID
            report for this input event
        """
        data = bytes(data)
        buf = struct.pack('< L H 4096s',
                          UHIDDevice._UHID_INPUT2,
                          len(data),
                          data)
        logger.debug(f'inject {buf[:len(data)]}')
        os.write(self._fd, buf)

    @property
    def udev_device(self):
        """
        The devices' udev device.

        The device may be None if udev hasn't processed the device yet.
        """
        if self._udev_device is None:
            for device in self._pyudev_context.list_devices(subsystem='hid'):
                try:
                    if self.uniq == device.properties['HID_UNIQ']:
                        self._udev_device = device
                        break
                except KeyError:
                    pass
        return self._udev_device

    @property
    def sys_path(self):
        """
        The device's /sys path
        """
        return self.udev_device.sys_path

    def create_kernel_device(self):
        """
        Create a kernel device from this device. Note that the device is not
        immediately ready to go after creation, you must wait for
        :meth:`start` and ideally for :meth:`open` to be called.

        :raises: :class:`UHIDIncompleteException` if the device does not
            have a name, report descriptor or the info bits set.
        """
        if (self._name is None or
           self._rdesc is None or
           self._info is None):
            raise UHIDIncompleteException("missing uhid initialization")

        buf = struct.pack('< L 128s 64s 64s H H L L L L 4096s',
                          UHIDDevice._UHID_CREATE2,
                          bytes(self._name, 'utf-8'),  # name
                          bytes(self._phys, 'utf-8'),  # phys
                          bytes(self.uniq, 'utf-8'),  # uniq
                          len(self._rdesc),  # rd_size
                          self.bus,  # bus
                          self.vid,  # vendor
                          self.pid,  # product
                          0,  # version
                          0,  # country
                          bytes(self._rdesc))  # rd_data[HID_MAX_DESCRIPTOR_SIZE]

        logger.debug('creating kernel device')
        n = os.write(self._fd, buf)
        assert n == len(buf)
        self._ready = True

    def destroy(self):
        """
        Destroy the device. The kernel will trigger the appropriate
        messages in response before removing the device.

        This function is called automatically on __exit__()
        """

        if self._ready:
            buf = struct.pack('< L', UHIDDevice._UHID_DESTROY)
            os.write(self._fd, buf)
            self._ready = False
            # equivalent to dispatch() but just for our device.
            # this ensures that the callbacks are called correctly
            poll = select.poll()
            poll.register(self._fd, select.POLLIN)
            while poll.poll(100):
                fun = self._polling_functions[self._fd]
                fun()

        UHIDDevice._devices.remove(self)
        self._remove_fd_from_poll(self._fd)
        os.close(self._fd)
        self._is_destroyed = True
        self.device_nodes.clear()
        self.hidraw_nodes.clear()

    def start(self, flags):
        """
        Called when the uhid device is ready to accept IO.

        This message is sent by the kernel, to receive this message you must
        call :meth:`dispatch`
        """
        logger.debug('start')

    def stop(self):
        """
        Called when the uhid device no longer accepts IO.

        This message is sent by the kernel, to receive this message you must
        call :meth:`dispatch`
        """
        logger.debug('stop')

    def open(self):
        """
        Called when a userspace client opens the created kernel device.

        This message is sent by the kernel, to receive this message you must
        call :meth:`dispatch`
        """
        logger.debug('open {}'.format(self.sys_path))

    def close(self):
        """
        Called when a userspace client closes the created kernel device.

        Sending events on a closed device will not result in anyone reading
        it.

        This message is sent by the kernel, to receive this message you must
        call :meth:`dispatch`
        """
        logger.debug('close')

    def set_report(self, req, rnum, rtype, data):
        """
        Callback invoked when a process calls SetReport on this UHID device.

        Return ``0`` on success or an errno on failure.

        The default method always returns ``EIO`` for a failure. Override
        this in your device if you want SetReport to succeed.

        :param req: the request identifier
        :param rnum: ???
        :param rtype: one of :attr:`UHID_FEATURE_REPORT`, :attr:`UHID_INPUT_REPORT`, or :attr:`UHID_OUTPUT_REPORT`
        :param list data: a byte string with the data
        """
        return 5  # EIO

    def _set_report(self, req, rnum, rtype, size, data):
        logger.debug('set report {} {} {} {} {} '.format(req, rnum, rtype, size, [f'{d:02x}' for d in data[:size]]))
        error = self.set_report(req, rnum, rtype, [int(x) for x in data[:size]])
        if self._ready:
            self._call_set_report(req, error)

    def get_report(self, req, rnum, rtype):
        """
        Callback invoked when a process calls SetReport on this UHID device.

        Return ``(0, [data bytes])`` on success or ``(errno, [])`` on
        failure.

        The default method always returns ``(EIO, [])`` for a failure.
        Override this in your device if you want GetReport to succeed.

        :param req: the request identifier
        :param rnum: ???
        :param rtype: one of :attr:`UHID_FEATURE_REPORT`, :attr:`UHID_INPUT_REPORT`, or :attr:`UHID_OUTPUT_REPORT`
        """
        return (5, [])  # EIO

    def _get_report(self, req, rnum, rtype):
        logger.debug('get report {} {} {}'.format(req, rnum, rtype))
        error, data = self.get_report(req, rnum, rtype)
        if self._ready:
            self._call_get_report(req, data, error)

    def output_report(self, data, size, rtype):
        """
        Callback invoked when a process sends raw data to the device.

        :param data: the data sent by the kernel
        :param size: size of the data
        :param rtype: one of :attr:`UHID_FEATURE_REPORT`, :attr:`UHID_INPUT_REPORT`, or :attr:`UHID_OUTPUT_REPORT`
        """
        logger.debug('output {} {} {}'.format(rtype, size, [f'{d:02x}' for d in data[:size]]))

    def _process_one_event(self):
        buf = os.read(self._fd, 4380)
        assert len(buf) == 4380
        evtype = struct.unpack_from('< L', buf)[0]
        if evtype == UHIDDevice._UHID_START:
            ev, flags = struct.unpack_from('< L Q', buf)
            self.start(flags)
        elif evtype == UHIDDevice._UHID_OPEN:
            self._open()
        elif evtype == UHIDDevice._UHID_STOP:
            self._stop()
        elif evtype == UHIDDevice._UHID_CLOSE:
            self._close()
        elif evtype == UHIDDevice._UHID_SET_REPORT:
            ev, req, rnum, rtype, size, data = struct.unpack_from('< L L B B H 4096s', buf)
            self._set_report(req, rnum, rtype, size, data)
        elif evtype == UHIDDevice._UHID_GET_REPORT:
            ev, req, rnum, rtype = struct.unpack_from('< L L B B', buf)
            self._get_report(req, rnum, rtype)
        elif evtype == UHIDDevice._UHID_OUTPUT:
            ev, data, size, rtype = struct.unpack_from('< L 4096s H B', buf)
            self._output_report(data, size, rtype)

    def create_report(self, data, global_data=None, reportID=None, application=None):
        """
        Convert the data object to an array of ints representing the report.
        Each property of the given data object is matched against the field
        usage name (think ``hasattr``) and filled in accordingly.::

            mouse = MouseData()
            mouse.b1 = int(l)
            mouse.b2 = int(r)
            mouse.b3 = int(m)
            mouse.x = x
            mouse.y = y

            data_bytes = uhid_device.create_report(mouse)

        The :class:`UHIDDevice` will create the report according to the
        device's report descriptor.
        """
        return self.parsed_rdesc.create_report(data, global_data, reportID, application)
