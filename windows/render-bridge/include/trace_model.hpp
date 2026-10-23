#pragma once
#include <algorithm>
#include <cstdint>
#include <compare>
#include <map>
#include <string>
#include <vector>

namespace forge::trace {
using Handle = std::uint64_t;
struct Resource {
    std::uint64_t id = 0;
    Handle handle = 0;
    std::uint64_t width = 0;
    std::uint32_t height = 0, format = 0, usage = 0;
    bool alive = true;
};
struct Descriptor {
    std::uint64_t resource_id = 0, offset = 0, size = 0;
    std::uint32_t type = 0;
};
struct Slot {
    Handle heap = 0;
    std::uint32_t offset = 0;
    auto operator<=>(const Slot &) const = default;
};

// IDs bind observations to one resource lifetime, even when native handles are reused.
// Missing descriptors overwrite old entries; overlapping copies use a source snapshot.
class Ledger {
public:
    static constexpr std::size_t resource_limit = 65536;
    static constexpr std::size_t view_limit = 65536;
    static constexpr std::size_t descriptor_limit = 262144;
    std::map<Handle, std::uint64_t> live;
    std::map<std::uint64_t, Resource> resources;
    std::map<Handle, std::uint64_t> views;
    std::map<Slot, Descriptor> descriptors;
    std::uint64_t dropped = 0;
    std::uint64_t resource_drops = 0, view_drops = 0, descriptor_drops = 0, copy_drops = 0, slot_drops = 0;

    std::uint64_t create(Handle handle, std::uint64_t width, std::uint32_t height,
                         std::uint32_t format, std::uint32_t usage) {
        destroy(handle);
        if (resources.size() >= resource_limit) { ++dropped; ++resource_drops; return 0; }
        const auto id = ++next_id;
        resources.emplace(id, Resource{id, handle, width, height, format, usage, true});
        live[handle] = id;
        return id;
    }
    void destroy(Handle handle) {
        const auto it = live.find(handle);
        if (it == live.end()) return;
        resources.at(it->second).alive = false;
        live.erase(it);
    }
    std::uint64_t resolve(Handle handle) const {
        const auto it = live.find(handle);
        return it == live.end() ? 0 : it->second;
    }
    void view(Handle handle, Handle resource) {
        const auto id = resolve(resource);
        // D3D12 permits null views. Huge preinitialized banks must not consume the
        // live catalog; overwriting a real view with null still invalidates it.
        if (!id) { views.erase(handle); return; }
        if (views.size() >= view_limit && !views.contains(handle)) { ++dropped; ++view_drops; return; }
        views[handle] = id;
    }
    std::uint64_t resolve_view(Handle handle) const {
        const auto it = views.find(handle);
        return it == views.end() ? 0 : it->second;
    }
    bool alive(std::uint64_t id) const {
        const auto it = resources.find(id);
        return it != resources.end() && it->second.alive;
    }
    void put(Slot slot, Descriptor descriptor) {
        if (!slot.heap) { ++dropped; ++slot_drops; return; }
        // Empty/unknown input clears the destination, including copied nulls.
        // Keeping an entry per null descriptor exhausted budgets before scene creation.
        if (!descriptor.resource_id) { descriptors.erase(slot); return; }
        if (descriptors.size() >= descriptor_limit && !descriptors.contains(slot)) { ++dropped; ++descriptor_drops; return; }
        descriptors[slot] = descriptor;
    }
    Descriptor get(Slot slot) const {
        const auto it = descriptors.find(slot);
        return it == descriptors.end() ? Descriptor{} : it->second;
    }
    void copy(Slot source, Slot destination, std::uint32_t count) {
        if (count > 4096 || source.offset > UINT32_MAX - count || destination.offset > UINT32_MAX - count) {
            ++dropped; ++copy_drops; return;
        }
        std::vector<Descriptor> snapshot;
        snapshot.reserve(count);
        for (std::uint32_t i = 0; i < count; ++i) snapshot.push_back(get({source.heap, source.offset + i}));
        for (std::uint32_t i = 0; i < count; ++i) put({destination.heap, destination.offset + i}, snapshot[i]);
    }
private:
    std::uint64_t next_id = 0;
};

inline std::string quote(const std::string &value) {
    constexpr char hex[] = "0123456789abcdef";
    std::string out = "\"";
    for (const unsigned char c : value) {
        if (c == '\"' || c == '\\') { out += '\\'; out += static_cast<char>(c); }
        else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += static_cast<char>(c);
    }
    return out + '\"';
}
}
