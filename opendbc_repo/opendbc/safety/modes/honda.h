#pragma once

#include "opendbc/safety/declarations.h"
#include "opendbc/safety/modes/honda_interceptor.h"
#include "opendbc/safety/modes/honda_stock_aol.h"

// All common address checks except SCM_BUTTONS which isn't on one Nidec safety configuration
#define HONDA_COMMON_NO_SCM_FEEDBACK_RX_CHECKS(pt_bus)                                                                                      \
  {.msg = {{0x1A6, (pt_bus), 8, 25U, .max_counter = 3U, .ignore_quality_flag = true},                  /* SCM_BUTTONS */       \
           {0x296, (pt_bus), 4, 25U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }}},                                 \
  {.msg = {{0x158, (pt_bus), 8, 100U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  /* ENGINE_DATA */      \
  {.msg = {{0x17C, (pt_bus), 8, 100U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  /* POWERTRAIN_DATA */  \

#define HONDA_COMMON_RX_CHECKS(pt_bus)                                                                                                  \
  HONDA_COMMON_NO_SCM_FEEDBACK_RX_CHECKS(pt_bus)                                                                                        \
  {.msg = {{0x326, (pt_bus), 8, 10U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  /* SCM_FEEDBACK */  \

// Alternate brake message is used on some Honda Bosch, and Honda Bosch radarless (where PT bus is 0)
#define HONDA_ALT_BRAKE_ADDR_CHECK(pt_bus)                                                                                              \
  {.msg = {{0x1BE, (pt_bus), 3, 50U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  /* BRAKE_MODULE */  \

enum {
  HONDA_BTN_NONE = 0,
  HONDA_BTN_MAIN = 1,
  HONDA_BTN_CANCEL = 2,
  HONDA_BTN_SET = 3,
  HONDA_BTN_RESUME = 4,
};

static int honda_brake = 0;
static bool honda_brake_switch_prev = false;
static bool honda_alt_brake_msg = false;
static bool honda_fwd_brake = false;
static bool honda_bosch_long = false;
static bool honda_bosch_radarless = false;
static bool honda_bosch_canfd = false;
static bool honda_mvl_stock = false;
static uint8_t honda_mvl_buttons_fresh = 0U;
static bool honda_rdx_high_gas = false;
static bool aol_honda_bosch_long = false;
// Legacy and source-bound Honda owners are mutually exclusive. Both require
// the same physical MAIN timestamp, so retain a single storage location.
#define aol_honda_main_ts honda_stock_aol_main_ts
#define AOL_HONDA_MAIN_TIMEOUT_US 300000U
typedef enum {HONDA_NIDEC, HONDA_BOSCH} HondaHw;
static HondaHw honda_hw = HONDA_NIDEC;

static void aol_honda_reset(void) {
  aol_honda_bosch_long = false;
  aol_honda_main_ts = 0U;
}

static uint8_t aol_honda_request_mask(void) {
  return (heartbeat_engaged && !relay_malfunction && !safety_rx_checks_invalid &&
          (safety_get_ts_elapsed(microsecond_timer_get(), aol_host_request_ts) <= AOL_HOST_REQUEST_TIMEOUT_US)) ?
         aol_host_axis_mask : 0U;
}

static uint8_t aol_honda_permission_mask(void) {
  const bool main_current = acc_main_on &&
    (safety_get_ts_elapsed(microsecond_timer_get(), aol_honda_main_ts) <= AOL_HONDA_MAIN_TIMEOUT_US);
  uint8_t permission = 0U;
  if (main_current && aol_rx_healthy()) {
    const uint8_t request = aol_get_request_mask();
    permission = request & 0x1U;
    if (controls_allowed && ((request & 0x2U) != 0U)) {
      permission |= 0x2U;
    }
  }
  return permission;
}

static unsigned int honda_get_pt_bus(void) {
  return ((honda_hw == HONDA_BOSCH) && !honda_bosch_radarless && !honda_bosch_canfd) ? 1U : 0U;
}

static uint32_t honda_get_checksum(const CANPacket_t *msg) {
  int checksum_byte = GET_LEN(msg) - 1U;
  return (uint8_t)(msg->data[checksum_byte]) & 0xFU;
}

static uint32_t honda_compute_checksum(const CANPacket_t *msg) {
  int len = GET_LEN(msg);
  uint8_t checksum = 0U;
  unsigned int addr = msg->addr;
  while (addr > 0U) {
    checksum += (uint8_t)(addr & 0xFU); addr >>= 4;
  }
  for (int j = 0; j < len; j++) {
    uint8_t byte = msg->data[j];
    checksum += (uint8_t)(byte & 0xFU) + (byte >> 4U);
    if (j == (len - 1)) {
      checksum -= (byte & 0xFU);  // remove checksum in message
    }
  }
  return (uint8_t)((8U - checksum) & 0xFU);
}

static uint8_t honda_get_counter(const CANPacket_t *msg) {
  int counter_byte = GET_LEN(msg) - 1U;
  return (msg->data[counter_byte] >> 4U) & 0x3U;
}

// Nidec BRAKE_COMMAND (0x1FA) carries the brake in COMPUTER_BRAKE (bytes 0-1), except on Nidec hybrids
// (Clarity), whose brake module reads COMPUTER_BRAKE_HYBRID (bytes 6-7). Nothing else occupies those hybrid bits, so a
// non-hybrid leaves them 0 and the larger of the two is the brake the car will apply, with no hybrid safety param.
static int honda_nidec_brake(const CANPacket_t *msg) {
  int brake = (msg->data[0] << 2) + ((msg->data[1] >> 6) & 0x3U);
  int brake_hybrid = (msg->data[6] << 2) + ((msg->data[7] >> 6) & 0x3U);
  return SAFETY_MAX(brake, brake_hybrid);
}

// Clarity angle-mode EPS (safety param HONDA_PARAM_ANGLE, Nidec only). The modified EPS firmware reads 0xE4 bytes 0-1
// as a steering-wheel angle target, in the units of its own STEERING_SENSORS (0x14A) STEER_ANGLE (0.1 deg, same sign),
// when byte 2 bit 7 (request) and bit 5 (angle payload) are both set; byte 3 bits 7:4 cut the loop's authority
// (15 = none; only reduces, not checked). A target of 0 steers to centre, so the torque rule "bytes 0-1 must be 0" does
// not protect an angle car.
// Rules: the standard vehicle-model angle rule of the other angle brands (steer_angle_cmd_checks_vm: 3.6 m/s^2 lateral
// accel, 3.6 m/s^3 lateral jerk, at speed - 1 m/s, last target reset to the measured angle after a violation or while
// not steering), with the angle for a lateral acceleration taken from the EPS's own clamp table (angle_ref AMAX, which
// matches the car: v x yaw rate / table accel = 1.02) instead of a bicycle model, plus Honda's frame format:
//  - lateral not allowed, or request and payload not both set: bytes 0-1, request and payload must all be 0
//  - steering needs a measured angle (0x14A, an RX check in this mode) no older than 50 ms
//  - |target| <= the 3.6 m/s^2 angle: 0.9 x the EPS 4.0 m/s^2 table, extended as 1/v^2 below 5 and above 30 m/s,
//    capped at 500 deg. No exemptions.
//  - per-frame step <= the angle the jerk limit allows in 10 ms: with jerk = accel = 3.6, that is the 3.6 m/s^2 angle
//    per second (31.8 deg/s at 20 m/s), and never more than the EPS's own jump threshold
//  - the first target after not steering or after a blocked frame is within one step of the measured angle (any of
//    the last 6 0x14A samples when that target is checked)
// Evidence: rwd-xray lab/clarity/PANDA_ANGLE_SAFETY_20261121 (re-simulated sender on the owner's drives, closed loop).
// Linear-angle EPS (build 0x0C on, rwd-xray lab/clarity/CLARITY_ANGLE_MODE_0x0C_20261122): the target is the rack-linear
// angle the EPS publishes on 0x6A2 bytes 0-1 (raw angle minus reference, before the firmware VGR map; same 0.1 deg units
// and sign). The first valid 0x6A2 (checksum, counter) latches linear mode until the next safety init: from then on the
// measured angle is 0x6A2's (0x14A no longer feeds it), a stale 0x6A2 (> 50 ms) blocks steering exactly as a stale 0x14A
// does, and the limits are the same physical limits in linear units (the 3.6 m/s^2 published angle converted through the
// firmware map at the EPS clamp table's knots, rwd-xray gen_linear_limit.py; the EPS clamp is never tighter). A build
// without 0x6A2 (0x0B) keeps the 0x14A rule above unchanged.
// Angle profiles (param bits 15:13, the fleet's 0x0C linear-angle EPS builds): profile 0 is the Clarity rule above.
// Profile 1..7 is one platform's row in HONDA_ANGLE_VM_PARAMS, on Nidec or Bosch: same 0xE4 frame and rules, linear from
// the start, 0x6A2 on the powertrain bus is the RX check and the only measured angle (0x14A and 0x156 never feed it).
// The linear unit is steering-wheel degrees at the on-center ratio, so the 3.6 m/s^2 angle is the standard vehicle model
// at that ratio (each EPS's own clamp is never tighter). A profile without a row never steers.
#define HONDA_PARAM_ANGLE 4096U
#define HONDA_ANGLE_MEAS_TIMEOUT_US 50000U
#define HONDA_ANGLE_MAX 5000  // 0.1 deg
#define HONDA_ANGLE_MAX_LINEAR 5784  // 0.1 deg: the 500 deg published cap in linear units
#define HONDA_PARAM_ANGLE_PROFILE_SHIFT 13U
#define HONDA_PARAM_ANGLE_PROFILE_MASK 0xE000U  // bits 15:13
static uint16_t honda_angle_profile = 0U;   // 0: Clarity rule; 1..7: a vehicle-model row (linear-angle EPS)
#define HONDA_ANGLE_PROFILE_NONE 8U  // angle mode on Bosch without a profile: no row, never steers
static bool honda_angle_mode = false;
static int honda_angle_last = 0;
static bool honda_angle_from_wheel = true;   // the next target's step is measured from the wheel, not the last target
static bool honda_angle_meas_seen = false;
static uint32_t honda_angle_meas_ts = 0U;
static bool honda_angle_linear = false;     // a valid 0x6A2 seen: target and measured angle are rack-linear
static int honda_angle_linear_counter = -1;  // last 0x6A2 counter (-1: none yet)

static void honda_angle_reset(bool enabled) {
  honda_angle_mode = enabled;
  honda_angle_last = 0;
  honda_angle_from_wheel = true;
  honda_angle_meas_seen = false;
  honda_angle_meas_ts = 0U;
  honda_angle_linear = false;
  honda_angle_linear_counter = -1;
}

static float honda_angle_interp(const float *xs, const float *ys, int n, float x) {
  float ret = ys[n - 1];
  if (x <= xs[0]) {
    ret = ys[0];
  } else {
    for (int i = 0; i < (n - 1); i++) {
      if (x < xs[i + 1]) {
        ret = ys[i] + ((ys[i + 1] - ys[i]) * (x - xs[i]) / (xs[i + 1] - xs[i]));
        break;
      }
    }
  }
  return ret;
}

// the 3.6 m/s^2 steering-wheel angle at speed (m/s, >= 1), 0.1 deg
static float honda_angle_accel_limit(float speed) {
  static const float V[8] = {5., 8., 10., 12., 16., 20., 25., 30.};
  static const float LIM[8] = {3411., 1440., 981., 722.7, 450., 317.7, 231.3, 183.6};  // 0.9 x angle_ref AMAX
  float lim;
  if (speed < V[0]) {
    lim = LIM[0] * (V[0] * V[0]) / (speed * speed);
  } else if (speed > V[7]) {
    lim = LIM[7] * (V[7] * V[7]) / (speed * speed);
  } else {
    lim = honda_angle_interp(V, LIM, 8, speed);
  }
  return SAFETY_MIN(lim, (float)HONDA_ANGLE_MAX);
}

// the 3.6 m/s^2 angle in the linear units of a linear-angle EPS (speed m/s, >= 1), 0.1 deg; 1/v^2 above 80 m/s
static float honda_angle_accel_limit_linear(float speed) {
  static const float LV[21] = {1.0f, 4.13f, 4.25f, 4.5f, 4.75f, 5.0f, 8.0f, 10.0f, 12.0f, 16.0f, 20.0f, 25.0f, 30.0f,
                               32.5f, 35.0f, 37.5f, 40.0f, 45.0f, 50.0f, 60.0f, 80.0f};
  static const float LLIM[21] = {5783.6f, 5783.0f, 5461.0f, 4863.4f, 4342.0f, 3901.1f, 1566.1f, 1026.5f, 736.3f,
                                 449.1f, 314.7f, 228.5f, 181.5f, 154.5f, 133.5f, 116.4f, 102.2f, 80.5f, 65.2f, 45.3f, 25.6f};
  // car-to-car spread (owner 11-23): the table fits the owner's car (1295 segments); a second Clarity (one highway route)
  // understeers less, so the table is scaled by the two cars' measured ratio at the cautious end:
  // (1 + 0.00049 v^2) / (1 + 0.00062 v^2), i.e. -7.5 % at 30 m/s, -4 % at 20, -1 % at 10, ~0 at parking speeds
  const float spread = (1.0f + (0.00049f * speed * speed)) / (1.0f + (0.00062f * speed * speed));
  float lim;
  if (speed > LV[20]) {
    lim = LLIM[20] * (LV[20] * LV[20]) / (speed * speed);
  } else {
    lim = honda_angle_interp(LV, LLIM, 21, speed);
  }
  return SAFETY_MIN(lim * spread, (float)HONDA_ANGLE_MAX_LINEAR);
}

// the angle profiles' vehicle models (index = profile - 1), the same rows as opendbc car/honda/angle_profiles.py
static const AngleSteeringParams HONDA_ANGLE_VM_PARAMS[] = {
  // measured on-center SR and understeer per platform, cautious side (angle_profiles.py); a platform shares a row only
  // when its limit stays within 0.90-1.00 of its own model (test_angle_profiles.py)
  {.slip_factor = -0.000782, .steer_ratio = 16.28, .wheelbase = 2.66},  // 1: HONDA_CRV_5G; ACURA_RDX_3G, HONDA_INSIGHT
  {.slip_factor = -0.000448, .steer_ratio = 14.99, .wheelbase = 2.70},  // 2: HONDA_CIVIC (Nidec)
  {.slip_factor = -0.000638, .steer_ratio = 16.0, .wheelbase = 2.70},   // 3: HONDA_CIVIC_BOSCH
  {.slip_factor = -0.00035, .steer_ratio = 17.81, .wheelbase = 3.00},   // 4: HONDA_ODYSSEY
  {.slip_factor = -0.00075, .steer_ratio = 18.01, .wheelbase = 3.18},   // 5: HONDA_RIDGELINE
  {.slip_factor = -0.001329, .steer_ratio = 17.47, .wheelbase = 2.82},  // 6: HONDA_PILOT
  {.slip_factor = -0.000973, .steer_ratio = 17.0, .wheelbase = 2.53},   // 7: HONDA_FIT
};
#define HONDA_ANGLE_VM_PROFILES (sizeof(HONDA_ANGLE_VM_PARAMS) / sizeof(HONDA_ANGLE_VM_PARAMS[0]))

// a vehicle-model profile with a row
static bool honda_angle_vm_valid(void) {
  return (honda_angle_profile >= 1U) && (honda_angle_profile <= HONDA_ANGLE_VM_PROFILES);
}

// a vehicle-model profile: the 3.6 m/s^2 angle, 0.1 deg (speed m/s, >= 1); 0 without a row
static float honda_angle_accel_limit_vm(float speed) {
  float lim = 0.0f;
  if (honda_angle_vm_valid()) {
    const AngleSteeringParams params = HONDA_ANGLE_VM_PARAMS[honda_angle_profile - 1U];
    const float max_accel = ISO_LATERAL_ACCEL + (EARTH_G * AVERAGE_ROAD_ROLL);  // ~3.6 m/s^2
    const float curvature_factor = get_curvature_factor(speed, params);
    lim = get_angle_from_curvature(max_accel / (speed * speed), curvature_factor, params) * 10.0f;
  }
  return SAFETY_MIN(lim, (float)HONDA_ANGLE_MAX_LINEAR);
}

// a rack-linear sample (0x6A2 bytes 0-1): the first one latches linear mode and restarts the window with linear samples only
static void honda_angle_linear_sample(const CANPacket_t *msg) {
  const int lin = to_signed((msg->data[0] << 8) | msg->data[1], 16);
  if (!honda_angle_linear) {
    honda_angle_linear = true;
    for (int i = 0; i < 6; i++) {
      update_sample(&angle_meas, lin);
    }
  } else {
    update_sample(&angle_meas, lin);
  }
  honda_angle_meas_seen = true;
  honda_angle_meas_ts = microsecond_timer_get();
}

static void honda_angle_rx(const CANPacket_t *msg, unsigned int pt_bus) {
  if (honda_angle_mode && (msg->bus == pt_bus)) {
    if (msg->addr == 0x158U) {
      UPDATE_VEHICLE_SPEED(((msg->data[0] << 8) | msg->data[1]) * 0.01 / 3.6);  // XMISSION_SPEED, 0.01 kph
    }
    if ((msg->addr == 0x6A2U) && (honda_angle_profile != 0U)) {  // the RX check of a profile: checksum and counter already verified
      honda_angle_linear_sample(msg);
    }
    if ((msg->addr == 0x14AU) && (honda_angle_profile == 0U) && !honda_angle_linear) {  // an RX check in angle mode: checksum, counter and rate already verified
      update_sample(&angle_meas, to_signed((msg->data[0] << 8) | msg->data[1], 16));
      honda_angle_meas_seen = true;
      honda_angle_meas_ts = microsecond_timer_get();
    }
  }
}

// EPS_LINEAR_ANGLE (0x6A2) is not an RX check (a 0x0B EPS never sends it), so it arrives through the optional ingress
// hook; it can only latch linear mode and feed the measured angle, never satisfy a required check.
static void honda_angle_optional_rx(const CANPacket_t *msg) {
  if (honda_angle_mode && (msg->bus == honda_get_pt_bus())) {
    if ((msg->addr == 0x6A2U) && (GET_LEN(msg) == 8U) && (honda_compute_checksum(msg) == honda_get_checksum(msg))) {
      const int counter = (int)honda_get_counter(msg);
      const bool in_sequence = (honda_angle_linear_counter < 0) || (counter == ((honda_angle_linear_counter + 1) & 3));
      honda_angle_linear_counter = counter;
      if (in_sequence) {  // EPS_LINEAR_ANGLE: bytes 0-1 the rack-linear angle
        honda_angle_linear_sample(msg);
      }
    }
  }
}

static bool honda_angle_tx_violation(const CANPacket_t *msg) {
  static const float V[9] = {0., 5., 8., 10., 12., 15., 20., 25., 30.};
  static const float JUMP[9] = {40., 40., 31., 25., 19., 10., 10., 10., 10.};          // EPS jump threshold, 0.1 deg per frame
  const int target = to_signed((msg->data[0] << 8) | msg->data[1], 16);
  const bool request = GET_BIT(msg, 23U);
  const bool payload = GET_BIT(msg, 21U);
  const bool steering = request && payload;
  bool violation = false;

  if (!lateral_controls_allowed() || !steering) {
    violation = (target != 0) || request || payload;
  } else {
    // fudge the speed down 1 m/s: both limits only widen as speed falls
    const float speed = SAFETY_MAX(((float)vehicle_speed.min / VEHICLE_SPEED_FACTOR) - 1.0f, 1.0f);
    const bool meas_fresh = honda_angle_meas_seen &&
      (safety_get_ts_elapsed(microsecond_timer_get(), honda_angle_meas_ts) <= HONDA_ANGLE_MEAS_TIMEOUT_US);
    float lim = honda_angle_accel_limit(speed);
    if (honda_angle_profile != 0U) {
      lim = honda_angle_accel_limit_vm(speed);
    } else if (honda_angle_linear) {
      lim = honda_angle_accel_limit_linear(speed);
    } else {
      // Nidec 0x14A rule: the published-angle table above
    }
    const int angle_max = (honda_angle_linear || (honda_angle_profile != 0U)) ? HONDA_ANGLE_MAX_LINEAR : HONDA_ANGLE_MAX;
    // jerk limit: with lateral jerk = lateral accel = 3.6, the angle rate is the accel angle per second (100 Hz frames)
    const float step = SAFETY_MIN(lim / 100.0f, honda_angle_interp(V, JUMP, 9, speed));
    const int step_can = (int)(step + 1.0f);
    const int lim_can = (int)(lim + 1.0f);
    // from the wheel: within one step of the last 6 measured samples (the standard's inactive check uses the same
    // min/max window; openpilot's carState angle is 10-20 ms older than the newest 0x14A); otherwise of the last target
    const int hi = honda_angle_from_wheel ? SAFETY_CLAMP(angle_meas.max, -angle_max, angle_max) : honda_angle_last;
    const int lo = honda_angle_from_wheel ? SAFETY_CLAMP(angle_meas.min, -angle_max, angle_max) : honda_angle_last;
    violation = !meas_fresh;
    violation |= (honda_angle_profile != 0U) && !honda_angle_vm_valid();
    violation |= safety_max_limit_check(target, hi + step_can, lo - step_can);
    violation |= safety_max_limit_check(target, lim_can, -lim_can);
  }
  honda_angle_last = target;
  // not steering, or a violation: the next target must be within one step of the wheel, measured when it is checked
  // (the standard resets the last target to the measured angle here; checking against the samples current at the next
  // frame follows a wheel that moves in between)
  honda_angle_from_wheel = violation || !lateral_controls_allowed() || !steering;
  return violation;
}

static void honda_rx_hook(const CANPacket_t *msg) {
  const bool pcm_cruise = ((honda_hw == HONDA_BOSCH) && !honda_bosch_long) || ((honda_hw == HONDA_NIDEC) && !honda_interceptor);
  unsigned int pt_bus = honda_get_pt_bus();
  bool normal_engagement = false;

  // sample speed
  if (msg->addr == 0x158U) {
    vehicle_moving = msg->data[0] | msg->data[1];
  }
  honda_angle_rx(msg, pt_bus);

  // check ACC main state
  // 0x326 for all Bosch and some Nidec, 0x1A6 for some Nidec
  if ((!aol_honda_bosch_long && ((msg->addr == 0x326U) || (msg->addr == 0x1A6U))) ||
      (aol_honda_bosch_long && msg_matches(msg, 0x326U, pt_bus, 8U))) {
    acc_main_on = GET_BIT(msg, ((msg->addr == 0x326U) ? 28U : 47U));
    if (aol_honda_bosch_long && (msg->addr == 0x326U)) {
      aol_honda_main_ts = microsecond_timer_get();
    }
    if (!acc_main_on) {
      controls_allowed = false;
      aol_set_host_request(0U);
    }
  }

  // enter controls when PCM enters cruise state
  if (pcm_cruise && (msg->addr == 0x17CU)) {
    const bool cruise_engaged = GET_BIT(msg, 38U);
    // engage on rising edge
    if (cruise_engaged && !cruise_engaged_prev) {
      normal_engagement = !controls_allowed;
      controls_allowed = true;
    }

    // Since some Nidec cars can brake down to 0 after the PCM disengages,
    // we don't disengage when the PCM does.
    if (!cruise_engaged && (honda_hw != HONDA_NIDEC)) {
      controls_allowed = false;
    }
    cruise_engaged_prev = cruise_engaged;
  }

  // state machine to enter and exit controls for button enabling
  // 0x1A6 for the ILX, 0x296 for the Civic Touring
  if ((!aol_honda_bosch_long && (msg_matches(msg, 0x1A6U, pt_bus) || msg_matches(msg, 0x296U, pt_bus))) ||
      (aol_honda_bosch_long && msg_matches(msg, 0x296U, pt_bus, 4U))) {
    if (honda_mvl_stock && msg_matches(msg, 0x296U, pt_bus, 4U) && (honda_mvl_buttons_fresh > 0U)) {
      honda_mvl_buttons_fresh--;
    }
    int button = (msg->data[0] & 0xE0U) >> 5;

    // enter controls on the falling edge of set or resume
    bool set = (button != HONDA_BTN_SET) && (cruise_button_prev == HONDA_BTN_SET);
    bool res = (button != HONDA_BTN_RESUME) && (cruise_button_prev == HONDA_BTN_RESUME);
    if (acc_main_on && !pcm_cruise && (set || res)) {
      normal_engagement = !controls_allowed;
      controls_allowed = true;
    }

    // exit controls once main or cancel are pressed. With stock AOL, CANCEL ends only longitudinal, like the brake:
    // the host's lateral request stands and the AOL token keeps lateral permission. MAIN still withdraws both.
    if ((button == HONDA_BTN_MAIN) || (button == HONDA_BTN_CANCEL)) {
      controls_allowed = false;
      if ((button == HONDA_BTN_CANCEL) && honda_stock_aol_flag(HONDA_STOCK_ENABLED)) {
        // Retain only the existing lateral request without renewing its deadline.
        aol_host_axis_mask &= 1U;
      } else {
        aol_set_host_request(0U);
      }
    }
    cruise_button_prev = button;
  }

  // user brake signal on 0x17C reports applied brake from computer brake on accord
  // and crv, which prevents the usual brake safety from working correctly. these
  // cars have a signal on 0x1BE which only detects user's brake being applied so
  // in these cases, this is used instead.
  // most hondas: 0x17C
  // accord, crv: 0x1BE
  if (honda_alt_brake_msg) {
    if (msg->addr == 0x1BEU) {
      brake_pressed = GET_BIT(msg, 4U);
    }
  } else {
    if (msg->addr == 0x17CU) {
      // also if brake switch is 1 for two CAN frames, as brake pressed is delayed
      const bool brake_switch = GET_BIT(msg, 32U);
      brake_pressed = (GET_BIT(msg, 53U)) || (brake_switch && honda_brake_switch_prev);
      honda_brake_switch_prev = brake_switch;
    }
  }

  honda_interceptor_rx(msg);
  if (!honda_interceptor && (msg->addr == 0x17CU)) {
    gas_pressed = msg->data[0] != 0U;
  }

  // disable stock Honda AEB in alternative experience
  if (!(alternative_experience & ALT_EXP_DISABLE_STOCK_AEB)) {
    if (msg_matches(msg, 0x1FAU, 2U)) {
      bool honda_stock_aeb = GET_BIT(msg, 29U);
      int honda_stock_brake = honda_nidec_brake(msg);

      // Forward AEB when stock braking is higher than openpilot braking
      // only stop forwarding when AEB event is over
      if (!honda_stock_aeb) {
        honda_fwd_brake = false;
      } else if (honda_stock_brake >= honda_brake) {
        honda_fwd_brake = true;
      } else {
        // Leave Honda forward brake as is
      }
    }
  }
  honda_stock_aol_rx(msg, pt_bus, normal_engagement);
}

static bool honda_tx_hook(const CANPacket_t *msg) {
  const LongitudinalLimits HONDA_BOSCH_LONG_LIMITS = {
    .max_accel = 200,   // accel is used for brakes
    .min_accel = -350,

    .max_gas = honda_rdx_high_gas ? 2200 : 2000,
    .inactive_gas = -30000,
  };

  const LongitudinalLimits HONDA_NIDEC_LONG_LIMITS = {
    .max_gas = 198,  // 0xc6
    .max_brake = 255,

    .inactive_speed = 0,
  };

  bool tx = true;

  unsigned int bus_pt = honda_get_pt_bus();
  unsigned int bus_buttons = (honda_bosch_radarless) ? 2U : bus_pt;  // the camera controls ACC on radarless Bosch cars

  // ACC_HUD: safety check (nidec w/o pedal)
  if (msg_matches(msg, 0x30CU, bus_pt)) {
    int pcm_speed = (msg->data[0] << 8) | msg->data[1];
    int pcm_gas = msg->data[2];

    bool violation = false;
    violation |= longitudinal_speed_checks(pcm_speed, HONDA_NIDEC_LONG_LIMITS);
    violation |= longitudinal_gas_checks(pcm_gas, HONDA_NIDEC_LONG_LIMITS);
    if (violation) {
      tx = false;
    }
  }

  // BRAKE: safety check (nidec)
  if (msg_matches(msg, 0x1FAU, bus_pt)) {
    honda_brake = honda_nidec_brake(msg);
    // COMPUTER_BRAKE keeps the Nidec 255. COMPUTER_BRAKE_HYBRID, read only by a hybrid's brake module (Clarity), may
    // reach 320: the stock ACC camera's own ceiling on that field (00000042--6d427003af segs 5/10), where 255 left
    // openpilot's hardest braking at ~-2.7 m/s2 against a -3.5 plan.
    const LongitudinalLimits HONDA_NIDEC_HYBRID_LIMITS = {.max_brake = 320};
    int brake_standard = (msg->data[0] << 2) + ((msg->data[1] >> 6) & 0x3U);
    int brake_hybrid = (msg->data[6] << 2) + ((msg->data[7] >> 6) & 0x3U);
    if (longitudinal_brake_checks(brake_standard, HONDA_NIDEC_LONG_LIMITS) ||
        longitudinal_brake_checks(brake_hybrid, HONDA_NIDEC_HYBRID_LIMITS)) {
      tx = false;
    }
    if (honda_fwd_brake) {
      tx = false;
    }

    // AEB: block all actuation. stock AEB messages are forwarded from the camera instead
    bool aeb_req = GET_BIT(msg, 29U);  // AEB_REQ_1
    int aeb_req_2 = msg->data[3] & 0x7U;  // AEB_REQ_2
    int aeb_status = msg->data[5] & 0x3U;  // AEB_STATUS
    if (aeb_req || (aeb_req_2 != 0) || (aeb_status != 0)) {
      tx = false;
    }
  }

  // BRAKE/GAS: safety check (bosch)
  if (msg_matches(msg, 0x1DFU, bus_pt)) {
    int accel = (msg->data[3] << 3) | ((msg->data[4] >> 5) & 0x7U);
    accel = to_signed(accel, 11);

    int gas = (msg->data[0] << 8) | msg->data[1];
    gas = to_signed(gas, 16);

    bool violation = false;
    violation |= longitudinal_accel_checks(accel, HONDA_BOSCH_LONG_LIMITS);
    violation |= longitudinal_gas_checks(gas, HONDA_BOSCH_LONG_LIMITS);

    // AEB: block all actuation
    violation |= GET_BIT(msg, 33U);  // AEB_STATUS
    violation |= GET_BIT(msg, 43U);  // AEB_PREPARE
    violation |= GET_BIT(msg, 47U);  // AEB_BRAKING
    if (violation) {
      tx = false;
    }
  }

  // ACCEL: safety check (radarless)
  if (msg_matches(msg, 0x1C8U, bus_pt)) {
    int accel = (msg->data[0] << 4) | (msg->data[1] >> 4);
    accel = to_signed(accel, 12);

    bool violation = false;
    violation |= longitudinal_accel_checks(accel, HONDA_BOSCH_LONG_LIMITS);

    // AEB: block all actuation
    violation |= GET_BIT(msg, 33U);  // AEB_STATUS
    violation |= GET_BIT(msg, 43U);  // AEB_PREPARE
    violation |= GET_BIT(msg, 47U);  // AEB_BRAKING
    if (violation) {
      tx = false;
    }
  }

  // STEER: safety check
  if (honda_angle_mode && (msg->addr == 0xE4U)) {
    if (honda_angle_tx_violation(msg)) {
      tx = false;
    }
  } else if ((msg->addr == 0xE4U) || (msg->addr == 0x194U)) {
    if (!lateral_controls_allowed()) {
      bool steer_applied = msg->data[0] | msg->data[1];
      if (steer_applied) {
        tx = false;
      }
    }
  } else {
  }

  // B-CAN turn signal (body BCM): only the exact cancel, or a well-formed start (byte2 must
  // be exactly 0x0F, a fixed control parameter the BCM requires) while a non-zero steering
  // command is permitted (the same condition as the steer check above)
  if (msg_matches(msg, 0x16F118F0U, 0U)) {
    const bool bcan_cancel = (GET_BYTES_64_LE(msg, 0, 8) == 0x0000000000000020ULL);
    const bool bcan_start = (msg->data[0] == 0x30U) &&
                            ((msg->data[1] == 0x0AU) || (msg->data[1] == 0x0BU)) &&
                            (msg->data[2] == 0x0FU) &&
                            (GET_BYTES_64_LE(msg, 3, 5) == 0U);
    if (!bcan_cancel && !((bcan_start) && lateral_controls_allowed())) {
      tx = false;
    }
  }

  // Bosch supplemental control check
  if (msg->addr == 0xE5U) {
    if ((GET_BYTES_64_LE(msg, 0, 8) & 0x00FFFFFFFFFFFFFFULL) != 0x0000000010800004ULL) {
      tx = false;
    }
  }

  // FORCE CANCEL: safety check only relevant when spamming the cancel button in Bosch HW
  // ensuring that only the cancel button press is sent (VAL 2) when controls are off.
  // This avoids unintended engagements while still allowing resume spam
  if ((msg_matches(msg, 0x296U, bus_buttons) || (honda_mvl_stock && msg_matches(msg, 0x296U, 2U, 4U))) && !controls_allowed) {
    if (((msg->data[0] >> 5) & 0x7U) != 2U) {
      tx = false;
    }
  }

  // Only tester present ("\x02\x3E\x80\x00\x00\x00\x00\x00") allowed on diagnostics address
  if (msg->addr == 0x18DAB0F1U) {
    if (GET_BYTES_64_LE(msg, 0, 8) != 0x0000000000803E02ULL) {
      tx = false;
    }
  }

  if (msg->addr == 0x200U) {
    tx = tx && honda_interceptor_tx(msg);
  }

  if (tx && honda_mvl_stock && msg_matches(msg, 0x296U, 2U, 4U)) {
    honda_mvl_buttons_fresh = 10U;
  }
  return tx;
}

static safety_config honda_nidec_init(uint16_t param_raw) {
  // the angle bits are independent of every other Nidec option, so the exact-value checks below see the param without them
  honda_angle_reset(GET_FLAG(param_raw, HONDA_PARAM_ANGLE));
  honda_angle_profile = honda_angle_mode ? ((param_raw & HONDA_PARAM_ANGLE_PROFILE_MASK) >> HONDA_PARAM_ANGLE_PROFILE_SHIFT) : 0U;
  const uint16_t param = param_raw & (uint16_t)~(HONDA_PARAM_ANGLE | HONDA_PARAM_ANGLE_PROFILE_MASK);
  honda_mvl_stock = false;
  honda_mvl_buttons_fresh = 0U;
  // 0x1FA is dynamically forwarded based on stock AEB
  // 0xE4 is steering on all cars except CRV and RDX, 0x194 for CRV and RDX,
  // 0x1FA is brake control, 0x30C is acc hud, 0x33D is lkas hud
  static const CanMsg HONDA_N_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0x194, 0, 4, .check_relay = true},
    {0x1FA, 0, 8, .check_relay = false},
    {0x30C, 0, 8, .check_relay = true},
    {0x33D, 0, 5, .check_relay = true},
  };

  static const CanMsg HONDA_N_INTERCEPTOR_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0x194, 0, 4, .check_relay = true},
    {0x1FA, 0, 8, .check_relay = false},
    {0x30C, 0, 8, .check_relay = true},
    {0x33D, 0, 5, .check_relay = true},
    {0x200, 0, 6, .check_relay = false},
  };
  static const RxCheck interceptor_source = {
    .msg = {{0x201, 0, 6, 50U, .ignore_checksum = true,
             .ignore_counter = true, .ignore_quality_flag = true}, {0}, {0}},
  };
  honda_interceptor_reset((param == 32U) || (param == 36U) ||
    ((alternative_experience == 32) && ((param == 544U) || (param == 548U) || (param == 804U))));
  const uint16_t HONDA_PARAM_NIDEC_ALT = 4;

  honda_hw = HONDA_NIDEC;
  honda_brake = 0;
  honda_brake_switch_prev = false;
  honda_fwd_brake = false;
  honda_alt_brake_msg = false;
  honda_bosch_long = false;
  honda_bosch_radarless = false;
  honda_bosch_canfd = false;
  honda_rdx_high_gas = false;

  safety_config ret = {0};

  bool enable_nidec_alt = GET_FLAG(param, HONDA_PARAM_NIDEC_ALT);

  if (enable_nidec_alt) {
    // For Nidecs with main on signal on an alternate msg (missing 0x326)
    static const RxCheck honda_nidec_alt_rx_checks[] = {
      HONDA_COMMON_NO_SCM_FEEDBACK_RX_CHECKS(0)
      {.msg = {{0x1FA, 2, 8, 50U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  // BRAKE_COMMAND
    };

    _Static_assert((sizeof(honda_nidec_alt_rx_checks) / sizeof(honda_nidec_alt_rx_checks[0])) <= 5U, "Honda baseline RX capacity");
    ret = honda_copy_rx(honda_nidec_alt_rx_checks, sizeof(honda_nidec_alt_rx_checks) / sizeof(honda_nidec_alt_rx_checks[0]), ret);
  } else {
    // Nidec includes BRAKE_COMMAND
    static const RxCheck honda_nidec_common_rx_checks[] = {
      HONDA_COMMON_RX_CHECKS(0)
      {.msg = {{0x1FA, 2, 8, 50U, .max_counter = 3U, .ignore_quality_flag = true}, { 0 }, { 0 }}},  // BRAKE_COMMAND
    };

    _Static_assert((sizeof(honda_nidec_common_rx_checks) / sizeof(honda_nidec_common_rx_checks[0])) <= 5U, "Honda baseline RX capacity");
    ret = honda_copy_rx(honda_nidec_common_rx_checks, sizeof(honda_nidec_common_rx_checks) / sizeof(honda_nidec_common_rx_checks[0]), ret);
  }

  if (honda_angle_mode && (ret.rx_checks_len < 7)) {
    // the measured angle the angle rule bounds the target against (never steers without it): STEERING_SENSORS for the
    // Clarity rule, EPS_LINEAR_ANGLE for a profile
    static const RxCheck angle_source[] = {
      {.msg = {{0x14A, 0, 8, 100U, .max_counter = 3U, .ignore_quality_flag = true}, {0}, {0}}},
      {.msg = {{0x6A2, 0, 8, 100U, .max_counter = 3U, .ignore_quality_flag = true}, {0}, {0}}},
    };
    honda_rx_workspace[ret.rx_checks_len] = angle_source[(honda_angle_profile != 0U) ? 1U : 0U];
    ret.rx_checks_len++;
  }

  if (honda_interceptor && (ret.rx_checks_len < 7)) {
    honda_rx_workspace[ret.rx_checks_len] = interceptor_source;
    ret.rx_checks_len++;
    SET_TX_MSGS(HONDA_N_INTERCEPTOR_TX_MSGS, ret);
  } else {
    SET_TX_MSGS(HONDA_N_TX_MSGS, ret);
  }
  ret = honda_stock_aol_configure(param, true, enable_nidec_alt, 0U, honda_angle_mode, ret);

  return ret;
}

static safety_config honda_bosch_init(uint16_t param_raw) {
  // the angle bits are independent of every other Bosch option, so the exact-value checks below see the param without them.
  // Bosch has no Clarity rule: angle mode on Bosch is always a profile (profile 0 there has no row and never steers)
  honda_angle_reset(GET_FLAG(param_raw, HONDA_PARAM_ANGLE));
  honda_angle_profile = honda_angle_mode ? ((param_raw & HONDA_PARAM_ANGLE_PROFILE_MASK) >> HONDA_PARAM_ANGLE_PROFILE_SHIFT) : 0U;
  if (honda_angle_mode && (honda_angle_profile == 0U)) {
    honda_angle_profile = HONDA_ANGLE_PROFILE_NONE;
  }
  const uint16_t param = param_raw & (uint16_t)~(HONDA_PARAM_ANGLE | HONDA_PARAM_ANGLE_PROFILE_MASK);
  honda_mvl_stock = ((param == 80U) || (param == 81U)) && ((alternative_experience == 0) || (alternative_experience == 32));
  honda_mvl_buttons_fresh = 0U;
  honda_interceptor_reset(false);
  // Bosch
  static const CanMsg HONDA_BOSCH_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0xE5, 0, 8, .check_relay = true},
    {0x296, 1, 4, .check_relay = false},
    {0x33D, 0, 5, .check_relay = true},
    {0x33D, 0, 8, .check_relay = true},
    {0x33DA, 0, 5, .check_relay = true},
    {0x33DB, 0, 8, .check_relay = true},
    {0x16F118F0, 0, 8, .check_relay = false},
  };

  // Bosch w/ gas and brakes
  static const CanMsg HONDA_BOSCH_LONG_TX_MSGS[] = {
    {0xE4, 1, 5, .check_relay = true},
    {0x1DF, 1, 8, .check_relay = true},
    {0x1EF, 1, 8, .check_relay = false},
    {0x1FA, 1, 8, .check_relay = false},
    {0x30C, 1, 8, .check_relay = false},
    {0x33D, 1, 5, .check_relay = true},
    {0x33D, 1, 8, .check_relay = true},
    {0x33DA, 1, 5, .check_relay = true},
    {0x33DB, 1, 8, .check_relay = true},
    {0x39F, 1, 8, .check_relay = false},
    {0x18DAB0F1, 1, 8, .check_relay = false},
    {0x16F118F0, 0, 8, .check_relay = false},
  };

  static const CanMsg HONDA_MVL_STOCK_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0x296, 0, 4, .check_relay = false},
    {0x296, 2, 4, .check_relay = false},
    {0x33D, 0, 8, .check_relay = true},
  };

  // Bosch radarless
  static const CanMsg HONDA_RADARLESS_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0x296, 2, 4, .check_relay = false},
    {0x33D, 0, 8, .check_relay = true},
  };

  // Bosch radarless w/ gas and brakes
  static const CanMsg HONDA_RADARLESS_LONG_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0x33D, 0, 8, .check_relay = true},
    {0x1C8, 0, 8, .check_relay = true},
    {0x30C, 0, 8, .check_relay = true},
  };

  static const CanMsg HONDA_CANFD_TX_MSGS[] = {
    {0xE4, 0, 5, .check_relay = true},
    {0x296, 0, 4, .check_relay = false},
    {0x33D, 0, 8, .check_relay = true},
  };

  const uint16_t HONDA_PARAM_ALT_BRAKE = 1;
  const uint16_t HONDA_PARAM_RADARLESS = 8;
  const uint16_t HONDA_PARAM_BOSCH_CANFD = 16;

  // Bosch radarless has the powertrain bus on bus 0
  static const RxCheck honda_bosch_pt0_rx_checks[] = {
    HONDA_COMMON_RX_CHECKS(0)
  };

  static const RxCheck honda_bosch_pt0_alt_brake_rx_checks[] = {
    HONDA_COMMON_RX_CHECKS(0)
    HONDA_ALT_BRAKE_ADDR_CHECK(0)
  };

  // Bosch has powertrain on bus 1, verified 0x1A6 does not exist
  static const RxCheck honda_bosch_pt1_rx_checks[] = {
    HONDA_COMMON_RX_CHECKS(1)
  };

  static const RxCheck honda_bosch_pt1_alt_brake_rx_checks[] = {
    HONDA_COMMON_RX_CHECKS(1)
    HONDA_ALT_BRAKE_ADDR_CHECK(1)
  };

  honda_hw = HONDA_BOSCH;
  honda_brake_switch_prev = false;
  honda_bosch_radarless = GET_FLAG(param, HONDA_PARAM_RADARLESS);
  honda_bosch_canfd = GET_FLAG(param, HONDA_PARAM_BOSCH_CANFD);
  // Checking for alternate brake override from safety parameter
  honda_alt_brake_msg = GET_FLAG(param, HONDA_PARAM_ALT_BRAKE);
  honda_rdx_high_gas = false;

  // radar disabled so allow gas/brakes
#ifdef ALLOW_DEBUG
  const uint16_t HONDA_PARAM_BOSCH_LONG = 2;
  honda_bosch_long = GET_FLAG(param, HONDA_PARAM_BOSCH_LONG);
  honda_rdx_high_gas = (param == 131U) || (param == 163U) || (param == 2211U);
  aol_honda_bosch_long = honda_bosch_long && ((param == 34U) || (param == 35U) || (param == 163U));
#endif
  if (aol_honda_bosch_long) {
    static const AolSafetyPolicy aol_honda_policy = {
      .reset = aol_honda_reset,
      .host_request = NULL,
      .request_mask = aol_honda_request_mask,
      .permission_mask = aol_honda_permission_mask,
      .rx_invalid = NULL,
    };
    aol_policy = &aol_honda_policy;
  }

  safety_config ret = {0};
  if (honda_bosch_radarless || honda_bosch_canfd) {
    if (honda_alt_brake_msg) {
      _Static_assert((sizeof(honda_bosch_pt0_alt_brake_rx_checks) / sizeof(honda_bosch_pt0_alt_brake_rx_checks[0])) <= 5U, "Honda baseline RX capacity");
    ret = honda_copy_rx(honda_bosch_pt0_alt_brake_rx_checks, sizeof(honda_bosch_pt0_alt_brake_rx_checks) / sizeof(honda_bosch_pt0_alt_brake_rx_checks[0]), ret);
    } else {
      _Static_assert((sizeof(honda_bosch_pt0_rx_checks) / sizeof(honda_bosch_pt0_rx_checks[0])) <= 5U, "Honda baseline RX capacity");
    ret = honda_copy_rx(honda_bosch_pt0_rx_checks, sizeof(honda_bosch_pt0_rx_checks) / sizeof(honda_bosch_pt0_rx_checks[0]), ret);
    }
  } else {
   if (honda_alt_brake_msg) {
     _Static_assert((sizeof(honda_bosch_pt1_alt_brake_rx_checks) / sizeof(honda_bosch_pt1_alt_brake_rx_checks[0])) <= 5U, "Honda baseline RX capacity");
    ret = honda_copy_rx(honda_bosch_pt1_alt_brake_rx_checks, sizeof(honda_bosch_pt1_alt_brake_rx_checks) / sizeof(honda_bosch_pt1_alt_brake_rx_checks[0]), ret);
   } else {
     _Static_assert((sizeof(honda_bosch_pt1_rx_checks) / sizeof(honda_bosch_pt1_rx_checks[0])) <= 5U, "Honda baseline RX capacity");
    ret = honda_copy_rx(honda_bosch_pt1_rx_checks, sizeof(honda_bosch_pt1_rx_checks) / sizeof(honda_bosch_pt1_rx_checks[0]), ret);
   }
  }

  if (honda_angle_mode && (ret.rx_checks_len < 7)) {
    // EPS_LINEAR_ANGLE: the measured angle the angle rule bounds the target against (never steers without it)
    static const RxCheck angle_source[] = {
      {.msg = {{0x6A2, 0, 8, 100U, .max_counter = 3U, .ignore_quality_flag = true}, {0}, {0}}},
      {.msg = {{0x6A2, 1, 8, 100U, .max_counter = 3U, .ignore_quality_flag = true}, {0}, {0}}},
    };
    honda_rx_workspace[ret.rx_checks_len] = angle_source[honda_get_pt_bus()];
    ret.rx_checks_len++;
  }

  if (honda_bosch_radarless) {
    if (honda_bosch_long) {
      SET_TX_MSGS(HONDA_RADARLESS_LONG_TX_MSGS, ret);
    } else {
      SET_TX_MSGS(HONDA_RADARLESS_TX_MSGS, ret);
    }
  } else if (honda_bosch_canfd) {
    if (honda_mvl_stock) {
      SET_TX_MSGS(HONDA_MVL_STOCK_TX_MSGS, ret);
    } else if ((param & 64U) == 0U) {
      SET_TX_MSGS(HONDA_CANFD_TX_MSGS, ret);
    } else {
      ret.tx_msgs = NULL;
      ret.tx_msgs_len = 0;
    }
  } else {
    if (honda_bosch_long) {
      SET_TX_MSGS(HONDA_BOSCH_LONG_TX_MSGS, ret);
    } else {
      SET_TX_MSGS(HONDA_BOSCH_TX_MSGS, ret);
    }
  }
  if (((param & 64U) != 0U) && !honda_mvl_stock) {
    ret.tx_msgs = NULL;
    ret.tx_msgs_len = 0;
  }
  ret = honda_stock_aol_configure(param, false, false, honda_get_pt_bus(), honda_angle_mode, ret);
  return ret;
}

static bool honda_nidec_fwd_hook(int bus_num, int addr) {
  bool block_msg = false;

  if (bus_num == 2) {
    // forwarded if stock AEB is active
    bool is_brake_msg = addr == 0x1FA;
    block_msg = is_brake_msg && !honda_fwd_brake;
  }

  return block_msg;
}

const safety_hooks honda_nidec_hooks = {
  .init = honda_nidec_init,
  .rx = honda_rx_hook,
  .optional_rx = honda_angle_optional_rx,
  .tx = honda_tx_hook,
  .fwd = honda_nidec_fwd_hook,
  .get_counter = honda_get_counter,
  .get_checksum = honda_get_checksum,
  .compute_checksum = honda_compute_checksum,
};

static bool honda_mvl_stock_fwd_hook(int bus_num, int addr) {
  return honda_mvl_stock && controls_allowed && (honda_mvl_buttons_fresh > 0U) &&
         (bus_num == 0) && (addr == 0x296);
}

const safety_hooks honda_bosch_hooks = {
  .fwd = honda_mvl_stock_fwd_hook,
  .init = honda_bosch_init,
  .rx = honda_rx_hook,
  .tx = honda_tx_hook,
  .get_counter = honda_get_counter,
  .get_checksum = honda_get_checksum,
  .compute_checksum = honda_compute_checksum,
};
