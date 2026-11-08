#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_2068083195310390242) {
   out_2068083195310390242[0] = delta_x[0] + nom_x[0];
   out_2068083195310390242[1] = delta_x[1] + nom_x[1];
   out_2068083195310390242[2] = delta_x[2] + nom_x[2];
   out_2068083195310390242[3] = delta_x[3] + nom_x[3];
   out_2068083195310390242[4] = delta_x[4] + nom_x[4];
   out_2068083195310390242[5] = delta_x[5] + nom_x[5];
   out_2068083195310390242[6] = delta_x[6] + nom_x[6];
   out_2068083195310390242[7] = delta_x[7] + nom_x[7];
   out_2068083195310390242[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_7749816067910704575) {
   out_7749816067910704575[0] = -nom_x[0] + true_x[0];
   out_7749816067910704575[1] = -nom_x[1] + true_x[1];
   out_7749816067910704575[2] = -nom_x[2] + true_x[2];
   out_7749816067910704575[3] = -nom_x[3] + true_x[3];
   out_7749816067910704575[4] = -nom_x[4] + true_x[4];
   out_7749816067910704575[5] = -nom_x[5] + true_x[5];
   out_7749816067910704575[6] = -nom_x[6] + true_x[6];
   out_7749816067910704575[7] = -nom_x[7] + true_x[7];
   out_7749816067910704575[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_3649779414745672103) {
   out_3649779414745672103[0] = 1.0;
   out_3649779414745672103[1] = 0.0;
   out_3649779414745672103[2] = 0.0;
   out_3649779414745672103[3] = 0.0;
   out_3649779414745672103[4] = 0.0;
   out_3649779414745672103[5] = 0.0;
   out_3649779414745672103[6] = 0.0;
   out_3649779414745672103[7] = 0.0;
   out_3649779414745672103[8] = 0.0;
   out_3649779414745672103[9] = 0.0;
   out_3649779414745672103[10] = 1.0;
   out_3649779414745672103[11] = 0.0;
   out_3649779414745672103[12] = 0.0;
   out_3649779414745672103[13] = 0.0;
   out_3649779414745672103[14] = 0.0;
   out_3649779414745672103[15] = 0.0;
   out_3649779414745672103[16] = 0.0;
   out_3649779414745672103[17] = 0.0;
   out_3649779414745672103[18] = 0.0;
   out_3649779414745672103[19] = 0.0;
   out_3649779414745672103[20] = 1.0;
   out_3649779414745672103[21] = 0.0;
   out_3649779414745672103[22] = 0.0;
   out_3649779414745672103[23] = 0.0;
   out_3649779414745672103[24] = 0.0;
   out_3649779414745672103[25] = 0.0;
   out_3649779414745672103[26] = 0.0;
   out_3649779414745672103[27] = 0.0;
   out_3649779414745672103[28] = 0.0;
   out_3649779414745672103[29] = 0.0;
   out_3649779414745672103[30] = 1.0;
   out_3649779414745672103[31] = 0.0;
   out_3649779414745672103[32] = 0.0;
   out_3649779414745672103[33] = 0.0;
   out_3649779414745672103[34] = 0.0;
   out_3649779414745672103[35] = 0.0;
   out_3649779414745672103[36] = 0.0;
   out_3649779414745672103[37] = 0.0;
   out_3649779414745672103[38] = 0.0;
   out_3649779414745672103[39] = 0.0;
   out_3649779414745672103[40] = 1.0;
   out_3649779414745672103[41] = 0.0;
   out_3649779414745672103[42] = 0.0;
   out_3649779414745672103[43] = 0.0;
   out_3649779414745672103[44] = 0.0;
   out_3649779414745672103[45] = 0.0;
   out_3649779414745672103[46] = 0.0;
   out_3649779414745672103[47] = 0.0;
   out_3649779414745672103[48] = 0.0;
   out_3649779414745672103[49] = 0.0;
   out_3649779414745672103[50] = 1.0;
   out_3649779414745672103[51] = 0.0;
   out_3649779414745672103[52] = 0.0;
   out_3649779414745672103[53] = 0.0;
   out_3649779414745672103[54] = 0.0;
   out_3649779414745672103[55] = 0.0;
   out_3649779414745672103[56] = 0.0;
   out_3649779414745672103[57] = 0.0;
   out_3649779414745672103[58] = 0.0;
   out_3649779414745672103[59] = 0.0;
   out_3649779414745672103[60] = 1.0;
   out_3649779414745672103[61] = 0.0;
   out_3649779414745672103[62] = 0.0;
   out_3649779414745672103[63] = 0.0;
   out_3649779414745672103[64] = 0.0;
   out_3649779414745672103[65] = 0.0;
   out_3649779414745672103[66] = 0.0;
   out_3649779414745672103[67] = 0.0;
   out_3649779414745672103[68] = 0.0;
   out_3649779414745672103[69] = 0.0;
   out_3649779414745672103[70] = 1.0;
   out_3649779414745672103[71] = 0.0;
   out_3649779414745672103[72] = 0.0;
   out_3649779414745672103[73] = 0.0;
   out_3649779414745672103[74] = 0.0;
   out_3649779414745672103[75] = 0.0;
   out_3649779414745672103[76] = 0.0;
   out_3649779414745672103[77] = 0.0;
   out_3649779414745672103[78] = 0.0;
   out_3649779414745672103[79] = 0.0;
   out_3649779414745672103[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_1056771187663311893) {
   out_1056771187663311893[0] = state[0];
   out_1056771187663311893[1] = state[1];
   out_1056771187663311893[2] = state[2];
   out_1056771187663311893[3] = state[3];
   out_1056771187663311893[4] = state[4];
   out_1056771187663311893[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8100000000000005*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_1056771187663311893[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_1056771187663311893[7] = state[7];
   out_1056771187663311893[8] = state[8];
}
void F_fun(double *state, double dt, double *out_4304917159562798668) {
   out_4304917159562798668[0] = 1;
   out_4304917159562798668[1] = 0;
   out_4304917159562798668[2] = 0;
   out_4304917159562798668[3] = 0;
   out_4304917159562798668[4] = 0;
   out_4304917159562798668[5] = 0;
   out_4304917159562798668[6] = 0;
   out_4304917159562798668[7] = 0;
   out_4304917159562798668[8] = 0;
   out_4304917159562798668[9] = 0;
   out_4304917159562798668[10] = 1;
   out_4304917159562798668[11] = 0;
   out_4304917159562798668[12] = 0;
   out_4304917159562798668[13] = 0;
   out_4304917159562798668[14] = 0;
   out_4304917159562798668[15] = 0;
   out_4304917159562798668[16] = 0;
   out_4304917159562798668[17] = 0;
   out_4304917159562798668[18] = 0;
   out_4304917159562798668[19] = 0;
   out_4304917159562798668[20] = 1;
   out_4304917159562798668[21] = 0;
   out_4304917159562798668[22] = 0;
   out_4304917159562798668[23] = 0;
   out_4304917159562798668[24] = 0;
   out_4304917159562798668[25] = 0;
   out_4304917159562798668[26] = 0;
   out_4304917159562798668[27] = 0;
   out_4304917159562798668[28] = 0;
   out_4304917159562798668[29] = 0;
   out_4304917159562798668[30] = 1;
   out_4304917159562798668[31] = 0;
   out_4304917159562798668[32] = 0;
   out_4304917159562798668[33] = 0;
   out_4304917159562798668[34] = 0;
   out_4304917159562798668[35] = 0;
   out_4304917159562798668[36] = 0;
   out_4304917159562798668[37] = 0;
   out_4304917159562798668[38] = 0;
   out_4304917159562798668[39] = 0;
   out_4304917159562798668[40] = 1;
   out_4304917159562798668[41] = 0;
   out_4304917159562798668[42] = 0;
   out_4304917159562798668[43] = 0;
   out_4304917159562798668[44] = 0;
   out_4304917159562798668[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_4304917159562798668[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_4304917159562798668[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_4304917159562798668[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_4304917159562798668[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_4304917159562798668[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_4304917159562798668[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_4304917159562798668[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_4304917159562798668[53] = -9.8100000000000005*dt;
   out_4304917159562798668[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_4304917159562798668[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_4304917159562798668[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4304917159562798668[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4304917159562798668[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_4304917159562798668[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_4304917159562798668[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_4304917159562798668[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_4304917159562798668[62] = 0;
   out_4304917159562798668[63] = 0;
   out_4304917159562798668[64] = 0;
   out_4304917159562798668[65] = 0;
   out_4304917159562798668[66] = 0;
   out_4304917159562798668[67] = 0;
   out_4304917159562798668[68] = 0;
   out_4304917159562798668[69] = 0;
   out_4304917159562798668[70] = 1;
   out_4304917159562798668[71] = 0;
   out_4304917159562798668[72] = 0;
   out_4304917159562798668[73] = 0;
   out_4304917159562798668[74] = 0;
   out_4304917159562798668[75] = 0;
   out_4304917159562798668[76] = 0;
   out_4304917159562798668[77] = 0;
   out_4304917159562798668[78] = 0;
   out_4304917159562798668[79] = 0;
   out_4304917159562798668[80] = 1;
}
void h_25(double *state, double *unused, double *out_1929353718823255889) {
   out_1929353718823255889[0] = state[6];
}
void H_25(double *state, double *unused, double *out_664622124210071326) {
   out_664622124210071326[0] = 0;
   out_664622124210071326[1] = 0;
   out_664622124210071326[2] = 0;
   out_664622124210071326[3] = 0;
   out_664622124210071326[4] = 0;
   out_664622124210071326[5] = 0;
   out_664622124210071326[6] = 1;
   out_664622124210071326[7] = 0;
   out_664622124210071326[8] = 0;
}
void h_24(double *state, double *unused, double *out_690260471304749903) {
   out_690260471304749903[0] = state[4];
   out_690260471304749903[1] = state[5];
}
void H_24(double *state, double *unused, double *out_5938116407123083920) {
   out_5938116407123083920[0] = 0;
   out_5938116407123083920[1] = 0;
   out_5938116407123083920[2] = 0;
   out_5938116407123083920[3] = 0;
   out_5938116407123083920[4] = 1;
   out_5938116407123083920[5] = 0;
   out_5938116407123083920[6] = 0;
   out_5938116407123083920[7] = 0;
   out_5938116407123083920[8] = 0;
   out_5938116407123083920[9] = 0;
   out_5938116407123083920[10] = 0;
   out_5938116407123083920[11] = 0;
   out_5938116407123083920[12] = 0;
   out_5938116407123083920[13] = 0;
   out_5938116407123083920[14] = 1;
   out_5938116407123083920[15] = 0;
   out_5938116407123083920[16] = 0;
   out_5938116407123083920[17] = 0;
}
void h_30(double *state, double *unused, double *out_5566803247077278239) {
   out_5566803247077278239[0] = state[4];
}
void H_30(double *state, double *unused, double *out_3182955082717319953) {
   out_3182955082717319953[0] = 0;
   out_3182955082717319953[1] = 0;
   out_3182955082717319953[2] = 0;
   out_3182955082717319953[3] = 0;
   out_3182955082717319953[4] = 1;
   out_3182955082717319953[5] = 0;
   out_3182955082717319953[6] = 0;
   out_3182955082717319953[7] = 0;
   out_3182955082717319953[8] = 0;
}
void h_26(double *state, double *unused, double *out_6510313099978940674) {
   out_6510313099978940674[0] = state[7];
}
void H_26(double *state, double *unused, double *out_3076881194663984898) {
   out_3076881194663984898[0] = 0;
   out_3076881194663984898[1] = 0;
   out_3076881194663984898[2] = 0;
   out_3076881194663984898[3] = 0;
   out_3076881194663984898[4] = 0;
   out_3076881194663984898[5] = 0;
   out_3076881194663984898[6] = 0;
   out_3076881194663984898[7] = 1;
   out_3076881194663984898[8] = 0;
}
void h_27(double *state, double *unused, double *out_1107432332621076796) {
   out_1107432332621076796[0] = state[3];
}
void H_27(double *state, double *unused, double *out_1639480134733593655) {
   out_1639480134733593655[0] = 0;
   out_1639480134733593655[1] = 0;
   out_1639480134733593655[2] = 0;
   out_1639480134733593655[3] = 1;
   out_1639480134733593655[4] = 0;
   out_1639480134733593655[5] = 0;
   out_1639480134733593655[6] = 0;
   out_1639480134733593655[7] = 0;
   out_1639480134733593655[8] = 0;
}
void h_29(double *state, double *unused, double *out_7878267558971427732) {
   out_7878267558971427732[0] = state[1];
}
void H_29(double *state, double *unused, double *out_3352842861603144688) {
   out_3352842861603144688[0] = 0;
   out_3352842861603144688[1] = 1;
   out_3352842861603144688[2] = 0;
   out_3352842861603144688[3] = 0;
   out_3352842861603144688[4] = 0;
   out_3352842861603144688[5] = 0;
   out_3352842861603144688[6] = 0;
   out_3352842861603144688[7] = 0;
   out_3352842861603144688[8] = 0;
}
void h_28(double *state, double *unused, double *out_504116447944599279) {
   out_504116447944599279[0] = state[0];
}
void H_28(double *state, double *unused, double *out_1389212590037818437) {
   out_1389212590037818437[0] = 1;
   out_1389212590037818437[1] = 0;
   out_1389212590037818437[2] = 0;
   out_1389212590037818437[3] = 0;
   out_1389212590037818437[4] = 0;
   out_1389212590037818437[5] = 0;
   out_1389212590037818437[6] = 0;
   out_1389212590037818437[7] = 0;
   out_1389212590037818437[8] = 0;
}
void h_31(double *state, double *unused, double *out_9056831590637407402) {
   out_9056831590637407402[0] = state[8];
}
void H_31(double *state, double *unused, double *out_3703089296897336374) {
   out_3703089296897336374[0] = 0;
   out_3703089296897336374[1] = 0;
   out_3703089296897336374[2] = 0;
   out_3703089296897336374[3] = 0;
   out_3703089296897336374[4] = 0;
   out_3703089296897336374[5] = 0;
   out_3703089296897336374[6] = 0;
   out_3703089296897336374[7] = 0;
   out_3703089296897336374[8] = 1;
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

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_2068083195310390242) {
  err_fun(nom_x, delta_x, out_2068083195310390242);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_7749816067910704575) {
  inv_err_fun(nom_x, true_x, out_7749816067910704575);
}
void car_H_mod_fun(double *state, double *out_3649779414745672103) {
  H_mod_fun(state, out_3649779414745672103);
}
void car_f_fun(double *state, double dt, double *out_1056771187663311893) {
  f_fun(state,  dt, out_1056771187663311893);
}
void car_F_fun(double *state, double dt, double *out_4304917159562798668) {
  F_fun(state,  dt, out_4304917159562798668);
}
void car_h_25(double *state, double *unused, double *out_1929353718823255889) {
  h_25(state, unused, out_1929353718823255889);
}
void car_H_25(double *state, double *unused, double *out_664622124210071326) {
  H_25(state, unused, out_664622124210071326);
}
void car_h_24(double *state, double *unused, double *out_690260471304749903) {
  h_24(state, unused, out_690260471304749903);
}
void car_H_24(double *state, double *unused, double *out_5938116407123083920) {
  H_24(state, unused, out_5938116407123083920);
}
void car_h_30(double *state, double *unused, double *out_5566803247077278239) {
  h_30(state, unused, out_5566803247077278239);
}
void car_H_30(double *state, double *unused, double *out_3182955082717319953) {
  H_30(state, unused, out_3182955082717319953);
}
void car_h_26(double *state, double *unused, double *out_6510313099978940674) {
  h_26(state, unused, out_6510313099978940674);
}
void car_H_26(double *state, double *unused, double *out_3076881194663984898) {
  H_26(state, unused, out_3076881194663984898);
}
void car_h_27(double *state, double *unused, double *out_1107432332621076796) {
  h_27(state, unused, out_1107432332621076796);
}
void car_H_27(double *state, double *unused, double *out_1639480134733593655) {
  H_27(state, unused, out_1639480134733593655);
}
void car_h_29(double *state, double *unused, double *out_7878267558971427732) {
  h_29(state, unused, out_7878267558971427732);
}
void car_H_29(double *state, double *unused, double *out_3352842861603144688) {
  H_29(state, unused, out_3352842861603144688);
}
void car_h_28(double *state, double *unused, double *out_504116447944599279) {
  h_28(state, unused, out_504116447944599279);
}
void car_H_28(double *state, double *unused, double *out_1389212590037818437) {
  H_28(state, unused, out_1389212590037818437);
}
void car_h_31(double *state, double *unused, double *out_9056831590637407402) {
  h_31(state, unused, out_9056831590637407402);
}
void car_H_31(double *state, double *unused, double *out_3703089296897336374) {
  H_31(state, unused, out_3703089296897336374);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
