#pragma once
#include <string>
class State {
public:
    std::wstring NVNGX_ApplicationDataPath;
    static State& Instance() { static State state; return state; }
};
