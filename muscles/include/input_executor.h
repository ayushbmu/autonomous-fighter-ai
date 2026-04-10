#pragma once

#include <cstdint>

#ifdef _WIN32
#define AF_EXPORT __declspec(dllexport)
#else
#define AF_EXPORT
#endif

extern "C" {
AF_EXPORT void af_press_key(uint16_t virtual_key);
AF_EXPORT void af_release_key(uint16_t virtual_key);
AF_EXPORT void af_tap_key(uint16_t virtual_key, uint32_t min_delay_ms, uint32_t max_delay_ms);
AF_EXPORT void af_move_mouse_relative(int32_t dx, int32_t dy);
AF_EXPORT void af_click_left(uint32_t min_delay_ms, uint32_t max_delay_ms);
AF_EXPORT void af_sleep_ms(uint32_t ms);
}
