#pragma once

#include "selfdrive/pandad/aol_protocol.h"

inline bool honda_aol_param(uint16_t param) {
  return (param == 34U) || (param == 35U) || (param == 163U);
}

inline constexpr AolSafetyProfile HONDA_AOL_PROFILE{20U, honda_aol_param, false};


inline bool honda_stock_aol_param(uint16_t param) {
  return (param == 0U) || (param == 1U) || (param == 8U) || (param == 9U) || (param == 10U) || (param == 11U) || (param == 16U) || (param == 17U) || (param == 80U) || (param == 81U) || (param == 512U) || (param == 513U) ||
         (param == 1058U) || (param == 1059U) || (param == 1570U) || (param == 1571U) || (param == 2082U) || (param == 2083U) || (param == 2211U);
}

// Clarity angle mode's panda bit (4096, opendbc honda.h HONDA_PARAM_ANGLE) only tightens 0xE4: 544 | 4096 is the same
// AOL configuration (11-21: the owner's pedal Clarity in angle mode reports 4640). Panda checks the bit against its mode.
inline bool honda_nidec_aol_param(uint16_t param_raw) {
  const uint16_t param = param_raw & static_cast<uint16_t>(~4096U);
  return (param == 0U) || (param == 4U) || (param == 260U) || (param == 544U) || (param == 548U) || (param == 804U);
}

inline constexpr AolSafetyProfile HONDA_STOCK_AOL_PROFILE{20U, honda_stock_aol_param, true};
inline constexpr AolSafetyProfile HONDA_NIDEC_AOL_PROFILE{1U, honda_nidec_aol_param, true};
