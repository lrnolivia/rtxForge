#pragma once
#include <algorithm>
#include <cmath>
#include <deque>
#include <map>
#include <string>

// Session-only editing state. No renderer, configuration file or game dependency.
namespace ForgeWorkbench
{
using Values = std::map<std::string, float>;
inline bool Equal(const Values& a, const Values& b)
{
    if(a.size() != b.size()) return false;
    for(const auto& [key, value] : a) {
        const auto other = b.find(key);
        if(other == b.end() || !std::isfinite(value) || !std::isfinite(other->second)
            || std::fabs(value - other->second) > .0001f) return false;
    }
    return true;
}
struct Edits
{
    static constexpr size_t Limit = 32;
    std::deque<Values> past, future;
    Values saved, a, b;
    bool initialized = false, comparing = false;
    int side = 0;
    void Start(const Values& values) { if(!initialized) { saved = values; initialized = true; } }
    void Record(const Values& before, const Values& after)
    {
        if(Equal(before, after)) return;
        if(past.empty() || !Equal(past.back(), before)) {
            if(past.size() == Limit) past.pop_front();
            past.push_back(before);
        }
        future.clear();
    }
    Values Undo(const Values& current)
    {
        if(past.empty()) return current;
        future.push_back(current); auto value = past.back(); past.pop_back(); return value;
    }
    Values Redo(const Values& current)
    {
        if(future.empty()) return current;
        past.push_back(current); auto value = future.back(); future.pop_back(); return value;
    }
    void BeginComparison(const Values& current) { a = b = current; side = 0; comparing = true; }
    Values Compare(int next, const Values& current)
    {
        if(!comparing) BeginComparison(current);
        (side == 0 ? a : b) = current;
        side = next == 1 ? 1 : 0;
        return side == 0 ? a : b;
    }
    void EndComparison(const Values& current) { a = b = current; comparing = false; side = 0; }
};
struct Sample { double time, nr, rendered, displayed; };
struct History
{
    std::deque<Sample> samples;
    static double Measured(double value) { return std::isfinite(value) && value > 0 ? value : -1; }
    void Add(double now, double nr, double rendered, double displayed)
    {
        if(!std::isfinite(now)) return;
        if(!samples.empty() && now < samples.back().time) samples.clear();
        if(!samples.empty() && now - samples.back().time < .5) return;
        samples.push_back({now, Measured(nr), Measured(rendered), Measured(displayed)});
        while(!samples.empty() && (now - samples.front().time > 30 || samples.size() > 61)) samples.pop_front();
    }
};
}
