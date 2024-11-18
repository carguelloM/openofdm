/*
* Delay using RAM
* Only support 2^n delay
*/
module delay_sample
#(
    parameter DATA_WIDTH = 16,
    parameter DELAY_SHIFT = 4
)
(
    input clock, 
    input enable,
    input reset,

    input [(DATA_WIDTH-1):0] data_in,
    input input_strobe,

    output [(DATA_WIDTH-1):0] data_out,
    output reg output_strobe
);

localparam DELAY_SIZE = 1<<DELAY_SHIFT;

reg [DELAY_SHIFT-1:0] 	  addr;
reg full;

dpram  #(.DATA_WIDTH(DATA_WIDTH), .ADDRESS_WIDTH(DELAY_SHIFT)) delay_line (
    .clock(clock),
    .enable_a(1),
    .write_enable(input_strobe),
    .write_address(addr),
    .write_data(data_in),
    .read_data_a(),
    .enable_b(input_strobe),
    .read_address(addr),
    .read_data(data_out)
);

always @(posedge clock) begin
    if (reset) begin
        addr <= 0;
        full <= 0;
    end else if (enable) begin
        if (input_strobe) begin
            addr <= addr + 1;
            if (addr == DELAY_SIZE-1) begin
                full <= 1;
            end
            output_strobe <= full;
        end else begin
            output_strobe <= 0;
        end
    end else begin
        output_strobe <= 0;
    end
end

endmodule
