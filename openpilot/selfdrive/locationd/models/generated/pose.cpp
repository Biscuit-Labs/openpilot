#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_7607340466644126338) {
   out_7607340466644126338[0] = delta_x[0] + nom_x[0];
   out_7607340466644126338[1] = delta_x[1] + nom_x[1];
   out_7607340466644126338[2] = delta_x[2] + nom_x[2];
   out_7607340466644126338[3] = delta_x[3] + nom_x[3];
   out_7607340466644126338[4] = delta_x[4] + nom_x[4];
   out_7607340466644126338[5] = delta_x[5] + nom_x[5];
   out_7607340466644126338[6] = delta_x[6] + nom_x[6];
   out_7607340466644126338[7] = delta_x[7] + nom_x[7];
   out_7607340466644126338[8] = delta_x[8] + nom_x[8];
   out_7607340466644126338[9] = delta_x[9] + nom_x[9];
   out_7607340466644126338[10] = delta_x[10] + nom_x[10];
   out_7607340466644126338[11] = delta_x[11] + nom_x[11];
   out_7607340466644126338[12] = delta_x[12] + nom_x[12];
   out_7607340466644126338[13] = delta_x[13] + nom_x[13];
   out_7607340466644126338[14] = delta_x[14] + nom_x[14];
   out_7607340466644126338[15] = delta_x[15] + nom_x[15];
   out_7607340466644126338[16] = delta_x[16] + nom_x[16];
   out_7607340466644126338[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_6802001497691266902) {
   out_6802001497691266902[0] = -nom_x[0] + true_x[0];
   out_6802001497691266902[1] = -nom_x[1] + true_x[1];
   out_6802001497691266902[2] = -nom_x[2] + true_x[2];
   out_6802001497691266902[3] = -nom_x[3] + true_x[3];
   out_6802001497691266902[4] = -nom_x[4] + true_x[4];
   out_6802001497691266902[5] = -nom_x[5] + true_x[5];
   out_6802001497691266902[6] = -nom_x[6] + true_x[6];
   out_6802001497691266902[7] = -nom_x[7] + true_x[7];
   out_6802001497691266902[8] = -nom_x[8] + true_x[8];
   out_6802001497691266902[9] = -nom_x[9] + true_x[9];
   out_6802001497691266902[10] = -nom_x[10] + true_x[10];
   out_6802001497691266902[11] = -nom_x[11] + true_x[11];
   out_6802001497691266902[12] = -nom_x[12] + true_x[12];
   out_6802001497691266902[13] = -nom_x[13] + true_x[13];
   out_6802001497691266902[14] = -nom_x[14] + true_x[14];
   out_6802001497691266902[15] = -nom_x[15] + true_x[15];
   out_6802001497691266902[16] = -nom_x[16] + true_x[16];
   out_6802001497691266902[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_8360352250640609347) {
   out_8360352250640609347[0] = 1.0;
   out_8360352250640609347[1] = 0.0;
   out_8360352250640609347[2] = 0.0;
   out_8360352250640609347[3] = 0.0;
   out_8360352250640609347[4] = 0.0;
   out_8360352250640609347[5] = 0.0;
   out_8360352250640609347[6] = 0.0;
   out_8360352250640609347[7] = 0.0;
   out_8360352250640609347[8] = 0.0;
   out_8360352250640609347[9] = 0.0;
   out_8360352250640609347[10] = 0.0;
   out_8360352250640609347[11] = 0.0;
   out_8360352250640609347[12] = 0.0;
   out_8360352250640609347[13] = 0.0;
   out_8360352250640609347[14] = 0.0;
   out_8360352250640609347[15] = 0.0;
   out_8360352250640609347[16] = 0.0;
   out_8360352250640609347[17] = 0.0;
   out_8360352250640609347[18] = 0.0;
   out_8360352250640609347[19] = 1.0;
   out_8360352250640609347[20] = 0.0;
   out_8360352250640609347[21] = 0.0;
   out_8360352250640609347[22] = 0.0;
   out_8360352250640609347[23] = 0.0;
   out_8360352250640609347[24] = 0.0;
   out_8360352250640609347[25] = 0.0;
   out_8360352250640609347[26] = 0.0;
   out_8360352250640609347[27] = 0.0;
   out_8360352250640609347[28] = 0.0;
   out_8360352250640609347[29] = 0.0;
   out_8360352250640609347[30] = 0.0;
   out_8360352250640609347[31] = 0.0;
   out_8360352250640609347[32] = 0.0;
   out_8360352250640609347[33] = 0.0;
   out_8360352250640609347[34] = 0.0;
   out_8360352250640609347[35] = 0.0;
   out_8360352250640609347[36] = 0.0;
   out_8360352250640609347[37] = 0.0;
   out_8360352250640609347[38] = 1.0;
   out_8360352250640609347[39] = 0.0;
   out_8360352250640609347[40] = 0.0;
   out_8360352250640609347[41] = 0.0;
   out_8360352250640609347[42] = 0.0;
   out_8360352250640609347[43] = 0.0;
   out_8360352250640609347[44] = 0.0;
   out_8360352250640609347[45] = 0.0;
   out_8360352250640609347[46] = 0.0;
   out_8360352250640609347[47] = 0.0;
   out_8360352250640609347[48] = 0.0;
   out_8360352250640609347[49] = 0.0;
   out_8360352250640609347[50] = 0.0;
   out_8360352250640609347[51] = 0.0;
   out_8360352250640609347[52] = 0.0;
   out_8360352250640609347[53] = 0.0;
   out_8360352250640609347[54] = 0.0;
   out_8360352250640609347[55] = 0.0;
   out_8360352250640609347[56] = 0.0;
   out_8360352250640609347[57] = 1.0;
   out_8360352250640609347[58] = 0.0;
   out_8360352250640609347[59] = 0.0;
   out_8360352250640609347[60] = 0.0;
   out_8360352250640609347[61] = 0.0;
   out_8360352250640609347[62] = 0.0;
   out_8360352250640609347[63] = 0.0;
   out_8360352250640609347[64] = 0.0;
   out_8360352250640609347[65] = 0.0;
   out_8360352250640609347[66] = 0.0;
   out_8360352250640609347[67] = 0.0;
   out_8360352250640609347[68] = 0.0;
   out_8360352250640609347[69] = 0.0;
   out_8360352250640609347[70] = 0.0;
   out_8360352250640609347[71] = 0.0;
   out_8360352250640609347[72] = 0.0;
   out_8360352250640609347[73] = 0.0;
   out_8360352250640609347[74] = 0.0;
   out_8360352250640609347[75] = 0.0;
   out_8360352250640609347[76] = 1.0;
   out_8360352250640609347[77] = 0.0;
   out_8360352250640609347[78] = 0.0;
   out_8360352250640609347[79] = 0.0;
   out_8360352250640609347[80] = 0.0;
   out_8360352250640609347[81] = 0.0;
   out_8360352250640609347[82] = 0.0;
   out_8360352250640609347[83] = 0.0;
   out_8360352250640609347[84] = 0.0;
   out_8360352250640609347[85] = 0.0;
   out_8360352250640609347[86] = 0.0;
   out_8360352250640609347[87] = 0.0;
   out_8360352250640609347[88] = 0.0;
   out_8360352250640609347[89] = 0.0;
   out_8360352250640609347[90] = 0.0;
   out_8360352250640609347[91] = 0.0;
   out_8360352250640609347[92] = 0.0;
   out_8360352250640609347[93] = 0.0;
   out_8360352250640609347[94] = 0.0;
   out_8360352250640609347[95] = 1.0;
   out_8360352250640609347[96] = 0.0;
   out_8360352250640609347[97] = 0.0;
   out_8360352250640609347[98] = 0.0;
   out_8360352250640609347[99] = 0.0;
   out_8360352250640609347[100] = 0.0;
   out_8360352250640609347[101] = 0.0;
   out_8360352250640609347[102] = 0.0;
   out_8360352250640609347[103] = 0.0;
   out_8360352250640609347[104] = 0.0;
   out_8360352250640609347[105] = 0.0;
   out_8360352250640609347[106] = 0.0;
   out_8360352250640609347[107] = 0.0;
   out_8360352250640609347[108] = 0.0;
   out_8360352250640609347[109] = 0.0;
   out_8360352250640609347[110] = 0.0;
   out_8360352250640609347[111] = 0.0;
   out_8360352250640609347[112] = 0.0;
   out_8360352250640609347[113] = 0.0;
   out_8360352250640609347[114] = 1.0;
   out_8360352250640609347[115] = 0.0;
   out_8360352250640609347[116] = 0.0;
   out_8360352250640609347[117] = 0.0;
   out_8360352250640609347[118] = 0.0;
   out_8360352250640609347[119] = 0.0;
   out_8360352250640609347[120] = 0.0;
   out_8360352250640609347[121] = 0.0;
   out_8360352250640609347[122] = 0.0;
   out_8360352250640609347[123] = 0.0;
   out_8360352250640609347[124] = 0.0;
   out_8360352250640609347[125] = 0.0;
   out_8360352250640609347[126] = 0.0;
   out_8360352250640609347[127] = 0.0;
   out_8360352250640609347[128] = 0.0;
   out_8360352250640609347[129] = 0.0;
   out_8360352250640609347[130] = 0.0;
   out_8360352250640609347[131] = 0.0;
   out_8360352250640609347[132] = 0.0;
   out_8360352250640609347[133] = 1.0;
   out_8360352250640609347[134] = 0.0;
   out_8360352250640609347[135] = 0.0;
   out_8360352250640609347[136] = 0.0;
   out_8360352250640609347[137] = 0.0;
   out_8360352250640609347[138] = 0.0;
   out_8360352250640609347[139] = 0.0;
   out_8360352250640609347[140] = 0.0;
   out_8360352250640609347[141] = 0.0;
   out_8360352250640609347[142] = 0.0;
   out_8360352250640609347[143] = 0.0;
   out_8360352250640609347[144] = 0.0;
   out_8360352250640609347[145] = 0.0;
   out_8360352250640609347[146] = 0.0;
   out_8360352250640609347[147] = 0.0;
   out_8360352250640609347[148] = 0.0;
   out_8360352250640609347[149] = 0.0;
   out_8360352250640609347[150] = 0.0;
   out_8360352250640609347[151] = 0.0;
   out_8360352250640609347[152] = 1.0;
   out_8360352250640609347[153] = 0.0;
   out_8360352250640609347[154] = 0.0;
   out_8360352250640609347[155] = 0.0;
   out_8360352250640609347[156] = 0.0;
   out_8360352250640609347[157] = 0.0;
   out_8360352250640609347[158] = 0.0;
   out_8360352250640609347[159] = 0.0;
   out_8360352250640609347[160] = 0.0;
   out_8360352250640609347[161] = 0.0;
   out_8360352250640609347[162] = 0.0;
   out_8360352250640609347[163] = 0.0;
   out_8360352250640609347[164] = 0.0;
   out_8360352250640609347[165] = 0.0;
   out_8360352250640609347[166] = 0.0;
   out_8360352250640609347[167] = 0.0;
   out_8360352250640609347[168] = 0.0;
   out_8360352250640609347[169] = 0.0;
   out_8360352250640609347[170] = 0.0;
   out_8360352250640609347[171] = 1.0;
   out_8360352250640609347[172] = 0.0;
   out_8360352250640609347[173] = 0.0;
   out_8360352250640609347[174] = 0.0;
   out_8360352250640609347[175] = 0.0;
   out_8360352250640609347[176] = 0.0;
   out_8360352250640609347[177] = 0.0;
   out_8360352250640609347[178] = 0.0;
   out_8360352250640609347[179] = 0.0;
   out_8360352250640609347[180] = 0.0;
   out_8360352250640609347[181] = 0.0;
   out_8360352250640609347[182] = 0.0;
   out_8360352250640609347[183] = 0.0;
   out_8360352250640609347[184] = 0.0;
   out_8360352250640609347[185] = 0.0;
   out_8360352250640609347[186] = 0.0;
   out_8360352250640609347[187] = 0.0;
   out_8360352250640609347[188] = 0.0;
   out_8360352250640609347[189] = 0.0;
   out_8360352250640609347[190] = 1.0;
   out_8360352250640609347[191] = 0.0;
   out_8360352250640609347[192] = 0.0;
   out_8360352250640609347[193] = 0.0;
   out_8360352250640609347[194] = 0.0;
   out_8360352250640609347[195] = 0.0;
   out_8360352250640609347[196] = 0.0;
   out_8360352250640609347[197] = 0.0;
   out_8360352250640609347[198] = 0.0;
   out_8360352250640609347[199] = 0.0;
   out_8360352250640609347[200] = 0.0;
   out_8360352250640609347[201] = 0.0;
   out_8360352250640609347[202] = 0.0;
   out_8360352250640609347[203] = 0.0;
   out_8360352250640609347[204] = 0.0;
   out_8360352250640609347[205] = 0.0;
   out_8360352250640609347[206] = 0.0;
   out_8360352250640609347[207] = 0.0;
   out_8360352250640609347[208] = 0.0;
   out_8360352250640609347[209] = 1.0;
   out_8360352250640609347[210] = 0.0;
   out_8360352250640609347[211] = 0.0;
   out_8360352250640609347[212] = 0.0;
   out_8360352250640609347[213] = 0.0;
   out_8360352250640609347[214] = 0.0;
   out_8360352250640609347[215] = 0.0;
   out_8360352250640609347[216] = 0.0;
   out_8360352250640609347[217] = 0.0;
   out_8360352250640609347[218] = 0.0;
   out_8360352250640609347[219] = 0.0;
   out_8360352250640609347[220] = 0.0;
   out_8360352250640609347[221] = 0.0;
   out_8360352250640609347[222] = 0.0;
   out_8360352250640609347[223] = 0.0;
   out_8360352250640609347[224] = 0.0;
   out_8360352250640609347[225] = 0.0;
   out_8360352250640609347[226] = 0.0;
   out_8360352250640609347[227] = 0.0;
   out_8360352250640609347[228] = 1.0;
   out_8360352250640609347[229] = 0.0;
   out_8360352250640609347[230] = 0.0;
   out_8360352250640609347[231] = 0.0;
   out_8360352250640609347[232] = 0.0;
   out_8360352250640609347[233] = 0.0;
   out_8360352250640609347[234] = 0.0;
   out_8360352250640609347[235] = 0.0;
   out_8360352250640609347[236] = 0.0;
   out_8360352250640609347[237] = 0.0;
   out_8360352250640609347[238] = 0.0;
   out_8360352250640609347[239] = 0.0;
   out_8360352250640609347[240] = 0.0;
   out_8360352250640609347[241] = 0.0;
   out_8360352250640609347[242] = 0.0;
   out_8360352250640609347[243] = 0.0;
   out_8360352250640609347[244] = 0.0;
   out_8360352250640609347[245] = 0.0;
   out_8360352250640609347[246] = 0.0;
   out_8360352250640609347[247] = 1.0;
   out_8360352250640609347[248] = 0.0;
   out_8360352250640609347[249] = 0.0;
   out_8360352250640609347[250] = 0.0;
   out_8360352250640609347[251] = 0.0;
   out_8360352250640609347[252] = 0.0;
   out_8360352250640609347[253] = 0.0;
   out_8360352250640609347[254] = 0.0;
   out_8360352250640609347[255] = 0.0;
   out_8360352250640609347[256] = 0.0;
   out_8360352250640609347[257] = 0.0;
   out_8360352250640609347[258] = 0.0;
   out_8360352250640609347[259] = 0.0;
   out_8360352250640609347[260] = 0.0;
   out_8360352250640609347[261] = 0.0;
   out_8360352250640609347[262] = 0.0;
   out_8360352250640609347[263] = 0.0;
   out_8360352250640609347[264] = 0.0;
   out_8360352250640609347[265] = 0.0;
   out_8360352250640609347[266] = 1.0;
   out_8360352250640609347[267] = 0.0;
   out_8360352250640609347[268] = 0.0;
   out_8360352250640609347[269] = 0.0;
   out_8360352250640609347[270] = 0.0;
   out_8360352250640609347[271] = 0.0;
   out_8360352250640609347[272] = 0.0;
   out_8360352250640609347[273] = 0.0;
   out_8360352250640609347[274] = 0.0;
   out_8360352250640609347[275] = 0.0;
   out_8360352250640609347[276] = 0.0;
   out_8360352250640609347[277] = 0.0;
   out_8360352250640609347[278] = 0.0;
   out_8360352250640609347[279] = 0.0;
   out_8360352250640609347[280] = 0.0;
   out_8360352250640609347[281] = 0.0;
   out_8360352250640609347[282] = 0.0;
   out_8360352250640609347[283] = 0.0;
   out_8360352250640609347[284] = 0.0;
   out_8360352250640609347[285] = 1.0;
   out_8360352250640609347[286] = 0.0;
   out_8360352250640609347[287] = 0.0;
   out_8360352250640609347[288] = 0.0;
   out_8360352250640609347[289] = 0.0;
   out_8360352250640609347[290] = 0.0;
   out_8360352250640609347[291] = 0.0;
   out_8360352250640609347[292] = 0.0;
   out_8360352250640609347[293] = 0.0;
   out_8360352250640609347[294] = 0.0;
   out_8360352250640609347[295] = 0.0;
   out_8360352250640609347[296] = 0.0;
   out_8360352250640609347[297] = 0.0;
   out_8360352250640609347[298] = 0.0;
   out_8360352250640609347[299] = 0.0;
   out_8360352250640609347[300] = 0.0;
   out_8360352250640609347[301] = 0.0;
   out_8360352250640609347[302] = 0.0;
   out_8360352250640609347[303] = 0.0;
   out_8360352250640609347[304] = 1.0;
   out_8360352250640609347[305] = 0.0;
   out_8360352250640609347[306] = 0.0;
   out_8360352250640609347[307] = 0.0;
   out_8360352250640609347[308] = 0.0;
   out_8360352250640609347[309] = 0.0;
   out_8360352250640609347[310] = 0.0;
   out_8360352250640609347[311] = 0.0;
   out_8360352250640609347[312] = 0.0;
   out_8360352250640609347[313] = 0.0;
   out_8360352250640609347[314] = 0.0;
   out_8360352250640609347[315] = 0.0;
   out_8360352250640609347[316] = 0.0;
   out_8360352250640609347[317] = 0.0;
   out_8360352250640609347[318] = 0.0;
   out_8360352250640609347[319] = 0.0;
   out_8360352250640609347[320] = 0.0;
   out_8360352250640609347[321] = 0.0;
   out_8360352250640609347[322] = 0.0;
   out_8360352250640609347[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_1729733863847722677) {
   out_1729733863847722677[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_1729733863847722677[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_1729733863847722677[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_1729733863847722677[3] = dt*state[12] + state[3];
   out_1729733863847722677[4] = dt*state[13] + state[4];
   out_1729733863847722677[5] = dt*state[14] + state[5];
   out_1729733863847722677[6] = state[6];
   out_1729733863847722677[7] = state[7];
   out_1729733863847722677[8] = state[8];
   out_1729733863847722677[9] = state[9];
   out_1729733863847722677[10] = state[10];
   out_1729733863847722677[11] = state[11];
   out_1729733863847722677[12] = state[12];
   out_1729733863847722677[13] = state[13];
   out_1729733863847722677[14] = state[14];
   out_1729733863847722677[15] = state[15];
   out_1729733863847722677[16] = state[16];
   out_1729733863847722677[17] = state[17];
}
void F_fun(double *state, double dt, double *out_6589700326730162728) {
   out_6589700326730162728[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6589700326730162728[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6589700326730162728[2] = 0;
   out_6589700326730162728[3] = 0;
   out_6589700326730162728[4] = 0;
   out_6589700326730162728[5] = 0;
   out_6589700326730162728[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6589700326730162728[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6589700326730162728[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_6589700326730162728[9] = 0;
   out_6589700326730162728[10] = 0;
   out_6589700326730162728[11] = 0;
   out_6589700326730162728[12] = 0;
   out_6589700326730162728[13] = 0;
   out_6589700326730162728[14] = 0;
   out_6589700326730162728[15] = 0;
   out_6589700326730162728[16] = 0;
   out_6589700326730162728[17] = 0;
   out_6589700326730162728[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6589700326730162728[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6589700326730162728[20] = 0;
   out_6589700326730162728[21] = 0;
   out_6589700326730162728[22] = 0;
   out_6589700326730162728[23] = 0;
   out_6589700326730162728[24] = 0;
   out_6589700326730162728[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6589700326730162728[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_6589700326730162728[27] = 0;
   out_6589700326730162728[28] = 0;
   out_6589700326730162728[29] = 0;
   out_6589700326730162728[30] = 0;
   out_6589700326730162728[31] = 0;
   out_6589700326730162728[32] = 0;
   out_6589700326730162728[33] = 0;
   out_6589700326730162728[34] = 0;
   out_6589700326730162728[35] = 0;
   out_6589700326730162728[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6589700326730162728[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6589700326730162728[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6589700326730162728[39] = 0;
   out_6589700326730162728[40] = 0;
   out_6589700326730162728[41] = 0;
   out_6589700326730162728[42] = 0;
   out_6589700326730162728[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6589700326730162728[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_6589700326730162728[45] = 0;
   out_6589700326730162728[46] = 0;
   out_6589700326730162728[47] = 0;
   out_6589700326730162728[48] = 0;
   out_6589700326730162728[49] = 0;
   out_6589700326730162728[50] = 0;
   out_6589700326730162728[51] = 0;
   out_6589700326730162728[52] = 0;
   out_6589700326730162728[53] = 0;
   out_6589700326730162728[54] = 0;
   out_6589700326730162728[55] = 0;
   out_6589700326730162728[56] = 0;
   out_6589700326730162728[57] = 1;
   out_6589700326730162728[58] = 0;
   out_6589700326730162728[59] = 0;
   out_6589700326730162728[60] = 0;
   out_6589700326730162728[61] = 0;
   out_6589700326730162728[62] = 0;
   out_6589700326730162728[63] = 0;
   out_6589700326730162728[64] = 0;
   out_6589700326730162728[65] = 0;
   out_6589700326730162728[66] = dt;
   out_6589700326730162728[67] = 0;
   out_6589700326730162728[68] = 0;
   out_6589700326730162728[69] = 0;
   out_6589700326730162728[70] = 0;
   out_6589700326730162728[71] = 0;
   out_6589700326730162728[72] = 0;
   out_6589700326730162728[73] = 0;
   out_6589700326730162728[74] = 0;
   out_6589700326730162728[75] = 0;
   out_6589700326730162728[76] = 1;
   out_6589700326730162728[77] = 0;
   out_6589700326730162728[78] = 0;
   out_6589700326730162728[79] = 0;
   out_6589700326730162728[80] = 0;
   out_6589700326730162728[81] = 0;
   out_6589700326730162728[82] = 0;
   out_6589700326730162728[83] = 0;
   out_6589700326730162728[84] = 0;
   out_6589700326730162728[85] = dt;
   out_6589700326730162728[86] = 0;
   out_6589700326730162728[87] = 0;
   out_6589700326730162728[88] = 0;
   out_6589700326730162728[89] = 0;
   out_6589700326730162728[90] = 0;
   out_6589700326730162728[91] = 0;
   out_6589700326730162728[92] = 0;
   out_6589700326730162728[93] = 0;
   out_6589700326730162728[94] = 0;
   out_6589700326730162728[95] = 1;
   out_6589700326730162728[96] = 0;
   out_6589700326730162728[97] = 0;
   out_6589700326730162728[98] = 0;
   out_6589700326730162728[99] = 0;
   out_6589700326730162728[100] = 0;
   out_6589700326730162728[101] = 0;
   out_6589700326730162728[102] = 0;
   out_6589700326730162728[103] = 0;
   out_6589700326730162728[104] = dt;
   out_6589700326730162728[105] = 0;
   out_6589700326730162728[106] = 0;
   out_6589700326730162728[107] = 0;
   out_6589700326730162728[108] = 0;
   out_6589700326730162728[109] = 0;
   out_6589700326730162728[110] = 0;
   out_6589700326730162728[111] = 0;
   out_6589700326730162728[112] = 0;
   out_6589700326730162728[113] = 0;
   out_6589700326730162728[114] = 1;
   out_6589700326730162728[115] = 0;
   out_6589700326730162728[116] = 0;
   out_6589700326730162728[117] = 0;
   out_6589700326730162728[118] = 0;
   out_6589700326730162728[119] = 0;
   out_6589700326730162728[120] = 0;
   out_6589700326730162728[121] = 0;
   out_6589700326730162728[122] = 0;
   out_6589700326730162728[123] = 0;
   out_6589700326730162728[124] = 0;
   out_6589700326730162728[125] = 0;
   out_6589700326730162728[126] = 0;
   out_6589700326730162728[127] = 0;
   out_6589700326730162728[128] = 0;
   out_6589700326730162728[129] = 0;
   out_6589700326730162728[130] = 0;
   out_6589700326730162728[131] = 0;
   out_6589700326730162728[132] = 0;
   out_6589700326730162728[133] = 1;
   out_6589700326730162728[134] = 0;
   out_6589700326730162728[135] = 0;
   out_6589700326730162728[136] = 0;
   out_6589700326730162728[137] = 0;
   out_6589700326730162728[138] = 0;
   out_6589700326730162728[139] = 0;
   out_6589700326730162728[140] = 0;
   out_6589700326730162728[141] = 0;
   out_6589700326730162728[142] = 0;
   out_6589700326730162728[143] = 0;
   out_6589700326730162728[144] = 0;
   out_6589700326730162728[145] = 0;
   out_6589700326730162728[146] = 0;
   out_6589700326730162728[147] = 0;
   out_6589700326730162728[148] = 0;
   out_6589700326730162728[149] = 0;
   out_6589700326730162728[150] = 0;
   out_6589700326730162728[151] = 0;
   out_6589700326730162728[152] = 1;
   out_6589700326730162728[153] = 0;
   out_6589700326730162728[154] = 0;
   out_6589700326730162728[155] = 0;
   out_6589700326730162728[156] = 0;
   out_6589700326730162728[157] = 0;
   out_6589700326730162728[158] = 0;
   out_6589700326730162728[159] = 0;
   out_6589700326730162728[160] = 0;
   out_6589700326730162728[161] = 0;
   out_6589700326730162728[162] = 0;
   out_6589700326730162728[163] = 0;
   out_6589700326730162728[164] = 0;
   out_6589700326730162728[165] = 0;
   out_6589700326730162728[166] = 0;
   out_6589700326730162728[167] = 0;
   out_6589700326730162728[168] = 0;
   out_6589700326730162728[169] = 0;
   out_6589700326730162728[170] = 0;
   out_6589700326730162728[171] = 1;
   out_6589700326730162728[172] = 0;
   out_6589700326730162728[173] = 0;
   out_6589700326730162728[174] = 0;
   out_6589700326730162728[175] = 0;
   out_6589700326730162728[176] = 0;
   out_6589700326730162728[177] = 0;
   out_6589700326730162728[178] = 0;
   out_6589700326730162728[179] = 0;
   out_6589700326730162728[180] = 0;
   out_6589700326730162728[181] = 0;
   out_6589700326730162728[182] = 0;
   out_6589700326730162728[183] = 0;
   out_6589700326730162728[184] = 0;
   out_6589700326730162728[185] = 0;
   out_6589700326730162728[186] = 0;
   out_6589700326730162728[187] = 0;
   out_6589700326730162728[188] = 0;
   out_6589700326730162728[189] = 0;
   out_6589700326730162728[190] = 1;
   out_6589700326730162728[191] = 0;
   out_6589700326730162728[192] = 0;
   out_6589700326730162728[193] = 0;
   out_6589700326730162728[194] = 0;
   out_6589700326730162728[195] = 0;
   out_6589700326730162728[196] = 0;
   out_6589700326730162728[197] = 0;
   out_6589700326730162728[198] = 0;
   out_6589700326730162728[199] = 0;
   out_6589700326730162728[200] = 0;
   out_6589700326730162728[201] = 0;
   out_6589700326730162728[202] = 0;
   out_6589700326730162728[203] = 0;
   out_6589700326730162728[204] = 0;
   out_6589700326730162728[205] = 0;
   out_6589700326730162728[206] = 0;
   out_6589700326730162728[207] = 0;
   out_6589700326730162728[208] = 0;
   out_6589700326730162728[209] = 1;
   out_6589700326730162728[210] = 0;
   out_6589700326730162728[211] = 0;
   out_6589700326730162728[212] = 0;
   out_6589700326730162728[213] = 0;
   out_6589700326730162728[214] = 0;
   out_6589700326730162728[215] = 0;
   out_6589700326730162728[216] = 0;
   out_6589700326730162728[217] = 0;
   out_6589700326730162728[218] = 0;
   out_6589700326730162728[219] = 0;
   out_6589700326730162728[220] = 0;
   out_6589700326730162728[221] = 0;
   out_6589700326730162728[222] = 0;
   out_6589700326730162728[223] = 0;
   out_6589700326730162728[224] = 0;
   out_6589700326730162728[225] = 0;
   out_6589700326730162728[226] = 0;
   out_6589700326730162728[227] = 0;
   out_6589700326730162728[228] = 1;
   out_6589700326730162728[229] = 0;
   out_6589700326730162728[230] = 0;
   out_6589700326730162728[231] = 0;
   out_6589700326730162728[232] = 0;
   out_6589700326730162728[233] = 0;
   out_6589700326730162728[234] = 0;
   out_6589700326730162728[235] = 0;
   out_6589700326730162728[236] = 0;
   out_6589700326730162728[237] = 0;
   out_6589700326730162728[238] = 0;
   out_6589700326730162728[239] = 0;
   out_6589700326730162728[240] = 0;
   out_6589700326730162728[241] = 0;
   out_6589700326730162728[242] = 0;
   out_6589700326730162728[243] = 0;
   out_6589700326730162728[244] = 0;
   out_6589700326730162728[245] = 0;
   out_6589700326730162728[246] = 0;
   out_6589700326730162728[247] = 1;
   out_6589700326730162728[248] = 0;
   out_6589700326730162728[249] = 0;
   out_6589700326730162728[250] = 0;
   out_6589700326730162728[251] = 0;
   out_6589700326730162728[252] = 0;
   out_6589700326730162728[253] = 0;
   out_6589700326730162728[254] = 0;
   out_6589700326730162728[255] = 0;
   out_6589700326730162728[256] = 0;
   out_6589700326730162728[257] = 0;
   out_6589700326730162728[258] = 0;
   out_6589700326730162728[259] = 0;
   out_6589700326730162728[260] = 0;
   out_6589700326730162728[261] = 0;
   out_6589700326730162728[262] = 0;
   out_6589700326730162728[263] = 0;
   out_6589700326730162728[264] = 0;
   out_6589700326730162728[265] = 0;
   out_6589700326730162728[266] = 1;
   out_6589700326730162728[267] = 0;
   out_6589700326730162728[268] = 0;
   out_6589700326730162728[269] = 0;
   out_6589700326730162728[270] = 0;
   out_6589700326730162728[271] = 0;
   out_6589700326730162728[272] = 0;
   out_6589700326730162728[273] = 0;
   out_6589700326730162728[274] = 0;
   out_6589700326730162728[275] = 0;
   out_6589700326730162728[276] = 0;
   out_6589700326730162728[277] = 0;
   out_6589700326730162728[278] = 0;
   out_6589700326730162728[279] = 0;
   out_6589700326730162728[280] = 0;
   out_6589700326730162728[281] = 0;
   out_6589700326730162728[282] = 0;
   out_6589700326730162728[283] = 0;
   out_6589700326730162728[284] = 0;
   out_6589700326730162728[285] = 1;
   out_6589700326730162728[286] = 0;
   out_6589700326730162728[287] = 0;
   out_6589700326730162728[288] = 0;
   out_6589700326730162728[289] = 0;
   out_6589700326730162728[290] = 0;
   out_6589700326730162728[291] = 0;
   out_6589700326730162728[292] = 0;
   out_6589700326730162728[293] = 0;
   out_6589700326730162728[294] = 0;
   out_6589700326730162728[295] = 0;
   out_6589700326730162728[296] = 0;
   out_6589700326730162728[297] = 0;
   out_6589700326730162728[298] = 0;
   out_6589700326730162728[299] = 0;
   out_6589700326730162728[300] = 0;
   out_6589700326730162728[301] = 0;
   out_6589700326730162728[302] = 0;
   out_6589700326730162728[303] = 0;
   out_6589700326730162728[304] = 1;
   out_6589700326730162728[305] = 0;
   out_6589700326730162728[306] = 0;
   out_6589700326730162728[307] = 0;
   out_6589700326730162728[308] = 0;
   out_6589700326730162728[309] = 0;
   out_6589700326730162728[310] = 0;
   out_6589700326730162728[311] = 0;
   out_6589700326730162728[312] = 0;
   out_6589700326730162728[313] = 0;
   out_6589700326730162728[314] = 0;
   out_6589700326730162728[315] = 0;
   out_6589700326730162728[316] = 0;
   out_6589700326730162728[317] = 0;
   out_6589700326730162728[318] = 0;
   out_6589700326730162728[319] = 0;
   out_6589700326730162728[320] = 0;
   out_6589700326730162728[321] = 0;
   out_6589700326730162728[322] = 0;
   out_6589700326730162728[323] = 1;
}
void h_4(double *state, double *unused, double *out_2977686091862971139) {
   out_2977686091862971139[0] = state[6] + state[9];
   out_2977686091862971139[1] = state[7] + state[10];
   out_2977686091862971139[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_6885981921967472245) {
   out_6885981921967472245[0] = 0;
   out_6885981921967472245[1] = 0;
   out_6885981921967472245[2] = 0;
   out_6885981921967472245[3] = 0;
   out_6885981921967472245[4] = 0;
   out_6885981921967472245[5] = 0;
   out_6885981921967472245[6] = 1;
   out_6885981921967472245[7] = 0;
   out_6885981921967472245[8] = 0;
   out_6885981921967472245[9] = 1;
   out_6885981921967472245[10] = 0;
   out_6885981921967472245[11] = 0;
   out_6885981921967472245[12] = 0;
   out_6885981921967472245[13] = 0;
   out_6885981921967472245[14] = 0;
   out_6885981921967472245[15] = 0;
   out_6885981921967472245[16] = 0;
   out_6885981921967472245[17] = 0;
   out_6885981921967472245[18] = 0;
   out_6885981921967472245[19] = 0;
   out_6885981921967472245[20] = 0;
   out_6885981921967472245[21] = 0;
   out_6885981921967472245[22] = 0;
   out_6885981921967472245[23] = 0;
   out_6885981921967472245[24] = 0;
   out_6885981921967472245[25] = 1;
   out_6885981921967472245[26] = 0;
   out_6885981921967472245[27] = 0;
   out_6885981921967472245[28] = 1;
   out_6885981921967472245[29] = 0;
   out_6885981921967472245[30] = 0;
   out_6885981921967472245[31] = 0;
   out_6885981921967472245[32] = 0;
   out_6885981921967472245[33] = 0;
   out_6885981921967472245[34] = 0;
   out_6885981921967472245[35] = 0;
   out_6885981921967472245[36] = 0;
   out_6885981921967472245[37] = 0;
   out_6885981921967472245[38] = 0;
   out_6885981921967472245[39] = 0;
   out_6885981921967472245[40] = 0;
   out_6885981921967472245[41] = 0;
   out_6885981921967472245[42] = 0;
   out_6885981921967472245[43] = 0;
   out_6885981921967472245[44] = 1;
   out_6885981921967472245[45] = 0;
   out_6885981921967472245[46] = 0;
   out_6885981921967472245[47] = 1;
   out_6885981921967472245[48] = 0;
   out_6885981921967472245[49] = 0;
   out_6885981921967472245[50] = 0;
   out_6885981921967472245[51] = 0;
   out_6885981921967472245[52] = 0;
   out_6885981921967472245[53] = 0;
}
void h_10(double *state, double *unused, double *out_2063640600098317601) {
   out_2063640600098317601[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_2063640600098317601[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_2063640600098317601[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_5665626610612883032) {
   out_5665626610612883032[0] = 0;
   out_5665626610612883032[1] = 9.8100000000000005*cos(state[1]);
   out_5665626610612883032[2] = 0;
   out_5665626610612883032[3] = 0;
   out_5665626610612883032[4] = -state[8];
   out_5665626610612883032[5] = state[7];
   out_5665626610612883032[6] = 0;
   out_5665626610612883032[7] = state[5];
   out_5665626610612883032[8] = -state[4];
   out_5665626610612883032[9] = 0;
   out_5665626610612883032[10] = 0;
   out_5665626610612883032[11] = 0;
   out_5665626610612883032[12] = 1;
   out_5665626610612883032[13] = 0;
   out_5665626610612883032[14] = 0;
   out_5665626610612883032[15] = 1;
   out_5665626610612883032[16] = 0;
   out_5665626610612883032[17] = 0;
   out_5665626610612883032[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_5665626610612883032[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_5665626610612883032[20] = 0;
   out_5665626610612883032[21] = state[8];
   out_5665626610612883032[22] = 0;
   out_5665626610612883032[23] = -state[6];
   out_5665626610612883032[24] = -state[5];
   out_5665626610612883032[25] = 0;
   out_5665626610612883032[26] = state[3];
   out_5665626610612883032[27] = 0;
   out_5665626610612883032[28] = 0;
   out_5665626610612883032[29] = 0;
   out_5665626610612883032[30] = 0;
   out_5665626610612883032[31] = 1;
   out_5665626610612883032[32] = 0;
   out_5665626610612883032[33] = 0;
   out_5665626610612883032[34] = 1;
   out_5665626610612883032[35] = 0;
   out_5665626610612883032[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_5665626610612883032[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_5665626610612883032[38] = 0;
   out_5665626610612883032[39] = -state[7];
   out_5665626610612883032[40] = state[6];
   out_5665626610612883032[41] = 0;
   out_5665626610612883032[42] = state[4];
   out_5665626610612883032[43] = -state[3];
   out_5665626610612883032[44] = 0;
   out_5665626610612883032[45] = 0;
   out_5665626610612883032[46] = 0;
   out_5665626610612883032[47] = 0;
   out_5665626610612883032[48] = 0;
   out_5665626610612883032[49] = 0;
   out_5665626610612883032[50] = 1;
   out_5665626610612883032[51] = 0;
   out_5665626610612883032[52] = 0;
   out_5665626610612883032[53] = 1;
}
void h_13(double *state, double *unused, double *out_7607718264744722863) {
   out_7607718264744722863[0] = state[3];
   out_7607718264744722863[1] = state[4];
   out_7607718264744722863[2] = state[5];
}
void H_13(double *state, double *unused, double *out_3950130943425378442) {
   out_3950130943425378442[0] = 0;
   out_3950130943425378442[1] = 0;
   out_3950130943425378442[2] = 0;
   out_3950130943425378442[3] = 1;
   out_3950130943425378442[4] = 0;
   out_3950130943425378442[5] = 0;
   out_3950130943425378442[6] = 0;
   out_3950130943425378442[7] = 0;
   out_3950130943425378442[8] = 0;
   out_3950130943425378442[9] = 0;
   out_3950130943425378442[10] = 0;
   out_3950130943425378442[11] = 0;
   out_3950130943425378442[12] = 0;
   out_3950130943425378442[13] = 0;
   out_3950130943425378442[14] = 0;
   out_3950130943425378442[15] = 0;
   out_3950130943425378442[16] = 0;
   out_3950130943425378442[17] = 0;
   out_3950130943425378442[18] = 0;
   out_3950130943425378442[19] = 0;
   out_3950130943425378442[20] = 0;
   out_3950130943425378442[21] = 0;
   out_3950130943425378442[22] = 1;
   out_3950130943425378442[23] = 0;
   out_3950130943425378442[24] = 0;
   out_3950130943425378442[25] = 0;
   out_3950130943425378442[26] = 0;
   out_3950130943425378442[27] = 0;
   out_3950130943425378442[28] = 0;
   out_3950130943425378442[29] = 0;
   out_3950130943425378442[30] = 0;
   out_3950130943425378442[31] = 0;
   out_3950130943425378442[32] = 0;
   out_3950130943425378442[33] = 0;
   out_3950130943425378442[34] = 0;
   out_3950130943425378442[35] = 0;
   out_3950130943425378442[36] = 0;
   out_3950130943425378442[37] = 0;
   out_3950130943425378442[38] = 0;
   out_3950130943425378442[39] = 0;
   out_3950130943425378442[40] = 0;
   out_3950130943425378442[41] = 1;
   out_3950130943425378442[42] = 0;
   out_3950130943425378442[43] = 0;
   out_3950130943425378442[44] = 0;
   out_3950130943425378442[45] = 0;
   out_3950130943425378442[46] = 0;
   out_3950130943425378442[47] = 0;
   out_3950130943425378442[48] = 0;
   out_3950130943425378442[49] = 0;
   out_3950130943425378442[50] = 0;
   out_3950130943425378442[51] = 0;
   out_3950130943425378442[52] = 0;
   out_3950130943425378442[53] = 0;
}
void h_14(double *state, double *unused, double *out_4555210887505306851) {
   out_4555210887505306851[0] = state[6];
   out_4555210887505306851[1] = state[7];
   out_4555210887505306851[2] = state[8];
}
void H_14(double *state, double *unused, double *out_3803193489672099949) {
   out_3803193489672099949[0] = 0;
   out_3803193489672099949[1] = 0;
   out_3803193489672099949[2] = 0;
   out_3803193489672099949[3] = 0;
   out_3803193489672099949[4] = 0;
   out_3803193489672099949[5] = 0;
   out_3803193489672099949[6] = 1;
   out_3803193489672099949[7] = 0;
   out_3803193489672099949[8] = 0;
   out_3803193489672099949[9] = 0;
   out_3803193489672099949[10] = 0;
   out_3803193489672099949[11] = 0;
   out_3803193489672099949[12] = 0;
   out_3803193489672099949[13] = 0;
   out_3803193489672099949[14] = 0;
   out_3803193489672099949[15] = 0;
   out_3803193489672099949[16] = 0;
   out_3803193489672099949[17] = 0;
   out_3803193489672099949[18] = 0;
   out_3803193489672099949[19] = 0;
   out_3803193489672099949[20] = 0;
   out_3803193489672099949[21] = 0;
   out_3803193489672099949[22] = 0;
   out_3803193489672099949[23] = 0;
   out_3803193489672099949[24] = 0;
   out_3803193489672099949[25] = 1;
   out_3803193489672099949[26] = 0;
   out_3803193489672099949[27] = 0;
   out_3803193489672099949[28] = 0;
   out_3803193489672099949[29] = 0;
   out_3803193489672099949[30] = 0;
   out_3803193489672099949[31] = 0;
   out_3803193489672099949[32] = 0;
   out_3803193489672099949[33] = 0;
   out_3803193489672099949[34] = 0;
   out_3803193489672099949[35] = 0;
   out_3803193489672099949[36] = 0;
   out_3803193489672099949[37] = 0;
   out_3803193489672099949[38] = 0;
   out_3803193489672099949[39] = 0;
   out_3803193489672099949[40] = 0;
   out_3803193489672099949[41] = 0;
   out_3803193489672099949[42] = 0;
   out_3803193489672099949[43] = 0;
   out_3803193489672099949[44] = 1;
   out_3803193489672099949[45] = 0;
   out_3803193489672099949[46] = 0;
   out_3803193489672099949[47] = 0;
   out_3803193489672099949[48] = 0;
   out_3803193489672099949[49] = 0;
   out_3803193489672099949[50] = 0;
   out_3803193489672099949[51] = 0;
   out_3803193489672099949[52] = 0;
   out_3803193489672099949[53] = 0;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_7607340466644126338) {
  err_fun(nom_x, delta_x, out_7607340466644126338);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_6802001497691266902) {
  inv_err_fun(nom_x, true_x, out_6802001497691266902);
}
void pose_H_mod_fun(double *state, double *out_8360352250640609347) {
  H_mod_fun(state, out_8360352250640609347);
}
void pose_f_fun(double *state, double dt, double *out_1729733863847722677) {
  f_fun(state,  dt, out_1729733863847722677);
}
void pose_F_fun(double *state, double dt, double *out_6589700326730162728) {
  F_fun(state,  dt, out_6589700326730162728);
}
void pose_h_4(double *state, double *unused, double *out_2977686091862971139) {
  h_4(state, unused, out_2977686091862971139);
}
void pose_H_4(double *state, double *unused, double *out_6885981921967472245) {
  H_4(state, unused, out_6885981921967472245);
}
void pose_h_10(double *state, double *unused, double *out_2063640600098317601) {
  h_10(state, unused, out_2063640600098317601);
}
void pose_H_10(double *state, double *unused, double *out_5665626610612883032) {
  H_10(state, unused, out_5665626610612883032);
}
void pose_h_13(double *state, double *unused, double *out_7607718264744722863) {
  h_13(state, unused, out_7607718264744722863);
}
void pose_H_13(double *state, double *unused, double *out_3950130943425378442) {
  H_13(state, unused, out_3950130943425378442);
}
void pose_h_14(double *state, double *unused, double *out_4555210887505306851) {
  h_14(state, unused, out_4555210887505306851);
}
void pose_H_14(double *state, double *unused, double *out_3803193489672099949) {
  H_14(state, unused, out_3803193489672099949);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
