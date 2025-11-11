import numpy as np
import os 
import sys

### This script assumes that OpenOFDM is in home

################## CONSTANTS #########################
NUM_LINES = 8 ## this is num lines to change in sync_long.v // should change to clearer name later
NUM_LINES_L_LTF_ROM = 160
HOME = os.path.expanduser('~')
NUM_SUBCARRIER = 64
NUM_TIME_SAMPLES = 160

################ LINE NUMBERS ############################
LINE_POS_SYNC = [554, 577, 597, 617]
LINE_POS_EQL = 60
LINE_POS_LTF_TX = 17

## value of subcarriers for L-LTF (legacy long training field) -- FOR TESTING
L_vector = np.array([ 0,  0,  0,  0,  0,  0,  1,  1,  -1, -1, 1,  1,  -1,
                      1,  -1, 1,  1,  1,  1,  1,  1,  -1, -1, 1,  1,  -1,
                      1,  -1, 1,  1,  1,  1,  0,  1,  -1, -1, 1,  1,  -1,
                      1,  -1, 1,  -1, -1, -1, -1, -1, 1,  1,  -1, -1, 1,
                     -1, 1,  -1, 1,  1,  1,  1,  0,  0,  0,  0,  0], dtype=np.complex64)

### LTF FREQ MASK -- FOR TESTING
LTF_REF_RAW = "0000101001100000010100110000000000000000010101100111110101001100"

def gen_ltf_time(ltf, num_subcarrs):
    return np.fft.ifft(np.fft.fftshift(ltf), num_subcarrs)

def gen_as_openofdm(ltf):

    ## multiplied by 1000 for quantization i suppose
    ## reduce to 16 bits
    ltf_time = ltf * 1000
    ltf_time_conj = np.conjugate(ltf_time);
    real_int16 = np.int16(np.round(ltf_time_conj.real))
    img_int16 = np.int16(np.round(ltf_time_conj.imag))

    return list(zip(real_int16, img_int16))


def apply_code_change(file_lines, new_code_lines, start_line, n_lines):
    start_idx = start_line - 1
    end_idx = start_idx + n_lines

    print("###### OLD LINES ####")
    lines_to_replace = file_lines[start_idx:end_idx]
    for ln in lines_to_replace:
        print(ln, end="")
    
    print("##### NEW LINES ####")
    for ln in new_code_lines:
        print(ln, end="")

    file_lines[start_idx:end_idx] = [ln for ln in new_code_lines]

    return file_lines


######## Generate Verilog MODS for verilog/sync_long.v ####

### note this expects LTF in time! 
def mods_syn_long(ltf):
    file_name = os.path.join("..",  "verilog", "sync_long.v")
    ltf_iter = 0
    new_lines = [None] * NUM_LINES
    stage_cntr = 0
    
    with open(file_name, "r") as f:
        f_lines = f.readlines()
    
    for old_line in LINE_POS_SYNC:
        for i in range(0, NUM_LINES):
            new_lines[i] = "\t" + "stage_Y" + str(i) + "<= {" 

            ## add real parth
            if(ltf[ltf_iter][0] < 0):
                new_lines[i] += "-"
            else:
                new_lines[i] += " "

            new_lines[i] = new_lines[i] +  "16\'d" + str(np.abs(ltf[ltf_iter][0])) + ", "   
            

            ## add imaginary part
            if(ltf[ltf_iter][1] < 0):
                new_lines[i] += "-"
            else:
                new_lines[i] += " "

            new_lines[i] = new_lines[i]  + "16\'d" + str(np.abs(ltf[ltf_iter][1])) + "};\n"
            
            ltf_iter+=1
        f_lines = apply_code_change(f_lines, new_lines, old_line, NUM_LINES)
    
    with open(file_name, "w") as f:
        f.writelines(f_lines)
    print("Done Writing to " + file_name)


