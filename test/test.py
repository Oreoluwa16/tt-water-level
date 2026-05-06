# SPDX-FileCopyrightText: (c) 2026 Ore-Oluwa
# SPDX-License-Identifier: Apache-2.0
#
# Cocotb testbench for the Water Level Controller FSM wrapped as
# tt_um_oreoluwa_water_level.
#
# Pin map (matches src/project.v):
#   ui_in[0] = s0_low
#   ui_in[1] = s1_high
#   uo_out[0]   = pump_out
#   uo_out[1]   = error_flag
#   uo_out[3:2] = current_state  (00 IDLE, 01 FILLING, 10 FULL, 11 ERROR)

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# State encodings (must match the RTL)
IDLE, FILLING, FULL, ERROR = 0b00, 0b01, 0b10, 0b11


def set_sensors(dut, s1_high: int, s0_low: int) -> None:
    """Drive the two sensor bits onto ui_in[1:0]."""
    dut.ui_in.value = ((s1_high & 1) << 1) | (s0_low & 1)


def pump(dut) -> int:
    return int(dut.uo_out.value) & 0x1


def error_flag(dut) -> int:
    return (int(dut.uo_out.value) >> 1) & 0x1


def state(dut) -> int:
    return (int(dut.uo_out.value) >> 2) & 0x3


async def reset(dut):
    """Hold reset, then release. Sensors are parked at 01 (mid-level) so
    that IDLE is a *stable* state when reset deasserts; otherwise an empty
    tank (00) would immediately drive the FSM into FILLING on the first edge.
    """
    dut.ena.value = 1
    dut.uio_in.value = 0
    set_sensors(dut, s1_high=0, s0_low=1)   # mid-level => IDLE stays IDLE
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_reset_state(dut):
    """After reset the FSM should be in IDLE with pump off and no error."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    assert state(dut) == IDLE,        f"expected IDLE after reset, got {state(dut):02b}"
    assert pump(dut) == 0,            "pump should be off in IDLE"
    assert error_flag(dut) == 0,      "error flag should be clear after reset"


@cocotb.test()
async def test_idle_to_filling(dut):
    """Tank empty (s1=0,s0=0) -> FSM goes from IDLE to FILLING with pump on."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    set_sensors(dut, s1_high=0, s0_low=0)   # empty
    await ClockCycles(dut.clk, 2)

    assert state(dut) == FILLING,     f"expected FILLING, got {state(dut):02b}"
    assert pump(dut) == 1,            "pump should be ON while filling"
    assert error_flag(dut) == 0


@cocotb.test()
async def test_filling_to_full(dut):
    """Sensors go 00 -> 01 (mid) -> 11 (full): pump turns off in FULL."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    # Empty -> start filling
    set_sensors(dut, 0, 0)
    await ClockCycles(dut.clk, 2)
    assert state(dut) == FILLING

    # Water rises past low sensor only
    set_sensors(dut, 0, 1)
    await ClockCycles(dut.clk, 2)
    assert state(dut) == FILLING,     "should keep filling at mid level"
    assert pump(dut) == 1

    # Water reaches both sensors -> FULL
    set_sensors(dut, 1, 1)
    await ClockCycles(dut.clk, 2)
    assert state(dut) == FULL,        f"expected FULL, got {state(dut):02b}"
    assert pump(dut) == 0,            "pump must be OFF in FULL"
    assert error_flag(dut) == 0


@cocotb.test()
async def test_full_then_drain_back_to_filling(dut):
    """From FULL, when tank drains to empty, the controller restarts filling."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    # Drive to FULL
    set_sensors(dut, 0, 0); await ClockCycles(dut.clk, 2)
    set_sensors(dut, 1, 1); await ClockCycles(dut.clk, 2)
    assert state(dut) == FULL

    # Empty the tank
    set_sensors(dut, 0, 0); await ClockCycles(dut.clk, 2)
    assert state(dut) == FILLING,     "should restart filling once tank is empty"
    assert pump(dut) == 1


@cocotb.test()
async def test_impossible_sensor_triggers_error(dut):
    """s1_high=1 while s0_low=0 is physically impossible -> ERROR + pump off."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    # From IDLE, force impossible combo
    set_sensors(dut, s1_high=1, s0_low=0)
    await ClockCycles(dut.clk, 2)

    assert state(dut) == ERROR,       f"expected ERROR, got {state(dut):02b}"
    assert pump(dut) == 0,            "pump must be OFF in ERROR"
    assert error_flag(dut) == 1,      "error_flag must be high in ERROR"


@cocotb.test()
async def test_error_recovers_when_sensors_clear(dut):
    """ERROR state clears back to IDLE once sensors read empty (00)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="us").start())
    await reset(dut)

    # Enter ERROR
    set_sensors(dut, 1, 0); await ClockCycles(dut.clk, 2)
    assert state(dut) == ERROR

    # Stay in ERROR while sensors still bad
    set_sensors(dut, 1, 0); await ClockCycles(dut.clk, 3)
    assert state(dut) == ERROR
    assert error_flag(dut) == 1

    # Sensors back to empty -> recover. From IDLE, the empty pattern
    # immediately routes to FILLING on the next edge, so accept either
    # IDLE or FILLING here.
    set_sensors(dut, 0, 0); await ClockCycles(dut.clk, 2)
    assert state(dut) in (IDLE, FILLING), \
        f"expected IDLE or FILLING after recovery, got {state(dut):02b}"
    assert error_flag(dut) == 0
