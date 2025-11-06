import numpy as np
import os 
import sys

### This script assumes that OpenOFDM is in home

################## CONSTANTS #########################
NUM_LINES = 8
HOME = os.path.expanduser('~')
NUM_SUBCARRIER = 64

################ LINE NUMBERS ############################
LINE_POS_SYNC = [554, 577, 597, 617]
LINE_POS_EQL = 60

## value of subcarriers for L-LTF (legacy long training field) -- FOR TESTING
L_vector = np.array([ 0,  0,  0,  0,  0,  0,  1,  1,  -1, -1, 1,  1,  -1,
                      1,  -1, 1,  1,  1,  1,  1,  1,  -1, -1, 1,  1,  -1,
                      1,  -1, 1,  1,  1,  1,  0,  1,  -1, -1, 1,  1,  -1,
                      1,  -1, 1,  -1, -1, -1, -1, -1, 1,  1,  -1, -1, 1,
                     -1, 1,  -1, 1,  1,  1,  1,  0,  0,  0,  0,  0], dtype=np.complex64)

### LTF FREQ MASK -- FOR TESTING
LTF_REF_RAW = "0000101001100000010100110000000000000000010101100111110101001100"


def gen_as_openofdm(ltf, num_subcarrs):

    ## multiplied by 1000 for quantization i suppose
    ## reduce to 16 bits
    ltf_time = np.fft.ifft(np.fft.fftshift(ltf), num_subcarrs) * 1000
    ltf_time_conj = np.conjugate(ltf_time);
    real_int16 = np.int16(np.round(ltf_time_conj.real))
    img_int16 = np.int16(np.round(ltf_time_conj.imag))

    return list(zip(real_int16, img_int16))


def apply_code_change(file_lines, new_code_lines, start_line):
    start_idx = start_line - 1
    end_idx = start_idx + NUM_LINES

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
        f_lines = apply_code_change(f_lines, new_lines, old_line)
    
    with open(file_name, "w") as f:
        f.writelines(f_lines)
    print("Done Writing to " + file_name)


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




######################## MAIN FUNCTION ######################
def main():
    ########## GENERATE LTF IN FREQUENCY ###################   

    rand_ltf = np.zeros(NUM_SUBCARRIER);
    valid_indices = np.arange(64);
    mask = (valid_indices >= 6) & (valid_indices <=58) & (valid_indices != 32)
    rand_ltf[mask] = np.random.choice([-1,1], size=np.sum(mask))
    print("#### RAND LTF ######")
    print(rand_ltf)

    ########## GET LTF IN TIME ##################
    rand_ltf_time = gen_as_openofdm(rand_ltf, NUM_SUBCARRIER)

    mods_syn_long(rand_ltf_time)
    mods_eql(rand_ltf)
    
    print("####### ADD THIS TO CPP TX FOR TEST ############")
    cpp_code = "std::vector<gr_complex> LONG_SYMB_T = {\n"
    for val in rand_ltf:
        cpp_code += f"    gr_complex({val.real:.4f}, {val.imag:.4f}),\n"
    cpp_code += "};"

    print(cpp_code)
    

if __name__ == "__main__":
    main()