### note this expects LTF in frequency
def mods_eql(ltf):
    file_name = os.path.join("..", "verilog", "equalizer.v")
    base_str = "\t64\'b"
    bit_array = np.zeros(NUM_SUBCARRIER, dtype=int)

    for i in range(NUM_SUBCARRIER):
        if(i < 6 or i == 32 or i > 58):
            bit_array[i] = 0 ## guard subcarriers
            continue

        if(ltf[i] == -1):
            bit_array[i] = 1

        else:
            bit_array[i] = 0

    ## FFT SHIFT to from {-32, -31, -30, -29, ......, 29, 30, 31, 32, 33} TO {1, 2, 3, 4, 5, ....., -1, -2, -3, -4}
    bit_array = np.fft.fftshift(bit_array)

    ## Create bit string
    bit_str = ''.join(str(bit) for bit in bit_array)

    ## Flip since bit 0 must be on the right (the one associated with bin 1)
    bit_str = bit_str[::-1]

    ## full str
    full_str = base_str + bit_str + ';\n'

    print("NEW LTS_REF: " + full_str, end="")
    with open(file_name, "r") as f:
        file_lines = f.readlines()

    file_lines[LINE_POS_EQL-1] = full_str;

    with open(file_name, "w") as f:
        f.writelines(file_lines)

    print("Done Writing to " + file_name)

    return 


def mods_tx(ltf_time):
    file_name = os.path.join("..", "..", "openofdm_tx", "src", "l_ltf_rom.v")
    ltf_iter = 0

    with open(file_name, "r") as f:
        f_lines = f.readlines()

    new_lines = [None] * NUM_TIME_SAMPLES

    ltf_time_quant =  np.clip(np.round(ltf_time * (2**15)), -32768, 32767)
    ltf_cp = ltf_time_quant[-32:]

    ltf_w_cp = np.concatenate((ltf_cp, ltf_time_quant, ltf_time_quant)) 
    I = np.int16(np.real(ltf_w_cp))
    Q = np.int16(np.imag(ltf_w_cp))

    print(np.imag(ltf_w_cp))

    # Cast to unsigned for correct bit shifting
    Iu = I.astype(np.uint16)
    Qu = Q.astype(np.uint16)
    
    # Combine into 32-bit words: I in upper 16 bits, Q in lower 16 bits
    words = (Iu.astype(np.uint32) << 16) | Qu


    for i in range(NUM_TIME_SAMPLES):
        new_lines[i] = '\t' + str(i)  + ':\t' + "dout = " + f"32'h{words[i]:08X}" + ";\n"
    
    f_lines = apply_code_change(f_lines, new_lines, LINE_POS_LTF_TX, NUM_LINES_L_LTF_ROM)


######################## MAIN FUNCTION ######################
def main():
    ########## GENERATE LTF IN FREQUENCY ###################   

    rand_ltf = np.zeros(NUM_SUBCARRIER);
    valid_indices = np.arange(64);
    mask = (valid_indices >= 6) & (valid_indices <=58) & (valid_indices != 32)
    rand_ltf[mask] = np.random.choice([-1,1], size=np.sum(mask))
    print("#### RAND LTF ######")
    print(rand_ltf)

    ## commet for normal functionality/ uncomment for debugin with standard preamble
    rand_ltf = L_vector 
    ########## GET LTF IN TIME ##################
    rand_ltf_time =  gen_ltf_time(rand_ltf, NUM_SUBCARRIER)
    rand_ltf_time_RX = gen_as_openofdm(rand_ltf_time)


    ## RX mods
    # mods_syn_long(rand_ltf_time_RX)
    # mods_eql(rand_ltf)
    mods_tx(rand_ltf_time)

    ## TX mods

    print("####### ADD THIS TO CPP TX FOR TEST ############")
    cpp_code = "std::vector<gr_complex> LONG_SYMB_T = {\n"
    for val in rand_ltf:
        cpp_code += f"    gr_complex({val.real:.4f}, {val.imag:.4f}),\n"
    cpp_code += "};"

    print(cpp_code)
    

if __name__ == "__main__":
    main()
