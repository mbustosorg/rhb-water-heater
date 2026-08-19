import time

import board
import busio
import digitalio
import microcontroller

import adafruit_wiznet5k.adafruit_wiznet5k as wiznet_module
from adafruit_wiznet5k.adafruit_wiznet5k_socketpool import SocketPool

display = None

# "[[]]" on a 7 segment display
CONNECTING_GLYPHS = (0x39, 0x39, 0x0F, 0x0F)

_eth_spi = None
_eth_cs = None
_eth_rst = None
_eth = None


def reboot():
    time.sleep(5)
    microcontroller.reset()


def toggle_connecting_display(count):
    """Flash "[[]]" while an ethernet connection is being attempted."""
    if display is None:
        return
    for i in range(4):
        display.set_digit_raw(i, 0x00 if count % 2 else CONNECTING_GLYPHS[i])


def set_two_digits(value, tens_digit, ones_digit):
    """Show `value' rounded across two digits.

    Senders broadcast floats, some of them unrounded, so round here rather
    than truncate.  Only 0-99 fits in two digits: peg anything higher at 99
    and show "--" below zero.

    This replaces a BCD trick -- int(str(int(v)), 16) -- that only worked for
    0-99 and silently showed 100 PSI as "00" and 120 as "20".
    """
    if display is None:
        return
    value = round(value)
    if value < 0:
        display.set_digit_raw(tens_digit, 0x40)
        display.set_digit_raw(ones_digit, 0x40)
        return
    if value > 99:
        value = 99
    display[tens_digit] = str(value // 10)
    display[ones_digit] = str(value % 10)


def _eth_hardware():
    """SPI and control pins can only be claimed once, so hold on to them."""
    global _eth_spi, _eth_cs, _eth_rst
    if _eth_spi is None:
        _eth_spi = busio.SPI(board.ETH_CLK, MOSI=board.ETH_MOSI, MISO=board.ETH_MISO)
        _eth_cs = digitalio.DigitalInOut(board.ETH_CS)
        _eth_rst = digitalio.DigitalInOut(board.ETH_RST)
    return _eth_spi, _eth_cs, _eth_rst


def _raw_ip(address):
    """"192.168.1.9" -> the four bytes the WIZnet registers want"""
    octets = [int(o) for o in address.split(".")]
    if len(octets) != 4 or any(o < 0 or o > 255 for o in octets):
        raise ValueError(f"Not an IPv4 address: {address}")
    return bytes(octets)


def ethernet_connection(address, subnet=None, gateway=None, dns=None):
    """One immediate attempt.  Returns a SocketPool, or None if not ready.

    Deliberately synchronous and non-blocking: the caller owns the retry loop
    and does the waiting.  An `await' in here would be awaited across a module
    boundary, which CircuitPython's asyncio does not support -- it raises
    "'generator' object has no attribute '__await__'".

    The rig is statically addressed, so the interface is configured from
    `address' rather than by DHCP.  There is no DHCP server on the wired side,
    and set_dhcp() blocks until it gets a lease that never comes.
    """
    global _eth
    try:
        if _eth is None:
            spi, cs, rst = _eth_hardware()
            _eth = wiznet_module.WIZNET5K(spi, cs, rst, is_dhcp=False)
        if not _eth.link_status:
            return None
        octets = address.split(".")
        _eth.ifconfig = (
            _raw_ip(address),
            _raw_ip(subnet or "255.255.255.0"),
            _raw_ip(gateway or ".".join(octets[:3] + ["1"])),
            _raw_ip(dns or gateway or ".".join(octets[:3] + ["1"])),
        )
        pool = SocketPool(_eth)
        print("Ethernet connected, ip =", _eth.pretty_ip(_eth.ip_address))
        return pool
    except Exception as e:
        print("Ethernet connection failed:", e)
        _eth = None
        return None
