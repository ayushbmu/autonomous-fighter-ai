#include "input_executor.h"

#include <algorithm>
#include <chrono>
#include <map>
#include <random>
#include <thread>

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

namespace {
// Track pressed keys globally to enable cleanup
std::map<uint16_t, bool> pressed_keys;

std::mt19937& rng() {
    static thread_local std::mt19937 generator(
        static_cast<uint32_t>(std::chrono::high_resolution_clock::now().time_since_epoch().count()));
    return generator;
}

uint32_t jittered_delay(uint32_t min_delay_ms, uint32_t max_delay_ms) {
    if (max_delay_ms < min_delay_ms) {
        std::swap(max_delay_ms, min_delay_ms);
    }
    std::uniform_int_distribution<uint32_t> distribution(min_delay_ms, max_delay_ms);
    return distribution(rng());
}

void send_keyboard_input(uint16_t virtual_key, DWORD flags) {
    INPUT input{};
    input.type = INPUT_KEYBOARD;
    input.ki.wVk = virtual_key;
    input.ki.dwFlags = flags;
    SendInput(1, &input, sizeof(INPUT));
}

void send_mouse_input(LONG dx, LONG dy, DWORD mouse_flags) {
    INPUT input{};
    input.type = INPUT_MOUSE;
    input.mi.dx = dx;
    input.mi.dy = dy;
    input.mi.dwFlags = mouse_flags;
    SendInput(1, &input, sizeof(INPUT));
}
}

extern "C" {
void af_press_key(uint16_t virtual_key) {
    send_keyboard_input(virtual_key, 0);
    pressed_keys[virtual_key] = true;
}

void af_release_key(uint16_t virtual_key) {
    send_keyboard_input(virtual_key, KEYEVENTF_KEYUP);
    pressed_keys[virtual_key] = false;
}

void af_reset_all_keys() {
    // Force release all tracked keys
    for (auto& [key, is_pressed] : pressed_keys) {
        if (is_pressed) {
            send_keyboard_input(key, KEYEVENTF_KEYUP);
        }
    }
    pressed_keys.clear();
}

void af_tap_key(uint16_t virtual_key, uint32_t min_delay_ms, uint32_t max_delay_ms) {
    af_press_key(virtual_key);
    std::this_thread::sleep_for(std::chrono::milliseconds(jittered_delay(min_delay_ms, max_delay_ms)));
    af_release_key(virtual_key);
}

void af_move_mouse_relative(int32_t dx, int32_t dy) {
    send_mouse_input(dx, dy, MOUSEEVENTF_MOVE);
}

void af_click_left(uint32_t min_delay_ms, uint32_t max_delay_ms) {
    send_mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN);
    std::this_thread::sleep_for(std::chrono::milliseconds(jittered_delay(min_delay_ms, max_delay_ms)));
    send_mouse_input(0, 0, MOUSEEVENTF_LEFTUP);
}

void af_sleep_ms(uint32_t ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}
}
