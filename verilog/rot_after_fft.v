`include "common_defs.v"

module rot_after_fft
#(
    DATA_WIDTH = 16
)
(
    input clock,
    input reset,
    input enable,

    input [3:0] fft_win_shift,
    input signed [15:0] phase_offset,
    input [15:0] Fc_in_MHz,
    //input [3:0] power_of_fft_size, // eg 6 means fft_Size=2^6
    input gi, // 0 is normal,1 is short
    input ht_detected, 
    //input is_ce, // is channel estimation? if so dist_from_ce is always 0 
    input [15:0] ofdm_sym_count_in,
    input signed [DATA_WIDTH-1:0] in_fft_i,
    input signed [DATA_WIDTH-1:0] in_fft_q,
    input input_strobe,
    
    output [`ROTATE_LUT_LEN_SHIFT-1:0] rot_addr,
    input [31:0] rot_data,

    output [5:0] sc_count_spy,
    output [15:0] sym_phase_spy,
    output signed [DATA_WIDTH-1:0] out_fft_i,
    output signed [DATA_WIDTH-1:0] out_fft_q,
    
    output wire output_strobe
);
`include "common_params.v"


localparam PW_OF_FFT_SIZE = 6;
localparam SCALE = PW_OF_FFT_SIZE+27; // 27 is the width of fractional bits of divider
localparam Fs = 20000000; 
localparam Fs_DIV_2PI = 6217; // round(Fs/(2*pi*2^ATAN_LUT_SCALE_SHIFT));
localparam SC_IDX_FOR_UPDATE = 55 ;
reg [33:0] Fc;
reg is_ht ; // flag of HT 
reg is_ce ; // flag of channel estimation
reg is_first_sym_after_ce; // flag for first ofdm symbol after cahnel estimation
reg signed [16:0] Sxy;
reg signed [16:0] Sxy_next;
reg signed [10:0] Sxy_init;
reg [5:0] sc_count ;
reg [15:0] ofdm_sym_count ;
reg signed [15:0] sym_phase ;
reg sym_phase_valid ; 
reg signed [DATA_WIDTH-1:0] fft_i_delay;
reg signed [DATA_WIDTH-1:0] fft_q_delay;
reg signed [15:0] next_sym_phase ;
reg signed [31:0] multi1;
reg signed [39:0] multi2;
reg multi2_valid;
reg signed [39:0] divisor;
reg divisor_valid;
reg signed [38:0] scaled_phase_per_sym ; 
reg signed [49:0] scaled_phase ; // accumulate scaled phase 
wire signed [38:0] div1_times_fftsize;
wire signed [38:0] div1_times_gi;
wire signed [38:0] div1_times_32;
wire signed [38:0] div1_times_dist_from_ce_init;
 
wire signed [31:0] dividend; // 32 bit integer
//reg signed [31:0] dividend_init;
wire signed [27:0] div1_fractional; // 28 bit fractional
wire signed [35:0] div1_int;
wire signed [27+4:0] div1;
wire signed [3:0] div1_int_comb_signbit;
wire div_valid;
wire signed [DATA_WIDTH-1:0] rot_out_i;
wire signed [DATA_WIDTH-1:0] rot_out_q;
wire signed [16:0] unscaled_phase;
reg [2:0] power_of_gi; 

assign sc_count_spy = sc_count ;
assign sym_phase_spy = sym_phase ;
//assign output_strobe = sym_phase_valid;
// lut defined for scale 512
always @(*) begin
    case (fft_win_shift)
    4'h0 : Sxy_init <= 0;
    4'h1 : Sxy_init <= 50;
    4'h2 : Sxy_init <= 101;
    4'h3 : Sxy_init <= 151;
    4'h4 : Sxy_init <= 201;
    4'h5 : Sxy_init <= 251;
    4'h6 : Sxy_init <= 302;
    4'h7 : Sxy_init <= 352;
    4'h8 : Sxy_init <= 402;
    4'h9 : Sxy_init <= 452;
    4'hA : Sxy_init <= 503;
    4'hB : Sxy_init <= 553;
    4'hC : Sxy_init <= 603;
    4'hD : Sxy_init <= 653;
    4'hE : Sxy_init <= 704;
    4'hF : Sxy_init <= 754;
    default: Sxy_init <= 0;
    endcase
end 

always @(posedge clock) begin
    if (reset) begin
        is_ht <= 0 ;
        is_ce <= 1 ;
        is_first_sym_after_ce <= 0 ;
        power_of_gi <= 4 ; // default power of gi is 4, 2^4 = 16
    end else if (enable) begin
        if (ofdm_sym_count <= 4) begin
            is_ht <= 0;
        end else if (ofdm_sym_count == 5) begin 
            is_ht <= ht_detected?  (sc_count < SC_IDX_FOR_UPDATE? 0:1) : 0;
        end else begin
            is_ht <= is_ht ;
        end
        if (ofdm_sym_count == 6)
            power_of_gi <= gi? (sc_count < SC_IDX_FOR_UPDATE? 4:3):4;
        else
            power_of_gi <= power_of_gi;
        
        if (ofdm_sym_count ==0) 
            is_ce <= 1 ;
        else if (ofdm_sym_count ==1)
            is_ce <= sc_count < SC_IDX_FOR_UPDATE? 1:0;
        else if (ofdm_sym_count ==5) 
            is_ce <= is_ht? (sc_count < SC_IDX_FOR_UPDATE? 0:1):0;   
        else if (ofdm_sym_count ==6)     
            is_ce <= is_ht? (sc_count < SC_IDX_FOR_UPDATE? 1:0):0; 
        else 
            is_ce <= 0 ;
            
        if (ofdm_sym_count == 1)
            is_first_sym_after_ce <= (sc_count < SC_IDX_FOR_UPDATE? 0:1) ;
        else if (ofdm_sym_count==2)
            is_first_sym_after_ce <= (sc_count < SC_IDX_FOR_UPDATE? 1:0) ;
        else if (ofdm_sym_count == 6) // 0 1: LTF, 2: L-SIG, 3:4 HT SIG, 5 HT STF, 6 HT LTF, 7 first HT data
            is_first_sym_after_ce <= is_ht? (sc_count < SC_IDX_FOR_UPDATE? 0:1):0;
        else if (ofdm_sym_count == 7) // 0 1: LTF, 2: L-SIG, 3:4 HT SIG, 5 HT STF, 6 HT LTF, 7 first HT data
            is_first_sym_after_ce <= is_ht? (sc_count < SC_IDX_FOR_UPDATE? 1:0):0;            
        else
            is_first_sym_after_ce <= 0 ;
    end 
end

always @(posedge clock) begin
    if (reset) begin
        sc_count <= 0;
        Sxy <= Sxy_init; // 2*PI*fftwinshift/fftsize ; use fixed winshift (1), fft size(64)
        Sxy_next <= Sxy_init;
        scaled_phase <= 0;
        sym_phase <= 0;
        scaled_phase_per_sym <=0;
        next_sym_phase <= 0;
        ofdm_sym_count <= 0;
        sym_phase_valid <= 0;
        multi1 <= 0;
        multi2 <= 0;
        multi2_valid <= 0;
        divisor <= 0;
        divisor_valid <=0;
        fft_i_delay <= 0;
        fft_q_delay <= 0;
        Fc <= 0 ;
        //div1_times_dist_from_ce_init <= 0;
    end else if (enable) begin
        if (input_strobe) begin
            sc_count <= sc_count+1 ;
            if (sc_count == 31) begin
                if (-next_sym_phase -Sxy < -PI) 
                    next_sym_phase <= -next_sym_phase - Sxy + DOUBLE_PI ;
                else if (-next_sym_phase - Sxy > PI)
                    next_sym_phase <= -next_sym_phase - Sxy - DOUBLE_PI ;
                else
                    next_sym_phase <= -next_sym_phase - Sxy;                             
            end else 
                if (next_sym_phase + Sxy > PI)
                    next_sym_phase <= next_sym_phase + Sxy - DOUBLE_PI ;
                else if (next_sym_phase + Sxy < -PI)
                    next_sym_phase <= next_sym_phase +Sxy + DOUBLE_PI ;
                else
                    next_sym_phase <= next_sym_phase + Sxy ;
            if (sc_count == 63) begin
                ofdm_sym_count <= ofdm_sym_count_in;
                Sxy <= Sxy_next ;
            end
            if (sc_count == 1 && ofdm_sym_count == 0) begin // first ofdm sym, need to calculate scaled_phase_per_sym 
                multi1 <= phase_offset * Fs ;
                multi2 <= phase_offset * Fs_DIV_2PI ;
                multi2_valid <= 1; 
                Fc <= Fc_in_MHz * 1000000;
            end
            if (multi2_valid) begin
                multi2_valid <= 0;
                divisor <= multi2 + Fc;
                divisor_valid <= 1 ;
            end       
            if (divisor_valid)
                divisor_valid <= 0;  
            if (sc_count == 58 && is_first_sym_after_ce == 1) begin
                scaled_phase_per_sym <= div1_times_fftsize+ div1_times_gi;
            end  
            if (sc_count == 58) 
                scaled_phase <= is_ce? (Sxy_init << SCALE): (is_first_sym_after_ce? (scaled_phase + div1_times_dist_from_ce_init):(scaled_phase + scaled_phase_per_sym) );
            if (sc_count == 60)
                Sxy_next <= phase_offset >=0 ? unscaled_phase:(unscaled_phase + |scaled_phase[SCALE-1:0]);                                            
        end 
        sym_phase <= next_sym_phase;
        sym_phase_valid <= input_strobe ;
        fft_i_delay <= in_fft_i;
        fft_q_delay <= in_fft_q;
    end
end
assign div1_int_comb_signbit = div1_int[3:0] - div1_fractional[27] ;
assign div1 = {div1_fractional[27],div1_int_comb_signbit,div1_fractional[26:0]} ;
assign dividend = multi1; // 6 is log2(fft_size)
assign div1_times_fftsize = div1 << PW_OF_FFT_SIZE;
assign div1_times_gi = div1 << power_of_gi ;
assign div1_times_32 = div1 << 5 ;
assign div1_times_dist_from_ce_init = is_ht? div1_times_fftsize + div1_times_gi: div1_times_fftsize + div1_times_gi + div1_times_32;
assign unscaled_phase = scaled_phase[49:SCALE] ;
div_for_rotafft inst(
    .aclk(clock), 
    .s_axis_divisor_tvalid(divisor_valid), 
    .s_axis_divisor_tdata(divisor), // divisor
    .s_axis_dividend_tvalid(divisor_valid), 
    .s_axis_dividend_tdata(dividend), // 
    .m_axis_dout_tvalid(div_valid), 
    .m_axis_dout_tdata({div1_int,div1_fractional})
 );

 
 rotate rotate_inst (
    .clock(clock),
    .enable(enable),
    .reset(reset),

    .in_i(fft_i_delay),
    .in_q(fft_q_delay),
    .phase(sym_phase),
    .input_strobe(sym_phase_valid),

    .rot_addr(rot_addr),
    .rot_data(rot_data),
    
    .out_i(rot_out_i),
    .out_q(rot_out_q),
    .output_strobe(output_strobe)
);

assign out_fft_i = (rot_out_i << 1);
assign out_fft_q = (rot_out_q << 1);

endmodule 
