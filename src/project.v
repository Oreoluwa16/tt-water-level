/*
 * Copyright (c) 2026 Ore-Oluwa
 * SPDX-License-Identifier: Apache-2.0
 *
 * Tiny Tapeout top-level wrapper for a 4-state Water Level Controller FSM.
 *
 * Pin map
 * -------
 * Inputs (ui_in):
 *   ui_in[0] = s0_low   -- Low-level sensor   (1 = water reaches low sensor)
 *   ui_in[1] = s1_high  -- High-level sensor  (1 = water reaches high sensor)
 *   ui_in[7:2] = unused
 *
 * Outputs (uo_out):
 *   uo_out[0] = pump_out          -- 1 = pump ON
 *   uo_out[1] = error_flag        -- 1 = impossible sensor combo (high wet, low dry)
 *   uo_out[3:2] = current_state   -- FSM state for debugging
 *                                    00 IDLE, 01 FILLING, 10 FULL, 11 ERROR
 *   uo_out[7:4] = 0
 *
 * uio_* are not used.
 */

`default_nettype none

module tt_um_oreoluwa_water_level (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, ignore
    input  wire       clk,      // clock
    input  wire       rst_n     // active-low reset
);

    // ---- Map TT pins to FSM signals ------------------------------------
    wire s0_low  = ui_in[0];
    wire s1_high = ui_in[1];

    wire       pump_out;
    wire       error_flag;
    wire [1:0] current_state;

    // ---- Instantiate the controller ------------------------------------
    WaterLevelController u_ctrl (
        .clk          (clk),
        .reset_n      (rst_n),
        .s1_high      (s1_high),
        .s0_low       (s0_low),
        .pump_out     (pump_out),
        .error_flag   (error_flag),
        .state_out    (current_state)
    );

    // ---- Drive TinyTapeout outputs -------------------------------------
    assign uo_out[0]   = pump_out;
    assign uo_out[1]   = error_flag;
    assign uo_out[3:2] = current_state;
    assign uo_out[7:4] = 4'b0000;

    // uio not used: make all pins inputs and drive 0
    assign uio_out = 8'h00;
    assign uio_oe  = 8'h00;

    // Tie-off unused inputs to silence lint warnings
    wire _unused = &{ena, ui_in[7:2], uio_in, 1'b0};

endmodule


// =====================================================================
//  Water Level Controller FSM
//  (cleaned up from the original WaterLevelController.v:
//   - removed trailing comma in port list
//   - declared error_flag as a proper output reg
//   - exposed current_state as state_out for debug)
// =====================================================================
module WaterLevelController (
    input  wire       clk,           // System clock
    input  wire       reset_n,       // Active-low asynchronous reset
    input  wire       s1_high,       // High-level sensor (Bit 1)
    input  wire       s0_low,        // Low-level sensor  (Bit 0)
    output reg        pump_out,      // Pump control signal
    output reg        error_flag,    // Asserted in ERROR state
    output wire [1:0] state_out      // Current FSM state (for debug)
);

    // State encodings
    localparam [1:0] IDLE    = 2'b00;
    localparam [1:0] FILLING = 2'b01;
    localparam [1:0] FULL    = 2'b10;
    localparam [1:0] ERROR   = 2'b11;

    reg [1:0] current_state, next_state;

    // Bundled sensor variable
    // Binary map: 2'b11 (Full), 2'b01 (Middle), 2'b00 (Empty), 2'b10 (Impossible)
    wire [1:0] sensor_bus = {s1_high, s0_low};

    assign state_out = current_state;

    // Sequential Logic: State Transitions
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n)
            current_state <= IDLE;
        else
            current_state <= next_state;
    end

    // Combinational Logic: Next State and Output
    always @(*) begin
        // Default assignments
        next_state = current_state;
        pump_out   = 1'b0;
        error_flag = 1'b0;

        case (current_state)
            IDLE: begin
                pump_out = 1'b0;
                if (sensor_bus == 2'b00)      next_state = FILLING;
                else if (sensor_bus == 2'b10) next_state = ERROR;
                else                          next_state = IDLE;
            end

            FILLING: begin
                pump_out = 1'b1;
                if      (sensor_bus == 2'b11) next_state = FULL;
                else if (sensor_bus == 2'b10) next_state = ERROR;
                else                          next_state = FILLING;
            end

            FULL: begin
                pump_out = 1'b0;
                if      (sensor_bus == 2'b10) next_state = ERROR;
                else if (sensor_bus == 2'b00) next_state = FILLING;
                else                          next_state = FULL;
            end

            ERROR: begin
                pump_out   = 1'b0;
                error_flag = 1'b1;
                if (sensor_bus == 2'b00) next_state = IDLE;
                else                     next_state = ERROR;
            end

            default: next_state = IDLE;
        endcase
    end

endmodule
